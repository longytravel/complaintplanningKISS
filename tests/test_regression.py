"""Regression tests — verifies complaints_model output matches known baseline values."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from complaints_model import SimConfig, simulate
from complaints_model.metrics import average_breach_rates, average_flow_breach_rates, is_stable

# Run baseline ONCE at module level to avoid overhead
_cfg = SimConfig()
_BASELINE_RESULT = simulate(_cfg)
_BASELINE_FINAL = _BASELINE_RESULT[-1]
_BASELINE_BREACH = average_breach_rates(_BASELINE_RESULT)
_BASELINE_FLOW = average_flow_breach_rates(_BASELINE_RESULT)

# ── Exact baseline values (captured from prove_maths before refactor) ──
BASELINE_WIP = 1031.6704226651175
BASELINE_UTIL = 0.7740802140257256
BASELINE_BREACH_RATES = (0.006830649888327079, 0.0, 0.0506038552834077)
BASELINE_FLOW_BREACH = (0.009289062999461578, 0.0, 0.030933333333333334)
BASELINE_CLOSURES = 297.09000538633387

def test_baseline_captures():
    """Sanity: simulation runs and produces 730 days of output."""
    assert len(_BASELINE_RESULT) == 730
    assert _BASELINE_FINAL["day"] == 729
    assert _BASELINE_FINAL["wip"] > 0
    assert "breaches_by_type" in _BASELINE_FINAL

def test_baseline_stability():
    """At 148 FTE with defaults, model reaches stable equilibrium."""
    assert is_stable(_BASELINE_RESULT, _cfg), "Model should be stable at 148 FTE"

def test_baseline_kpis():
    """Capture specific KPI ranges that must hold after refactor."""
    assert 500 < _BASELINE_FINAL["wip"] < 2000, f"WIP {_BASELINE_FINAL['wip']} out of expected range"
    combined, fca, psd2 = _BASELINE_BREACH
    assert fca < 0.01, f"FCA breach {fca} too high"
    assert 0.70 < _BASELINE_FINAL["effective_util"] < 1.0, f"Util {_BASELINE_FINAL['effective_util']} unexpected"

def test_baseline_exact_values():
    """Verify exact numeric values match pre-refactor prove_maths output."""
    assert abs(_BASELINE_FINAL["wip"] - BASELINE_WIP) < 1e-6, f"WIP drifted: {_BASELINE_FINAL['wip']}"
    assert abs(_BASELINE_FINAL["effective_util"] - BASELINE_UTIL) < 1e-6
    assert abs(_BASELINE_FINAL["closures"] - BASELINE_CLOSURES) < 1e-6

    for i, (got, expected) in enumerate(zip(_BASELINE_BREACH, BASELINE_BREACH_RATES)):
        assert abs(got - expected) < 1e-6, f"Breach rate[{i}] drifted: {got} vs {expected}"

    for i, (got, expected) in enumerate(zip(_BASELINE_FLOW, BASELINE_FLOW_BREACH)):
        assert abs(got - expected) < 1e-6, f"Flow breach[{i}] drifted: {got} vs {expected}"

if __name__ == "__main__":
    print(f"Day {_BASELINE_FINAL['day']}: WIP={_BASELINE_FINAL['wip']:.10f}, "
          f"Closures={_BASELINE_FINAL['closures']:.10f}, "
          f"Util={_BASELINE_FINAL['effective_util']:.10f}")
    print(f"Breach rates: {_BASELINE_BREACH}")
    print(f"Flow breach: {_BASELINE_FLOW}")
    print("Baseline captured successfully.")
