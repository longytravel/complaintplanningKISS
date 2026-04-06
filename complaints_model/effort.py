"""Effort and burden calculations."""
from __future__ import annotations

from .cohort import Cohort
from .time_utils import regulatory_age

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


def burden_mult(reg_age: int) -> float:
    for (lo, hi), mult in BURDEN.items():
        if lo <= reg_age <= hi:
            return mult
    return 2.5


def case_effort(
    cohort: Cohort,
    base_effort: float,
    handoff_overhead: float,
    handoff_effort_hours: float,
    src_effort_ratio: float,
    src_window: int,
) -> float:
    """Calculate effort per case from live age — not frozen at allocation time.

    Seeded cases retain their work-already-done discount.
    SRC cases get effort discount only while within the SRC window.
    """
    if cohort.seeded:
        return cohort.effort_per_case
    reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
    effort = base_effort * burden_mult(reg_age) + handoff_overhead * handoff_effort_hours
    if cohort.is_src and reg_age <= src_window:
        effort *= src_effort_ratio
    return effort
