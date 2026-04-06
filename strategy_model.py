"""
Strategy-aware simulation model — fork of prove_maths.py
=========================================================

Adds configurable allocation and work prioritisation strategies without
modifying the original prove_maths.py module.

Two module-level globals control behaviour:
  ALLOCATION_STRATEGY  — which cases leave the unallocated queue first
  WORK_STRATEGY        — which cases a handler picks from their diary

Both default to "nearest_target" (identical to prove_maths behaviour).
Set these before calling simulate() to test different strategies.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean

# ── Constants (unchanged from prove_maths) ──────────────────────────
from prove_maths import (
    DEFAULT_FTE, SHRINKAGE, ABSENCE_SHRINKAGE, HOURS_PER_DAY,
    UTILISATION, PROFICIENCY, DIARY_LIMIT, DAILY_INTAKE, BASE_EFFORT,
    MIN_DIARY_DAYS, MIN_DIARY_DAYS_NON_SRC, HANDOFF_OVERHEAD, HANDOFF_EFFORT_HOURS, LATE_DEMAND_RATE,
    DAYS, SLICES_PER_DAY, UNALLOCATED_BUFFER, PARKINSON_FLOOR,
    PARKINSON_FULL_PACE_QUEUE, SRC_BOOST_MAX, SRC_BOOST_DECAY_DAYS,
    SERVICE_TARGETS, REGULATORY_DEADLINES, BREACH_TARGETS, INTAKE_PROPORTIONS,
    SRC_RATES, SRC_WINDOW, SRC_DIST, SRC_EFFORT_RATIO, PSD2_EXTENSION_RATE,
    BURDEN, AGE_BANDS,
)

# ── Helpers (don't create Cohort — duck-typed, work with extended Cohort) ──
from prove_maths import (
    is_workday, burden_mult, case_effort,
    count_business_days_forward, count_business_days_signed,
    regulatory_age, remaining_workdays_to_target, remaining_workdays_to_deadline,
    make_age, intake_distribution, starting_wip_distribution,
    count_by_type, count_breaches, count_over_target, count_age_bands,
    calculate_instantaneous_fte_demand,
    last_n_days, last_n_workdays, average_breach_rates, average_flow_breach_rates,
    is_stable, summarise_closure_metrics,
)


# ═══════════════════════════════════════════════════════════════════════
# Strategy configuration
# ═══════════════════════════════════════════════════════════════════════

ALLOCATION_STRATEGY = "nearest_target"
WORK_STRATEGY = "nearest_target"


# ═══════════════════════════════════════════════════════════════════════
# Extended Cohort (adds last_worked_day)
# ═══════════════════════════════════════════════════════════════════════

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
    last_worked_day: int | None = None


# ═══════════════════════════════════════════════════════════════════════
# Strategy registry
# ═══════════════════════════════════════════════════════════════════════

def _nearest_target_key(c: Cohort, d: int):
    """Current behaviour — balance target and deadline."""
    return (
        remaining_workdays_to_target(c.case_type, c.cal_age, c.biz_age, d),
        remaining_workdays_to_deadline(c.case_type, c.cal_age, c.biz_age, d),
        -regulatory_age(c.case_type, c.cal_age, c.biz_age),
    )


STRATEGIES = {
    "nearest_deadline": lambda c, d: remaining_workdays_to_deadline(
        c.case_type, c.cal_age, c.biz_age, d
    ),
    "nearest_target": _nearest_target_key,
    "youngest_first": lambda c, d: regulatory_age(
        c.case_type, c.cal_age, c.biz_age
    ),
    "oldest_first": lambda c, d: -regulatory_age(
        c.case_type, c.cal_age, c.biz_age
    ),
    "psd2_priority": lambda c, d: (
        0 if c.case_type.startswith("PSD2") else 1,
        remaining_workdays_to_deadline(c.case_type, c.cal_age, c.biz_age, d),
    ),
    "longest_wait": lambda c, d: c.arrival_day,
    "lowest_effort": lambda c, d: case_effort(c),
    "longest_untouched": lambda c, d: (
        c.last_worked_day if c.last_worked_day is not None else -999999
    ),
}


# ═══════════════════════════════════════════════════════════════════════
# Redefined functions (create Cohort instances or use strategy lookup)
# ═══════════════════════════════════════════════════════════════════════

def seed_pool(total_cases: float, allocated: bool) -> list[Cohort]:
    cohorts: list[Cohort] = []
    for case_type, proportion in INTAKE_PROPORTIONS.items():
        cases_for_type = total_cases * proportion
        for reg_age, count in starting_wip_distribution(cases_for_type):
            cal_age, biz_age = make_age(reg_age, case_type)
            effort = BASE_EFFORT * burden_mult(reg_age)
            if allocated:
                effort *= max(0.1, 1.0 - 0.9 * min(reg_age, 10) / 10.0)
            alloc_day = -max(1, reg_age // 2) if allocated else None
            cohorts.append(
                Cohort(
                    count=count,
                    case_type=case_type,
                    cal_age=cal_age,
                    biz_age=biz_age,
                    effort_per_case=effort,
                    is_src=False,
                    arrival_day=-reg_age,
                    allocation_day=alloc_day,
                    seeded=True,
                    last_worked_day=alloc_day,
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
            cohort.last_worked_day,
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
                last_worked_day=cohort.last_worked_day,
            )
        else:
            merged[key].count += cohort.count
    return list(merged.values())


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
                        last_worked_day=cohort.last_worked_day,
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
                        last_worked_day=cohort.last_worked_day,
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

    alloc_key = STRATEGIES[ALLOCATION_STRATEGY]
    unallocated.sort(key=lambda cohort: alloc_key(cohort, sim_day))
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
                    last_worked_day=cohort.last_worked_day,
                )
            )

        if move <= 0.01:
            continue

        reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
        alloc_delay = sim_day - cohort.arrival_day
        src_boost = SRC_BOOST_MAX * (0.5 ** (alloc_delay / SRC_BOOST_DECAY_DAYS))
        effective_src_rate = min(0.95, SRC_RATES[cohort.case_type] + src_boost)
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
                    effort_per_case=0.0,
                    is_src=True,
                    arrival_day=cohort.arrival_day,
                    allocation_day=sim_day,
                    seeded=False,
                    last_worked_day=sim_day,
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
                    effort_per_case=0.0,
                    is_src=False,
                    arrival_day=cohort.arrival_day,
                    allocation_day=sim_day,
                    seeded=False,
                    last_worked_day=sim_day,
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
        if cohort.allocation_day is None:
            return False
        cal_days = sim_day - cohort.allocation_day
        if cal_days < 0:
            return False
        full_weeks, remainder = divmod(cal_days, 7)
        biz_days = full_weeks * 5
        for i in range(remainder):
            if is_workday(cohort.allocation_day + full_weeks * 7 + i):
                biz_days += 1
        min_days = MIN_DIARY_DAYS if cohort.is_src else MIN_DIARY_DAYS_NON_SRC
        return biz_days >= min_days

    work_key = STRATEGIES[WORK_STRATEGY]

    src_candidates = [
        cohort for cohort in allocated
        if cohort.is_src and cohort.count > 0.01 and closeable(cohort)
    ]
    src_candidates.sort(key=lambda cohort: work_key(cohort, sim_day))

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
            cohort.last_worked_day = sim_day
            reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
            close_sums[cohort.case_type]["n"] += close
            close_sums[cohort.case_type]["reg"] += reg_age * close
            close_sums[cohort.case_type]["cal"] += cohort.cal_age * close
            close_sums[cohort.case_type]["sys"] += (sim_day - cohort.arrival_day) * close
            if reg_age > REGULATORY_DEADLINES[cohort.case_type]:
                breached_closures_by_type[cohort.case_type] += close

    regular_candidates = [
        cohort for cohort in allocated if cohort.count > 0.01 and closeable(cohort)
    ]
    regular_candidates.sort(key=lambda cohort: work_key(cohort, sim_day))

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
            cohort.last_worked_day = sim_day
            reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
            close_sums[cohort.case_type]["n"] += closed
            close_sums[cohort.case_type]["reg"] += reg_age * closed
            close_sums[cohort.case_type]["cal"] += cohort.cal_age * closed
            close_sums[cohort.case_type]["sys"] += (sim_day - cohort.arrival_day) * closed
            if reg_age > REGULATORY_DEADLINES[cohort.case_type]:
                breached_closures_by_type[cohort.case_type] += closed

    return allocated, closures_total, dict(closures_by_type), close_sums, dict(breached_closures_by_type)


def simulate(fte: int, util_override: float | None = None, max_wip: float = 50_000) -> list[dict]:
    max_utilisation = util_override if util_override is not None else UTILISATION
    on_desk_productive = fte * (1 - SHRINKAGE)
    on_desk_present = fte * (1 - ABSENCE_SHRINKAGE)
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

            # 5th pass: end-of-day refill
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

            src_schedule[workday_num] = dict(src_allocated_today)
            workday_num += 1

        allocated = [cohort for cohort in allocated if cohort.count > 0.01]
        unallocated = [cohort for cohort in unallocated if cohort.count > 0.01]

        if day % 14 == 0:
            allocated = merge_cohorts(allocated)
            unallocated = merge_cohorts(unallocated)

        all_open = unallocated + allocated
        total_wip = sum(cohort.count for cohort in all_open)

        # Circuit breaker: death spiral detected — stop before memory corruption
        if total_wip > max_wip and day > 60:
            results.append({
                "day": day, "workday": workday, "wip": total_wip,
                "unalloc": sum(c.count for c in unallocated),
                "alloc": sum(c.count for c in allocated),
                "open_by_type": count_by_type(all_open),
                "breaches_by_type": {}, "over_target_by_type": {},
                "age_bands": {l: 0.0 for l, _, _ in AGE_BANDS},
                "age_bands_by_type": {ct: {l: 0.0 for l, _, _ in AGE_BANDS} for ct in ["FCA","PSD2_15","PSD2_35"]},
                "allocations": allocations_total,
                "allocations_by_type": dict(allocations_by_type),
                "avg_allocation_delay": weighted_delay_total / allocations_total if allocations_total > 0 else 0.0,
                "closures": closures_total,
                "closures_by_type": dict(closures_by_type),
                "breached_closures_by_type": dict(breached_closures_total),
                "close_sums": close_sums_total,
                "demand_fte": 0.0, "effective_util": effective_util,
                "desired_wip": desired_wip,
                "occupancy_start": 0.0, "occupancy_avg": 0.0, "occupancy_end": 0.0,
                "slot_capacity": max_slots,
                "max_unallocated_wait": 999, "max_diary_untouched": 999,
                "avg_diary_untouched": 999.0,
            })
            break

        open_by_type = count_by_type(all_open)
        breaches_by_type = count_breaches(all_open)
        over_target_by_type = count_over_target(all_open)
        age_bands, age_bands_by_type = count_age_bands(all_open)
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

        # ── New neglect metrics ─────────────────────────────────────
        max_unallocated_wait = max(
            (day - c.arrival_day for c in unallocated),
            default=0,
        )
        max_diary_untouched = max(
            (day - c.last_worked_day for c in allocated if c.last_worked_day is not None),
            default=0,
        )
        alloc_with_lwd = [c for c in allocated if c.last_worked_day is not None]
        total_alloc_lwd = sum(c.count for c in alloc_with_lwd)
        avg_diary_untouched = (
            sum((day - c.last_worked_day) * c.count for c in alloc_with_lwd)
            / total_alloc_lwd
            if total_alloc_lwd > 0.01 else 0.0
        )

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
                "max_unallocated_wait": max_unallocated_wait,
                "max_diary_untouched": max_diary_untouched,
                "avg_diary_untouched": avg_diary_untouched,
            }
        )

    return results
