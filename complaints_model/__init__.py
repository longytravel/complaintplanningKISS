"""Complaints Workforce Demand Model — modular package.

Usage:
    from complaints_model import SimConfig, simulate
    cfg = SimConfig(fte=148, daily_intake=300)
    result = simulate(cfg)
"""
from .config import SimConfig
from .simulation import simulate
from .strategies import STRATEGIES
from .cohort import Cohort
from .metrics import (
    average_breach_rates, average_flow_breach_rates,
    is_stable, summarise_closure_metrics,
    last_n_days, last_n_workdays,
    count_by_type, count_breaches, count_over_target, count_age_bands,
)
from .reporting import print_stable_pack, print_fte_sweep
from .bands import Band, FCA_BANDS, PSD2_BANDS, COMBINED_BANDS, get_bands_for_model, assign_band
from .pool_config import OptimConfig, BandAllocation, ALLOC_STRATEGIES, WORK_STRATEGIES
from .harm import score_case_harm, accumulate_daily_harm
from .pool_simulation import simulate_pooled

__all__ = [
    "SimConfig", "simulate", "STRATEGIES", "Cohort",
    "average_breach_rates", "average_flow_breach_rates",
    "is_stable", "summarise_closure_metrics",
    "last_n_days", "last_n_workdays",
    "count_by_type", "count_breaches", "count_over_target", "count_age_bands",
    "print_stable_pack", "print_fte_sweep",
    "Band", "FCA_BANDS", "PSD2_BANDS", "COMBINED_BANDS", "get_bands_for_model", "assign_band",
    "OptimConfig", "BandAllocation", "ALLOC_STRATEGIES", "WORK_STRATEGIES",
    "score_case_harm", "accumulate_daily_harm",
    "simulate_pooled",
]
