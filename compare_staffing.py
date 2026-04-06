"""
Side-by-side comparison: understaffed vs overstaffed.

Runs the model for 1 year (365 days) at two FTE levels (configured
via UNDER_FTE / OVER_FTE below). Every metric is printed side-by-side
so we can verify the model behaves correctly — an understaffed system
should show growing WIP, rising breach rates, longer close times, and
higher utilisation. An overstaffed system should show stable/falling
WIP, zero breaches, shorter close times, and Parkinson's Law absorbing
the overcapacity.
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from complaints_model import SimConfig, simulate
from complaints_model.metrics import (
    last_n_workdays, average_breach_rates, average_flow_breach_rates,
    is_stable, summarise_closure_metrics,
)
from complaints_model.regulatory import BREACH_TARGETS
from statistics import mean

cfg = SimConfig(days=365)

UNDER_FTE = 105
OVER_FTE = 125

print("=" * 100)
print(f"STAFFING COMPARISON — 1 YEAR (365 days)")
print(f"Understaffed: {UNDER_FTE} FTE  |  Overstaffed: {OVER_FTE} FTE")
print(f"Daily intake: {cfg.daily_intake}  |  Shrinkage: {cfg.shrinkage:.0%}  |  Min stable: ~119 FTE")
print("=" * 100)

# Run both simulations
print("\nRunning simulations...")
result_under = simulate(SimConfig(fte=UNDER_FTE, days=365))
result_over = simulate(SimConfig(fte=OVER_FTE, days=365))
print("Done.\n")


def section(title: str) -> None:
    print(f"\n{'─' * 100}")
    print(f"  {title}")
    print(f"{'─' * 100}")


def row(label: str, val_under, val_over, fmt: str = ".1f", unit: str = "", warn_if=None) -> None:
    """Print a comparison row. warn_if: 'higher' or 'lower' flags the understaffed value."""
    if isinstance(val_under, float):
        s_u = f"{val_under:{fmt}}{unit}"
        s_o = f"{val_over:{fmt}}{unit}"
    else:
        s_u = str(val_under)
        s_o = str(val_over)

    flag = ""
    if warn_if and isinstance(val_under, (int, float)) and isinstance(val_over, (int, float)):
        if warn_if == "higher" and val_under > val_over * 1.05:
            flag = " ⚠"
        elif warn_if == "lower" and val_under < val_over * 0.95:
            flag = " ⚠"

    print(f"  {label:<45} {s_u:>20}  {s_o:>20}{flag}")


def header() -> None:
    print(f"  {'Metric':<45} {'UNDERSTAFFED':>20}  {'OVERSTAFFED':>20}")
    print(f"  {'':─<45} {'':─>20}  {'':─>20}")


# ── Capacity parameters ──
section("CAPACITY PARAMETERS")
header()
on_desk_prod_u = UNDER_FTE * (1 - cfg.shrinkage)
on_desk_prod_o = OVER_FTE * (1 - cfg.shrinkage)
on_desk_pres_u = UNDER_FTE * (1 - cfg.absence_shrinkage)
on_desk_pres_o = OVER_FTE * (1 - cfg.absence_shrinkage)
row("Headcount FTE", UNDER_FTE, OVER_FTE, "d")
row("On-desk productive (after shrinkage)", on_desk_prod_u, on_desk_prod_o, ".1f")
row("On-desk present (after absence)", on_desk_pres_u, on_desk_pres_o, ".1f")
row("Diary slots (present × limit)", on_desk_pres_u * cfg.diary_limit, on_desk_pres_o * cfg.diary_limit, ".1f")
row("Max productive hrs/day", on_desk_prod_u * cfg.hours_per_day, on_desk_prod_o * cfg.hours_per_day, ".1f", " hrs")
row("Theoretical cases/day (max hrs ÷ base effort)",
    on_desk_prod_u * cfg.hours_per_day / cfg.base_effort,
    on_desk_prod_o * cfg.hours_per_day / cfg.base_effort, ".1f")

# ── End-state snapshot ──
section("END-STATE SNAPSHOT (Day 365)")
header()
fu = result_under[-1]
fo = result_over[-1]
row("Total WIP", fu["wip"], fo["wip"], ".0f", warn_if="higher")
row("Unallocated", fu["unalloc"], fo["unalloc"], ".0f", warn_if="higher")
row("Allocated (in diaries)", fu["alloc"], fo["alloc"], ".0f")
row("Desired WIP (slots + buffer)", fu["desired_wip"], fo["desired_wip"], ".0f")
row("Slot capacity", fu["slot_capacity"], fo["slot_capacity"], ".0f")
row("Diary occupancy %", fu["alloc"] / fu["slot_capacity"] * 100, fo["alloc"] / fo["slot_capacity"] * 100, ".1f", "%")
row("Effective utilisation", fu["effective_util"] * 100, fo["effective_util"] * 100, ".1f", "%", warn_if="higher")
row("FTE demand (instantaneous)", fu["demand_fte"], fo["demand_fte"], ".1f", warn_if="higher")

# ── WIP by type ──
section("WIP BY CASE TYPE (Day 365)")
header()
for ct in ["FCA", "PSD2_15", "PSD2_35"]:
    row(f"  {ct} open", fu["open_by_type"].get(ct, 0), fo["open_by_type"].get(ct, 0), ".0f")
    row(f"  {ct} breached (stock)", fu["breaches_by_type"].get(ct, 0), fo["breaches_by_type"].get(ct, 0), ".0f", warn_if="higher")
    row(f"  {ct} over target", fu["over_target_by_type"].get(ct, 0), fo["over_target_by_type"].get(ct, 0), ".0f", warn_if="higher")

# ── Age profile ──
section("AGE PROFILE (Day 365)")
header()
for label in ["0-3", "4-15", "16-35", "36-56", "57+"]:
    row(f"  Band {label}", fu["age_bands"].get(label, 0), fo["age_bands"].get(label, 0), ".0f")

# ── Steady-state metrics (last 60 workdays) ──
section("STEADY-STATE METRICS (last 60 workdays)")
header()

last60u = last_n_workdays(result_under, 60)
last60o = last_n_workdays(result_over, 60)

row("Avg daily closures", mean(r["closures"] for r in last60u), mean(r["closures"] for r in last60o), ".1f")
row("Avg daily allocations", mean(r["allocations"] for r in last60u), mean(r["allocations"] for r in last60o), ".1f")
row("Avg allocation delay (days)", mean(r["avg_allocation_delay"] for r in last60u), mean(r["avg_allocation_delay"] for r in last60o), ".1f", warn_if="higher")
row("Avg effective utilisation %",
    mean(r["effective_util"] for r in last60u) * 100,
    mean(r["effective_util"] for r in last60o) * 100, ".1f", "%")
row("Avg diary occupancy (start)",
    mean(r["occupancy_start"] for r in last60u),
    mean(r["occupancy_start"] for r in last60o), ".0f")
row("Avg diary occupancy (end)",
    mean(r["occupancy_end"] for r in last60u),
    mean(r["occupancy_end"] for r in last60o), ".0f")

# Closure metrics by type
for ct in ["FCA", "PSD2_15", "PSD2_35"]:
    avg_close_u, avg_reg_u, avg_cal_u, avg_sys_u = summarise_closure_metrics(last60u, ct)
    avg_close_o, avg_reg_o, avg_cal_o, avg_sys_o = summarise_closure_metrics(last60o, ct)
    row(f"  {ct} closures/day", avg_close_u, avg_close_o, ".1f")
    row(f"  {ct} avg reg age at close", avg_reg_u, avg_reg_o, ".1f", " days", warn_if="higher")
    row(f"  {ct} avg cal age at close", avg_cal_u, avg_cal_o, ".1f", " days")
    row(f"  {ct} avg system time", avg_sys_u, avg_sys_o, ".1f", " days")

# ── Breach rates ──
section("BREACH RATES (last 30 days)")
header()

stock_total_u, stock_fca_u, stock_psd2_u = average_breach_rates(result_under, 30)
stock_total_o, stock_fca_o, stock_psd2_o = average_breach_rates(result_over, 30)
flow_total_u, flow_fca_u, flow_psd2_u = average_flow_breach_rates(result_under, 30)
flow_total_o, flow_fca_o, flow_psd2_o = average_flow_breach_rates(result_over, 30)

row("Stock breach rate (total)", stock_total_u * 100, stock_total_o * 100, ".2f", "%", warn_if="higher")
row("Stock breach rate (FCA)", stock_fca_u * 100, stock_fca_o * 100, ".2f", "%", warn_if="higher")
row("Stock breach rate (PSD2)", stock_psd2_u * 100, stock_psd2_o * 100, ".2f", "%", warn_if="higher")
row("Flow breach rate (total)", flow_total_u * 100, flow_total_o * 100, ".2f", "%", warn_if="higher")
row("Flow breach rate (FCA)", flow_fca_u * 100, flow_fca_o * 100, ".2f", "%", warn_if="higher")
row("Flow breach rate (PSD2)", flow_psd2_u * 100, flow_psd2_o * 100, ".2f", "%", warn_if="higher")

row("FCA breach target", BREACH_TARGETS["FCA"] * 100, BREACH_TARGETS["FCA"] * 100, ".0f", "%")
row("PSD2 breach target", BREACH_TARGETS["PSD2"] * 100, BREACH_TARGETS["PSD2"] * 100, ".0f", "%")

# ── Stability ──
section("STABILITY CHECK")
header()
stable_u = is_stable(result_under)
stable_o = is_stable(result_over)
wip_delta_u = result_under[-1]["wip"] - result_under[-31]["wip"]
wip_delta_o = result_over[-1]["wip"] - result_over[-31]["wip"]
row("WIP change (last 30 days)", wip_delta_u, wip_delta_o, ".0f", warn_if="higher")
row("Stable?", "YES" if stable_u else "NO", "YES" if stable_o else "NO")

# ── WIP trajectory (every 30 days) ──
section("WIP TRAJECTORY (every 30 days)")
print(f"  {'Day':<10} {'Under WIP':>12} {'Under Unall':>12} {'Under Util%':>12}  |  {'Over WIP':>12} {'Over Unall':>12} {'Over Util%':>12}")
print(f"  {'':─<10} {'':─>12} {'':─>12} {'':─>12}  |  {'':─>12} {'':─>12} {'':─>12}")
for d in range(29, 365, 30):
    ru = result_under[d]
    ro = result_over[d]
    print(f"  {d+1:<10d} {ru['wip']:>12.0f} {ru['unalloc']:>12.0f} {ru['effective_util']*100:>11.1f}%  |  {ro['wip']:>12.0f} {ro['unalloc']:>12.0f} {ro['effective_util']*100:>11.1f}%")

# ── Closures trajectory (every 30 days, workday averages) ──
section("CLOSURES TRAJECTORY (30-day workday averages)")
print(f"  {'Period':<12} {'Under Close':>12} {'Under Delay':>12} {'Under Occ%':>12}  |  {'Over Close':>12} {'Over Delay':>12} {'Over Occ%':>12}")
print(f"  {'':─<12} {'':─>12} {'':─>12} {'':─>12}  |  {'':─>12} {'':─>12} {'':─>12}")
for end_day in range(59, 365, 30):
    start_day = max(0, end_day - 29)
    chunk_u = [r for r in result_under[start_day:end_day+1] if r["workday"]]
    chunk_o = [r for r in result_over[start_day:end_day+1] if r["workday"]]
    if not chunk_u or not chunk_o:
        continue
    label = f"d{start_day+1}-{end_day+1}"
    avg_close_u = mean(r["closures"] for r in chunk_u)
    avg_close_o = mean(r["closures"] for r in chunk_o)
    avg_delay_u = mean(r["avg_allocation_delay"] for r in chunk_u)
    avg_delay_o = mean(r["avg_allocation_delay"] for r in chunk_o)
    avg_occ_u = mean(r["occupancy_end"] / r["slot_capacity"] * 100 for r in chunk_u)
    avg_occ_o = mean(r["occupancy_end"] / r["slot_capacity"] * 100 for r in chunk_o)
    print(f"  {label:<12} {avg_close_u:>12.1f} {avg_delay_u:>12.1f} {avg_occ_u:>11.1f}%  |  {avg_close_o:>12.1f} {avg_delay_o:>12.1f} {avg_occ_o:>11.1f}%")

# ── Summary verdict ──
section("VERDICT")
print()
if not stable_u and stable_o:
    print("  ✓ CORRECT: Understaffed system is unstable, overstaffed is stable.")
elif stable_u and stable_o:
    print("  ⚠ BOTH STABLE — understaffed FTE may not be low enough to show divergence.")
elif not stable_u and not stable_o:
    print("  ⚠ BOTH UNSTABLE — overstaffed FTE may not be high enough.")
else:
    print("  ✗ UNEXPECTED: Understaffed is stable but overstaffed is not!")

# Check expected behaviours
checks = []
if fu["wip"] > fo["wip"]:
    checks.append(("WIP higher when understaffed", True))
else:
    checks.append(("WIP higher when understaffed", False))

if fu["unalloc"] > fo["unalloc"]:
    checks.append(("Unallocated higher when understaffed", True))
else:
    checks.append(("Unallocated higher when understaffed", False))

if fu["effective_util"] >= fo["effective_util"]:
    checks.append(("Utilisation higher when understaffed", True))
else:
    checks.append(("Utilisation higher when understaffed", False))

avg_delay_u_60 = mean(r["avg_allocation_delay"] for r in last60u)
avg_delay_o_60 = mean(r["avg_allocation_delay"] for r in last60o)
if avg_delay_u_60 > avg_delay_o_60:
    checks.append(("Allocation delay higher when understaffed", True))
else:
    checks.append(("Allocation delay higher when understaffed", False))

if stock_total_u >= stock_total_o:
    checks.append(("Breach rate higher when understaffed", True))
else:
    checks.append(("Breach rate higher when understaffed", False))

if wip_delta_u > wip_delta_o:
    checks.append(("WIP growing faster when understaffed", True))
else:
    checks.append(("WIP growing faster when understaffed", False))

print()
all_pass = True
for label, passed in checks:
    icon = "✓" if passed else "✗"
    if not passed:
        all_pass = False
    print(f"  {icon} {label}")

print()
if all_pass:
    print("  ═══ ALL SANITY CHECKS PASSED — model behaves correctly ═══")
else:
    print("  ═══ SOME CHECKS FAILED — investigate above ═══")
print()
