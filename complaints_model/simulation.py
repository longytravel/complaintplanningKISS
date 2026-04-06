"""Main simulation loop — orchestrates daily complaint flow."""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

from .config import SimConfig
from .cohort import Cohort, merge_cohorts
from .time_utils import is_workday, make_age
from .effort import case_effort
from .regulatory import apply_psd2_extensions
from .intake import (
    intake_distribution, seed_pool, INTAKE_PROPORTIONS,
)
from .allocation import allocate_up_to_capacity
from .work import process_work_slice
from .metrics import (
    count_by_type, count_breaches, count_over_target, count_age_bands,
    calculate_instantaneous_fte_demand,
)


def simulate(
    cfg: SimConfig,
    util_override: float | None = None,
    max_wip: float = 50_000,
) -> list[dict]:
    max_utilisation = util_override if util_override is not None else cfg.utilisation
    on_desk_productive = cfg.fte * (1 - cfg.shrinkage)
    on_desk_present = cfg.fte * (1 - cfg.absence_shrinkage)
    max_slots = on_desk_present * cfg.diary_limit
    desired_wip = max_slots + cfg.unallocated_buffer

    full_pace_queue = cfg.parkinson_full_pace_queue

    unallocated = seed_pool(2500 * 0.25, allocated=False, cfg=cfg)
    allocated = seed_pool(2500 * 0.75, allocated=True, cfg=cfg)
    src_schedule: dict[int, dict[str, float]] = {}
    results: list[dict] = []
    workday_num = 0

    for day in range(cfg.days):
        workday = is_workday(day)

        # Parkinson's Law: pace driven by visible unallocated queue
        current_unalloc = sum(c.count for c in unallocated)
        pressure = min(current_unalloc / full_pace_queue, 1.0) if full_pace_queue > 0 else 1.0
        effective_util = cfg.parkinson_floor + (max_utilisation - cfg.parkinson_floor) * pressure
        productive_hours = (
            on_desk_productive * cfg.hours_per_day * effective_util
            * cfg.proficiency * (1 - cfg.late_demand_rate)
        )
        slice_budget = productive_hours / cfg.slices_per_day if cfg.slices_per_day > 0 else 0.0

        for cohort in unallocated + allocated:
            cohort.cal_age += 1
            if workday:
                cohort.biz_age += 1

        if workday:
            for case_type, proportion in INTAKE_PROPORTIONS.items():
                for reg_age, count in intake_distribution(cfg.daily_intake * proportion):
                    cal_age, biz_age = make_age(reg_age, case_type)
                    unallocated.append(
                        Cohort(
                            count=count,
                            case_type=case_type,
                            cal_age=cal_age,
                            biz_age=biz_age,
                            effort_per_case=0.0,
                            is_src=False,
                            arrival_day=day,
                            allocation_day=None,
                            seeded=False,
                        )
                    )

        if workday:
            unallocated = apply_psd2_extensions(unallocated, cfg.psd2_extension_rate)
            allocated = apply_psd2_extensions(allocated, cfg.psd2_extension_rate)

        allocations_total = 0.0
        weighted_delay_total = 0.0
        allocations_by_type = defaultdict(float)
        closures_total = 0.0
        closures_by_type = defaultdict(float)
        close_sums_total = {
            case_type: {"n": 0.0, "reg": 0.0, "cal": 0.0, "sys": 0.0}
            for case_type in ["FCA", "PSD2_15", "PSD2_35"]
        }
        breached_closures_total = defaultdict(float)
        occupancy_before_work = []
        src_allocated_today = defaultdict(float)
        src_closed_today = defaultdict(float)

        if workday:
            for _ in range(cfg.slices_per_day):
                (
                    unallocated,
                    allocated,
                    slice_allocations,
                    slice_delay,
                    slice_alloc_by_type,
                ) = allocate_up_to_capacity(
                    unallocated,
                    allocated,
                    max_slots,
                    day,
                    src_allocated_today,
                    cfg,
                )
                allocations_total += slice_allocations
                weighted_delay_total += slice_delay
                for case_type, count in slice_alloc_by_type.items():
                    allocations_by_type[case_type] += count

                occupancy_before_work.append(sum(cohort.count for cohort in allocated))

                (
                    allocated,
                    slice_closures,
                    slice_closures_by_type,
                    slice_close_sums,
                    slice_breached_closures,
                ) = process_work_slice(
                    allocated,
                    slice_budget,
                    day,
                    workday_num,
                    src_allocated_today,
                    src_schedule,
                    src_closed_today,
                    cfg,
                )
                closures_total += slice_closures
                for case_type, count in slice_closures_by_type.items():
                    closures_by_type[case_type] += count
                for case_type in close_sums_total:
                    for key in close_sums_total[case_type]:
                        close_sums_total[case_type][key] += slice_close_sums[case_type][key]
                for case_type, count in slice_breached_closures.items():
                    breached_closures_total[case_type] += count

                allocated = [cohort for cohort in allocated if cohort.count > 0.01]

            # 5th pass: end-of-day refill
            (
                unallocated,
                allocated,
                slice_allocations,
                slice_delay,
                slice_alloc_by_type,
            ) = allocate_up_to_capacity(
                unallocated,
                allocated,
                max_slots,
                day,
                src_allocated_today,
                cfg,
            )
            allocations_total += slice_allocations
            weighted_delay_total += slice_delay
            for case_type, count in slice_alloc_by_type.items():
                allocations_by_type[case_type] += count

            src_schedule[workday_num] = dict(src_allocated_today)
            workday_num += 1

        allocated = [cohort for cohort in allocated if cohort.count > 0.01]
        unallocated = [cohort for cohort in unallocated if cohort.count > 0.01]

        if day % 14 == 0:
            allocated = merge_cohorts(allocated)
            unallocated = merge_cohorts(unallocated)

        all_open = unallocated + allocated
        open_by_type = count_by_type(all_open)
        breaches_by_type = count_breaches(all_open)
        over_target_by_type = count_over_target(all_open)
        age_bands, age_bands_by_type = count_age_bands(all_open)

        total_wip = sum(cohort.count for cohort in all_open)
        total_unallocated = sum(cohort.count for cohort in unallocated)
        total_allocated = sum(cohort.count for cohort in allocated)
        instantaneous_fte_demand = calculate_instantaneous_fte_demand(
            unallocated, allocated, day, cfg
        )
        avg_allocation_delay = (
            weighted_delay_total / allocations_total if allocations_total > 0 else 0.0
        )
        occupancy_start = (
            occupancy_before_work[0] if occupancy_before_work else total_allocated
        )
        occupancy_avg = (
            mean(occupancy_before_work) if occupancy_before_work else total_allocated
        )
        occupancy_end = total_allocated

        # Neglect metrics
        max_unallocated_wait = max(
            (day - c.arrival_day for c in unallocated),
            default=0,
        )
        max_diary_untouched = max(
            (day - c.last_worked_day for c in allocated if c.last_worked_day is not None),
            default=0,
        )
        alloc_with_lwd = [c for c in allocated if c.last_worked_day is not None]
        total_alloc_lwd = sum(c.count for c in alloc_with_lwd)
        avg_diary_untouched = (
            sum((day - c.last_worked_day) * c.count for c in alloc_with_lwd)
            / total_alloc_lwd
            if total_alloc_lwd > 0.01 else 0.0
        )

        results.append(
            {
                "day": day,
                "workday": workday,
                "wip": total_wip,
                "unalloc": total_unallocated,
                "alloc": total_allocated,
                "open_by_type": open_by_type,
                "breaches_by_type": breaches_by_type,
                "over_target_by_type": over_target_by_type,
                "age_bands": age_bands,
                "age_bands_by_type": age_bands_by_type,
                "allocations": allocations_total,
                "allocations_by_type": dict(allocations_by_type),
                "avg_allocation_delay": avg_allocation_delay,
                "closures": closures_total,
                "closures_by_type": dict(closures_by_type),
                "breached_closures_by_type": dict(breached_closures_total),
                "close_sums": close_sums_total,
                "demand_fte": instantaneous_fte_demand,
                "effective_util": effective_util,
                "desired_wip": desired_wip,
                "occupancy_start": occupancy_start,
                "occupancy_avg": occupancy_avg,
                "occupancy_end": occupancy_end,
                "slot_capacity": max_slots,
                "max_unallocated_wait": max_unallocated_wait,
                "max_diary_untouched": max_diary_untouched,
                "avg_diary_untouched": avg_diary_untouched,
            }
        )

        if total_wip > max_wip:
            break

    return results
