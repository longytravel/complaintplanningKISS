"""CLI output formatting — print_stable_pack, print_fte_sweep, main."""
from __future__ import annotations

from statistics import mean

from .config import SimConfig
from .simulation import simulate
from .effort import AGE_BANDS
from .metrics import (
    last_n_days, last_n_workdays,
    average_breach_rates, average_flow_breach_rates,
    is_stable, summarise_closure_metrics,
)


def print_stable_pack(cfg: SimConfig, result: list[dict]) -> None:
    on_desk_productive = cfg.fte * (1 - cfg.shrinkage)
    on_desk_present = cfg.fte * (1 - cfg.absence_shrinkage)
    final = result[-1]
    last30 = last_n_days(result, 30)
    last60_workdays = last_n_workdays(result, 60)
    total_rate, fca_rate, psd2_rate = average_breach_rates(result, last_days=30)
    flow_total, flow_fca, flow_psd2 = average_flow_breach_rates(result, last_days=30)
    clear_day = next((row["day"] + 1 for row in result if row["wip"] < 0.5), None)

    target_wip = on_desk_present * cfg.diary_limit + cfg.unallocated_buffer
    print("=" * 96)
    print(f"FULL 365 DAY RUN - {cfg.fte} FTE (ROLLING DIARY REFILL + PARKINSON'S LAW)")
    print("=" * 96)
    print(
        f"Present FTE: {on_desk_present:.1f}, diary slots: {on_desk_present * cfg.diary_limit:.0f}, "
        f"productive FTE: {on_desk_productive:.1f}, "
        f"max hours/day: {on_desk_productive * cfg.hours_per_day * cfg.utilisation * cfg.proficiency:.1f}"
    )
    print(
        f"Parkinson's Law: desired WIP = {final['desired_wip']:.0f} (diary {on_desk_present * cfg.diary_limit:.0f} + buffer {cfg.unallocated_buffer}), "
        f"util floor = {cfg.parkinson_floor:.0%}, min diary days = {cfg.min_diary_days}"
    )
    print(f"Effective util at end: {final['effective_util']:.1%}")
    print(f"Full-pace queue (auto): {cfg.parkinson_full_pace_queue}")

    print("\nStability")
    for d in [30, 90, 180, 365, cfg.days]:
        if d <= len(result):
            print(f"  Day {d:>4} WIP: {result[min(d-1, len(result)-1)]['wip']:>8,.0f}")
    print(f"  WIP change, last 30 days: {final['wip'] - result[-31]['wip']:+,.0f}")
    print(
        f"  Avg closures/workday, last 60 days: "
        f"{mean(row['closures'] for row in last60_workdays):.1f}"
    )
    print(
        f"  Avg allocations/workday, last 60 days: "
        f"{mean(row['allocations'] for row in last60_workdays):.1f}"
    )
    print(
        f"  Diaries start/avg/end, last 60 days: "
        f"{mean(row['occupancy_start'] for row in last60_workdays):.1f} / "
        f"{mean(row['occupancy_avg'] for row in last60_workdays):.1f} / "
        f"{mean(row['occupancy_end'] for row in last60_workdays):.1f}"
    )
    print(
        f"  Fill ratio start/avg/end, last 60 days: "
        f"{mean(row['occupancy_start'] / row['slot_capacity'] for row in last60_workdays) * 100:.1f}% / "
        f"{mean(row['occupancy_avg'] / row['slot_capacity'] for row in last60_workdays) * 100:.1f}% / "
        f"{mean(row['occupancy_end'] / row['slot_capacity'] for row in last60_workdays) * 100:.1f}%"
    )
    print(f"  Backlog fully clears by day: {clear_day}")

    print("\nOpen stock at day 365")
    for case_type in ["FCA", "PSD2_15", "PSD2_35"]:
        print(f"  {case_type:>7}: {final['open_by_type'].get(case_type, 0.0):>8.0f}")
    print(f"  Total:   {final['wip']:>8.0f}")

    print("\nBreaches at day 365")
    psd2_breach = final["breaches_by_type"].get("PSD2_15", 0.0) + final["breaches_by_type"].get("PSD2_35", 0.0)
    print(f"  FCA breached open:   {final['breaches_by_type'].get('FCA', 0.0):.0f}")
    print(f"  PSD2 breached open:  {psd2_breach:.0f}")
    print(f"  Total breached open: {sum(final['breaches_by_type'].values()):.0f}")
    print(f"  Stock breach rate (open breached / open WIP), avg last 30 days:")
    print(f"    FCA:  {fca_rate * 100:.2f}%  |  PSD2: {psd2_rate * 100:.2f}%  |  Total: {total_rate * 100:.2f}%")
    print(f"  Flow breach rate (breached closures / total closures), last 30 days:")
    print(f"    FCA:  {flow_fca * 100:.2f}%  |  PSD2: {flow_psd2 * 100:.2f}%  |  Total: {flow_total * 100:.2f}%")

    print("\nOver internal service target at day 365")
    for case_type in ["FCA", "PSD2_15", "PSD2_35"]:
        open_count = final["open_by_type"].get(case_type, 0.0)
        over_target = final["over_target_by_type"].get(case_type, 0.0)
        pct = (over_target / open_count * 100.0) if open_count > 0 else 0.0
        print(f"  {case_type:>7}: {over_target:>8.0f} ({pct:>5.1f}%)")

    print("\nAge profile at day 365 on regulatory clock")
    for label, _, _ in AGE_BANDS:
        count = final["age_bands"][label]
        share = (count / max(final["wip"], 1.0)) * 100.0
        print(f"  {label:>5}: {count:>8.0f} ({share:>5.1f}%)")

    print("\nAge profile by type at day 365")
    for case_type in ["FCA", "PSD2_15", "PSD2_35"]:
        print(f"  {case_type}")
        open_count = max(final["open_by_type"].get(case_type, 0.0), 1.0)
        for label, _, _ in AGE_BANDS:
            count = final["age_bands_by_type"][case_type][label]
            if count > 0.5:
                print(f"    {label:>5}: {count:>8.0f} ({count / open_count * 100:>5.1f}%)")

    print("\nClosure metrics, last 60 workdays")
    for case_type in ["FCA", "PSD2_15", "PSD2_35"]:
        avg_close_day, avg_reg, avg_cal, avg_sys = summarise_closure_metrics(
            last60_workdays, case_type
        )
        if avg_close_day <= 0.01:
            continue
        print(
            f"  {case_type:>7}: closures/day {avg_close_day:>6.1f} | "
            f"avg reg age at close {avg_reg:>5.1f} | avg cal age {avg_cal:>5.1f} | "
            f"avg days in system {avg_sys:>5.1f}"
        )

    print("\nAllocation metrics, last 60 workdays")
    for case_type in ["FCA", "PSD2_15", "PSD2_35"]:
        avg_alloc = sum(
            row["allocations_by_type"].get(case_type, 0.0) for row in last60_workdays
        ) / len(last60_workdays)
        print(f"  {case_type:>7}: allocations/day {avg_alloc:>6.1f}")
    print(
        f"  Total avg allocation delay: "
        f"{mean(row['avg_allocation_delay'] for row in last60_workdays):.1f} days"
    )

    print("\nTrajectory snapshots")
    for day in [0, 30, 60, 90, 120, 180, 240, 300, 364]:
        if day >= len(result):
            continue
        row = result[day]
        psd2_open = row["open_by_type"].get("PSD2_15", 0.0) + row["open_by_type"].get("PSD2_35", 0.0)
        psd2_breach = row["breaches_by_type"].get("PSD2_15", 0.0) + row["breaches_by_type"].get("PSD2_35", 0.0)
        print(
            f"  Day {day + 1:>3}: WIP {row['wip']:>7.0f} | "
            f"Unalloc {row['unalloc']:>7.0f} | Alloc {row['alloc']:>6.0f} | "
            f"Util {row['effective_util']:>4.0%} | "
            f"FCA br {row['breaches_by_type'].get('FCA', 0.0):>6.0f} | "
            f"PSD2 br {psd2_breach:>6.0f}"
        )

    print("\n30-day blocks while the model settles")
    for start, end, name in [
        (0, 29, "Days 1-30"),
        (30, 59, "Days 31-60"),
        (60, 89, "Days 61-90"),
        (90, 119, "Days 91-120"),
        (120, 149, "Days 121-150"),
    ]:
        if start >= len(result):
            continue
        block = [row for row in result[start : end + 1] if row["workday"]]
        print(name)
        print(f"  Avg allocations/day: {mean(row['allocations'] for row in block):.1f}")
        print(f"  Avg closures/day:    {mean(row['closures'] for row in block):.1f}")
        print(
            f"  Avg start/avg/end fill: "
            f"{mean(row['occupancy_start'] for row in block):.1f} / "
            f"{mean(row['occupancy_avg'] for row in block):.1f} / "
            f"{mean(row['occupancy_end'] for row in block):.1f}"
        )
        print(
            f"  Avg alloc delay:     {mean(row['avg_allocation_delay'] for row in block):.1f} days"
        )
        for case_type in ["FCA", "PSD2_15", "PSD2_35"]:
            avg_close_day, avg_reg, avg_cal, avg_sys = summarise_closure_metrics(
                block, case_type
            )
            if avg_close_day <= 0.01:
                continue
            print(
                f"  {case_type:>7}: close/day {avg_close_day:>6.1f} | "
                f"avg reg age {avg_reg:>5.1f} | avg cal age {avg_cal:>5.1f} | "
                f"avg days in system {avg_sys:>5.1f}"
            )
        print()


