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

__all__ = [
    "SimConfig", "simulate", "STRATEGIES", "Cohort",
    "average_breach_rates", "average_flow_breach_rates",
    "is_stable", "summarise_closure_metrics",
    "last_n_days", "last_n_workdays",
    "count_by_type", "count_breaches", "count_over_target", "count_age_bands",
    "print_stable_pack", "print_fte_sweep",
]
