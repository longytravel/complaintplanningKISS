"""Simulation configuration — all tuneable parameters in one frozen dataclass."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class SimConfig:
    # Staffing
    fte: int = 148
    shrinkage: float = 0.42
    absence_shrinkage: float = 0.15
    hours_per_day: float = 7.0
    utilisation: float = 1.00
    proficiency: float = 1.0

    # Caseload
    diary_limit: int = 7
    daily_intake: int = 300
    base_effort: float = 1.5
    min_diary_days: int = 0
    min_diary_days_non_src: int = 3
    handoff_overhead: float = 0.15
    handoff_effort_hours: float = 0.5
    late_demand_rate: float = 0.08

    # Simulation
    days: int = 730
    slices_per_day: int = 4

    # Parkinson's Law
    unallocated_buffer: int = 300
    parkinson_floor: float = 0.70
    parkinson_full_pace_queue: int = 600

    # SRC dynamics
    src_boost_max: float = 0.15
    src_boost_decay_days: int = 5
    src_window: int = 3
    src_effort_ratio: float = 0.7

    # Regulatory
    psd2_extension_rate: float = 0.05

    # Strategies
    allocation_strategy: str = "nearest_target"
    work_strategy: str = "nearest_target"

    @property
    def productive_fte(self) -> float:
        """FTE available for case work (after all shrinkage)."""
        return self.fte * (1 - self.shrinkage)

    @property
    def present_fte(self) -> float:
        """FTE physically present (after absence only)."""
        return self.fte * (1 - self.absence_shrinkage)

    @property
    def max_diary_slots(self) -> float:
        """Total diary capacity across all present handlers."""
        return self.present_fte * self.diary_limit
