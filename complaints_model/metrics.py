"""KPI computation — breach rates, stability, closure summaries."""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

from .config import SimConfig
from .cohort import Cohort
from .time_utils import regulatory_age
from .effort import burden_mult, case_effort, AGE_BANDS
from .regulatory import (
    SERVICE_TARGETS, REGULATORY_DEADLINES, BREACH_TARGETS,
    remaining_workdays_to_target,
)


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
    cfg: SimConfig,
) -> float:
    productive_hours_per_fte = (
        (1 - cfg.shrinkage) * cfg.hours_per_day * cfg.utilisation
        * cfg.proficiency * (1 - cfg.late_demand_rate)
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
        eff = case_effort(cohort, cfg.base_effort, cfg.handoff_overhead,
                          cfg.handoff_effort_hours, cfg.src_effort_ratio, cfg.src_window)
        total_demand_hours += cohort.count * eff / target_remaining

    for cohort in unallocated:
        reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
        est_effort = cohort.count * cfg.base_effort * burden_mult(reg_age)
        target_remaining = max(
            1,
            remaining_workdays_to_target(
                cohort.case_type, cohort.cal_age, cohort.biz_age, sim_day
            ),
        )
        total_demand_hours += est_effort / target_remaining

    return total_demand_hours / productive_hours_per_fte


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


def is_stable(result: list[dict], cfg: SimConfig | None = None) -> bool:
    if len(result) < 31:
        return False
    daily_intake = cfg.daily_intake if cfg else 300
    wip_change_30 = result[-1]["wip"] - result[-31]["wip"]
    wip_threshold = daily_intake / 12
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
