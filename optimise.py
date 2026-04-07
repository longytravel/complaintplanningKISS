# optimise.py
"""CLI runner — Optuna-based FTE pool optimisation."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from statistics import mean

import optuna

from complaints_model.config import SimConfig
from complaints_model.pool_config import (
    OptimConfig, BandAllocation, ALLOC_STRATEGIES, WORK_STRATEGIES,
)
from complaints_model.bands import get_bands_for_model
from complaints_model.pool_simulation import simulate_pooled


OBJECTIVES = [
    "composite_harm", "lowest_wip",
    "lowest_psd2", "lowest_fca", "lowest_total_breaches",
]

POOLING_MODELS = ["separate", "combined", "hybrid"]


def build_optim_config(params: dict, total_fte: int, **harm_kwargs) -> OptimConfig:
    """Build OptimConfig from a flat parameter dict (as produced by suggest_params)."""
    pooling_model = params["pooling_model"]
    bands = get_bands_for_model(pooling_model)
    band_names = [b.name for b in bands]

    allocations = []
    fte_used = 0
    for i, bname in enumerate(band_names):
        if i < len(band_names) - 1:
            fte = params[f"{bname}_fte"]
            fte_used += fte
        else:
            fte = max(0, total_fte - fte_used)
        alloc_strat = params[f"{bname}_alloc"]
        work_strat = params[f"{bname}_work"]
        allocations.append(BandAllocation(bname, fte, alloc_strat, work_strat))

    return OptimConfig(
        total_fte=total_fte,
        pooling_model=pooling_model,
        band_allocations=allocations,
        **harm_kwargs,
    )


def suggest_params(trial: optuna.Trial, total_fte: int) -> dict:
    """Have Optuna suggest all parameters for a trial."""
    params: dict = {}
    pooling_model = trial.suggest_categorical("pooling_model", POOLING_MODELS)
    params["pooling_model"] = pooling_model

    bands = get_bands_for_model(pooling_model)
    band_names = [b.name for b in bands]

    fte_remaining = total_fte
    for i, bname in enumerate(band_names):
        if i < len(band_names) - 1:
            max_fte = min(fte_remaining, total_fte)
            fte = trial.suggest_int(f"{bname}_fte", 0, max_fte)
            fte_remaining -= fte
            fte_remaining = max(0, fte_remaining)
            params[f"{bname}_fte"] = fte
        params[f"{bname}_alloc"] = trial.suggest_categorical(
            f"{bname}_alloc", ALLOC_STRATEGIES,
        )
        params[f"{bname}_work"] = trial.suggest_categorical(
            f"{bname}_work", WORK_STRATEGIES,
        )

    return params


def compute_objective(results: list[dict], objective: str) -> float:
    """Extract the objective value from simulation results."""
    if len(results) < 730:
        return float("inf")

    steady = results[366:]

    if objective == "composite_harm":
        return results[-1]["cumulative_harm"]

    if objective == "lowest_wip":
        return mean(r["wip"] for r in steady)

    if objective == "lowest_psd2":
        def psd2_breach_pct(r: dict) -> float:
            total = r["open_by_type"].get("PSD2_15", 0) + r["open_by_type"].get("PSD2_35", 0)
            breached = r["breaches_by_type"].get("PSD2_15", 0) + r["breaches_by_type"].get("PSD2_35", 0)
            return (breached / total * 100) if total > 0 else 0.0
        return mean(psd2_breach_pct(r) for r in steady)

    if objective == "lowest_fca":
        def fca_breach_pct(r: dict) -> float:
            total = r["open_by_type"].get("FCA", 0)
            breached = r["breaches_by_type"].get("FCA", 0)
            return (breached / total * 100) if total > 0 else 0.0
        return mean(fca_breach_pct(r) for r in steady)

    if objective == "lowest_total_breaches":
        def total_breach_pct(r: dict) -> float:
            total = sum(r["open_by_type"].values())
            breached = sum(r["breaches_by_type"].values())
            return (breached / total * 100) if total > 0 else 0.0
        return mean(total_breach_pct(r) for r in steady)

    raise ValueError(f"Unknown objective: {objective}")


_SUBPROCESS_SCRIPT = r'''
import json, sys
from complaints_model.pool_config import OptimConfig, BandAllocation
from complaints_model.bands import get_bands_for_model
from complaints_model.pool_simulation import simulate_pooled

params = json.loads(sys.argv[1])
total_fte = int(sys.argv[2])
harm_kw = json.loads(sys.argv[3])
pm = params["pooling_model"]
bands = get_bands_for_model(pm)
band_names = [b.name for b in bands]
allocs = []
fte_used = 0
for i, bn in enumerate(band_names):
    if i < len(band_names) - 1:
        fte = params.get(f"{bn}_fte", 0)
        fte_used += fte
    else:
        fte = max(0, total_fte - fte_used)
    allocs.append(BandAllocation(bn, fte, params[f"{bn}_alloc"], params[f"{bn}_work"]))
oc = OptimConfig(total_fte=total_fte, pooling_model=pm, band_allocations=allocs, **harm_kw)
results = simulate_pooled(oc, max_wip=50_000)
out = {"days": len(results)}
for day_idx in range(400, 730, 50):
    if day_idx < len(results):
        r = results[day_idx]
        out[f"cp_{day_idx}"] = {"harm": r["cumulative_harm"], "wip": r["wip"]}
if len(results) >= 730:
    out["final"] = {"harm": results[-1]["cumulative_harm"],
                    "wip": results[-1]["wip"],
                    "open_by_type": results[-1]["open_by_type"],
                    "breaches_by_type": results[-1]["breaches_by_type"]}
    from statistics import mean
    steady = results[366:]
    out["steady_avg_wip"] = mean(r["wip"] for r in steady)
    def breach_pct(r, types):
        total = sum(r["open_by_type"].get(t, 0) for t in types)
        breached = sum(r["breaches_by_type"].get(t, 0) for t in types)
        return (breached / total * 100) if total > 0 else 0.0
    out["steady_psd2_pct"] = mean(breach_pct(r, ["PSD2_15", "PSD2_35"]) for r in steady)
    out["steady_fca_pct"] = mean(breach_pct(r, ["FCA"]) for r in steady)
    out["steady_total_pct"] = mean(
        breach_pct(r, list(r["open_by_type"].keys())) for r in steady)
print(json.dumps(out))
'''


def _run_trial_subprocess(
    params: dict, total_fte: int, harm_kwargs: dict,
) -> dict | None:
    """Run a single trial in a subprocess to avoid CPython cache corruption."""
    try:
        r = subprocess.run(
            [sys.executable, "-c", _SUBPROCESS_SCRIPT,
             json.dumps(params), str(total_fte), json.dumps(harm_kwargs)],
            capture_output=True, text=True, timeout=180,
        )
        if r.returncode != 0:
            return None
        return json.loads(r.stdout.strip())
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


_USE_SUBPROCESS = sys.platform == "win32"


def _objective_inprocess(
    trial: optuna.Trial,
    total_fte: int,
    obj_name: str,
    harm_kwargs: dict,
) -> float:
    """Direct in-process objective (fast, used on Linux/macOS)."""
    params = suggest_params(trial, total_fte)
    optim_cfg = build_optim_config(params, total_fte, **harm_kwargs)

    results = simulate_pooled(optim_cfg, max_wip=50_000)

    # Pruning: report at checkpoints after steady-state start
    for checkpoint in range(400, 730, 50):
        if checkpoint < len(results):
            r = results[checkpoint]
            if obj_name == "composite_harm":
                trial.report(r["cumulative_harm"], checkpoint)
            else:
                trial.report(r["wip"], checkpoint)
            if trial.should_prune():
                raise optuna.TrialPruned()

    return compute_objective(results, obj_name)


def _objective_subprocess(
    trial: optuna.Trial,
    total_fte: int,
    obj_name: str,
    harm_kwargs: dict,
) -> float:
    """Subprocess-isolated objective (avoids CPython crash on Windows)."""
    params = suggest_params(trial, total_fte)

    result = _run_trial_subprocess(params, total_fte, harm_kwargs)
    if result is None or result["days"] < 730:
        return float("inf")

    # Pruning via checkpoint data
    for checkpoint in range(400, 730, 50):
        key = f"cp_{checkpoint}"
        if key in result:
            val = result[key]["harm"] if obj_name == "composite_harm" else result[key]["wip"]
            trial.report(val, checkpoint)
            if trial.should_prune():
                raise optuna.TrialPruned()

    if obj_name == "composite_harm":
        return result["final"]["harm"]
    if obj_name == "lowest_wip":
        return result["steady_avg_wip"]
    if obj_name == "lowest_psd2":
        return result["steady_psd2_pct"]
    if obj_name == "lowest_fca":
        return result["steady_fca_pct"]
    if obj_name == "lowest_total_breaches":
        return result["steady_total_pct"]
    raise ValueError(f"Unknown objective: {obj_name}")


def objective(
    trial: optuna.Trial,
    total_fte: int,
    obj_name: str,
    harm_kwargs: dict,
) -> float:
    """Optuna objective — subprocess on Windows, direct on Linux/macOS."""
    if _USE_SUBPROCESS:
        return _objective_subprocess(trial, total_fte, obj_name, harm_kwargs)
    return _objective_inprocess(trial, total_fte, obj_name, harm_kwargs)


def run_study(
    obj_name: str = "composite_harm",
    total_fte: int = 148,
    n_trials: int = 200,
    harm_breach_weight: float = 3.0,
    harm_neglect_weight: float = 1.0,
    harm_wip_weight: float = 1.0,
) -> optuna.Study:
    """Create and run an Optuna study."""
    timestamp = int(time.time())
    study_name = f"{obj_name}_{total_fte}fte_{timestamp}"

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=20),
        storage=f"sqlite:///optimisation_results.db",
        study_name=study_name,
    )

    harm_kwargs = {
        "harm_breach_weight": harm_breach_weight,
        "harm_neglect_weight": harm_neglect_weight,
        "harm_wip_weight": harm_wip_weight,
    }

    study.optimize(
        lambda trial: objective(trial, total_fte, obj_name, harm_kwargs),
        n_trials=n_trials,
        show_progress_bar=True,
    )

    return study


def print_results(study: optuna.Study) -> None:
    """Print study results to stdout."""
    best = study.best_trial
    print(f"\n{'='*60}")
    print(f"Best trial: #{best.number}")
    print(f"Best value: {best.value:,.2f}")
    print(f"{'='*60}")
    print("\nBest parameters:")
    for key, val in sorted(best.params.items()):
        print(f"  {key}: {val}")

    try:
        importances = optuna.importance.get_param_importances(study)
        print(f"\nParameter importance:")
        for param, imp in sorted(importances.items(), key=lambda x: -x[1])[:10]:
            print(f"  {param}: {imp:.3f}")
    except Exception:
        pass

    print(f"\nCompleted trials: {len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])}")
    print(f"Pruned trials: {len([t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED])}")
    print(f"Failed trials: {len([t for t in study.trials if t.state == optuna.trial.TrialState.FAIL])}")


def main():
    parser = argparse.ArgumentParser(description="FTE Pool Optimisation via Optuna")
    parser.add_argument("--objective", choices=OBJECTIVES, default="composite_harm")
    parser.add_argument("--fte", type=int, default=148)
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--breach-weight", type=float, default=3.0)
    parser.add_argument("--neglect-weight", type=float, default=1.0)
    parser.add_argument("--wip-weight", type=float, default=1.0)
    args = parser.parse_args()

    study = run_study(
        obj_name=args.objective,
        total_fte=args.fte,
        n_trials=args.trials,
        harm_breach_weight=args.breach_weight,
        harm_neglect_weight=args.neglect_weight,
        harm_wip_weight=args.wip_weight,
    )
    print_results(study)


if __name__ == "__main__":
    main()
