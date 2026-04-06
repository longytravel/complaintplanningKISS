"""Time and calendar utilities for the simulation."""
from __future__ import annotations


def is_workday(day: int) -> bool:
    """Monday-Friday = workday (day 0 = Monday)."""
    return (day % 7) < 5


def count_business_days_forward(sim_day: int, calendar_days: int) -> int:
    """Count business days in the next `calendar_days` from sim_day."""
    if calendar_days <= 0:
        return 0
    full_weeks, remainder = divmod(calendar_days, 7)
    biz_days = full_weeks * 5
    for i in range(remainder):
        if is_workday(sim_day + full_weeks * 7 + i):
            biz_days += 1
    return biz_days


def count_business_days_signed(sim_day: int, remaining_cal_days: int) -> int:
    """Count business days for signed calendar day offsets (past or future)."""
    if remaining_cal_days == 0:
        return 0
    if remaining_cal_days > 0:
        return count_business_days_forward(sim_day, remaining_cal_days)
    due_day = sim_day + remaining_cal_days
    return -count_business_days_forward(due_day, -remaining_cal_days)


def regulatory_age(case_type: str, cal_age: int, biz_age: int) -> int:
    """Regulatory age: FCA counts calendar days, PSD2 counts business days."""
    if case_type == "FCA":
        return cal_age
    return biz_age


def make_age(reg_age: int, case_type: str) -> tuple[int, int]:
    """Reconstruct (cal_age, biz_age) from regulatory age and case type."""
    if case_type == "FCA":
        return reg_age, count_business_days_forward(0, reg_age)
    return reg_age + (reg_age // 5) * 2, reg_age
