"""Cohort dataclass — the atomic unit of the simulation."""
from __future__ import annotations
from dataclasses import dataclass


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


def merge_cohorts(cohorts: list[Cohort]) -> list[Cohort]:
    """Combine cohorts with identical attributes (except count) to reduce list size."""
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
