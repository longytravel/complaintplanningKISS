# complaints_model/pool_simulation.py
"""Pool-aware simulation -- multiple handler pools with per-band strategies."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from statistics import mean

from .config import SimConfig
from .cohort import Cohort, merge_cohorts
from .time_utils import is_workday, make_age
from .effort import case_effort
from .regulatory import apply_psd2_extensions
from .intake import intake_distribution, seed_pool, INTAKE_PROPORTIONS
from .allocation import allocate_up_to_capacity
from .work import process_work_slice
from .metrics import (
    count_by_type, count_breaches, count_over_target, count_age_bands,
    calculate_instantaneous_fte_demand,
)
from .bands import get_bands_for_model, assign_band, detect_transitions
from .pool_config import OptimConfig, BandAllocation
from .harm import accumulate_daily_harm


def simulate_pooled(
    optim_cfg: OptimConfig,
    max_wip: float = 50_000,
) -> list[dict]:
    """Run 730-day pool-aware simulation.

    Returns list of daily result dicts (same shape as simulate() plus 'harm').
    """
    cfg = optim_cfg.base_config
    bands = get_bands_for_model(optim_cfg.pooling_model)
    band_names = [b.name for b in bands]

    # Build per-band config and capacity
    band_alloc_map: dict[str, BandAllocation] = {
        ba.band_name: ba for ba in optim_cfg.band_allocations
    }
    band_cfgs: dict[str, SimConfig] = {}
    band_max_slots: dict[str, float] = {}
    band_productive: dict[str, float] = {}

    for bname in band_names:
        ba = band_alloc_map[bname]
        band_cfgs[bname] = replace(
            cfg,
            fte=ba.fte,
            allocation_strategy=ba.allocation_strategy,
            work_strategy=ba.work_strategy,
        )
        present = ba.fte * (1 - cfg.absence_shrinkage)
        band_max_slots[bname] = present * cfg.diary_limit
        band_productive[bname] = ba.fte * (1 - cfg.shrinkage)

    # Initialise pools
    pools: dict[str, dict[str, list[Cohort]]] = {
        bname: {"unallocated": [], "allocated": []}
        for bname in band_names
    }

    # Seed initial WIP into bands
    initial_unalloc = seed_pool(2500 * 0.25, allocated=False, cfg=cfg)
    initial_alloc = seed_pool(2500 * 0.75, allocated=True, cfg=cfg)
    for c in initial_unalloc:
        bname = assign_band(c, bands)
        pools[bname]["unallocated"].append(c)
    for c in initial_alloc:
        bname = assign_band(c, bands)
        pools[bname]["allocated"].append(c)

    # Per-band SRC tracking
    band_src_schedule: dict[str, dict[int, dict[str, float]]] = {
        bname: {} for bname in band_names
    }

    results: list[dict] = []
    workday_num = 0
    cumulative_harm = 0.0
    steady_state_start = 366

    for day in range(cfg.days):
        workday = is_workday(day)

        # --- Age all cohorts ---
        for bname in band_names:
            for c in pools[bname]["unallocated"] + pools[bname]["allocated"]:
                c.cal_age += 1
                if workday:
                    c.biz_age += 1

        # --- PSD2 extensions ---
        if workday:
            for bname in band_names:
                pools[bname]["unallocated"] = apply_psd2_extensions(
                    pools[bname]["unallocated"], cfg.psd2_extension_rate
                )
                pools[bname]["allocated"] = apply_psd2_extensions(
                    pools[bname]["allocated"], cfg.psd2_extension_rate
                )

        # --- Intake (before transitions so new cases land in correct band) ---
        if workday:
            for case_type, proportion in INTAKE_PROPORTIONS.items():
                for reg_age, count in intake_distribution(cfg.daily_intake * proportion):
                    cal_age, biz_age = make_age(reg_age, case_type)
                    new_cohort = Cohort(
                        count=count,
                        case_type=case_type,
                        cal_age=cal_age,
                        biz_age=biz_age,
                        effort_per_case=0.0,
                        is_src=False,
                        arrival_day=day,
                        allocation_day=None,
                        seeded=False,
                        last_worked_day=None,
                    )
                    bname = assign_band(new_cohort, bands)
                    pools[bname]["unallocated"].append(new_cohort)

        # --- Band transitions (after aging, so ages are current) ---
        # Collect all movers first, then reassign after the scan to avoid
        # appending into pools that are still being iterated.
        pending_unalloc: list[Cohort] = []   # movers from unallocated queues
        pending_alloc: list[Cohort] = []     # movers from allocated diaries

        for bname in band_names:
            stay_u, move_u = detect_transitions(
                pools[bname]["unallocated"], bname, bands
            )
            pools[bname]["unallocated"] = stay_u
            pending_unalloc.extend(move_u)

            # Allocated: check band, collect movers (preserve allocation state)
            stay_a: list[Cohort] = []
            for c in pools[bname]["allocated"]:
                if assign_band(c, bands) == bname:
                    stay_a.append(c)
                else:
                    pending_alloc.append(c)
            pools[bname]["allocated"] = stay_a

        # Now reassign all collected movers
        for c in pending_unalloc:
            new_band = assign_band(c, bands)
            pools[new_band]["unallocated"].append(c)
        for c in pending_alloc:
            new_band = assign_band(c, bands)
            pools[new_band]["allocated"].append(c)

        # --- Per-band allocation + work ---
        allocations_total = 0.0
        weighted_delay_total = 0.0
        allocations_by_type: dict[str, float] = defaultdict(float)
        closures_total = 0.0
        closures_by_type: dict[str, float] = defaultdict(float)
        close_sums_total = {
            ct: {"n": 0.0, "reg": 0.0, "cal": 0.0, "sys": 0.0}
            for ct in ["FCA", "PSD2_15", "PSD2_35"]
        }
        breached_closures_total: dict[str, float] = defaultdict(float)
        occupancy_before_work: list[float] = []

        if workday:
            for bname in band_names:
                ba = band_alloc_map[bname]
                if ba.fte == 0:
                    continue

                bcfg = band_cfgs[bname]
                b_max_slots = band_max_slots[bname]
                b_productive = band_productive[bname]

                # Parkinson's Law per band
                band_unalloc_count = sum(
                    c.count for c in pools[bname]["unallocated"]
                )
                full_pace_q = max(1.0, b_max_slots * 0.5)
                pressure = min(band_unalloc_count / full_pace_q, 1.0)
                eff_util = (
                    cfg.parkinson_floor
                    + (cfg.utilisation - cfg.parkinson_floor) * pressure
                )
                productive_hours = (
                    b_productive
                    * cfg.hours_per_day
                    * eff_util
                    * cfg.proficiency
                    * (1 - cfg.late_demand_rate)
                )
                b_slice_budget = (
                    productive_hours / cfg.slices_per_day
                    if cfg.slices_per_day > 0
                    else 0.0
                )

                band_src_alloc_today: dict[str, float] = defaultdict(float)
                band_src_closed_today: dict[str, float] = defaultdict(float)

                for _ in range(cfg.slices_per_day):
                    # Allocate
                    (
                        pools[bname]["unallocated"],
                        pools[bname]["allocated"],
                        sl_allocs,
                        sl_delay,
                        sl_abt,
                    ) = allocate_up_to_capacity(
                        pools[bname]["unallocated"],
                        pools[bname]["allocated"],
                        b_max_slots,
                        day,
                        band_src_alloc_today,
                        bcfg,
                    )
                    allocations_total += sl_allocs
                    weighted_delay_total += sl_delay
                    for ct, cnt in sl_abt.items():
                        allocations_by_type[ct] += cnt

                    occupancy_before_work.append(
                        sum(c.count for c in pools[bname]["allocated"])
                    )

                    # Work
                    (
                        pools[bname]["allocated"],
                        sl_closures,
                        sl_cbt,
                        sl_cs,
                        sl_bcbt,
                    ) = process_work_slice(
                        pools[bname]["allocated"],
                        b_slice_budget,
                        day,
                        workday_num,
                        band_src_alloc_today,
                        band_src_schedule[bname],
                        band_src_closed_today,
                        bcfg,
                    )
                    closures_total += sl_closures
                    for ct, cnt in sl_cbt.items():
                        closures_by_type[ct] += cnt
                    for ct in close_sums_total:
                        for key in close_sums_total[ct]:
                            close_sums_total[ct][key] += sl_cs[ct][key]
                    for ct, cnt in sl_bcbt.items():
                        breached_closures_total[ct] += cnt

                    pools[bname]["allocated"] = [
                        c for c in pools[bname]["allocated"] if c.count > 0.01
                    ]

                # End-of-day refill
                (
                    pools[bname]["unallocated"],
                    pools[bname]["allocated"],
                    sl_allocs,
                    sl_delay,
                    sl_abt,
                ) = allocate_up_to_capacity(
                    pools[bname]["unallocated"],
                    pools[bname]["allocated"],
                    b_max_slots,
                    day,
                    band_src_alloc_today,
                    bcfg,
                )
                allocations_total += sl_allocs
                weighted_delay_total += sl_delay
                for ct, cnt in sl_abt.items():
                    allocations_by_type[ct] += cnt

                band_src_schedule[bname][workday_num] = dict(band_src_alloc_today)

            workday_num += 1

        # --- Cleanup + merge ---
        for bname in band_names:
            pools[bname]["allocated"] = [
                c for c in pools[bname]["allocated"] if c.count > 0.01
            ]
            pools[bname]["unallocated"] = [
                c for c in pools[bname]["unallocated"] if c.count > 0.01
            ]
            if day % 14 == 0:
                pools[bname]["allocated"] = merge_cohorts(
                    pools[bname]["allocated"]
                )
                pools[bname]["unallocated"] = merge_cohorts(
                    pools[bname]["unallocated"]
                )

        # --- Aggregate metrics ---
        all_unalloc = []
        all_alloc = []
        for bname in band_names:
            all_unalloc.extend(pools[bname]["unallocated"])
            all_alloc.extend(pools[bname]["allocated"])

        all_open = all_unalloc + all_alloc
        total_wip = sum(c.count for c in all_open)
        total_unallocated = sum(c.count for c in all_unalloc)
        total_allocated = sum(c.count for c in all_alloc)

        open_by_type = count_by_type(all_open)
        breaches_by_type = count_breaches(all_open)
        over_target_by_type = count_over_target(all_open)
        age_bands_metric, age_bands_by_type = count_age_bands(all_open)

        instantaneous_fte_demand = calculate_instantaneous_fte_demand(
            all_unalloc, all_alloc, day, cfg,
        )
        avg_allocation_delay = (
            weighted_delay_total / allocations_total
            if allocations_total > 0
            else 0.0
        )

        all_slots = sum(band_max_slots[bn] for bn in band_names)
        occupancy_start = (
            occupancy_before_work[0] if occupancy_before_work else total_allocated
        )
        occupancy_avg = (
            mean(occupancy_before_work) if occupancy_before_work else total_allocated
        )
        occupancy_end = total_allocated

        max_unallocated_wait = max(
            (day - c.arrival_day for c in all_unalloc),
            default=0,
        )
        max_diary_untouched = max(
            (
                day - c.last_worked_day
                for c in all_alloc
                if c.last_worked_day is not None
            ),
            default=0,
        )
        alloc_with_lwd = [c for c in all_alloc if c.last_worked_day is not None]
        total_alloc_lwd = sum(c.count for c in alloc_with_lwd)
        avg_diary_untouched = (
            sum(
                (day - c.last_worked_day) * c.count for c in alloc_with_lwd
            )
            / total_alloc_lwd
            if total_alloc_lwd > 0.01
            else 0.0
        )

        # --- Harm (steady state only) ---
        daily_harm = 0.0
        if day >= steady_state_start:
            daily_harm = accumulate_daily_harm(
                all_open,
                day,
                optim_cfg.harm_breach_weight,
                optim_cfg.harm_neglect_weight,
                optim_cfg.harm_wip_weight,
            )
            cumulative_harm += daily_harm

        # Effective utilisation (weighted across active bands)
        effective_util = cfg.parkinson_floor  # fallback for non-workdays
        if workday:
            total_prod = sum(
                band_productive[bn]
                for bn in band_names
                if band_alloc_map[bn].fte > 0
            )
            if total_prod > 0:
                weighted_util = 0.0
                for bname in band_names:
                    if band_alloc_map[bname].fte == 0:
                        continue
                    bu = sum(c.count for c in pools[bname]["unallocated"])
                    fpq = max(1.0, band_max_slots[bname] * 0.5)
                    pr = min(bu / fpq, 1.0)
                    eu = (
                        cfg.parkinson_floor
                        + (cfg.utilisation - cfg.parkinson_floor) * pr
                    )
                    weighted_util += eu * band_productive[bname]
                effective_util = weighted_util / total_prod

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
                "age_bands": age_bands_metric,
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
                "desired_wip": all_slots + cfg.unallocated_buffer,
                "occupancy_start": occupancy_start,
                "occupancy_avg": occupancy_avg,
                "occupancy_end": occupancy_end,
                "slot_capacity": all_slots,
                "max_unallocated_wait": max_unallocated_wait,
                "max_diary_untouched": max_diary_untouched,
                "avg_diary_untouched": avg_diary_untouched,
                "harm": daily_harm,
                "cumulative_harm": cumulative_harm,
            }
        )

        if total_wip > max_wip:
            break

    return results
