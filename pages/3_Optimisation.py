# pages/3_Optimisation.py
"""Streamlit page — FTE pool optimisation via Optuna."""
from __future__ import annotations

import streamlit as st
import optuna
import plotly.graph_objects as go

from complaints_model.config import SimConfig
from complaints_model.pool_config import (
    OptimConfig, BandAllocation, ALLOC_STRATEGIES, WORK_STRATEGIES,
)
from complaints_model.bands import get_bands_for_model
from complaints_model.pool_simulation import simulate_pooled
from optimise import (
    suggest_params, build_optim_config, compute_objective,
    OBJECTIVES, POOLING_MODELS,
)

st.set_page_config(page_title="FTE Optimisation", layout="wide")
st.title("FTE Pool Optimisation")

# ── Sidebar controls ─────────────────────────────────────────────
st.sidebar.header("Optimisation Settings")

obj_name = st.sidebar.selectbox(
    "Objective", OBJECTIVES,
    format_func=lambda x: x.replace("_", " ").title(),
)
total_fte = st.sidebar.number_input("Total FTE", 100, 300, 148, step=1)
n_trials = st.sidebar.slider("Trials", 50, 2000, 200, step=50)
pooling_model = st.sidebar.selectbox("Pooling Model", POOLING_MODELS + ["all"],
                                      format_func=lambda x: x.title())

show_weights = obj_name == "composite_harm"
if show_weights:
    st.sidebar.subheader("Harm Weights")
    breach_w = st.sidebar.slider("Breach weight", 0.0, 10.0, 3.0, 0.5)
    neglect_w = st.sidebar.slider("Neglect weight", 0.0, 10.0, 1.0, 0.5)
    wip_w = st.sidebar.slider("WIP weight", 0.0, 10.0, 1.0, 0.5)
else:
    breach_w, neglect_w, wip_w = 3.0, 1.0, 1.0

run_btn = st.sidebar.button("Run Optimisation", type="primary")

# ── State ─────────────────────────────────────────────────────────
if "optim_study" not in st.session_state:
    st.session_state.optim_study = None
if "optim_best_results" not in st.session_state:
    st.session_state.optim_best_results = None

# ── Run optimisation ──────────────────────────────────────────────
if run_btn:
    progress = st.progress(0, text="Starting optimisation...")
    status = st.empty()

    harm_kwargs = {
        "harm_breach_weight": breach_w,
        "harm_neglect_weight": neglect_w,
        "harm_wip_weight": wip_w,
    }

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=min(20, n_trials // 5)),
    )

    best_val = [float("inf")]

    def trial_callback(study: optuna.Study, trial: optuna.trial.FrozenTrial) -> None:
        pct = min(1.0, (trial.number + 1) / n_trials)
        if trial.value is not None and trial.value < best_val[0]:
            best_val[0] = trial.value
        progress.progress(pct, text=f"Trial {trial.number+1}/{n_trials} — best: {best_val[0]:,.1f}")

    def make_objective(pm: str | None):
        def obj(trial: optuna.Trial) -> float:
            if pm is not None:
                params = {"pooling_model": pm}
                bands = get_bands_for_model(pm)
            else:
                pm_chosen = trial.suggest_categorical("pooling_model", POOLING_MODELS)
                params = {"pooling_model": pm_chosen}
                bands = get_bands_for_model(pm_chosen)

            band_names = [b.name for b in bands]
            fte_remaining = total_fte
            for i, bname in enumerate(band_names):
                if i < len(band_names) - 1:
                    fte = trial.suggest_int(f"{bname}_fte", 0, min(fte_remaining, total_fte))
                    fte_remaining = max(0, fte_remaining - fte)
                    params[f"{bname}_fte"] = fte
                params[f"{bname}_alloc"] = trial.suggest_categorical(f"{bname}_alloc", ALLOC_STRATEGIES)
                params[f"{bname}_work"] = trial.suggest_categorical(f"{bname}_work", WORK_STRATEGIES)

            oc = build_optim_config(params, total_fte, **harm_kwargs)
            results = simulate_pooled(oc, max_wip=50_000)

            # Pruning
            for cp in range(400, 730, 50):
                if cp < len(results):
                    val = results[cp]["cumulative_harm"] if obj_name == "composite_harm" else results[cp]["wip"]
                    trial.report(val, cp)
                    if trial.should_prune():
                        raise optuna.TrialPruned()

            return compute_objective(results, obj_name)
        return obj

    pm_arg = None if pooling_model == "all" else pooling_model
    study.optimize(make_objective(pm_arg), n_trials=n_trials, callbacks=[trial_callback])

    progress.progress(1.0, text="Optimisation complete!")
    st.session_state.optim_study = study

# ── Display results ───────────────────────────────────────────────
study = st.session_state.optim_study

