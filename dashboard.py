"""Complaints Workforce Demand Model — Interactive Dashboard"""

import streamlit as st
import plotly.graph_objects as go
from collections import defaultdict
from statistics import mean

from complaints_model import SimConfig, simulate

st.set_page_config(page_title="Complaints Demand Model", layout="wide")
st.title("Complaints Workforce Demand Simulation")
st.caption("v2.0 — modular engine")

# ── Sidebar: all config sliders ──────────────────────────────────────────────

st.sidebar.header("Staffing & Hours")
fte = st.sidebar.slider("FTE", 50, 300, 120, 1)
shrinkage = st.sidebar.slider("Shrinkage", 0.00, 0.80, 0.42, 0.01)
absence_shrinkage = st.sidebar.slider("Absence Shrinkage", 0.00, 0.50, 0.15, 0.01)
hours_per_day = st.sidebar.slider("Hours / Day", 4.0, 10.0, 7.0, 0.5)
utilisation = st.sidebar.slider("Max Utilisation", 0.50, 1.00, 1.00, 0.01)
proficiency = st.sidebar.slider("Proficiency", 0.50, 1.50, 1.0, 0.05)

st.sidebar.header("Demand & Caseload")
daily_intake = st.sidebar.slider("Daily Intake", 100, 600, 300, 5)
base_effort = st.sidebar.slider("Base Effort (hrs)", 0.5, 5.0, 1.5, 0.1)
diary_limit = st.sidebar.slider("Diary Limit", 1, 20, 7, 1)
min_diary_days = st.sidebar.slider("Min Diary Days", 0, 10, 0, 1)
handoff_overhead = st.sidebar.slider("Handoff Overhead", 0.00, 0.50, 0.15, 0.01)
handoff_effort_hours = st.sidebar.slider("Handoff Effort (hrs)", 0.0, 2.0, 0.5, 0.1)
late_demand_rate = st.sidebar.slider("Late Demand Rate", 0.00, 0.30, 0.08, 0.01)

st.sidebar.header("Parkinson's Law")
parkinson_floor = st.sidebar.slider("Parkinson Floor", 0.30, 1.00, 0.70, 0.05)
parkinson_fpq = st.sidebar.slider("Full Pace Queue", 100, 2000, 600, 50)
unallocated_buffer = st.sidebar.slider("Unallocated Buffer", 0, 1000, 300, 50)

st.sidebar.header("SRC (Summary Resolution)")
src_window = st.sidebar.slider("SRC Window (days)", 0, 10, 3, 1)
src_effort_ratio = st.sidebar.slider("SRC Effort Ratio", 0.10, 1.00, 0.70, 0.05)
src_boost_max = st.sidebar.slider("SRC Boost Max", 0.00, 0.50, 0.15, 0.01)
src_boost_decay = st.sidebar.slider("SRC Boost Decay (days)", 1, 15, 5, 1)

st.sidebar.header("Regulatory")
psd2_extension_rate = st.sidebar.slider("PSD2 Extension Rate", 0.00, 0.50, 0.05, 0.01)
slices_per_day = st.sidebar.slider("Slices / Day", 1, 8, 4, 1)

# ── Share params with Strategy Comparison page via session_state ────────────
st.session_state.update({
    "param_fte": fte, "param_shrinkage": shrinkage,
    "param_absence_shrinkage": absence_shrinkage,
    "param_hours_per_day": hours_per_day, "param_utilisation": utilisation,
    "param_proficiency": proficiency, "param_daily_intake": daily_intake,
    "param_base_effort": base_effort, "param_diary_limit": diary_limit,
    "param_min_diary_days": min_diary_days,
    "param_handoff_overhead": handoff_overhead,
    "param_handoff_effort_hours": handoff_effort_hours,
    "param_late_demand_rate": late_demand_rate,
    "param_parkinson_floor": parkinson_floor,
    "param_parkinson_fpq": parkinson_fpq,
    "param_unallocated_buffer": unallocated_buffer,
    "param_src_window": src_window, "param_src_effort_ratio": src_effort_ratio,
    "param_src_boost_max": src_boost_max, "param_src_boost_decay": src_boost_decay,
    "param_psd2_extension_rate": psd2_extension_rate,
    "param_slices_per_day": slices_per_day,
})


# ── Run simulation with caching ─────────────────────────────────────────────

