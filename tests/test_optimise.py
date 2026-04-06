# tests/test_optimise.py
"""Tests for Optuna optimisation runner."""
import pytest
from optimise import build_optim_config, compute_objective


class TestBuildOptimConfig:
    def test_builds_valid_config_combined(self):
        """Simulates what a trial would produce for combined model."""
        params = {
            "pooling_model": "combined",
            "C1_fte": 50, "C2_fte": 40, "C3_fte": 30, "C4_fte": 18,
            "C1_alloc": "youngest_first", "C1_work": "oldest_first",
            "C2_alloc": "nearest_deadline", "C2_work": "nearest_deadline",
            "C3_alloc": "nearest_target", "C3_work": "nearest_target",
            "C4_alloc": "oldest_first", "C4_work": "nearest_deadline",
            "C5_alloc": "nearest_deadline", "C5_work": "lowest_effort",
        }
        oc = build_optim_config(params, total_fte=148)
        assert oc.total_fte == 148
        assert len(oc.band_allocations) == 5
        # Last band gets remainder
        assert oc.band_allocations[-1].fte == 148 - 50 - 40 - 30 - 18

    def test_fte_remainder_clamped_to_zero(self):
        """If first N-1 bands use all FTE, last band gets 0."""
        params = {
            "pooling_model": "combined",
            "C1_fte": 50, "C2_fte": 50, "C3_fte": 30, "C4_fte": 18,
            "C1_alloc": "youngest_first", "C1_work": "oldest_first",
            "C2_alloc": "youngest_first", "C2_work": "oldest_first",
            "C3_alloc": "youngest_first", "C3_work": "oldest_first",
            "C4_alloc": "youngest_first", "C4_work": "oldest_first",
            "C5_alloc": "youngest_first", "C5_work": "oldest_first",
        }
        oc = build_optim_config(params, total_fte=148)
        assert oc.band_allocations[-1].fte == 0


class TestComputeObjective:
    def test_composite_harm_returns_float(self):
        results = [
            {"day": d, "harm": 0.0, "cumulative_harm": 0.0,
             "wip": 2000, "breaches_by_type": {"FCA": 0, "PSD2_15": 0, "PSD2_35": 0},
             "open_by_type": {"FCA": 1400, "PSD2_15": 500, "PSD2_35": 100}}
            for d in range(730)
        ]
        for r in results[366:]:
            r["harm"] = 100.0
            r["cumulative_harm"] = 100.0 * (r["day"] - 365)
        val = compute_objective(results, "composite_harm")
        assert isinstance(val, float)
        assert val > 0

    def test_lowest_wip_returns_mean(self):
        results = [
            {"day": d, "wip": 2000.0 + d * 0.1,
             "breaches_by_type": {"FCA": 0, "PSD2_15": 0, "PSD2_35": 0},
             "open_by_type": {"FCA": 1400, "PSD2_15": 500, "PSD2_35": 100}}
            for d in range(730)
        ]
        val = compute_objective(results, "lowest_wip")
        assert isinstance(val, float)
        expected = sum(r["wip"] for r in results[366:]) / len(results[366:])
        assert val == pytest.approx(expected)

    def test_death_spiral_returns_infinity(self):
        """If simulation stopped early (< 730 days), return infinity."""
        results = [{"day": d, "wip": 50000, "harm": 0, "cumulative_harm": 0,
                     "breaches_by_type": {}, "open_by_type": {}} for d in range(200)]
        val = compute_objective(results, "composite_harm")
        assert val == float("inf")
