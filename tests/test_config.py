"""Tests for SimConfig dataclass."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from complaints_model.config import SimConfig

def test_defaults_match_prove_maths():
    """Default SimConfig values must match prove_maths module-level constants."""
    cfg = SimConfig()
    assert cfg.fte == 148
    assert cfg.shrinkage == 0.42
    assert cfg.absence_shrinkage == 0.15
    assert cfg.hours_per_day == 7.0
    assert cfg.utilisation == 1.00
    assert cfg.proficiency == 1.0
    assert cfg.diary_limit == 7
    assert cfg.daily_intake == 300
    assert cfg.base_effort == 1.5
    assert cfg.min_diary_days == 0
    assert cfg.min_diary_days_non_src == 3
    assert cfg.handoff_overhead == 0.15
    assert cfg.handoff_effort_hours == 0.5
    assert cfg.late_demand_rate == 0.08
    assert cfg.days == 730
    assert cfg.slices_per_day == 4
    assert cfg.parkinson_floor == 0.70
    assert cfg.parkinson_full_pace_queue == 600
    assert cfg.allocation_strategy == "nearest_target"
    assert cfg.work_strategy == "nearest_target"

def test_frozen():
    """SimConfig should be immutable."""
    cfg = SimConfig()
    try:
        cfg.fte = 200
        assert False, "Should have raised FrozenInstanceError"
    except AttributeError:
        pass

def test_custom_values():
    """Can create config with custom values."""
    cfg = SimConfig(fte=120, daily_intake=400, allocation_strategy="youngest_first")
    assert cfg.fte == 120
    assert cfg.daily_intake == 400
    assert cfg.allocation_strategy == "youngest_first"
    # Other fields keep defaults
    assert cfg.shrinkage == 0.42

def test_derived_properties():
    """Derived capacity calculations."""
    cfg = SimConfig(fte=148)
    assert cfg.productive_fte == 148 * (1 - 0.42)  # 85.84
    assert cfg.present_fte == 148 * (1 - 0.15)     # 125.8
    assert cfg.max_diary_slots == 148 * (1 - 0.15) * 7  # 880.6
