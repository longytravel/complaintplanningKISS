# tests/test_pool_simulation.py
"""Tests for pool-aware multi-band simulation."""
import pytest
from complaints_model.config import SimConfig
from complaints_model.pool_config import OptimConfig, BandAllocation
from complaints_model.pool_simulation import simulate_pooled


class TestSimulatePooledBasic:
    def test_returns_list_of_dicts(self):
        """Minimal single-band combined config runs and returns results."""
        oc = OptimConfig(
            total_fte=148,
            pooling_model="combined",
            band_allocations=[
                BandAllocation("C1", 50, "youngest_first", "oldest_first"),
                BandAllocation("C2", 40, "nearest_deadline", "nearest_deadline"),
                BandAllocation("C3", 30, "nearest_target", "nearest_target"),
                BandAllocation("C4", 18, "oldest_first", "nearest_deadline"),
                BandAllocation("C5", 10, "nearest_deadline", "lowest_effort"),
            ],
        )
        results = simulate_pooled(oc)
        assert isinstance(results, list)
        assert len(results) > 0
        assert "wip" in results[0]
        assert "harm" in results[0]

    def test_circuit_breaker_stops_death_spiral(self):
        """Absurd config (all FTE in last band) should hit circuit breaker."""
        oc = OptimConfig(
            total_fte=148,
            pooling_model="combined",
            band_allocations=[
                BandAllocation("C1", 0, "youngest_first", "oldest_first"),
                BandAllocation("C2", 0, "youngest_first", "oldest_first"),
                BandAllocation("C3", 0, "youngest_first", "oldest_first"),
                BandAllocation("C4", 0, "youngest_first", "oldest_first"),
                BandAllocation("C5", 148, "youngest_first", "oldest_first"),
            ],
        )
        results = simulate_pooled(oc, max_wip=10_000)
        # Should stop well before 730 days
        assert len(results) < 730

    def test_harm_accumulates_only_in_steady_state(self):
        """Harm in results should be 0 for days < 366."""
        oc = OptimConfig(
            total_fte=148,
            pooling_model="combined",
            band_allocations=[
                BandAllocation("C1", 50, "youngest_first", "oldest_first"),
                BandAllocation("C2", 40, "nearest_deadline", "nearest_deadline"),
                BandAllocation("C3", 30, "nearest_target", "nearest_target"),
                BandAllocation("C4", 18, "oldest_first", "nearest_deadline"),
                BandAllocation("C5", 10, "nearest_deadline", "lowest_effort"),
            ],
        )
        results = simulate_pooled(oc)
        # First 366 days should have harm == 0
        for r in results[:366]:
            assert r["harm"] == 0.0
        # At least some days in 366-730 should have harm > 0
        steady_harms = [r["harm"] for r in results[366:]]
        assert any(h > 0 for h in steady_harms)


class TestSimulatePooledSeparate:
    def test_separate_model_runs(self):
        """10-band separate model completes."""
        oc = OptimConfig(
            total_fte=148,
            pooling_model="separate",
            band_allocations=[
                BandAllocation("F1", 25, "youngest_first", "oldest_first"),
                BandAllocation("F2", 20, "nearest_deadline", "nearest_deadline"),
                BandAllocation("F3", 15, "nearest_target", "nearest_target"),
                BandAllocation("F4", 15, "oldest_first", "nearest_deadline"),
                BandAllocation("F5", 5, "nearest_deadline", "lowest_effort"),
                BandAllocation("P1", 25, "youngest_first", "oldest_first"),
                BandAllocation("P2", 18, "nearest_deadline", "nearest_deadline"),
                BandAllocation("P3", 10, "nearest_target", "nearest_target"),
                BandAllocation("P4", 5, "nearest_deadline", "nearest_deadline"),
                BandAllocation("P5", 10, "nearest_deadline", "lowest_effort"),
            ],
        )
        results = simulate_pooled(oc)
        assert len(results) == 730


class TestSimulatePooledHybrid:
    def test_hybrid_model_runs(self):
        """6-band hybrid model completes."""
        oc = OptimConfig(
            total_fte=148,
            pooling_model="hybrid",
            band_allocations=[
                BandAllocation("F1", 20, "youngest_first", "oldest_first"),
                BandAllocation("F2", 20, "nearest_deadline", "nearest_deadline"),
                BandAllocation("F3", 15, "nearest_target", "nearest_target"),
                BandAllocation("F4", 10, "oldest_first", "nearest_deadline"),
                BandAllocation("F5", 5, "nearest_deadline", "lowest_effort"),
                BandAllocation("PSD2", 78, "youngest_first", "oldest_first"),
            ],
        )
        results = simulate_pooled(oc)
        assert len(results) == 730