@st.cache_data(show_spinner="Running simulation...")
def run_simulation(
    p_fte, p_shrinkage, p_absence_shrinkage, p_hours_per_day, p_utilisation,
    p_proficiency, p_daily_intake, p_base_effort, p_diary_limit, p_min_diary_days,
    p_handoff_overhead, p_handoff_effort_hours, p_late_demand_rate,
    p_parkinson_floor, p_parkinson_fpq, p_unallocated_buffer,
    p_src_window, p_src_effort_ratio, p_src_boost_max, p_src_boost_decay,
    p_psd2_extension_rate, p_slices_per_day,
):
    cfg = SimConfig(
        fte=p_fte, shrinkage=p_shrinkage, absence_shrinkage=p_absence_shrinkage,
        hours_per_day=p_hours_per_day, utilisation=p_utilisation, proficiency=p_proficiency,
        daily_intake=p_daily_intake, base_effort=p_base_effort, diary_limit=p_diary_limit,
        min_diary_days=p_min_diary_days, handoff_overhead=p_handoff_overhead,
        handoff_effort_hours=p_handoff_effort_hours, late_demand_rate=p_late_demand_rate,
        parkinson_floor=p_parkinson_floor, parkinson_full_pace_queue=p_parkinson_fpq,
        unallocated_buffer=p_unallocated_buffer, src_window=p_src_window,
        src_effort_ratio=p_src_effort_ratio, src_boost_max=p_src_boost_max,
        src_boost_decay_days=p_src_boost_decay, psd2_extension_rate=p_psd2_extension_rate,
        slices_per_day=p_slices_per_day, days=365,
    )
    return simulate(cfg)


results = run_simulation(
    fte, shrinkage, absence_shrinkage, hours_per_day, utilisation,
    proficiency, daily_intake, base_effort, diary_limit, min_diary_days,
    handoff_overhead, handoff_effort_hours, late_demand_rate,
    parkinson_floor, parkinson_fpq, unallocated_buffer,
    src_window, src_effort_ratio, src_boost_max, src_boost_decay,
    psd2_extension_rate, slices_per_day,
)


# ── Flatten daily records ────────────────────────────────────────────────────

def flatten(results):
    d = defaultdict(list)
    for row in results:
        d["day"].append(row["day"] + 1)
        d["workday"].append(row["workday"])
        d["wip"].append(row["wip"])
        d["unalloc"].append(row["unalloc"])
        d["alloc"].append(row["alloc"])
        d["desired_wip"].append(row["desired_wip"])
        d["closures"].append(row["closures"])
        d["allocations"].append(row["allocations"])
        d["demand_fte"].append(row["demand_fte"])
        d["effective_util"].append(row["effective_util"])
        d["avg_alloc_delay"].append(row["avg_allocation_delay"])
        d["occupancy_start"].append(row["occupancy_start"])
        d["occupancy_avg"].append(row["occupancy_avg"])
        d["occupancy_end"].append(row["occupancy_end"])
        d["slot_capacity"].append(row["slot_capacity"])
        for ct in ["FCA", "PSD2_15", "PSD2_35"]:
            d[f"open_{ct}"].append(row["open_by_type"].get(ct, 0.0))
            d[f"breach_{ct}"].append(row["breaches_by_type"].get(ct, 0.0))
            d[f"over_target_{ct}"].append(row["over_target_by_type"].get(ct, 0.0))
            d[f"closures_{ct}"].append(row["closures_by_type"].get(ct, 0.0))
            d[f"breached_close_{ct}"].append(row["breached_closures_by_type"].get(ct, 0.0))
            n = row["close_sums"][ct]["n"]
            d[f"avg_reg_close_{ct}"].append(
                row["close_sums"][ct]["reg"] / n if n > 0.01 else 0.0
            )
        for label in ["0-3", "4-15", "16-35", "36-56", "57+"]:
            d[f"age_{label}"].append(row["age_bands"].get(label, 0.0))
    return dict(d)


df = flatten(results)
wd_days = [d for d, w in zip(df["day"], df["workday"]) if w]


def wd(series):
    return [v for v, w in zip(series, df["workday"]) if w]


# ── Chart helpers ────────────────────────────────────────────────────────────

LAYOUT = dict(
    height=370,
    margin=dict(l=50, r=20, t=30, b=40),
    xaxis_title="Day",
    legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="left", x=0),
)


def chart(traces, yaxis_title="", x=None):
    fig = go.Figure()
    for name, y_data, x_data in traces:
        fig.add_trace(go.Scatter(
            x=x_data if x_data is not None else (x or df["day"]),
            y=y_data, mode="lines", name=name,
        ))
    fig.update_layout(**LAYOUT, yaxis_title=yaxis_title)
    return fig