if study is None:
    st.info("Configure settings in the sidebar and click **Run Optimisation** to start.")
    st.stop()

best = study.best_trial
col1, col2, col3 = st.columns(3)
col1.metric("Best Score", f"{best.value:,.2f}")
completed = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])
pruned = len([t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED])
col2.metric("Completed / Pruned", f"{completed} / {pruned}")
col3.metric("Best Trial", f"#{best.number}")

# Best configuration table
st.subheader("Best Configuration")
pm = best.params.get("pooling_model", "combined")
bands = get_bands_for_model(pm)
band_names = [b.name for b in bands]

rows = []
fte_used = 0
for i, bname in enumerate(band_names):
    if i < len(band_names) - 1:
        fte = best.params.get(f"{bname}_fte", 0)
        fte_used += fte
    else:
        fte = max(0, total_fte - fte_used)
    alloc = best.params.get(f"{bname}_alloc", "—")
    work = best.params.get(f"{bname}_work", "—")
    rows.append({"Band": bname, "FTE": fte, "Allocation Strategy": alloc, "Work Strategy": work})

st.table(rows)

# Optuna visualisation charts
st.subheader("Optimisation Charts")
chart_cols = st.columns(2)

try:
    fig_history = optuna.visualization.plot_optimization_history(study)
    chart_cols[0].plotly_chart(fig_history, use_container_width=True)
except Exception:
    chart_cols[0].warning("Could not render optimisation history.")

try:
    fig_importance = optuna.visualization.plot_param_importances(study)
    chart_cols[1].plotly_chart(fig_importance, use_container_width=True)
except Exception:
    chart_cols[1].warning("Could not render parameter importance.")

try:
    fig_parallel = optuna.visualization.plot_parallel_coordinate(study)
    st.plotly_chart(fig_parallel, use_container_width=True)
except Exception:
    st.warning("Could not render parallel coordinate plot.")

# Replay best config
st.subheader("Replay Best Configuration")
if st.button("Replay Best Config"):
    with st.spinner("Running simulation with best config..."):
        best_params = dict(best.params)
        if "pooling_model" not in best_params:
            best_params["pooling_model"] = pooling_model if pooling_model != "all" else "combined"
        harm_kw = {
            "harm_breach_weight": breach_w,
            "harm_neglect_weight": neglect_w,
            "harm_wip_weight": wip_w,
        }
        oc = build_optim_config(best_params, total_fte, **harm_kw)
        replay_results = simulate_pooled(oc)
        st.session_state.optim_best_results = replay_results

replay = st.session_state.optim_best_results
if replay is not None:
    import plotly.express as px

    days = [r["day"] for r in replay]
    wips = [r["wip"] for r in replay]
    harms = [r["harm"] for r in replay]
    closures = [r["closures"] for r in replay if r["workday"]]
    work_days = [r["day"] for r in replay if r["workday"]]

    rc1, rc2 = st.columns(2)
    rc1.plotly_chart(
        px.line(x=days, y=wips, labels={"x": "Day", "y": "WIP"}, title="WIP Over Time"),
        use_container_width=True,
    )
    rc2.plotly_chart(
        px.line(x=days, y=harms, labels={"x": "Day", "y": "Daily Harm"}, title="Daily Harm Score"),
        use_container_width=True,
    )

    # Breach rates
    fca_breach = [
        r["breaches_by_type"].get("FCA", 0) / max(r["open_by_type"].get("FCA", 1), 1) * 100
        for r in replay
    ]
    psd2_breach = [
        (r["breaches_by_type"].get("PSD2_15", 0) + r["breaches_by_type"].get("PSD2_35", 0))
        / max(r["open_by_type"].get("PSD2_15", 0) + r["open_by_type"].get("PSD2_35", 0), 1) * 100
        for r in replay
    ]
    rc3, rc4 = st.columns(2)
    rc3.plotly_chart(
        px.line(x=days, y=fca_breach, labels={"x": "Day", "y": "%"}, title="FCA Stock Breach %"),
        use_container_width=True,
    )
    rc4.plotly_chart(
        px.line(x=days, y=psd2_breach, labels={"x": "Day", "y": "%"}, title="PSD2 Stock Breach %"),
        use_container_width=True,
    )

    rc5, rc6 = st.columns(2)
    rc5.plotly_chart(
        px.line(x=work_days, y=closures, labels={"x": "Day", "y": "Closures"}, title="Daily Closures"),
        use_container_width=True,
    )
    cum_harm = [r["cumulative_harm"] for r in replay]
    rc6.plotly_chart(
        px.line(x=days, y=cum_harm, labels={"x": "Day", "y": "Cumulative Harm"}, title="Cumulative Harm"),
        use_container_width=True,
    )
