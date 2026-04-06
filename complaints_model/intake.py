"""Intake profiles, SRC rates, and pool seeding."""
from __future__ import annotations

from .config import SimConfig
from .cohort import Cohort
from .time_utils import make_age
from .effort import burden_mult

INTAKE_PROPORTIONS = {
    "FCA": 0.70,
    "PSD2_15": 0.30,
}

SRC_RATES = {
    "FCA": 0.40,
    "PSD2_15": 0.40,
    "PSD2_35": 0.10,
}

# AM/PM allocation split — drives blended SRC closure distribution
AM_ALLOCATION_SHARE = 0.70
PM_ALLOCATION_SHARE = 0.30
AM_SRC_DIST = (0.30, 0.50, 0.20)
PM_SRC_DIST = (0.05, 0.475, 0.475)
SRC_DIST = (0.22, 0.50, 0.28)

# Intake age profile: proportion of daily intake arriving pre-aged
INTAKE_AGE_PROFILE = {
    0:  0.85,
    1:  0.02,
    2:  0.02,
    3:  0.02,
    4:  0.02,
    5:  0.02,
    **{age: 0.04 / 15 for age in range(6, 21)},
    40: 0.01,
}


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


def seed_pool(total_cases: float, allocated: bool, cfg: SimConfig) -> list[Cohort]:
    cohorts: list[Cohort] = []
    for case_type, proportion in INTAKE_PROPORTIONS.items():
        cases_for_type = total_cases * proportion
        for reg_age, count in starting_wip_distribution(cases_for_type):
            cal_age, biz_age = make_age(reg_age, case_type)
            effort = cfg.base_effort * burden_mult(reg_age)
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
