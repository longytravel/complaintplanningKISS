"""
Scenario runner for allocation/work strategy comparison.

Runs all 36 strategy combinations (6 allocation x 6 work) and prints
a ranked comparison table. Each scenario runs in a subprocess to avoid
memory accumulation crashes on Windows.

Usage:
    python run_scenarios.py                     # default sort by WIP
    python run_scenarios.py --sort-by fca_stock  # sort by FCA breach %
    python run_scenarios.py --skip-regression    # skip baseline check
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

from complaints_model.config import SimConfig

_DEFAULT_CFG = SimConfig()
DEFAULT_FTE = _DEFAULT_CFG.fte
DAILY_INTAKE = _DEFAULT_CFG.daily_intake


ALLOCATION_STRATEGIES = [
    "nearest_deadline", "nearest_target", "youngest_first",
    "oldest_first", "psd2_priority", "longest_wait",
]
WORK_STRATEGIES = [
    "nearest_deadline", "nearest_target", "youngest_first",
    "oldest_first", "lowest_effort", "longest_untouched",
]

SORT_CHOICES = [
    "wip", "fca_stock", "psd2_stock", "fca_flow", "psd2_flow",
    "fca_close_age", "psd2_close_age", "max_unalloc_wait",
    "max_diary_untouched", "util",
]

# Script executed in subprocess for each scenario
_WORKER_SCRIPT = r'''
import json, sys
from statistics import mean
from complaints_model import SimConfig, simulate
from complaints_model.metrics import average_breach_rates, average_flow_breach_rates

alloc, work, fte = sys.argv[1], sys.argv[2], int(sys.argv[3])
cfg = SimConfig(fte=fte, allocation_strategy=alloc, work_strategy=work)
result = simulate(cfg)

n = min(30, len(result))
last30 = result[-n:]
last30_work = [r for r in last30 if r["workday"]]

final_wip = result[-1]["wip"]
circuit_broke = not result[-1].get("breaches_by_type") and final_wip > 10000

if circuit_broke:
    fca_stock = psd2_stock = fca_flow = psd2_flow = 1.0
else:
    _t, fca_stock, psd2_stock = average_breach_rates(result, last_days=n)
    _tf, fca_flow, psd2_flow = average_flow_breach_rates(result, last_days=n)

fca_n = sum(r["close_sums"]["FCA"]["n"] for r in last30_work)
fca_age = sum(r["close_sums"]["FCA"]["reg"] for r in last30_work) / fca_n if fca_n > 0.01 else 0.0
psd_n = sum(r["close_sums"]["PSD2_15"]["n"] + r["close_sums"]["PSD2_35"]["n"] for r in last30_work)
psd_age = (sum(r["close_sums"]["PSD2_15"]["reg"] + r["close_sums"]["PSD2_35"]["reg"] for r in last30_work) / psd_n) if psd_n > 0.01 else 0.0

print(json.dumps({
    "wip": mean(r["wip"] for r in last30),
    "fca_stock": fca_stock * 100,
    "psd2_stock": psd2_stock * 100,
    "fca_flow": fca_flow * 100,
    "psd2_flow": psd2_flow * 100,
    "fca_close_age": fca_age,
    "psd2_close_age": psd_age,
    "max_unalloc_wait": mean(r["max_unallocated_wait"] for r in last30),
    "max_diary_untouched": mean(r["max_diary_untouched"] for r in last30),
    "util": mean(r["effective_util"] for r in last30) * 100,
}))
'''


def run_scenario(alloc: str, work: str, fte: int, retries: int = 4) -> tuple[dict | None, str]:
    """Run a single scenario in a subprocess with retries for transient crashes."""
    for attempt in range(1 + retries):
        try:
            proc = subprocess.run(
                [sys.executable, "-c", _WORKER_SCRIPT, alloc, work, str(fte)],
                capture_output=True, text=True, timeout=300,
            )
        except subprocess.TimeoutExpired:
            return None, "TIMEOUT (300s)"
        if proc.returncode == 0:
            return json.loads(proc.stdout.strip()), ""
        # Transient crash — retry
        if attempt < retries:
            continue
        err = proc.stderr.strip().split("\n")[-1] if proc.stderr else f"exit {proc.returncode}"
        return None, err


def run_regression() -> bool:
    """Verify default config simulation produces known baseline values."""
    from complaints_model import SimConfig, simulate
    from complaints_model.metrics import average_breach_rates

    print("Regression check: complaints_model with default config")

    t0 = time.time()
    cfg = SimConfig()
    result = simulate(cfg)
    t1 = time.time()

    b_wip = result[-1]["wip"]
    expected_wip = 1031.6704226651175
    pct = abs(b_wip - expected_wip) / max(expected_wip, 1.0) * 100

    print(f"  complaints_model: {t1 - t0:.1f}s  final WIP = {b_wip:.1f}")
    print(f"  Expected WIP: {expected_wip:.1f}")

    if pct < 0.5:
        print(f"  PASSED (WIP diff = {pct:.6f}%)")
        return True
    else:
        print(f"  FAILED (WIP diff = {pct:.2f}%)")
        return False


def print_table(scenarios: list[dict], sort_key: str, fte: int) -> None:
    """Print the ranked comparison table."""
    reverse = sort_key == "util"
    scenarios.sort(key=lambda s: s[sort_key], reverse=reverse)

    w = 140
    print()
    print(f"SCENARIO COMPARISON ({fte} FTE, {DAILY_INTAKE} intake/day)")
    print("=" * w)
    print(
        f"{'Rank':>4}  {'Alloc Strategy':>17}  {'Work Strategy':>17}  "
        f"{'WIP':>7}  {'sFCA%':>6}  {'sPSD%':>6}  "
        f"{'fFCA%':>6}  {'fPSD%':>6}  "
        f"{'FCAAge':>6}  {'PSDAge':>6}  "
        f"{'MaxWait':>7}  {'MaxNegl':>7}  {'Util':>5}"
    )
    print("-" * w)
    for rank, s in enumerate(scenarios, 1):
        print(
            f"{rank:>4}  {s['alloc']:>17}  {s['work']:>17}  "
            f"{s['wip']:>7.0f}  {s['fca_stock']:>5.1f}%  {s['psd2_stock']:>5.1f}%  "
            f"{s['fca_flow']:>5.1f}%  {s['psd2_flow']:>5.1f}%  "
            f"{s['fca_close_age']:>5.1f}d  {s['psd2_close_age']:>5.1f}d  "
            f"{s['max_unalloc_wait']:>5.1f}d  {s['max_diary_untouched']:>5.1f}d  "
            f"{s['util']:>4.0f}%"
        )
    print("=" * w)

    direction = "descending" if reverse else "ascending"
    label = sort_key.replace("_", " ")
    print(f"\nSorted by: {label} ({direction}). Use --sort-by <column> to change.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare allocation/work strategy scenarios"
    )
    parser.add_argument(
        "--sort-by", default="wip", choices=SORT_CHOICES,
        help="KPI to sort by (default: wip)",
    )
    parser.add_argument(
        "--fte", type=int, default=DEFAULT_FTE,
        help=f"FTE level to simulate (default: {DEFAULT_FTE})",
    )
    parser.add_argument(
        "--skip-regression", action="store_true",
        help="Skip regression check against prove_maths baseline",
    )
    args = parser.parse_args()

    fte = args.fte

    # ── Regression check ────────────────────────────────────────────
    if not args.skip_regression:
        if not run_regression():
            print("\nAborting: regression failed.")
            sys.exit(1)
        print()

    # ── Run all 36 scenarios (each in subprocess) ───────────────────
    total = len(ALLOCATION_STRATEGIES) * len(WORK_STRATEGIES)
    print(f"Running {total} scenarios ({fte} FTE, {DAILY_INTAKE} intake/day)...")
    print(f"Each scenario runs in a subprocess for memory isolation.")
    print()

    scenarios: list[dict] = []
    failures: list[tuple[str, str]] = []
    t_start = time.time()

    for i, alloc in enumerate(ALLOCATION_STRATEGIES):
        for j, work in enumerate(WORK_STRATEGIES):
            n = i * len(WORK_STRATEGIES) + j + 1
            print(
                f"  [{n:>2}/{total}] {alloc:>17} / {work:<17}",
                end="", flush=True,
            )

            t0 = time.time()
            kpis, err = run_scenario(alloc, work, fte)
            elapsed = time.time() - t0

            if kpis is None:
                print(f"  {elapsed:>4.1f}s  FAILED: {err}")
                failures.append((alloc, work))
                continue

            kpis["alloc"] = alloc
            kpis["work"] = work
            scenarios.append(kpis)

            print(
                f"  {elapsed:>4.1f}s  "
                f"WIP={kpis['wip']:>7.0f}  "
                f"sFCA={kpis['fca_stock']:>5.1f}%  "
                f"sPSD={kpis['psd2_stock']:>5.1f}%"
            )

    t_total = time.time() - t_start
    print(f"\n{len(scenarios)}/{total} scenarios completed in {t_total:.0f}s")

    if failures:
        print(f"\nFailed scenarios:")
        for alloc, work in failures:
            print(f"  {alloc} / {work}")

    # ── Print ranked table ──────────────────────────────────────────
    if scenarios:
        print_table(scenarios, args.sort_by, fte)


if __name__ == "__main__":
    main()
