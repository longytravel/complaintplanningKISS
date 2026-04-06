"""Strategy registry — sort-key functions for allocation and work prioritisation."""
from __future__ import annotations

from .cohort import Cohort
from .time_utils import regulatory_age
from .regulatory import remaining_workdays_to_target, remaining_workdays_to_deadline
from .effort import case_effort


def _nearest_target_key(c: Cohort, d: int, cfg=None):
    """Current behaviour — balance target and deadline."""
    return (
        remaining_workdays_to_target(c.case_type, c.cal_age, c.biz_age, d),
        remaining_workdays_to_deadline(c.case_type, c.cal_age, c.biz_age, d),
        -regulatory_age(c.case_type, c.cal_age, c.biz_age),
    )


def _nearest_deadline_key(c: Cohort, d: int, cfg=None):
    return remaining_workdays_to_deadline(c.case_type, c.cal_age, c.biz_age, d)


def _youngest_first_key(c: Cohort, d: int, cfg=None):
    return regulatory_age(c.case_type, c.cal_age, c.biz_age)


def _oldest_first_key(c: Cohort, d: int, cfg=None):
    return -regulatory_age(c.case_type, c.cal_age, c.biz_age)


def _psd2_priority_key(c: Cohort, d: int, cfg=None):
    return (
        0 if c.case_type.startswith("PSD2") else 1,
        remaining_workdays_to_deadline(c.case_type, c.cal_age, c.biz_age, d),
    )


def _longest_wait_key(c: Cohort, d: int, cfg=None):
    return c.arrival_day


def _lowest_effort_key(c: Cohort, d: int, cfg=None):
    if cfg is not None:
        return case_effort(c, cfg.base_effort, cfg.handoff_overhead,
                           cfg.handoff_effort_hours, cfg.src_effort_ratio, cfg.src_window)
    return c.effort_per_case


def _longest_untouched_key(c: Cohort, d: int, cfg=None):
    return c.last_worked_day if c.last_worked_day is not None else -999999


STRATEGIES = {
    "nearest_deadline": _nearest_deadline_key,
    "nearest_target": _nearest_target_key,
    "youngest_first": _youngest_first_key,
    "oldest_first": _oldest_first_key,
    "psd2_priority": _psd2_priority_key,
    "longest_wait": _longest_wait_key,
    "lowest_effort": _lowest_effort_key,
    "longest_untouched": _longest_untouched_key,
}


def get_sort_key(strategy_name: str):
    """Look up a strategy sort-key function by name. Raises KeyError if unknown."""
    return STRATEGIES[strategy_name]