def stacked_area(traces, yaxis_title="", x=None):
    fig = go.Figure()
    for name, y_data, x_data in traces:
        fig.add_trace(go.Scatter(
            x=x_data if x_data is not None else (x or df["day"]),
            y=y_data, mode="lines", name=name, stackgroup="one",
        ))
    fig.update_layout(**LAYOUT, yaxis_title=yaxis_title)
    return fig


# ── KPI Cards ────────────────────────────────────────────────────────────────

final = results[-1]
last30_wd = [r for r in results[-60:] if r["workday"]][-30:]

avg_closures = mean(r["closures"] for r in last30_wd) if last30_wd else 0
avg_util = mean(r["effective_util"] for r in last30_wd) if last30_wd else 0
avg_delay = mean(r["avg_allocation_delay"] for r in last30_wd) if last30_wd else 0

fca_open = final["open_by_type"].get("FCA", 0)
fca_breach = final["breaches_by_type"].get("FCA", 0)
fca_breach_pct = (fca_breach / fca_open * 100) if fca_open > 0 else 0

psd2_open = final["open_by_type"].get("PSD2_15", 0) + final["open_by_type"].get("PSD2_35", 0)
psd2_breach = final["breaches_by_type"].get("PSD2_15", 0) + final["breaches_by_type"].get("PSD2_35", 0)
psd2_breach_pct = (psd2_breach / psd2_open * 100) if psd2_open > 0 else 0

# Flow breach: % of cases closed in last 30 workdays that were breached when closed
fca_closed_30 = sum(r["closures_by_type"].get("FCA", 0) for r in last30_wd)
fca_breached_closed_30 = sum(r["breached_closures_by_type"].get("FCA", 0) for r in last30_wd)
fca_flow_pct = (fca_breached_closed_30 / fca_closed_30 * 100) if fca_closed_30 > 0 else 0

psd2_closed_30 = sum(
    r["closures_by_type"].get("PSD2_15", 0) + r["closures_by_type"].get("PSD2_35", 0)
    for r in last30_wd
)
psd2_breached_closed_30 = sum(
    r["breached_closures_by_type"].get("PSD2_15", 0) + r["breached_closures_by_type"].get("PSD2_35", 0)
    for r in last30_wd
)
psd2_flow_pct = (psd2_breached_closed_30 / psd2_closed_30 * 100) if psd2_closed_30 > 0 else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("WIP (Day 365)", f"{final['wip']:,.0f}")
c2.metric("Unallocated", f"{final['unalloc']:,.0f}")
c3.metric("Avg Closures/day", f"{avg_closures:,.1f}")
c4.metric("Effective Util", f"{avg_util:.1%}")

c5, c6, c7, c8 = st.columns(4)
c5.metric("Allocated", f"{final['alloc']:,.0f}")
c6.metric("Avg Alloc Delay", f"{avg_delay:.1f} days")
c7.metric("FCA Stock Breach %", f"{fca_breach_pct:.1f}%")
c8.metric("PSD2 Stock Breach %", f"{psd2_breach_pct:.1f}%")

c9, c10, c11, c12 = st.columns(4)
c9.metric("FCA Flow Breach %", f"{fca_flow_pct:.1f}%", help="% of FCA cases closed breached (last 30 workdays)")
c10.metric("PSD2 Flow Breach %", f"{psd2_flow_pct:.1f}%", help="% of PSD2 cases closed breached (last 30 workdays)")
c11.metric("FTE", f"{fte}")
c12.metric("Daily Intake", f"{daily_intake}")


# ── Section 1: Work In Progress ──────────────────────────────────────────────

st.header("Work In Progress")
col1, col2 = st.columns(2)
with col1:
    st.subheader("WIP Trajectory")
    st.plotly_chart(chart([
        ("Total WIP", df["wip"], None),
        ("Unallocated", df["unalloc"], None),
        ("Allocated", df["alloc"], None),
        ("Desired WIP", df["desired_wip"], None),
    ], yaxis_title="Cases"), use_container_width=True)
with col2:
    st.subheader("Open Stock by Type")
    st.plotly_chart(stacked_area([
        ("FCA", df["open_FCA"], None),
        ("PSD2 (15d)", df["open_PSD2_15"], None),
        ("PSD2 (35d)", df["open_PSD2_35"], None),
    ], yaxis_title="Cases"), use_container_width=True)


# ── Section 2: Diary Occupancy ───────────────────────────────────────────────

