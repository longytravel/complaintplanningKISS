"""Work engine — handlers close cases from their diaries."""
from __future__ import annotations

from collections import defaultdict

from .config import SimConfig
from .cohort import Cohort
from .time_utils import is_workday, regulatory_age
from .effort import case_effort
from .strategies import get_sort_key
from .regulatory import REGULATORY_DEADLINES
from .intake import SRC_DIST


def process_work_slice(
    allocated: list[Cohort],
    slice_budget: float,
    sim_day: int,
    workday_num: int,
    src_allocated_today: dict[str, float],
    src_schedule: dict[int, dict[str, float]],
    src_closed_today: dict[str, float],
    cfg: SimConfig,
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

    def _case_effort(cohort: Cohort) -> float:
        return case_effort(cohort, cfg.base_effort, cfg.handoff_overhead,
                           cfg.handoff_effort_hours, cfg.src_effort_ratio, cfg.src_window)

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
        min_days = cfg.min_diary_days if cohort.is_src else cfg.min_diary_days_non_src
        return biz_days >= min_days

    # SRC closures first
    sort_key_fn = get_sort_key(cfg.work_strategy)
    src_candidates = [
        cohort for cohort in allocated if cohort.is_src and cohort.count > 0.01 and closeable(cohort)
    ]
    src_candidates.sort(key=lambda cohort: sort_key_fn(cohort, sim_day, cfg))

    for cohort in src_candidates:
        if budget <= 0.01:
            break
        remaining_due = due_by_type[cohort.case_type] - src_closed_today[cohort.case_type]
        if remaining_due <= 0.01:
            continue
        close = min(cohort.count, remaining_due)
        eff = _case_effort(cohort)
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

    # Regular closures
    regular_candidates = [cohort for cohort in allocated if cohort.count > 0.01 and closeable(cohort)]
    regular_candidates.sort(key=lambda cohort: sort_key_fn(cohort, sim_day, cfg))

    for cohort in regular_candidates:
        if budget <= 0.01:
            break
        eff = _case_effort(cohort)
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
