"""
Complaints Workforce Demand Model — Proof Harness
==================================================

PURPOSE
-------
Answers: "How many FTE do we need to handle X complaints/day without breaching
regulatory deadlines, given realistic operational behaviour?"

This is NOT a simple intake/effort/FTE calculator. It simulates 730 days of
complaint flow through a two-pool system (unallocated queue -> handler diaries)
and finds the steady-state equilibrium including:
  - Parkinson's Law (people slow down when the queue is thin)
  - Dynamic first-contact resolution (younger cases resolve more on first touch)
  - Burden scaling (older cases cost more effort per case)
  - Diary capacity constraints (handlers have a max caseload)
  - Regulatory deadline tracking (FCA 56 cal days, PSD2 15/35 biz days)

KEY FINDING (with current defaults)
------------------------------------
120 FTE handles 300 complaints/day at steady state:
  - Diaries full (714 cases), ~300 unallocated buffer
  - Effective utilisation 86-88% (Parkinson absorbs overcapacity)
  - FCA avg age at close ~7.6 days, system time ~6.4 days
  - Allocation delay ~1 day (cases allocated day 0 or 1)
  - 0% FCA breaches, ~2% PSD2 breaches

MODEL FLOW (per simulated day)
------------------------------
1. Age all cases (+1 calendar day; +1 business day if workday)
2. Inject daily intake into unallocated pool (with configurable age profile)
3. Apply PSD2 15->35 day extensions where applicable
4. For each work slice (4 per day):
   a. Allocate: move cases from unallocated -> diary (priority: nearest to target)
   b. Work: close cases from diary (SRCs first, then by priority)
   c. Refill: freed diary slots get refilled immediately (rolling refill)
5. Record metrics for the day

PARKINSON'S LAW MECHANISM
--------------------------
Real teams don't work at 100% pace when the queue is empty. They pace to
deadlines, wait for customer responses, do more thorough work, etc.

The model scales effective utilisation with the visible unallocated queue:
  pressure = min(unallocated / PARKINSON_FULL_PACE_QUEUE, 1.0)
  effective_util = PARKINSON_FLOOR + (max_util - PARKINSON_FLOOR) * pressure

This creates a natural equilibrium: if throughput > intake, the queue shrinks,
pace drops, throughput falls back to intake. The queue stabilises at a level
where throughput = intake.

PARKINSON_FULL_PACE_QUEUE (FPQ) is the key tuning lever:
  - Higher FPQ = people tolerate bigger queues before working at full pace
    -> equilibrium has more unallocated cases, higher util, longer close times
  - Lower FPQ = people respond to small queues quickly
    -> equilibrium has fewer unallocated cases, lower util, shorter close times

DYNAMIC SRC (SUMMARY RESOLUTION COMMUNICATION)
------------------------------------------------
Cases aged 0-3 regulatory days can be resolved via Summary Resolution
Communication — a quicker, lighter-touch outcome. The model boosts SRC rates
when allocation delay is low (younger cases are easier to resolve quickly):
  src_boost = SRC_BOOST_MAX * 0.5^(alloc_delay / SRC_BOOST_DECAY_DAYS)
A well-staffed team with short queues gets MORE SRCs, creating a virtuous cycle.

SRC cases receive a 0.7x effort multiplier (they're simpler to close). However,
SRC is only possible within the SRC_WINDOW (0-3 reg days). If a case tagged
SRC ages beyond day 3 without closing, it loses the discount and reverts to
full effort. The AM/PM allocation split (70/30) also affects same-day closure
rates — afternoon allocations rarely close same-day.

CONFIGURABLE PARAMETERS (tune these with real data)
----------------------------------------------------
Operational:
  DAILY_INTAKE        - complaints arriving per workday
  SHRINKAGE           - total shrinkage (42% = holidays, training, meetings, etc.)
  ABSENCE_SHRINKAGE   - absence component within shrinkage (drives diary slots)
  HOURS_PER_DAY       - contracted hours per day
  DIARY_LIMIT         - max cases per handler diary
  BASE_EFFORT         - productive hours per case at band 1 (no burden scaling)
  PROFICIENCY         - staff proficiency multiplier (1.0 = fully trained)

Parkinson's Law:
  PARKINSON_FLOOR           - minimum utilisation when queue is empty (default 70%)
  PARKINSON_FULL_PACE_QUEUE - queue depth for 100% pace (default 600, tune to match reality)

Case dynamics:
  SRC_RATES           - base first-touch closure rates by case type
  SRC_BOOST_MAX       - additional SRC rate when allocation delay ~ 0
  SRC_BOOST_DECAY_DAYS - how quickly SRC boost decays with allocation delay
  BURDEN              - effort multiplier by case age band (older = more expensive)
  INTAKE_AGE_PROFILE  - proportion of intake arriving pre-aged
  MIN_DIARY_DAYS      - minimum business days before closure (0 = same-day OK)

Regulatory:
  SERVICE_TARGETS       - internal target days by case type
  REGULATORY_DEADLINES  - hard regulatory deadlines
  BREACH_TARGETS        - acceptable breach rate thresholds

OUTPUT
------
1. FTE Sweep: table showing equilibrium WIP, unallocated, util, close times
   for a range of FTE levels
2. Detailed Pack: full metrics for DEFAULT_FTE including trajectory, age
   profile, closure metrics, 30-day settlement blocks
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean


DEFAULT_FTE = 120
FTE_SWEEP = range(119, 130)

SHRINKAGE = 0.42          # total shrinkage: drives productive hours
ABSENCE_SHRINKAGE = 0.15  # absence component (within 42%): drives diary slots
HOURS_PER_DAY = 7.0
UTILISATION = 1.00        # max utilisation ceiling (Parkinson's Law reduces this dynamically)
PROFICIENCY = 1.0
DIARY_LIMIT = 7
DAILY_INTAKE = 300
BASE_EFFORT = 1.5         # productive hours of work per case (band 1, no burden scaling)
MIN_DIARY_DAYS = 0        # 0 = same-day close allowed (SRCs); avg days to close driven by effort + Parkinson's Law
HANDOFF_OVERHEAD = 0.15   # fraction of cases requiring handoff; each handoff adds HANDOFF_EFFORT_HOURS extra
HANDOFF_EFFORT_HOURS = 0.5 # additional hours of effort added per handoff (setup/re-familiarisation)
LATE_DEMAND_RATE = 0.08   # fraction of productive hours consumed by late demand / rework outside the queue
DAYS = 730
SLICES_PER_DAY = 4

# Parkinson's Law / endogenous utilisation
# Driven by the visible unallocated queue — when queue is healthy, people work at
# full pace. When queue thins out, pace drops (due-date pacing, longer waits, etc.)
# FULL_PACE_QUEUE: unallocated count where people hit 100% util (pressure=1.0).
#   Higher = people tolerate bigger queues before working at full pace.
#   Lower = people respond to small queue changes quickly.
#   Equilibrium unalloc is where pressure produces util matching throughput to intake.
#   Tune this with real operational data.
UNALLOCATED_BUFFER = 300          # target steady-state unallocated pool (for reporting)
PARKINSON_FLOOR = 0.70            # minimum effective utilisation when queue is empty
PARKINSON_FULL_PACE_QUEUE = 600   # queue depth at which handlers hit max pace

# Dynamic SRC: when cases are young at allocation, more resolve on first contact
# SRC_RATES are the BASE rates; boosted when avg allocation delay is low
SRC_BOOST_MAX = 0.15      # max additional SRC rate when allocation delay ~ 0
SRC_BOOST_DECAY_DAYS = 5  # allocation delay (days) at which boost halves

SERVICE_TARGETS = {
    "FCA": 21,
    "PSD2_15": 10,
    "PSD2_35": 25,
}

REGULATORY_DEADLINES = {
    "FCA": 56,
    "PSD2_15": 15,
    "PSD2_35": 35,
}

BREACH_TARGETS = {
    "FCA": 0.03,
    "PSD2": 0.10,
}

INTAKE_PROPORTIONS = {
    "FCA": 0.70,
    "PSD2_15": 0.30,
}

SRC_RATES = {
    "FCA": 0.40,
    "PSD2_15": 0.40,
    "PSD2_35": 0.10,
}

SRC_WINDOW = 3            # max regulatory age (days) for SRC closure eligibility

# AM/PM allocation split — drives blended SRC closure distribution
# 70% of diary capacity frees up in the morning, 30% in the afternoon
AM_ALLOCATION_SHARE = 0.70
PM_ALLOCATION_SHARE = 0.30
AM_SRC_DIST = (0.30, 0.50, 0.20)   # 30% same-day, 50% next workday, 20% day after
PM_SRC_DIST = (0.05, 0.475, 0.475) # 5% same-day (little time left), rest split evenly
# Blended: AM*0.70 + PM*0.30
SRC_DIST = (0.22, 0.50, 0.28)

SRC_EFFORT_RATIO = 0.7   # SRC cases are simpler — 0.7x effort multiplier within 0-3 day window
PSD2_EXTENSION_RATE = 0.05

# Intake age profile: proportion of daily intake arriving pre-aged
# Sum must equal 1.0. Day 40 cases arrive pre-breached for PSD2 (15-day deadline).
INTAKE_AGE_PROFILE = {
    0:  0.85,   # arrive fresh
    1:  0.02,   # 1 day old
    2:  0.02,   # 2 days old
    3:  0.02,   # 3 days old
    4:  0.02,   # 4 days old
    5:  0.02,   # 5 days old (subtotal days 1-5: 10%)
    # days 6-20: 4% spread evenly
    **{age: 0.04 / 15 for age in range(6, 21)},
    40: 0.01,   # arrive pre-aged/pre-breached from upstream process
}

BURDEN = {
    (0, 3): 0.7,
    (4, 15): 1.0,
    (16, 35): 1.5,
    (36, 56): 2.0,
    (57, 999): 2.5,
}

AGE_BANDS = [
    ("0-3", 0, 3),
    ("4-15", 4, 15),
    ("16-35", 16, 35),
    ("36-56", 36, 56),
    ("57+", 57, 9999),
]


@dataclass
class Cohort:
    count: float
    case_type: str
    cal_age: int
    biz_age: int
    effort_per_case: float
    is_src: bool
    arrival_day: int
    allocation_day: int | None
    seeded: bool = False


def is_workday(day: int) -> bool:
    return (day % 7) < 5


def burden_mult(reg_age: int) -> float:
    for (lo, hi), mult in BURDEN.items():
        if lo <= reg_age <= hi:
            return mult
    return 2.5


def case_effort(cohort: "Cohort") -> float:
    """Calculate effort per case from live age — not frozen at allocation time.

    Seeded cases retain their work-already-done discount.
    SRC cases get 0.7x effort only while within the SRC window (0-3 reg days).
    """
    if cohort.seeded:
        return cohort.effort_per_case
    reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
    effort = BASE_EFFORT * burden_mult(reg_age) + HANDOFF_OVERHEAD * HANDOFF_EFFORT_HOURS
    if cohort.is_src and reg_age <= SRC_WINDOW:
        effort *= SRC_EFFORT_RATIO
    return effort


def count_business_days_forward(sim_day: int, calendar_days: int) -> int:
    if calendar_days <= 0:
        return 0
    full_weeks, remainder = divmod(calendar_days, 7)
    biz_days = full_weeks * 5
    for i in range(remainder):
        if is_workday(sim_day + full_weeks * 7 + i):
            biz_days += 1
    return biz_days


def count_business_days_signed(sim_day: int, remaining_cal_days: int) -> int:
    if remaining_cal_days == 0:
        return 0
    if remaining_cal_days > 0:
        return count_business_days_forward(sim_day, remaining_cal_days)
    due_day = sim_day + remaining_cal_days
    return -count_business_days_forward(due_day, -remaining_cal_days)


def regulatory_age(case_type: str, cal_age: int, biz_age: int) -> int:
    if case_type == "FCA":
        return cal_age
    return biz_age


def remaining_workdays_to_target(
    case_type: str,
    cal_age: int,
    biz_age: int,
    sim_day: int,
) -> int:
    target = SERVICE_TARGETS[case_type]
    if case_type == "FCA":
        return count_business_days_signed(sim_day, target - cal_age)
    return target - biz_age


def remaining_workdays_to_deadline(
    case_type: str,
    cal_age: int,
    biz_age: int,
    sim_day: int,
) -> int:
    deadline = REGULATORY_DEADLINES[case_type]
    if case_type == "FCA":
        return count_business_days_signed(sim_day, deadline - cal_age)
    return deadline - biz_age


def make_age(reg_age: int, case_type: str) -> tuple[int, int]:
    if case_type == "FCA":
        return reg_age, count_business_days_forward(0, reg_age)
    return reg_age + (reg_age // 5) * 2, reg_age


def intake_distribution(total_cases: float) -> list[tuple[int, float]]:
    return [(age, total_cases * prop) for age, prop in INTAKE_AGE_PROFILE.items()]


def starting_wip_distribution(total_cases: float) -> list[tuple[int, float]]:
    result = []
    for age in range(0, 4):
        result.append((age, total_cases * 0.40 / 4.0))
    for age in range(4, 8):
        result.append((age, total_cases * 0.30 / 4.0))
    for age in range(8, 29):
        result.append((age, total_cases * 0.20 / 21.0))
    for age in range(29, 57):
        result.append((age, total_cases * 0.07 / 28.0))
    for age in range(57, 62):
        result.append((age, total_cases * 0.03 / 5.0))
    return result


def seed_pool(total_cases: float, allocated: bool) -> list[Cohort]:
    cohorts: list[Cohort] = []
    for case_type, proportion in INTAKE_PROPORTIONS.items():
        cases_for_type = total_cases * proportion
        for reg_age, count in starting_wip_distribution(cases_for_type):
            cal_age, biz_age = make_age(reg_age, case_type)
            effort = BASE_EFFORT * burden_mult(reg_age)
            if allocated:
                effort *= max(0.1, 1.0 - 0.9 * min(reg_age, 10) / 10.0)
            cohorts.append(
                Cohort(
                    count=count,
                    case_type=case_type,
                    cal_age=cal_age,
                    biz_age=biz_age,
                    effort_per_case=effort,
                    is_src=False,
                    arrival_day=-reg_age,
                    allocation_day=-max(1, reg_age // 2) if allocated else None,
                    seeded=True,
                )
            )
    return cohorts


def merge_cohorts(cohorts: list[Cohort]) -> list[Cohort]:
    merged: dict[tuple, Cohort] = {}
    for cohort in cohorts:
        if cohort.count <= 0.01:
            continue
        key = (
            cohort.case_type,
            cohort.cal_age,
            cohort.biz_age,
            round(cohort.effort_per_case, 4),
            cohort.is_src,
            cohort.arrival_day,
            cohort.allocation_day,
            cohort.seeded,
        )
        if key not in merged:
            merged[key] = Cohort(
                count=cohort.count,
                case_type=cohort.case_type,
                cal_age=cohort.cal_age,
                biz_age=cohort.biz_age,
                effort_per_case=cohort.effort_per_case,
                is_src=cohort.is_src,
                arrival_day=cohort.arrival_day,
                allocation_day=cohort.allocation_day,
                seeded=cohort.seeded,
            )
        else:
            merged[key].count += cohort.count
    return list(merged.values())


def priority_key(cohort: Cohort, sim_day: int) -> tuple[int, int, int]:
    target_remaining = remaining_workdays_to_target(
        cohort.case_type, cohort.cal_age, cohort.biz_age, sim_day
    )
    deadline_remaining = remaining_workdays_to_deadline(
        cohort.case_type, cohort.cal_age, cohort.biz_age, sim_day
    )
    reg = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
    return (target_remaining, deadline_remaining, -reg)


def count_by_type(cohorts: list[Cohort]) -> dict[str, float]:
    result = defaultdict(float)
    for cohort in cohorts:
        result[cohort.case_type] += cohort.count
    return dict(result)


def count_breaches(cohorts: list[Cohort]) -> dict[str, float]:
    result = defaultdict(float)
    for cohort in cohorts:
        reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
        if reg_age > REGULATORY_DEADLINES[cohort.case_type]:
            result[cohort.case_type] += cohort.count
    return dict(result)


def count_over_target(cohorts: list[Cohort]) -> dict[str, float]:
    result = defaultdict(float)
    for cohort in cohorts:
        reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
        if reg_age > SERVICE_TARGETS[cohort.case_type]:
            result[cohort.case_type] += cohort.count
    return dict(result)


def count_age_bands(
    cohorts: list[Cohort],
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    total = {label: 0.0 for label, _, _ in AGE_BANDS}
    by_type = {
        case_type: {label: 0.0 for label, _, _ in AGE_BANDS}
        for case_type in ["FCA", "PSD2_15", "PSD2_35"]
    }
    for cohort in cohorts:
        reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
        for label, lo, hi in AGE_BANDS:
            if lo <= reg_age <= hi:
                total[label] += cohort.count
                by_type[cohort.case_type][label] += cohort.count
                break
    return total, by_type


def calculate_instantaneous_fte_demand(
    unallocated: list[Cohort],
    allocated: list[Cohort],
    sim_day: int,
) -> float:
    productive_hours_per_fte = (
        (1 - SHRINKAGE) * HOURS_PER_DAY * UTILISATION * PROFICIENCY * (1 - LATE_DEMAND_RATE)
    )
    if productive_hours_per_fte <= 0:
        return 0.0

    total_demand_hours = 0.0
    for cohort in allocated:
        target_remaining = max(
            1,
            remaining_workdays_to_target(
                cohort.case_type, cohort.cal_age, cohort.biz_age, sim_day
            ),
        )
        total_demand_hours += cohort.count * case_effort(cohort) / target_remaining

    for cohort in unallocated:
        reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
        est_effort = cohort.count * BASE_EFFORT * burden_mult(reg_age)
        target_remaining = max(
            1,
            remaining_workdays_to_target(
                cohort.case_type, cohort.cal_age, cohort.biz_age, sim_day
            ),
        )
        total_demand_hours += est_effort / target_remaining

    return total_demand_hours / productive_hours_per_fte


def apply_psd2_extensions(pool: list[Cohort]) -> list[Cohort]:
    result: list[Cohort] = []
    for cohort in pool:
        if cohort.case_type == "PSD2_15" and cohort.biz_age == 15:
            extension_count = cohort.count * PSD2_EXTENSION_RATE
            stay_count = cohort.count - extension_count
            if stay_count > 0.01:
                result.append(
                    Cohort(
                        count=stay_count,
                        case_type="PSD2_15",
                        cal_age=cohort.cal_age,
                        biz_age=cohort.biz_age,
                        effort_per_case=cohort.effort_per_case,
                        is_src=cohort.is_src,
                        arrival_day=cohort.arrival_day,
                        allocation_day=cohort.allocation_day,
                        seeded=cohort.seeded,
                    )
                )
            if extension_count > 0.01:
                result.append(
                    Cohort(
                        count=extension_count,
                        case_type="PSD2_35",
                        cal_age=cohort.cal_age,
                        biz_age=cohort.biz_age,
                        effort_per_case=cohort.effort_per_case,
                        is_src=cohort.is_src,
                        arrival_day=cohort.arrival_day,
                        allocation_day=cohort.allocation_day,
                        seeded=cohort.seeded,
                    )
                )
        else:
            result.append(cohort)
    return result


def allocate_up_to_capacity(
    unallocated: list[Cohort],
    allocated: list[Cohort],
    max_slots: float,
    sim_day: int,
    src_allocated_today: dict[str, float],
) -> tuple[list[Cohort], list[Cohort], float, float, dict[str, float]]:
    current_alloc = sum(cohort.count for cohort in allocated)
    available_slots = max(0.0, max_slots - current_alloc)
    if available_slots <= 0.01:
        return unallocated, allocated, 0.0, 0.0, {}

    unallocated.sort(key=lambda cohort: priority_key(cohort, sim_day))
    kept_unallocated: list[Cohort] = []
    new_allocated: list[Cohort] = []
    allocations = 0.0
    weighted_delay = 0.0
    allocations_by_type = defaultdict(float)

    for cohort in unallocated:
        if available_slots <= 0.01:
            kept_unallocated.append(cohort)
            continue

        move = min(cohort.count, available_slots)
        stay = cohort.count - move
        available_slots -= move

        if stay > 0.01:
            kept_unallocated.append(
                Cohort(
                    count=stay,
                    case_type=cohort.case_type,
                    cal_age=cohort.cal_age,
                    biz_age=cohort.biz_age,
                    effort_per_case=cohort.effort_per_case,
                    is_src=cohort.is_src,
                    arrival_day=cohort.arrival_day,
                    allocation_day=cohort.allocation_day,
                    seeded=cohort.seeded,
                )
            )

        if move <= 0.01:
            continue

        reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
        # Dynamic SRC: younger cases at allocation -> higher summary resolution rate
        alloc_delay = sim_day - cohort.arrival_day
        src_boost = SRC_BOOST_MAX * (0.5 ** (alloc_delay / SRC_BOOST_DECAY_DAYS))
        effective_src_rate = min(0.95, SRC_RATES[cohort.case_type] + src_boost)
        # SRC window: only count distribution days that close within 0-3 reg days
        src_eligible = sum(w for i, w in enumerate(SRC_DIST) if reg_age + i <= SRC_WINDOW)
        effective_src_rate *= src_eligible
        src_count = move * effective_src_rate
        regular_count = move - src_count

        allocations += move
        weighted_delay += (sim_day - cohort.arrival_day) * move
        allocations_by_type[cohort.case_type] += move

        if src_count > 0.01:
            new_allocated.append(
                Cohort(
                    count=src_count,
                    case_type=cohort.case_type,
                    cal_age=cohort.cal_age,
                    biz_age=cohort.biz_age,
                    effort_per_case=0.0,  # calculated dynamically at closure via case_effort()
                    is_src=True,
                    arrival_day=cohort.arrival_day,
                    allocation_day=sim_day,
                    seeded=False,  # fresh allocation — seed discount doesn't apply
                )
            )
            src_allocated_today[cohort.case_type] += src_count

        if regular_count > 0.01:
            new_allocated.append(
                Cohort(
                    count=regular_count,
                    case_type=cohort.case_type,
                    cal_age=cohort.cal_age,
                    biz_age=cohort.biz_age,
                    effort_per_case=0.0,  # calculated dynamically at closure via case_effort()
                    is_src=False,
                    arrival_day=cohort.arrival_day,
                    allocation_day=sim_day,
                    seeded=False,  # fresh allocation — seed discount doesn't apply
                )
            )

    allocated.extend(new_allocated)
    return (
        kept_unallocated,
        allocated,
        allocations,
        weighted_delay,
        dict(allocations_by_type),
    )


def process_work_slice(
    allocated: list[Cohort],
    slice_budget: float,
    sim_day: int,
    workday_num: int,
    src_allocated_today: dict[str, float],
    src_schedule: dict[int, dict[str, float]],
    src_closed_today: dict[str, float],
) -> tuple[
    list[Cohort],
    float,
    dict[str, float],
    dict[str, dict[str, float]],
    dict[str, float],
]:
    closures_total = 0.0
    closures_by_type = defaultdict(float)
    close_sums = {
        case_type: {"n": 0.0, "reg": 0.0, "cal": 0.0, "sys": 0.0}
        for case_type in ["FCA", "PSD2_15", "PSD2_35"]
    }
    breached_closures_by_type = defaultdict(float)
    budget = slice_budget

    due_by_type = defaultdict(float)
    for lag, weight in enumerate(SRC_DIST):
        for case_type, count in src_schedule.get(workday_num - lag, {}).items():
            due_by_type[case_type] += weight * count
    for case_type, count in src_allocated_today.items():
        due_by_type[case_type] += SRC_DIST[0] * count

    def closeable(cohort: Cohort) -> bool:
        """Case can only close after MIN_DIARY_DAYS business days in diary.

        NOTE: at MIN_DIARY_DAYS > 0, this counts the allocation day itself
        as a business day, so the effective guard is off-by-one (e.g.,
        MIN_DIARY_DAYS=1 would allow closure on the same day if allocated
        on a workday). Masked at current default of 0.
        """
        if cohort.allocation_day is None:
            return False
        cal_days = sim_day - cohort.allocation_day
        if cal_days < 0:
            return False
        # O(1) business day count
        full_weeks, remainder = divmod(cal_days, 7)
        biz_days = full_weeks * 5
        for i in range(remainder):
            if is_workday(cohort.allocation_day + full_weeks * 7 + i):
                biz_days += 1
        return biz_days >= MIN_DIARY_DAYS

    src_candidates = [
        cohort for cohort in allocated if cohort.is_src and cohort.count > 0.01 and closeable(cohort)
    ]
    src_candidates.sort(key=lambda cohort: priority_key(cohort, sim_day))

    for cohort in src_candidates:
        if budget <= 0.01:
            break
        remaining_due = due_by_type[cohort.case_type] - src_closed_today[cohort.case_type]
        if remaining_due <= 0.01:
            continue
        close = min(cohort.count, remaining_due)
        eff = case_effort(cohort)
        cost = close * eff
        if cost > budget and eff > 0:
            close = budget / eff
            cost = budget
        cohort.count -= close
        src_closed_today[cohort.case_type] += close
        closures_total += close
        closures_by_type[cohort.case_type] += close
        budget -= cost
        if close > 0.01:
            reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
            close_sums[cohort.case_type]["n"] += close
            close_sums[cohort.case_type]["reg"] += reg_age * close
            close_sums[cohort.case_type]["cal"] += cohort.cal_age * close
            close_sums[cohort.case_type]["sys"] += (sim_day - cohort.arrival_day) * close
            if reg_age > REGULATORY_DEADLINES[cohort.case_type]:
                breached_closures_by_type[cohort.case_type] += close

    regular_candidates = [cohort for cohort in allocated if cohort.count > 0.01 and closeable(cohort)]
    regular_candidates.sort(key=lambda cohort: priority_key(cohort, sim_day))

    for cohort in regular_candidates:
        if budget <= 0.01:
            break
        eff = case_effort(cohort)
        if eff <= 0:
            continue
        hours_needed = cohort.count * eff
        hours_given = min(budget, hours_needed)
        closed = min(cohort.count, hours_given / eff)
        cohort.count -= closed
        closures_total += closed
        closures_by_type[cohort.case_type] += closed
        budget -= hours_given
        if closed > 0.01:
            reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
            close_sums[cohort.case_type]["n"] += closed
            close_sums[cohort.case_type]["reg"] += reg_age * closed
            close_sums[cohort.case_type]["cal"] += cohort.cal_age * closed
            close_sums[cohort.case_type]["sys"] += (sim_day - cohort.arrival_day) * closed
            if reg_age > REGULATORY_DEADLINES[cohort.case_type]:
                breached_closures_by_type[cohort.case_type] += closed

    return allocated, closures_total, dict(closures_by_type), close_sums, dict(breached_closures_by_type)


def simulate(fte: int, util_override: float | None = None) -> list[dict]:
    max_utilisation = util_override if util_override is not None else UTILISATION
    on_desk_productive = fte * (1 - SHRINKAGE)           # for throughput
    on_desk_present = fte * (1 - ABSENCE_SHRINKAGE)       # for diary slots
    max_slots = on_desk_present * DIARY_LIMIT
    desired_wip = max_slots + UNALLOCATED_BUFFER

    full_pace_queue = PARKINSON_FULL_PACE_QUEUE

    unallocated = seed_pool(2500 * 0.25, allocated=False)
    allocated = seed_pool(2500 * 0.75, allocated=True)
    src_schedule: dict[int, dict[str, float]] = {}
    results: list[dict] = []
    workday_num = 0

    for day in range(DAYS):
        workday = is_workday(day)

        # Parkinson's Law: pace driven by visible unallocated queue
        current_unalloc = sum(c.count for c in unallocated)
        pressure = min(current_unalloc / full_pace_queue, 1.0) if full_pace_queue > 0 else 1.0
        effective_util = PARKINSON_FLOOR + (max_utilisation - PARKINSON_FLOOR) * pressure
        productive_hours = on_desk_productive * HOURS_PER_DAY * effective_util * PROFICIENCY * (1 - LATE_DEMAND_RATE)
        slice_budget = productive_hours / SLICES_PER_DAY if SLICES_PER_DAY > 0 else 0.0

        for cohort in unallocated + allocated:
            cohort.cal_age += 1
            if workday:
                cohort.biz_age += 1

        if workday:
            for case_type, proportion in INTAKE_PROPORTIONS.items():
                for reg_age, count in intake_distribution(DAILY_INTAKE * proportion):
                    cal_age, biz_age = make_age(reg_age, case_type)
                    unallocated.append(
                        Cohort(
                            count=count,
                            case_type=case_type,
                            cal_age=cal_age,
                            biz_age=biz_age,
                            effort_per_case=0.0,
                            is_src=False,
                            arrival_day=day,
                            allocation_day=None,
                            seeded=False,
                        )
                    )

        if workday:
            unallocated = apply_psd2_extensions(unallocated)
            allocated = apply_psd2_extensions(allocated)

        allocations_total = 0.0
        weighted_delay_total = 0.0
        allocations_by_type = defaultdict(float)
        closures_total = 0.0
        closures_by_type = defaultdict(float)
        close_sums_total = {
            case_type: {"n": 0.0, "reg": 0.0, "cal": 0.0, "sys": 0.0}
            for case_type in ["FCA", "PSD2_15", "PSD2_35"]
        }
        breached_closures_total = defaultdict(float)
        occupancy_before_work = []
        src_allocated_today = defaultdict(float)
        src_closed_today = defaultdict(float)

        if workday:
            for _ in range(SLICES_PER_DAY):
                (
                    unallocated,
                    allocated,
                    slice_allocations,
                    slice_delay,
                    slice_alloc_by_type,
                ) = allocate_up_to_capacity(
                    unallocated,
                    allocated,
                    max_slots,
                    day,
                    src_allocated_today,
                )
                allocations_total += slice_allocations
                weighted_delay_total += slice_delay
                for case_type, count in slice_alloc_by_type.items():
                    allocations_by_type[case_type] += count

                occupancy_before_work.append(sum(cohort.count for cohort in allocated))

                (
                    allocated,
                    slice_closures,
                    slice_closures_by_type,
                    slice_close_sums,
                    slice_breached_closures,
                ) = process_work_slice(
                    allocated,
                    slice_budget,
                    day,
                    workday_num,
                    src_allocated_today,
                    src_schedule,
                    src_closed_today,
                )
                closures_total += slice_closures
                for case_type, count in slice_closures_by_type.items():
                    closures_by_type[case_type] += count
                for case_type in close_sums_total:
                    for key in close_sums_total[case_type]:
                        close_sums_total[case_type][key] += slice_close_sums[case_type][key]
                for case_type, count in slice_breached_closures.items():
                    breached_closures_total[case_type] += count

                allocated = [cohort for cohort in allocated if cohort.count > 0.01]

            # 5th pass: end-of-day refill — freed diary slots get backfilled
            (
                unallocated,
                allocated,
                slice_allocations,
                slice_delay,
                slice_alloc_by_type,
            ) = allocate_up_to_capacity(
                unallocated,
                allocated,
                max_slots,
                day,
                src_allocated_today,
            )
            allocations_total += slice_allocations
            weighted_delay_total += slice_delay
            for case_type, count in slice_alloc_by_type.items():
                allocations_by_type[case_type] += count

            # Save SRC schedule AFTER all allocations (including refill)
            src_schedule[workday_num] = dict(src_allocated_today)
            workday_num += 1

        allocated = [cohort for cohort in allocated if cohort.count > 0.01]
        unallocated = [cohort for cohort in unallocated if cohort.count > 0.01]

        if day % 14 == 0:
            allocated = merge_cohorts(allocated)
            unallocated = merge_cohorts(unallocated)

        all_open = unallocated + allocated
        open_by_type = count_by_type(all_open)
        breaches_by_type = count_breaches(all_open)
        over_target_by_type = count_over_target(all_open)
        age_bands, age_bands_by_type = count_age_bands(all_open)

        total_wip = sum(cohort.count for cohort in all_open)
        total_unallocated = sum(cohort.count for cohort in unallocated)
        total_allocated = sum(cohort.count for cohort in allocated)
        instantaneous_fte_demand = calculate_instantaneous_fte_demand(
            unallocated, allocated, day
        )
        avg_allocation_delay = (
            weighted_delay_total / allocations_total if allocations_total > 0 else 0.0
        )
        occupancy_start = (
            occupancy_before_work[0] if occupancy_before_work else total_allocated
        )
        occupancy_avg = (
            mean(occupancy_before_work) if occupancy_before_work else total_allocated
        )
        occupancy_end = total_allocated

        results.append(
            {
                "day": day,
                "workday": workday,
                "wip": total_wip,
                "unalloc": total_unallocated,
                "alloc": total_allocated,
                "open_by_type": open_by_type,
                "breaches_by_type": breaches_by_type,
                "over_target_by_type": over_target_by_type,
                "age_bands": age_bands,
                "age_bands_by_type": age_bands_by_type,
                "allocations": allocations_total,
                "allocations_by_type": dict(allocations_by_type),
                "avg_allocation_delay": avg_allocation_delay,
                "closures": closures_total,
                "closures_by_type": dict(closures_by_type),
                "breached_closures_by_type": dict(breached_closures_total),
                "close_sums": close_sums_total,
                "demand_fte": instantaneous_fte_demand,
                "effective_util": effective_util,
                "desired_wip": desired_wip,
                "occupancy_start": occupancy_start,
                "occupancy_avg": occupancy_avg,
                "occupancy_end": occupancy_end,
                "slot_capacity": max_slots,
            }
        )

    return results


def last_n_days(result: list[dict], n: int) -> list[dict]:
    return result[-n:]


def last_n_workdays(result: list[dict], n_workdays: int) -> list[dict]:
    workdays = [row for row in result if row["workday"]]
    return workdays[-n_workdays:]


def average_breach_rates(
    result: list[dict],
    last_days: int = 30,
) -> tuple[float, float, float]:
    recent = last_n_days(result, last_days)
    total_rate = mean(
        sum(row["breaches_by_type"].values()) / max(row["wip"], 1.0)
        for row in recent
    )
    fca_rate = mean(
        row["breaches_by_type"].get("FCA", 0.0)
        / max(row["open_by_type"].get("FCA", 0.0), 1.0)
        for row in recent
    )
    psd2_rate = mean(
        (
            row["breaches_by_type"].get("PSD2_15", 0.0)
            + row["breaches_by_type"].get("PSD2_35", 0.0)
        )
        / max(
            row["open_by_type"].get("PSD2_15", 0.0)
            + row["open_by_type"].get("PSD2_35", 0.0),
            1.0,
        )
        for row in recent
    )
    return total_rate, fca_rate, psd2_rate


def average_flow_breach_rates(
    result: list[dict],
    last_days: int = 30,
) -> tuple[float, float, float]:
    recent = [r for r in last_n_days(result, last_days) if r["workday"]]
    fca_closed = sum(r["closures_by_type"].get("FCA", 0.0) for r in recent)
    fca_breached = sum(r["breached_closures_by_type"].get("FCA", 0.0) for r in recent)
    psd2_closed = sum(
        r["closures_by_type"].get("PSD2_15", 0.0) + r["closures_by_type"].get("PSD2_35", 0.0)
        for r in recent
    )
    psd2_breached = sum(
        r["breached_closures_by_type"].get("PSD2_15", 0.0)
        + r["breached_closures_by_type"].get("PSD2_35", 0.0)
        for r in recent
    )
    total_closed = fca_closed + psd2_closed
    total_breached = fca_breached + psd2_breached
    return (
        total_breached / max(total_closed, 1.0),
        fca_breached / max(fca_closed, 1.0),
        psd2_breached / max(psd2_closed, 1.0),
    )


def is_stable(result: list[dict]) -> bool:
    if len(result) < 31:
        return False
    wip_change_30 = result[-1]["wip"] - result[-31]["wip"]
    wip_threshold = DAILY_INTAKE / 12  # ~25 at 300/day, scales with intake
    _total_rate, fca_rate, psd2_rate = average_breach_rates(result, last_days=30)
    _flow_total, flow_fca, flow_psd2 = average_flow_breach_rates(result, last_days=30)
    return (
        -wip_threshold <= wip_change_30 <= wip_threshold
        and fca_rate <= BREACH_TARGETS["FCA"]
        and psd2_rate <= BREACH_TARGETS["PSD2"]
        and flow_fca <= BREACH_TARGETS["FCA"]
        and flow_psd2 <= BREACH_TARGETS["PSD2"]
    )


def summarise_closure_metrics(
    rows: list[dict],
    case_type: str,
) -> tuple[float, float, float, float]:
    close_n = sum(row["close_sums"][case_type]["n"] for row in rows)
    if close_n <= 0.01:
        return 0.0, 0.0, 0.0, 0.0
    avg_close_day = sum(
        row["closures_by_type"].get(case_type, 0.0) for row in rows
    ) / len(rows)
    avg_reg = sum(row["close_sums"][case_type]["reg"] for row in rows) / close_n
    avg_cal = sum(row["close_sums"][case_type]["cal"] for row in rows) / close_n
    avg_sys = sum(row["close_sums"][case_type]["sys"] for row in rows) / close_n
    return avg_close_day, avg_reg, avg_cal, avg_sys


def print_stable_pack(fte: int, result: list[dict]) -> None:
    on_desk_productive = fte * (1 - SHRINKAGE)
    on_desk_present = fte * (1 - ABSENCE_SHRINKAGE)
    final = result[-1]
    last30 = last_n_days(result, 30)
    last60_workdays = last_n_workdays(result, 60)
    total_rate, fca_rate, psd2_rate = average_breach_rates(result, last_days=30)
    flow_total, flow_fca, flow_psd2 = average_flow_breach_rates(result, last_days=30)
    clear_day = next((row["day"] + 1 for row in result if row["wip"] < 0.5), None)

    target_wip = on_desk_present * DIARY_LIMIT + UNALLOCATED_BUFFER
    print("=" * 96)
    print(f"FULL 365 DAY RUN - {fte} FTE (ROLLING DIARY REFILL + PARKINSON'S LAW)")
    print("=" * 96)
    print(
        f"Present FTE: {on_desk_present:.1f}, diary slots: {on_desk_present * DIARY_LIMIT:.0f}, "
        f"productive FTE: {on_desk_productive:.1f}, "
        f"max hours/day: {on_desk_productive * HOURS_PER_DAY * UTILISATION * PROFICIENCY:.1f}"
    )
    print(
        f"Parkinson's Law: desired WIP = {final['desired_wip']:.0f} (diary {on_desk_present * DIARY_LIMIT:.0f} + buffer {UNALLOCATED_BUFFER}), "
        f"util floor = {PARKINSON_FLOOR:.0%}, min diary days = {MIN_DIARY_DAYS}"
    )
    print(f"Effective util at end: {final['effective_util']:.1%}")
    print(f"Full-pace queue (auto): {PARKINSON_FULL_PACE_QUEUE}")

    print("\nStability")
    for d in [30, 90, 180, 365, DAYS]:
        if d <= len(result):
            print(f"  Day {d:>4} WIP: {result[min(d-1, len(result)-1)]['wip']:>8,.0f}")
    print(f"  WIP change, last 30 days: {final['wip'] - result[-31]['wip']:+,.0f}")
    print(
        f"  Avg closures/workday, last 60 days: "
        f"{mean(row['closures'] for row in last60_workdays):.1f}"
    )
    print(
        f"  Avg allocations/workday, last 60 days: "
        f"{mean(row['allocations'] for row in last60_workdays):.1f}"
    )
    print(
        f"  Diaries start/avg/end, last 60 days: "
        f"{mean(row['occupancy_start'] for row in last60_workdays):.1f} / "
        f"{mean(row['occupancy_avg'] for row in last60_workdays):.1f} / "
        f"{mean(row['occupancy_end'] for row in last60_workdays):.1f}"
    )
    print(
        f"  Fill ratio start/avg/end, last 60 days: "
        f"{mean(row['occupancy_start'] / row['slot_capacity'] for row in last60_workdays) * 100:.1f}% / "
        f"{mean(row['occupancy_avg'] / row['slot_capacity'] for row in last60_workdays) * 100:.1f}% / "
        f"{mean(row['occupancy_end'] / row['slot_capacity'] for row in last60_workdays) * 100:.1f}%"
    )
    print(f"  Backlog fully clears by day: {clear_day}")

    print("\nOpen stock at day 365")
    for case_type in ["FCA", "PSD2_15", "PSD2_35"]:
        print(f"  {case_type:>7}: {final['open_by_type'].get(case_type, 0.0):>8.0f}")
    print(f"  Total:   {final['wip']:>8.0f}")

    print("\nBreaches at day 365")
    psd2_breach = final["breaches_by_type"].get("PSD2_15", 0.0) + final["breaches_by_type"].get("PSD2_35", 0.0)
    print(f"  FCA breached open:   {final['breaches_by_type'].get('FCA', 0.0):.0f}")
    print(f"  PSD2 breached open:  {psd2_breach:.0f}")
    print(f"  Total breached open: {sum(final['breaches_by_type'].values()):.0f}")
    print(f"  Stock breach rate (open breached / open WIP), avg last 30 days:")
    print(f"    FCA:  {fca_rate * 100:.2f}%  |  PSD2: {psd2_rate * 100:.2f}%  |  Total: {total_rate * 100:.2f}%")
    print(f"  Flow breach rate (breached closures / total closures), last 30 days:")
    print(f"    FCA:  {flow_fca * 100:.2f}%  |  PSD2: {flow_psd2 * 100:.2f}%  |  Total: {flow_total * 100:.2f}%")

    print("\nOver internal service target at day 365")
    for case_type in ["FCA", "PSD2_15", "PSD2_35"]:
        open_count = final["open_by_type"].get(case_type, 0.0)
        over_target = final["over_target_by_type"].get(case_type, 0.0)
        pct = (over_target / open_count * 100.0) if open_count > 0 else 0.0
        print(f"  {case_type:>7}: {over_target:>8.0f} ({pct:>5.1f}%)")

    print("\nAge profile at day 365 on regulatory clock")
    for label, _, _ in AGE_BANDS:
        count = final["age_bands"][label]
        share = (count / max(final["wip"], 1.0)) * 100.0
        print(f"  {label:>5}: {count:>8.0f} ({share:>5.1f}%)")

    print("\nAge profile by type at day 365")
    for case_type in ["FCA", "PSD2_15", "PSD2_35"]:
        print(f"  {case_type}")
        open_count = max(final["open_by_type"].get(case_type, 0.0), 1.0)
        for label, _, _ in AGE_BANDS:
            count = final["age_bands_by_type"][case_type][label]
            if count > 0.5:
                print(f"    {label:>5}: {count:>8.0f} ({count / open_count * 100:>5.1f}%)")

    print("\nClosure metrics, last 60 workdays")
    for case_type in ["FCA", "PSD2_15", "PSD2_35"]:
        avg_close_day, avg_reg, avg_cal, avg_sys = summarise_closure_metrics(
            last60_workdays, case_type
        )
        if avg_close_day <= 0.01:
            continue
        print(
            f"  {case_type:>7}: closures/day {avg_close_day:>6.1f} | "
            f"avg reg age at close {avg_reg:>5.1f} | avg cal age {avg_cal:>5.1f} | "
            f"avg days in system {avg_sys:>5.1f}"
        )

    print("\nAllocation metrics, last 60 workdays")
    for case_type in ["FCA", "PSD2_15", "PSD2_35"]:
        avg_alloc = sum(
            row["allocations_by_type"].get(case_type, 0.0) for row in last60_workdays
        ) / len(last60_workdays)
        print(f"  {case_type:>7}: allocations/day {avg_alloc:>6.1f}")
    print(
        f"  Total avg allocation delay: "
        f"{mean(row['avg_allocation_delay'] for row in last60_workdays):.1f} days"
    )

    print("\nTrajectory snapshots")
    for day in [0, 30, 60, 90, 120, 180, 240, 300, 364]:
        row = result[day]
        psd2_open = row["open_by_type"].get("PSD2_15", 0.0) + row["open_by_type"].get("PSD2_35", 0.0)
        psd2_breach = row["breaches_by_type"].get("PSD2_15", 0.0) + row["breaches_by_type"].get("PSD2_35", 0.0)
        print(
            f"  Day {day + 1:>3}: WIP {row['wip']:>7.0f} | "
            f"Unalloc {row['unalloc']:>7.0f} | Alloc {row['alloc']:>6.0f} | "
            f"Util {row['effective_util']:>4.0%} | "
            f"FCA br {row['breaches_by_type'].get('FCA', 0.0):>6.0f} | "
            f"PSD2 br {psd2_breach:>6.0f}"
        )

    print("\n30-day blocks while the model settles")
    for start, end, name in [
        (0, 29, "Days 1-30"),
        (30, 59, "Days 31-60"),
        (60, 89, "Days 61-90"),
        (90, 119, "Days 91-120"),
        (120, 149, "Days 121-150"),
    ]:
        block = [row for row in result[start : end + 1] if row["workday"]]
        print(name)
        print(f"  Avg allocations/day: {mean(row['allocations'] for row in block):.1f}")
        print(f"  Avg closures/day:    {mean(row['closures'] for row in block):.1f}")
        print(
            f"  Avg start/avg/end fill: "
            f"{mean(row['occupancy_start'] for row in block):.1f} / "
            f"{mean(row['occupancy_avg'] for row in block):.1f} / "
            f"{mean(row['occupancy_end'] for row in block):.1f}"
        )
        print(
            f"  Avg alloc delay:     {mean(row['avg_allocation_delay'] for row in block):.1f} days"
        )
        for case_type in ["FCA", "PSD2_15", "PSD2_35"]:
            avg_close_day, avg_reg, avg_cal, avg_sys = summarise_closure_metrics(
                block, case_type
            )
            if avg_close_day <= 0.01:
                continue
            print(
                f"  {case_type:>7}: close/day {avg_close_day:>6.1f} | "
                f"avg reg age {avg_reg:>5.1f} | avg cal age {avg_cal:>5.1f} | "
                f"avg days in system {avg_sys:>5.1f}"
            )
        print()


def print_fte_sweep(rows: list[dict]) -> None:
    print("=" * 120)
    print(f"FTE SWEEP - {DAYS} DAYS, PARKINSON'S LAW (floor={PARKINSON_FLOOR:.0%}, FPQ={PARKINSON_FULL_PACE_QUEUE})")
    print("=" * 120)
    print(
        f"{'FTE':>4} {'WIP':>7} {'dWIP30':>7} {'Unalloc':>8} {'Alloc':>6} {'Util':>6} "
        f"{'Close':>6} {'Delay':>6} {'FCA Age':>8} {'SysTime':>8} {'StockBr':>7} {'FlowBr':>7} {'Stable':>6}"
    )
    for row in rows:
        stable_flag = "YES" if row["stable"] else ""
        print(
            f"{row['fte']:>4} {row['final_wip']:>7.0f} {row['dwip30']:>+7.0f} "
            f"{row['final_unalloc']:>8.0f} {row['final_alloc']:>6.0f} {row['util']:>5.1%} "
            f"{row['close60']:>6.1f} {row['alloc_delay']:>5.1f}d "
            f"{row['fca_age']:>8.1f} {row['sys_time']:>8.1f} "
            f"{row['breach30']:>6.2f}% {row['flow_breach30']:>6.2f}% {stable_flag:>6}"
        )

    stable = [row for row in rows if row["stable"]]
    if stable:
        print(f"\nMinimum stable FTE: {stable[0]['fte']}")
    else:
        print("\nNo stable FTE found in the sweep range.")


def main() -> None:
    print("=" * 96)
    print("COMPLAINTS DEMAND MODEL - CORRECTED PROOF HARNESS")
    print("=" * 96)
    print(
        "Key correction: diary slots are now refilled throughout the day, so "
        "occupancy stays near capacity when backlog is waiting."
    )
    print(
        f"Assumptions held constant: shrinkage {SHRINKAGE:.0%}, utilisation "
        f"{UTILISATION:.0%}, proficiency {PROFICIENCY:.2f}, intake {DAILY_INTAKE}/day."
    )

    import gc

    sweep_rows = []
    detailed_result = None
    for fte in FTE_SWEEP:
        result = simulate(fte)
        last60_workdays = last_n_workdays(result, 60)
        total_rate, fca_rate, psd2_rate = average_breach_rates(result, last_days=30)
        flow_total, _flow_fca, _flow_psd2 = average_flow_breach_rates(result, last_days=30)
        on_desk_present = fte * (1 - ABSENCE_SHRINKAGE)
        cn = sum(row["close_sums"]["FCA"]["n"] for row in last60_workdays)
        avg_fca_age = sum(row["close_sums"]["FCA"]["reg"] for row in last60_workdays) / cn if cn > 0.01 else 0
        avg_sys_time = sum(row["close_sums"]["FCA"]["sys"] for row in last60_workdays) / cn if cn > 0.01 else 0
        sweep_rows.append(
            {
                "fte": fte,
                "final_wip": result[-1]["wip"],
                "dwip30": result[-1]["wip"] - result[-31]["wip"],
                "final_unalloc": result[-1]["unalloc"],
                "final_alloc": result[-1]["alloc"],
                "util": result[-1]["effective_util"],
                "diary_slots": on_desk_present * DIARY_LIMIT,
                "close60": mean(row["closures"] for row in last60_workdays),
                "alloc_delay": mean(row["avg_allocation_delay"] for row in last60_workdays),
                "fca_age": avg_fca_age,
                "sys_time": avg_sys_time,
                "breach30": total_rate * 100.0,
                "flow_breach30": flow_total * 100.0,
                "fca30": fca_rate * 100.0,
                "psd230": psd2_rate * 100.0,
                "stable": is_stable(result),
            }
        )
        if fte == DEFAULT_FTE:
            detailed_result = result
        else:
            del result
            gc.collect()

    print_fte_sweep(sweep_rows)
    if detailed_result is not None:
        print()
        print_stable_pack(DEFAULT_FTE, detailed_result)


if __name__ == "__main__":
    main()
