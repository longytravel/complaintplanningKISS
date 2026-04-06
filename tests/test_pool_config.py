# tests/test_pool_config.py
"""Tests for OptimConfig dataclass."""
import pytest
from complaints_model.pool_config import OptimConfig, BandAllocation, ALLOC_STRATEGIES, WORK_STRATEGIES
from complaints_model.config import SimConfig


class TestBandAllocation:
    def test_creation(self):
        ba = BandAllocation(band_name="F1", fte=20, allocation_strategy="youngest_first", work_strategy="oldest_first")
        assert ba.band_name == "F1"
        assert ba.fte == 20
        assert ba.allocation_strategy == "youngest_first"
        assert ba.work_strategy == "oldest_first"


class TestOptimConfig:
    def test_creation_with_valid_fte_sum(self):
        bands = [
            BandAllocation("F1", 30, "youngest_first", "oldest_first"),
            BandAllocation("F2", 40, "nearest_deadline", "nearest_deadline"),
            BandAllocation("F3", 30, "nearest_target", "nearest_target"),
            BandAllocation("F4", 28, "oldest_first", "lowest_effort"),
            BandAllocation("F5", 20, "nearest_deadline", "longest_untouched"),
        ]
        oc = OptimConfig(
            total_fte=148, pooling_model="separate", band_allocations=bands,
        )
        assert oc.total_fte == 148
        assert len(oc.band_allocations) == 5

    def test_fte_sum_validation(self):
        """FTE allocations must sum to total_fte."""
        bands = [
            BandAllocation("F1", 100, "youngest_first", "oldest_first"),
            BandAllocation("F2", 100, "youngest_first", "oldest_first"),
        ]
        with pytest.raises(ValueError, match="FTE.*must sum"):
            OptimConfig(total_fte=148, pooling_model="separate", band_allocations=bands)

    def test_default_harm_weights(self):
        bands = [BandAllocation("C1", 148, "youngest_first", "oldest_first")]
        oc = OptimConfig(total_fte=148, pooling_model="combined", band_allocations=bands)
        assert oc.harm_breach_weight == 3.0
        assert oc.harm_neglect_weight == 1.0
        assert oc.harm_wip_weight == 1.0

    def test_base_config_defaults_to_simconfig(self):
        bands = [BandAllocation("C1", 148, "youngest_first", "oldest_first")]
        oc = OptimConfig(total_fte=148, pooling_model="combined", band_allocations=bands)
        assert oc.base_config.diary_limit == 7
        assert oc.base_config.shrinkage == 0.42

    def test_zero_fte_band_allowed(self):
        """A band with 0 FTE is valid -- cases age through it."""
        bands = [
            BandAllocation("F1", 0, "youngest_first", "oldest_first"),
            BandAllocation("F2", 148, "nearest_deadline", "nearest_deadline"),
        ]
        oc = OptimConfig(total_fte=148, pooling_model="separate", band_allocations=bands)
        assert oc.band_allocations[0].fte == 0


class TestStrategyLists:
    def test_alloc_strategies_count(self):
        assert len(ALLOC_STRATEGIES) == 6
        assert "youngest_first" in ALLOC_STRATEGIES
        assert "psd2_priority" in ALLOC_STRATEGIES
        assert "lowest_effort" not in ALLOC_STRATEGIES

    def test_work_strategies_count(self):
        assert len(WORK_STRATEGIES) == 6
        assert "lowest_effort" in WORK_STRATEGIES
        assert "longest_untouched" in WORK_STRATEGIES
        assert "psd2_priority" not in WORK_STRATEGIES
