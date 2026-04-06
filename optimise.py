# optimise.py
"""CLI runner — Optuna-based FTE pool optimisation."""
from __future__ import annotations

import argparse
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


def objective(
    trial: optuna.Trial,
    total_fte: int,
    obj_name: str,
    harm_kwargs: dict,
) -> float:
    """Optuna objective function — one trial."""
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
