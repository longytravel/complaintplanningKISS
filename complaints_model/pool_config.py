# complaints_model/pool_config.py
"""Configuration for pool-based FTE optimisation."""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import SimConfig


ALLOC_STRATEGIES: list[str] = [
    "nearest_deadline", "nearest_target", "youngest_first",
    "oldest_first", "psd2_priority", "longest_wait",
]

WORK_STRATEGIES: list[str] = [
    "nearest_deadline", "nearest_target", "youngest_first",
    "oldest_first", "lowest_effort", "longest_untouched",
]


@dataclass(frozen=True)
class BandAllocation:
    """FTE and strategy assignment for a single band."""
    band_name: str
    fte: int
    allocation_strategy: str
    work_strategy: str


@dataclass(frozen=True)
class OptimConfig:
    """Full configuration for a pooled simulation trial."""
    total_fte: int
    pooling_model: str  # "separate", "combined", "hybrid"
    band_allocations: list[BandAllocation]

    # Harm weights (only used for composite objective)
    harm_breach_weight: float = 3.0
    harm_neglect_weight: float = 1.0
    harm_wip_weight: float = 1.0

    # Base simulation parameters (shared across all bands)
    base_config: SimConfig = field(default_factory=SimConfig)

    def __post_init__(self):
        fte_sum = sum(ba.fte for ba in self.band_allocations)
        if fte_sum != self.total_fte:
            raise ValueError(
                f"FTE allocations must sum to {self.total_fte}, got {fte_sum}"
            )
