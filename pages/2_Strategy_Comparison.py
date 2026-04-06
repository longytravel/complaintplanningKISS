"""Strategy Comparison Dashboard — Page 2

Reads system parameters from session_state (set by Page 1) and runs all 36
allocation × work strategy combinations. Displays heatmaps for screening and
drill-down time-series for selected combos.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
from collections import defaultdict
from statistics import mean

import prove_maths as pm
import strategy_model as sm

st.set_page_config(page_title="Strategy Comparison", layout="wide")
st.title("Strategy Comparison")

# ── Strategy lists (order matches design spec) ─────────────────────────────

ALLOC_STRATEGIES = [
    "nearest_deadline", "nearest_target", "youngest_first",
    "oldest_first", "psd2_priority", "longest_wait",
]
WORK_STRATEGIES = [
    "nearest_deadline", "nearest_target", "youngest_first",
    "oldest_first", "lowest_effort", "longest_untouched",
]

COMBO_COLORS = [
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
]

LAYOUT = dict(
    height=370,
    margin=dict(l=50, r=20, t=30, b=40),
    xaxis_title="Day",
    legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="left", x=0),
)


# ── Read params from session_state (Page 1) with module defaults ───────────

def get_param(name, default):
    return st.session_state.get(f"param_{name}", default)


fte = get_param("fte", 120)
shrinkage = get_param("shrinkage", 0.42)
absence_shrinkage = get_param("absence_shrinkage", 0.15)
hours_per_day = get_param("hours_per_day", 7.0)
utilisation = get_param("utilisation", 1.00)
proficiency = get_param("proficiency", 1.0)
daily_intake = get_param("daily_intake", 300)
base_effort = get_param("base_effort", 1.5)
diary_limit = get_param("diary_limit", 7)
min_diary_days = get_param("min_diary_days", 0)
handoff_overhead = get_param("handoff_overhead", 0.15)
handoff_effort_hours = get_param("handoff_effort_hours", 0.5)
late_demand_rate = get_param("late_demand_rate", 0.08)
parkinson_floor = get_param("parkinson_floor", 0.70)
parkinson_fpq = get_param("parkinson_fpq", 600)
unallocated_buffer = get_param("unallocated_buffer", 300)
src_window = get_param("src_window", 3)
src_effort_ratio = get_param("src_effort_ratio", 0.70)
src_boost_max = get_param("src_boost_max", 0.15)
src_boost_decay = get_param("src_boost_decay", 5)
psd2_extension_rate = get_param("psd2_extension_rate", 0.05)
slices_per_day = get_param("slices_per_day", 4)

ALL_PARAMS = (
    fte, shrinkage, absence_shrinkage, hours_per_day, utilisation,
    proficiency, daily_intake, base_effort, diary_limit, min_diary_days,
    handoff_overhead, handoff_effort_hours, late_demand_rate,
    parkinson_floor, parkinson_fpq, unallocated_buffer,
    src_window, src_effort_ratio, src_boost_max, src_boost_decay,
    psd2_extension_rate, slices_per_day,
)


# ═══════════════════════════════════════════════════════════════════════════
# Section 1: Parameter Summary
# ═══════════════════════════════════════════════════════════════════════════

st.markdown("##### Current System Parameters")
st.caption("These are set on the **System Dashboard** page. Navigate there to change them.")

p1, p2, p3, p4, p5, p6 = st.columns(6)
p1.metric("FTE", f"{fte}")
p2.metric("Daily Intake", f"{daily_intake}")
p3.metric("Shrinkage", f"{shrinkage:.0%}")
p4.metric("Base Effort", f"{base_effort}h")
p5.metric("Diary Limit", f"{diary_limit}")
p6.metric("Parkinson Floor", f"{parkinson_floor:.0%}")

st.divider()


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _set_model_params():
    """Push current params into both prove_maths and strategy_model modules."""
    for mod in (pm, sm):
        mod.SHRINKAGE = shrinkage
        mod.ABSENCE_SHRINKAGE = absence_shrinkage
        mod.HOURS_PER_DAY = hours_per_day
        mod.UTILISATION = utilisation
        mod.PROFICIENCY = proficiency
        mod.DAILY_INTAKE = daily_intake
        mod.BASE_EFFORT = base_effort
        mod.DIARY_LIMIT = diary_limit
        mod.MIN_DIARY_DAYS = min_diary_days
        mod.HANDOFF_OVERHEAD = handoff_overhead
        mod.HANDOFF_EFFORT_HOURS = handoff_effort_hours
        mod.LATE_DEMAND_RATE = late_demand_rate
        mod.PARKINSON_FLOOR = parkinson_floor
        mod.PARKINSON_FULL_PACE_QUEUE = parkinson_fpq
        mod.UNALLOCATED_BUFFER = unallocated_buffer
        mod.SRC_WINDOW = src_window
        mod.SRC_EFFORT_RATIO = src_effort_ratio
        mod.SRC_BOOST_MAX = src_boost_max
        mod.SRC_BOOST_DECAY_DAYS = src_boost_decay
        mod.PSD2_EXTENSION_RATE = psd2_extension_rate
        mod.SLICES_PER_DAY = slices_per_day
        mod.DAYS = 365


@st.cache_data(show_spinner=False)
def _run_single_combo(alloc_strategy, work_strategy, params_tuple):
    """Run one strategy combo. Cached by (strategies + all params)."""
    _set_model_params()
    sm.ALLOCATION_STRATEGY = alloc_strategy
    sm.WORK_STRATEGY = work_strategy
    return sm.simulate(params_tuple[0])  # params_tuple[0] == fte


def _extract_kpis(results):
    """Extract endpoint KPIs from simulation results."""
    final = results[-1]
    wip = final["wip"]
    unstable = wip > 50_000 or len(results) < 365

    fca_open = final["open_by_type"].get("FCA", 0)
    fca_breach = final["breaches_by_type"].get("FCA", 0)
    fca_stock = (fca_breach / fca_open * 100) if fca_open > 0 else 0

    psd2_open = (final["open_by_type"].get("PSD2_15", 0)
                 + final["open_by_type"].get("PSD2_35", 0))
    psd2_breach = (final["breaches_by_type"].get("PSD2_15", 0)
                   + final["breaches_by_type"].get("PSD2_35", 0))
    psd2_stock = (psd2_breach / psd2_open * 100) if psd2_open > 0 else 0

    last30_wd = [r for r in results[-60:] if r["workday"]][-30:]

    fca_closed = sum(r["closures_by_type"].get("FCA", 0) for r in last30_wd)
    fca_br_closed = sum(r["breached_closures_by_type"].get("FCA", 0) for r in last30_wd)
    fca_flow = (fca_br_closed / fca_closed * 100) if fca_closed > 0 else 0

    psd2_closed = sum(
        r["closures_by_type"].get("PSD2_15", 0) + r["closures_by_type"].get("PSD2_35", 0)
        for r in last30_wd
    )
    psd2_br_closed = sum(
        r["breached_closures_by_type"].get("PSD2_15", 0)
        + r["breached_closures_by_type"].get("PSD2_35", 0)
        for r in last30_wd
    )
    psd2_flow = (psd2_br_closed / psd2_closed * 100) if psd2_closed > 0 else 0

    avg_closures = mean(r["closures"] for r in last30_wd) if last30_wd else 0

    return {
        "wip": wip,
        "fca_stock_breach_pct": fca_stock,
        "psd2_stock_breach_pct": psd2_stock,
        "fca_flow_breach_pct": fca_flow,
        "psd2_flow_breach_pct": psd2_flow,
        "avg_closures": avg_closures,
        "max_unalloc_wait": final.get("max_unallocated_wait", 0),
        "max_diary_neglect": final.get("max_diary_untouched", 0),
        "avg_diary_neglect": final.get("avg_diary_untouched", 0),
        "unstable": unstable,
    }


def _extract_timeseries(results):
    """Extract time-series arrays for drill-down charts."""
    days, wip, closures, unalloc, workday = [], [], [], [], []
    fca_bp, psd2_bp = [], []
    age = {label: [] for label in ["0-3", "4-15", "16-35", "36-56", "57+"]}

    for r in results:
        days.append(r["day"] + 1)
        wip.append(r["wip"])
        closures.append(r["closures"])
        unalloc.append(r["unalloc"])
        workday.append(r["workday"])

        fo = r["open_by_type"].get("FCA", 0)
        fb = r["breaches_by_type"].get("FCA", 0)
        fca_bp.append((fb / fo * 100) if fo > 0 else 0)

        po = (r["open_by_type"].get("PSD2_15", 0)
              + r["open_by_type"].get("PSD2_35", 0))
        pb = (r["breaches_by_type"].get("PSD2_15", 0)
              + r["breaches_by_type"].get("PSD2_35", 0))
        psd2_bp.append((pb / po * 100) if po > 0 else 0)

        for label in age:
            age[label].append(r["age_bands"].get(label, 0))

    return {
        "days": days, "wip": wip, "closures": closures,
        "unalloc": unalloc, "workday": workday,
        "fca_breach_pct": fca_bp, "psd2_breach_pct": psd2_bp,
        "age_bands": age,
    }


def _pretty(name):
    """'nearest_deadline' -> 'nearest deadline'"""
    return name.replace("_", " ")


# ═══════════════════════════════════════════════════════════════════════════
# Section 2: Heatmap Screening — "Run All 36"
# ═══════════════════════════════════════════════════════════════════════════

st.header("Strategy Heatmaps — All 36 Combinations")

if st.button("Run All 36 Strategy Combinations", type="primary"):
    kpis = {}
    combos = [(a, w) for a in ALLOC_STRATEGIES for w in WORK_STRATEGIES]
    progress = st.progress(0, text="Running strategy simulations...")
    for i, (alloc, work) in enumerate(combos):
        progress.progress(
            (i + 1) / len(combos),
            text=f"Simulating {_pretty(alloc)} / {_pretty(work)}  ({i+1}/36)",
        )
        results = _run_single_combo(alloc, work, ALL_PARAMS)
        kpis[f"{alloc} / {work}"] = _extract_kpis(results)
    progress.empty()
    st.session_state["batch_kpis"] = kpis
    st.session_state["batch_params"] = ALL_PARAMS
    st.success("All 36 combinations complete.")

# Staleness check
if "batch_kpis" in st.session_state:
    if st.session_state.get("batch_params") != ALL_PARAMS:
        st.warning(
            "System parameters have changed since the last batch run. "
            "Click **Run All 36** to refresh."
        )

if "batch_kpis" not in st.session_state:
    st.info("Click the button above to run all 36 strategy combinations.")
    st.stop()

kpis = st.session_state["batch_kpis"]


# ── Heatmap rendering ──────────────────────────────────────────────────────

METRIC_CONFIG = [
    # (title, kpi_key, low_is_good, format_str)
    ("Final WIP",              "wip",                  True,  ",.0f"),
    ("FCA Stock Breach %",     "fca_stock_breach_pct", True,  ".1f"),
    ("PSD2 Stock Breach %",    "psd2_stock_breach_pct",True,  ".1f"),
    ("FCA Flow Breach %",      "fca_flow_breach_pct",  True,  ".1f"),
    ("PSD2 Flow Breach %",     "psd2_flow_breach_pct", True,  ".1f"),
    ("Avg Closures / Day",     "avg_closures",         False, ".1f"),
    ("Max Unallocated Wait",   "max_unalloc_wait",     True,  ".0f"),
    ("Max Diary Neglect",      "max_diary_neglect",    True,  ".0f"),
    ("Avg Diary Neglect",      "avg_diary_neglect",    True,  ".1f"),
]


def _make_heatmap(metric_title, metric_key, low_is_good, fmt):
    z = []
    annotations = []
    for alloc in ALLOC_STRATEGIES:
        row_z = []
        row_t = []
        for work in WORK_STRATEGIES:
            k = kpis[f"{alloc} / {work}"]
            if k["unstable"]:
                row_z.append(None)
                row_t.append("UNSTABLE")
            else:
                val = k[metric_key]
                row_z.append(val)
                row_t.append(format(val, fmt))
        z.append(row_z)
        annotations.append(row_t)

    # Replace None (unstable) with a sentinel beyond the stable range
    stable_vals = [v for row in z for v in row if v is not None]
    if stable_vals:
        if low_is_good:
            sentinel = max(stable_vals) * 1.5 if max(stable_vals) > 0 else 1
        else:
            sentinel = min(stable_vals) * 0.5 if min(stable_vals) > 0 else 0
    else:
        sentinel = 1
    for i in range(len(z)):
        for j in range(len(z[i])):
            if z[i][j] is None:
                z[i][j] = sentinel

    colorscale = "RdYlGn_r" if low_is_good else "RdYlGn"

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=[_pretty(s) for s in WORK_STRATEGIES],
        y=[_pretty(s) for s in ALLOC_STRATEGIES],
        text=annotations,
        texttemplate="%{text}",
        textfont=dict(size=10),
        colorscale=colorscale,
        hoverongaps=False,
        showscale=False,
    ))
    fig.update_layout(
        title=dict(text=metric_title, font=dict(size=14)),
        xaxis_title="Work Strategy",
        yaxis_title="Allocation Strategy",
        height=340,
        margin=dict(l=130, r=10, t=35, b=80),
        xaxis=dict(tickangle=-45, tickfont=dict(size=9)),
        yaxis=dict(tickfont=dict(size=9)),
    )
    return fig


# 3×3 grid of heatmaps
for row_start in range(0, 9, 3):
    cols = st.columns(3)
    for col_idx, (title, key, low_good, fmt) in enumerate(
        METRIC_CONFIG[row_start:row_start + 3]
    ):
        with cols[col_idx]:
            st.plotly_chart(
                _make_heatmap(title, key, low_good, fmt),
                use_container_width=True,
            )

st.divider()


# ═══════════════════════════════════════════════════════════════════════════
# Section 3: Combo Picker
# ═══════════════════════════════════════════════════════════════════════════

st.header("Strategy Deep Dive")

all_combo_labels = [f"{a} / {w}" for a in ALLOC_STRATEGIES for w in WORK_STRATEGIES]
# Filter out unstable combos from default suggestions
stable_combos = [c for c in all_combo_labels if not kpis[c]["unstable"]]

selected = st.multiselect(
    "Select 2–3 combos to compare",
    options=all_combo_labels,
    default=[],
    max_selections=5,
    format_func=lambda x: f"{_pretty(x.split(' / ')[0])}  /  {_pretty(x.split(' / ')[1])}",
)

if not selected:
    st.info("Pick combos above to see detailed time-series comparison.")
    st.stop()


# ═══════════════════════════════════════════════════════════════════════════
# Section 4: Drill-Down Time-Series
# ═══════════════════════════════════════════════════════════════════════════

# Build time-series for selected combos (cache hit — already computed)
ts_data = {}
for combo in selected:
    alloc, work = combo.split(" / ")
    results = _run_single_combo(alloc, work, ALL_PARAMS)
    ts_data[combo] = _extract_timeseries(results)

color_map = {combo: COMBO_COLORS[i % len(COMBO_COLORS)] for i, combo in enumerate(selected)}


def _overlay_chart(series_key, yaxis_title, workday_only=False):
    """Create an overlay line chart for one metric across selected combos."""
    fig = go.Figure()
    for combo in selected:
        ts = ts_data[combo]
        if workday_only:
            x = [d for d, w in zip(ts["days"], ts["workday"]) if w]
            y = [v for v, w in zip(ts[series_key], ts["workday"]) if w]
        else:
            x = ts["days"]
            y = ts[series_key]
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines",
            name=_pretty(combo),
            line=dict(color=color_map[combo]),
        ))
    fig.update_layout(**LAYOUT, yaxis_title=yaxis_title)
    return fig


# Chart 1 & 2: WIP + Closures
col1, col2 = st.columns(2)
with col1:
    st.subheader("WIP Over Time")
    st.plotly_chart(_overlay_chart("wip", "Cases"), use_container_width=True)
with col2:
    st.subheader("Closures Per Day")
    st.plotly_chart(
        _overlay_chart("closures", "Cases", workday_only=True),
        use_container_width=True,
    )

# Chart 3 & 4: Breach %
col1, col2 = st.columns(2)
with col1:
    st.subheader("FCA Stock Breach % Over Time")
    st.plotly_chart(_overlay_chart("fca_breach_pct", "Breach %"), use_container_width=True)
with col2:
    st.subheader("PSD2 Stock Breach % Over Time")
    st.plotly_chart(_overlay_chart("psd2_breach_pct", "Breach %"), use_container_width=True)

# Chart 5: Unallocated queue
st.subheader("Unallocated Queue Size")
st.plotly_chart(_overlay_chart("unalloc", "Cases"), use_container_width=True)

# Chart 6: Age profile — side-by-side stacked area (one per combo)
st.subheader("Age Profile")
age_cols = st.columns(len(selected))
age_labels = ["0-3", "4-15", "16-35", "36-56", "57+"]
for col, combo in zip(age_cols, selected):
    with col:
        ts = ts_data[combo]
        fig = go.Figure()
        for label in age_labels:
            fig.add_trace(go.Scatter(
                x=ts["days"], y=ts["age_bands"][label],
                mode="lines", name=label, stackgroup="one",
            ))
        fig.update_layout(
            **LAYOUT,
            title=dict(text=_pretty(combo), font=dict(size=12)),
            yaxis_title="Cases",
        )
        st.plotly_chart(fig, use_container_width=True)