def print_fte_sweep(rows: list[dict], cfg: SimConfig | None = None) -> None:
    days = cfg.days if cfg else 730
    floor = cfg.parkinson_floor if cfg else 0.70
    fpq = cfg.parkinson_full_pace_queue if cfg else 600
    print("=" * 120)
    print(f"FTE SWEEP - {days} DAYS, PARKINSON'S LAW (floor={floor:.0%}, FPQ={fpq})")
    print("=" * 120)
    print(
        f"{'FTE':>4} {'WIP':>7} {'dWIP30':>7} {'Unalloc':>8} {'Alloc':>6} {'Util':>6} "
        f"{'Close':>6} {'Delay':>6} {'FCA Age':>8} {'SysTime':>8} {'StockBr':>7} {'FlowBr':>7} {'Stable':>6}"
    )
    for row in rows:
        stable_flag = "YES" if row["stable"] else ""
        print(
            f"{row['fte']:>4} {row['final_wip']:>7.0f} {row['dwip30']:>+7.0f} "
            f"{row['final_unalloc']:>8.0f} {row['final_alloc']:>6.0f} {row['util']:>5.1%} "
            f"{row['close60']:>6.1f} {row['alloc_delay']:>5.1f}d "
            f"{row['fca_age']:>8.1f} {row['sys_time']:>8.1f} "
            f"{row['breach30']:>6.2f}% {row['flow_breach30']:>6.2f}% {stable_flag:>6}"
        )

    stable = [row for row in rows if row["stable"]]
    if stable:
        print(f"\nMinimum stable FTE: {stable[0]['fte']}")
    else:
        print("\nNo stable FTE found in the sweep range.")


