"""Regulatory deadlines, service targets, and PSD2 extension logic."""
from __future__ import annotations

from .cohort import Cohort
from .time_utils import count_business_days_signed

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


def apply_psd2_extensions(pool: list[Cohort], psd2_extension_rate: float) -> list[Cohort]:
    result: list[Cohort] = []
    for cohort in pool:
        if cohort.case_type == "PSD2_15" and cohort.biz_age == 15:
            extension_count = cohort.count * psd2_extension_rate
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