st.header("Diary Occupancy")
st.plotly_chart(chart([
    ("Start of Day", wd(df["occupancy_start"]), wd_days),
    ("Average", wd(df["occupancy_avg"]), wd_days),
    ("End of Day", wd(df["occupancy_end"]), wd_days),
    ("Slot Capacity", wd(df["slot_capacity"]), wd_days),
], yaxis_title="Slots"), use_container_width=True)


# ── Section 3: Allocations & Closures ────────────────────────────────────────

st.header("Flow: Allocations & Closures")
col1, col2 = st.columns(2)
with col1:
    st.subheader("Allocations vs Closures")
    st.plotly_chart(chart([
        ("Allocations", wd(df["allocations"]), wd_days),
        ("Closures", wd(df["closures"]), wd_days),
    ], yaxis_title="Cases"), use_container_width=True)
with col2:
    st.subheader("Closures by Type")
    st.plotly_chart(chart([
        ("FCA", wd(df["closures_FCA"]), wd_days),
        ("PSD2 (15d)", wd(df["closures_PSD2_15"]), wd_days),
        ("PSD2 (35d)", wd(df["closures_PSD2_35"]), wd_days),
    ], yaxis_title="Cases"), use_container_width=True)


# ── Section 4: Utilisation & Demand ──────────────────────────────────────────

st.header("Utilisation & Demand")
col1, col2 = st.columns(2)
with col1:
    st.subheader("Effective Utilisation")
    st.plotly_chart(chart([
        ("Effective Util", wd(df["effective_util"]), wd_days),
    ], yaxis_title="Utilisation"), use_container_width=True)
with col2:
    st.subheader("FTE Demand vs Configured")
    fig = chart([
        ("FTE Demand", wd(df["demand_fte"]), wd_days),
    ], yaxis_title="FTE")
    fig.add_hline(y=fte, line_dash="dash", line_color="red",
                  annotation_text=f"Configured: {fte}")
    st.plotly_chart(fig, use_container_width=True)


# ── Section 5: Breaches ──────────────────────────────────────────────────────

st.header("Breaches")
col1, col2 = st.columns(2)
with col1:
    st.subheader("Open Breaches by Type")
    st.plotly_chart(chart([
        ("FCA", df["breach_FCA"], None),
        ("PSD2 (15d)", df["breach_PSD2_15"], None),
        ("PSD2 (35d)", df["breach_PSD2_35"], None),
    ], yaxis_title="Cases"), use_container_width=True)
with col2:
    st.subheader("Over Service Target by Type")
    st.plotly_chart(chart([
        ("FCA", df["over_target_FCA"], None),
        ("PSD2 (15d)", df["over_target_PSD2_15"], None),
        ("PSD2 (35d)", df["over_target_PSD2_35"], None),
    ], yaxis_title="Cases"), use_container_width=True)


# ── Section 6: Age Profile ──────────────────────────────────────────────────

st.header("Age Profile")
st.plotly_chart(stacked_area([
    ("0-3 days", df["age_0-3"], None),
    ("4-15 days", df["age_4-15"], None),
    ("16-35 days", df["age_16-35"], None),
    ("36-56 days", df["age_36-56"], None),
    ("57+ days", df["age_57+"], None),
], yaxis_title="Cases"), use_container_width=True)


# ── Section 7: Allocation Delay ──────────────────────────────────────────────

st.header("Allocation Delay")
st.plotly_chart(chart([
    ("Avg Allocation Delay", wd(df["avg_alloc_delay"]), wd_days),
], yaxis_title="Days"), use_container_width=True)


# ── Section 8: Closure Quality ───────────────────────────────────────────────

st.header("Closure Quality")
col1, col2 = st.columns(2)
with col1:
    st.subheader("Breached Closures by Type")
    st.plotly_chart(chart([
        ("FCA", wd(df["breached_close_FCA"]), wd_days),
        ("PSD2 (15d)", wd(df["breached_close_PSD2_15"]), wd_days),
        ("PSD2 (35d)", wd(df["breached_close_PSD2_35"]), wd_days),
    ], yaxis_title="Cases"), use_container_width=True)
with col2:
    st.subheader("Avg Regulatory Age at Close")
    st.plotly_chart(chart([
        ("FCA", wd(df["avg_reg_close_FCA"]), wd_days),
        ("PSD2 (15d)", wd(df["avg_reg_close_PSD2_15"]), wd_days),
        ("PSD2 (35d)", wd(df["avg_reg_close_PSD2_35"]), wd_days),
    ], yaxis_title="Reg Days"), use_container_width=True)
