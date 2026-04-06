# complaints_model/harm.py
"""Harm score accumulation — per-case-per-day customer harm scoring."""
from __future__ import annotations

from .cohort import Cohort
from .regulatory import REGULATORY_DEADLINES


def _days_past_deadline(cohort: Cohort) -> int:
    """Days past regulatory deadline (0 if not breached)."""
    deadline = REGULATORY_DEADLINES[cohort.case_type]
    if cohort.case_type == "FCA":
        overshoot = cohort.cal_age - deadline
    else:
        overshoot = cohort.biz_age - deadline
    return max(0, overshoot)


def score_case_harm(
    cohort: Cohort,
    sim_day: int,
    breach_w: float,
    neglect_w: float,
    wip_w: float,
) -> float:
    """Score total harm for a cohort on a single day.

    Returns harm × cohort.count (not per-case).
    """
    breach = breach_w * _days_past_deadline(cohort)
    touched = cohort.last_worked_day if cohort.last_worked_day is not None else cohort.arrival_day
    neglect = neglect_w * max(0, sim_day - touched)
    wip = wip_w
    return (breach + neglect + wip) * cohort.count


def accumulate_daily_harm(
    all_open: list[Cohort],
    sim_day: int,
    breach_w: float,
    neglect_w: float,
    wip_w: float,
) -> float:
    """Sum harm across all open cases for one day."""
    return sum(
        score_case_harm(c, sim_day, breach_w, neglect_w, wip_w)
        for c in all_open
    )