def main() -> None:
    cfg = SimConfig()
    import gc

    sweep_rows = []
    detailed_result = None
    for fte in range(135, 155):
        test_cfg = SimConfig(fte=fte)
        result = simulate(test_cfg)
        last60_workdays = last_n_workdays(result, 60)
        total_rate, fca_rate, psd2_rate = average_breach_rates(result, last_days=30)
        flow_total, _flow_fca, _flow_psd2 = average_flow_breach_rates(result, last_days=30)
        on_desk_present = fte * (1 - cfg.absence_shrinkage)
        cn = sum(row["close_sums"]["FCA"]["n"] for row in last60_workdays)
        avg_fca_age = sum(row["close_sums"]["FCA"]["reg"] for row in last60_workdays) / cn if cn > 0.01 else 0
        avg_sys_time = sum(row["close_sums"]["FCA"]["sys"] for row in last60_workdays) / cn if cn > 0.01 else 0
        sweep_rows.append(
            {
                "fte": fte,
                "final_wip": result[-1]["wip"],
                "dwip30": result[-1]["wip"] - result[-31]["wip"],
                "final_unalloc": result[-1]["unalloc"],
                "final_alloc": result[-1]["alloc"],
                "util": result[-1]["effective_util"],
                "diary_slots": on_desk_present * cfg.diary_limit,
                "close60": mean(row["closures"] for row in last60_workdays),
                "alloc_delay": mean(row["avg_allocation_delay"] for row in last60_workdays),
                "fca_age": avg_fca_age,
                "sys_time": avg_sys_time,
                "breach30": total_rate * 100.0,
                "flow_breach30": flow_total * 100.0,
                "fca30": fca_rate * 100.0,
                "psd230": psd2_rate * 100.0,
                "stable": is_stable(result, test_cfg),
            }
        )
        if fte == cfg.fte:
            detailed_result = result
        else:
            del result
            gc.collect()

    print_fte_sweep(sweep_rows, cfg)
    if detailed_result is not None:
        print()
        print_stable_pack(cfg, detailed_result)


if __name__ == "__main__":
    main()
