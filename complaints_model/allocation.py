"""Allocation engine — moves cases from unallocated queue to handler diaries."""
from __future__ import annotations

from collections import defaultdict

from .config import SimConfig
from .cohort import Cohort
from .time_utils import regulatory_age
from .strategies import get_sort_key
from .intake import SRC_RATES, SRC_DIST


def allocate_up_to_capacity(
    unallocated: list[Cohort],
    allocated: list[Cohort],
    max_slots: float,
    sim_day: int,
    src_allocated_today: dict[str, float],
    cfg: SimConfig,
) -> tuple[list[Cohort], list[Cohort], float, float, dict[str, float]]:
    current_alloc = sum(cohort.count for cohort in allocated)
    available_slots = max(0.0, max_slots - current_alloc)
    if available_slots <= 0.01:
        return unallocated, allocated, 0.0, 0.0, {}

    sort_key_fn = get_sort_key(cfg.allocation_strategy)
    unallocated.sort(key=lambda cohort: sort_key_fn(cohort, sim_day, cfg))
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
        src_boost = cfg.src_boost_max * (0.5 ** (alloc_delay / cfg.src_boost_decay_days))
        effective_src_rate = min(0.95, SRC_RATES[cohort.case_type] + src_boost)
        src_eligible = sum(w for i, w in enumerate(SRC_DIST) if reg_age + i <= cfg.src_window)
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
