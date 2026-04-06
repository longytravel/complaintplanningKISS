# Modular Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor prove_maths.py + strategy_model.py into a clean `complaints_model/` package with SimConfig dataclass, one-file-per-responsibility, merged strategy support, and zero regression.

**Architecture:** Package with 12 focused modules. SimConfig frozen dataclass replaces all global mutation. Strategy sort-keys built into allocation/work modules. Dependency flow is strictly one-directional (config → cohort → regulatory → effort → strategies → intake → allocation/work → simulation → metrics → reporting).

**Tech Stack:** Python 3.11+, dataclasses (stdlib only — no new deps for core model). Streamlit + Plotly for dashboard (existing).

**Design spec:** `docs/superpowers/specs/2026-04-06-modular-refactor-design.md`

---

### Task 1: Capture regression baseline

**Files:**
- Create: `tests/test_regression.py`
- Read: `prove_maths.py` (existing, unchanged)

We need a snapshot of current output before touching anything.

- [ ] **Step 1: Create test file that captures baseline metrics**

```python
"""Regression tests — captures prove_maths output as baseline for refactor validation."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import prove_maths as pm

def _run_baseline():
    """Run simulation with all defaults, return final-day dict + summary metrics."""
    pm.DAYS = 730
    pm.DAILY_INTAKE = 300
    pm.SHRINKAGE = 0.42
    pm.ABSENCE_SHRINKAGE = 0.15
    pm.HOURS_PER_DAY = 7.0
    pm.UTILISATION = 1.00
    pm.PROFICIENCY = 1.0
    pm.DIARY_LIMIT = 7
    pm.BASE_EFFORT = 1.5
    pm.MIN_DIARY_DAYS = 0
    pm.MIN_DIARY_DAYS_NON_SRC = 3
    pm.HANDOFF_OVERHEAD = 0.15
    pm.HANDOFF_EFFORT_HOURS = 0.5
    pm.LATE_DEMAND_RATE = 0.08
    pm.SLICES_PER_DAY = 4
    pm.UNALLOCATED_BUFFER = 300
    pm.PARKINSON_FLOOR = 0.70
    pm.PARKINSON_FULL_PACE_QUEUE = 600
    pm.SRC_BOOST_MAX = 0.15
    pm.SRC_BOOST_DECAY_DAYS = 5
    pm.SRC_WINDOW = 3
    pm.SRC_EFFORT_RATIO = 0.7
    pm.PSD2_EXTENSION_RATE = 0.05
    result = pm.simulate(148)
    return result

def test_baseline_captures():
    """Sanity: simulation runs and produces 730 days of output."""
    result = _run_baseline()
    assert len(result) == 730
    final = result[-1]
    assert final["day"] == 729
    assert final["wip"] > 0
    assert "fca_breach_pct" in final
    assert "psd2_breach_pct" in final

def test_baseline_stability():
    """At 148 FTE with defaults, model reaches stable equilibrium."""
    result = _run_baseline()
    assert pm.is_stable(result), "Model should be stable at 148 FTE"

def test_baseline_kpis():
    """Capture specific KPI ranges that must hold after refactor."""
    result = _run_baseline()
    final = result[-1]
    # WIP should be in reasonable range (not exploding, not zero)
    assert 500 < final["wip"] < 2000, f"WIP {final['wip']} out of expected range"
    # FCA breaches should be near zero at 148 FTE
    assert final["fca_breach_pct"] < 0.01, f"FCA breach {final['fca_breach_pct']} too high"
    # Effective utilisation should be reasonable
    assert 0.70 < final["effective_util"] < 1.0, f"Util {final['effective_util']} unexpected"

if __name__ == "__main__":
    result = _run_baseline()
    final = result[-1]
    print(f"Day {final['day']}: WIP={final['wip']:.0f}, "
          f"FCA breach={final['fca_breach_pct']:.4f}, "
          f"PSD2 breach={final['psd2_breach_pct']:.4f}, "
          f"Util={final['effective_util']:.4f}")
    print("Baseline captured successfully.")
```

- [ ] **Step 2: Create tests directory**

Run: `mkdir -p tests`

- [ ] **Step 3: Run baseline tests**

Run: `cd "C:/Users/ROG/Projects/Complaints Planning - KISS" && python -m pytest tests/test_regression.py -v`
Expected: 3 PASSED

- [ ] **Step 4: Capture exact numeric baseline for later comparison**

Run: `cd "C:/Users/ROG/Projects/Complaints Planning - KISS" && python tests/test_regression.py`
Expected: Prints final-day metrics. **Save these numbers — they are the regression target.**

- [ ] **Step 5: Commit**

```bash
git add tests/test_regression.py
git commit -m "test: add regression baseline before modular refactor"
```

---

### Task 2: Create complaints_model/config.py — SimConfig dataclass

**Files:**
- Create: `complaints_model/__init__.py` (empty for now)
- Create: `complaints_model/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write test for SimConfig**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `complaints_model` doesn't exist yet

- [ ] **Step 3: Create package and config module**

Create `complaints_model/__init__.py`:
```python
"""Complaints Workforce Demand Model — modular package."""
```

Create `complaints_model/config.py`:
```python
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
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_config.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add complaints_model/__init__.py complaints_model/config.py tests/test_config.py
git commit -m "feat: add SimConfig dataclass with defaults and derived properties"
```

---

### Task 3: Create time_utils.py and cohort.py

**Files:**
- Create: `complaints_model/time_utils.py`
- Create: `complaints_model/cohort.py`
- Create: `tests/test_time_utils.py`
- Create: `tests/test_cohort.py`

- [ ] **Step 1: Write tests for time utilities**

```python
"""Tests for time utility functions."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from complaints_model.time_utils import is_workday, count_business_days_forward, count_business_days_signed, make_age

def test_is_workday():
    assert is_workday(0) == True   # Monday
    assert is_workday(4) == True   # Friday
    assert is_workday(5) == False  # Saturday
    assert is_workday(6) == False  # Sunday
    assert is_workday(7) == True   # Monday again

def test_count_business_days_forward():
    # 7 calendar days from Monday = 5 business days
    assert count_business_days_forward(0, 7) == 5
    # 1 calendar day from Friday = 0 business days (Saturday)
    assert count_business_days_forward(4, 1) == 0

def test_make_age_fca():
    # FCA uses calendar age — cal_age should equal reg_age
    cal, biz = make_age(10, "FCA")
    assert cal == 10

def test_make_age_psd2():
    # PSD2 uses business age — biz_age should equal reg_age
    cal, biz = make_age(10, "PSD2_15")
    assert biz == 10
```

- [ ] **Step 2: Write tests for Cohort**

```python
"""Tests for Cohort dataclass and merge."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from complaints_model.cohort import Cohort, merge_cohorts

def test_cohort_creation():
    c = Cohort(count=10, case_type="FCA", cal_age=5, biz_age=3,
               effort_per_case=1.5, is_src=False, arrival_day=0, allocation_day=None)
    assert c.count == 10
    assert c.last_worked_day is None  # default

def test_merge_cohorts():
    c1 = Cohort(count=10, case_type="FCA", cal_age=5, biz_age=3,
                effort_per_case=1.5, is_src=False, arrival_day=0, allocation_day=1)
    c2 = Cohort(count=5, case_type="FCA", cal_age=5, biz_age=3,
                effort_per_case=1.5, is_src=False, arrival_day=0, allocation_day=1)
    merged = merge_cohorts([c1, c2])
    assert len(merged) == 1
    assert merged[0].count == 15

def test_merge_different_types_not_merged():
    c1 = Cohort(count=10, case_type="FCA", cal_age=5, biz_age=3,
                effort_per_case=1.5, is_src=False, arrival_day=0, allocation_day=1)
    c2 = Cohort(count=5, case_type="PSD2_15", cal_age=5, biz_age=3,
                effort_per_case=1.5, is_src=False, arrival_day=0, allocation_day=1)
    merged = merge_cohorts([c1, c2])
    assert len(merged) == 2
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_time_utils.py tests/test_cohort.py -v`
Expected: FAIL — modules don't exist

- [ ] **Step 4: Create time_utils.py**

Extract from prove_maths.py lines 237-335:

```python
"""Time and calendar utilities for the simulation."""
from __future__ import annotations


def is_workday(day: int) -> bool:
    """Monday-Friday = workday (day 0 = Monday)."""
    return (day % 7) < 5


def count_business_days_forward(sim_day: int, calendar_days: int) -> int:
    """Count business days in the next `calendar_days` from sim_day."""
    return sum(1 for d in range(sim_day + 1, sim_day + 1 + calendar_days) if is_workday(d))


def count_business_days_signed(sim_day: int, remaining_cal_days: int) -> int:
    """Count business days for signed calendar day offsets (past or future)."""
    if remaining_cal_days >= 0:
        return count_business_days_forward(sim_day, remaining_cal_days)
    else:
        return -sum(1 for d in range(sim_day, sim_day + remaining_cal_days, -1) if is_workday(d))


def regulatory_age(case_type: str, cal_age: int, biz_age: int) -> int:
    """Regulatory age: FCA counts calendar days, PSD2 counts business days."""
    if case_type == "FCA":
        return cal_age
    return biz_age


def make_age(reg_age: int, case_type: str) -> tuple[int, int]:
    """Reconstruct (cal_age, biz_age) from regulatory age and case type.

    Approximation: assumes 5/7 ratio for business days.
    """
    if case_type == "FCA":
        cal_age = reg_age
        biz_age = round(reg_age * 5 / 7)
    else:
        biz_age = reg_age
        cal_age = round(reg_age * 7 / 5)
    return cal_age, biz_age
```

- [ ] **Step 5: Create cohort.py**

Extract Cohort dataclass (with last_worked_day from strategy_model) and merge_cohorts:

```python
"""Cohort dataclass — the atomic unit of the simulation."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Cohort:
    count: float
    case_type: str
    cal_age: int
    biz_age: int
    effort_per_case: float
    is_src: bool
    arrival_day: int
    allocation_day: int | None
    seeded: bool = False
    last_worked_day: int | None = None


def merge_cohorts(cohorts: list[Cohort]) -> list[Cohort]:
    """Combine cohorts with identical attributes (except count) to reduce list size."""
    buckets: dict[tuple, Cohort] = {}
    for c in cohorts:
        key = (c.case_type, c.cal_age, c.biz_age, c.is_src,
               c.arrival_day, c.allocation_day, c.seeded, c.last_worked_day)
        if key in buckets:
            buckets[key].count += c.count
        else:
            buckets[key] = Cohort(
                count=c.count, case_type=c.case_type, cal_age=c.cal_age,
                biz_age=c.biz_age, effort_per_case=c.effort_per_case,
                is_src=c.is_src, arrival_day=c.arrival_day,
                allocation_day=c.allocation_day, seeded=c.seeded,
                last_worked_day=c.last_worked_day,
            )
    return list(buckets.values())
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_time_utils.py tests/test_cohort.py -v`
Expected: All PASSED

- [ ] **Step 7: Commit**

```bash
git add complaints_model/time_utils.py complaints_model/cohort.py tests/test_time_utils.py tests/test_cohort.py
git commit -m "feat: add time_utils and cohort modules"
```

---

### Task 4: Create regulatory.py and effort.py

**Files:**
- Create: `complaints_model/regulatory.py`
- Create: `complaints_model/effort.py`
- Create: `tests/test_regulatory.py`
- Create: `tests/test_effort.py`

- [ ] **Step 1: Write tests for regulatory**

```python
"""Tests for regulatory deadline and target calculations."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from complaints_model.cohort import Cohort
from complaints_model.regulatory import (
    remaining_workdays_to_target, remaining_workdays_to_deadline,
    apply_psd2_extensions, SERVICE_TARGETS, REGULATORY_DEADLINES,
)

def test_service_targets():
    assert SERVICE_TARGETS["FCA"] == 21
    assert SERVICE_TARGETS["PSD2_15"] == 10

def test_remaining_to_target_fca():
    c = Cohort(count=1, case_type="FCA", cal_age=10, biz_age=7,
               effort_per_case=1.5, is_src=False, arrival_day=0, allocation_day=0)
    remaining = remaining_workdays_to_target(c, sim_day=14)
    assert remaining > 0  # 21 cal day target - 10 cal age = 11 days remaining

def test_remaining_to_deadline_fca():
    c = Cohort(count=1, case_type="FCA", cal_age=50, biz_age=35,
               effort_per_case=1.5, is_src=False, arrival_day=0, allocation_day=0)
    remaining = remaining_workdays_to_deadline(c, sim_day=70)
    assert remaining >= 0  # 56 - 50 = 6 cal days remaining

def test_psd2_extension():
    """PSD2_15 cases at biz_age 15 get 5% extended to PSD2_35."""
    pool = [Cohort(count=100, case_type="PSD2_15", cal_age=21, biz_age=15,
                   effort_per_case=1.5, is_src=False, arrival_day=0, allocation_day=0)]
    result = apply_psd2_extensions(pool, psd2_extension_rate=0.05)
    types = {c.case_type: c.count for c in result}
    assert abs(types.get("PSD2_35", 0) - 5.0) < 0.01
    assert abs(types.get("PSD2_15", 0) - 95.0) < 0.01
```

- [ ] **Step 2: Write tests for effort**

```python
"""Tests for effort/burden calculations."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from complaints_model.cohort import Cohort
from complaints_model.effort import burden_mult, case_effort

def test_burden_young_cases():
    assert burden_mult(0) == 0.7   # 0-3 band
    assert burden_mult(3) == 0.7

def test_burden_mid_cases():
    assert burden_mult(10) == 1.0  # 4-15 band

def test_burden_old_cases():
    assert burden_mult(40) == 2.0  # 36-56 band

def test_case_effort_src():
    """SRC cases within window get 0.7x discount."""
    c = Cohort(count=1, case_type="FCA", cal_age=2, biz_age=1,
               effort_per_case=0.0, is_src=True, arrival_day=0, allocation_day=0)
    effort = case_effort(c, base_effort=1.5, src_effort_ratio=0.7, src_window=3)
    # reg_age=2 (FCA=cal), burden=0.7, SRC discount=0.7
    assert abs(effort - 1.5 * 0.7 * 0.7) < 0.01

def test_case_effort_non_src():
    """Non-SRC cases don't get discount."""
    c = Cohort(count=1, case_type="FCA", cal_age=10, biz_age=7,
               effort_per_case=0.0, is_src=False, arrival_day=0, allocation_day=0)
    effort = case_effort(c, base_effort=1.5, src_effort_ratio=0.7, src_window=3)
    # reg_age=10 (FCA=cal), burden=1.0, no SRC discount
    assert abs(effort - 1.5 * 1.0) < 0.01
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_regulatory.py tests/test_effort.py -v`
Expected: FAIL

- [ ] **Step 4: Create regulatory.py**

Extract from prove_maths.py — deadline constants, remaining_workdays functions, PSD2 extensions:

```python
"""Regulatory deadlines, service targets, and PSD2 extension logic."""
from __future__ import annotations

from .cohort import Cohort
from .time_utils import regulatory_age, count_business_days_signed

SERVICE_TARGETS = {"FCA": 21, "PSD2_15": 10, "PSD2_35": 25}
REGULATORY_DEADLINES = {"FCA": 56, "PSD2_15": 15, "PSD2_35": 35}
BREACH_TARGETS = {"FCA": 0.03, "PSD2": 0.10}


def remaining_workdays_to_target(cohort: Cohort, sim_day: int) -> int:
    """Workdays remaining until service target for this cohort."""
    target = SERVICE_TARGETS[cohort.case_type]
    reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
    if cohort.case_type == "FCA":
        remaining_cal = target - reg_age
        return count_business_days_signed(sim_day, remaining_cal)
    else:
        return target - reg_age


def remaining_workdays_to_deadline(cohort: Cohort, sim_day: int) -> int:
    """Workdays remaining until regulatory deadline for this cohort."""
    deadline = REGULATORY_DEADLINES[cohort.case_type]
    reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
    if cohort.case_type == "FCA":
        remaining_cal = deadline - reg_age
        return count_business_days_signed(sim_day, remaining_cal)
    else:
        return deadline - reg_age


def apply_psd2_extensions(pool: list[Cohort], psd2_extension_rate: float) -> list[Cohort]:
    """At biz_age 15, extend a fraction of PSD2_15 cases to PSD2_35."""
    result: list[Cohort] = []
    for cohort in pool:
        if cohort.case_type == "PSD2_15" and cohort.biz_age == 15:
            extension_count = cohort.count * psd2_extension_rate
            stay_count = cohort.count - extension_count
            if stay_count > 0:
                result.append(Cohort(
                    count=stay_count, case_type="PSD2_15",
                    cal_age=cohort.cal_age, biz_age=cohort.biz_age,
                    effort_per_case=cohort.effort_per_case, is_src=cohort.is_src,
                    arrival_day=cohort.arrival_day, allocation_day=cohort.allocation_day,
                    seeded=cohort.seeded, last_worked_day=cohort.last_worked_day,
                ))
            if extension_count > 0:
                result.append(Cohort(
                    count=extension_count, case_type="PSD2_35",
                    cal_age=cohort.cal_age, biz_age=cohort.biz_age,
                    effort_per_case=cohort.effort_per_case, is_src=cohort.is_src,
                    arrival_day=cohort.arrival_day, allocation_day=cohort.allocation_day,
                    seeded=cohort.seeded, last_worked_day=cohort.last_worked_day,
                ))
        else:
            result.append(cohort)
    return result
```

- [ ] **Step 5: Create effort.py**

Extract from prove_maths.py — burden bands and case_effort:

```python
"""Effort and burden calculations — how much work each case costs."""
from __future__ import annotations

from .cohort import Cohort
from .time_utils import regulatory_age

BURDEN = {
    (0, 3): 0.7,
    (4, 15): 1.0,
    (16, 35): 1.5,
    (36, 56): 2.0,
    (57, 999): 2.5,
}


def burden_mult(reg_age: int) -> float:
    """Effort multiplier based on case regulatory age."""
    for (lo, hi), mult in BURDEN.items():
        if lo <= reg_age <= hi:
            return mult
    return 1.0


def case_effort(cohort: Cohort, base_effort: float, src_effort_ratio: float, src_window: int) -> float:
    """Calculate productive hours per case, accounting for burden and SRC discount."""
    reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
    effort = base_effort * burden_mult(reg_age)
    if cohort.is_src and reg_age <= src_window:
        effort *= src_effort_ratio
    return effort
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_regulatory.py tests/test_effort.py -v`
Expected: All PASSED

- [ ] **Step 7: Commit**

```bash
git add complaints_model/regulatory.py complaints_model/effort.py tests/test_regulatory.py tests/test_effort.py
git commit -m "feat: add regulatory and effort modules"
```

---

### Task 5: Create strategies.py

**Files:**
- Create: `complaints_model/strategies.py`
- Create: `tests/test_strategies.py`

- [ ] **Step 1: Write tests for strategy registry**

```python
"""Tests for strategy sort-key functions."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from complaints_model.strategies import STRATEGIES, get_sort_key
from complaints_model.cohort import Cohort

def test_all_strategies_registered():
    expected = {"nearest_deadline", "nearest_target", "youngest_first",
                "oldest_first", "psd2_priority", "longest_wait",
                "lowest_effort", "longest_untouched"}
    assert set(STRATEGIES.keys()) == expected

def test_get_sort_key_returns_callable():
    fn = get_sort_key("nearest_target")
    assert callable(fn)

def test_youngest_first_sorts_by_age_ascending():
    fn = get_sort_key("youngest_first")
    young = Cohort(count=1, case_type="FCA", cal_age=2, biz_age=1,
                   effort_per_case=0, is_src=False, arrival_day=0, allocation_day=0)
    old = Cohort(count=1, case_type="FCA", cal_age=20, biz_age=14,
                 effort_per_case=0, is_src=False, arrival_day=0, allocation_day=0)
    cfg_stub = type("Cfg", (), {"base_effort": 1.5, "src_effort_ratio": 0.7, "src_window": 3})()
    assert fn(young, 0, cfg_stub) < fn(old, 0, cfg_stub)

def test_oldest_first_sorts_by_age_descending():
    fn = get_sort_key("oldest_first")
    young = Cohort(count=1, case_type="FCA", cal_age=2, biz_age=1,
                   effort_per_case=0, is_src=False, arrival_day=0, allocation_day=0)
    old = Cohort(count=1, case_type="FCA", cal_age=20, biz_age=14,
                 effort_per_case=0, is_src=False, arrival_day=0, allocation_day=0)
    cfg_stub = type("Cfg", (), {"base_effort": 1.5, "src_effort_ratio": 0.7, "src_window": 3})()
    assert fn(young, 0, cfg_stub) > fn(old, 0, cfg_stub)

def test_invalid_strategy_raises():
    try:
        get_sort_key("nonexistent")
        assert False, "Should have raised KeyError"
    except KeyError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_strategies.py -v`
Expected: FAIL

- [ ] **Step 3: Create strategies.py**

Merge strategy registry from strategy_model.py with config-aware sort keys:

```python
"""Allocation and work prioritisation strategies.

Each strategy is a sort-key function: (cohort, sim_day, cfg) -> comparable value.
Lower values = higher priority (sorted ascending).
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from .time_utils import regulatory_age
from .regulatory import remaining_workdays_to_target, remaining_workdays_to_deadline
from .effort import case_effort

if TYPE_CHECKING:
    from .config import SimConfig
    from .cohort import Cohort


def _nearest_deadline_key(c: Cohort, sim_day: int, cfg: SimConfig):
    return remaining_workdays_to_deadline(c, sim_day)


def _nearest_target_key(c: Cohort, sim_day: int, cfg: SimConfig):
    target_remaining = remaining_workdays_to_target(c, sim_day)
    deadline_remaining = remaining_workdays_to_deadline(c, sim_day)
    return (target_remaining, deadline_remaining)


def _youngest_first_key(c: Cohort, sim_day: int, cfg: SimConfig):
    return regulatory_age(c.case_type, c.cal_age, c.biz_age)


def _oldest_first_key(c: Cohort, sim_day: int, cfg: SimConfig):
    return -regulatory_age(c.case_type, c.cal_age, c.biz_age)


def _psd2_priority_key(c: Cohort, sim_day: int, cfg: SimConfig):
    is_psd2 = 0 if c.case_type.startswith("PSD2") else 1
    return (is_psd2, remaining_workdays_to_deadline(c, sim_day))


def _longest_wait_key(c: Cohort, sim_day: int, cfg: SimConfig):
    return c.arrival_day  # lower arrival_day = waited longer = higher priority


def _lowest_effort_key(c: Cohort, sim_day: int, cfg: SimConfig):
    return case_effort(c, cfg.base_effort, cfg.src_effort_ratio, cfg.src_window)


def _longest_untouched_key(c: Cohort, sim_day: int, cfg: SimConfig):
    return c.last_worked_day if c.last_worked_day is not None else -999999


STRATEGIES = {
    "nearest_deadline": _nearest_deadline_key,
    "nearest_target": _nearest_target_key,
    "youngest_first": _youngest_first_key,
    "oldest_first": _oldest_first_key,
    "psd2_priority": _psd2_priority_key,
    "longest_wait": _longest_wait_key,
    "lowest_effort": _lowest_effort_key,
    "longest_untouched": _longest_untouched_key,
}


def get_sort_key(strategy_name: str):
    """Look up a strategy sort-key function by name. Raises KeyError if unknown."""
    return STRATEGIES[strategy_name]
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_strategies.py -v`
Expected: All PASSED

- [ ] **Step 5: Commit**

```bash
git add complaints_model/strategies.py tests/test_strategies.py
git commit -m "feat: add strategy registry with 8 allocation/work strategies"
```

---

### Task 6: Create intake.py

**Files:**
- Create: `complaints_model/intake.py`
- Create: `tests/test_intake.py`

- [ ] **Step 1: Write tests for intake**

```python
"""Tests for intake generation and pool seeding."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from complaints_model.intake import (
    intake_distribution, starting_wip_distribution, seed_pool,
    INTAKE_PROPORTIONS, INTAKE_AGE_PROFILE, SRC_RATES,
)
from complaints_model.config import SimConfig

def test_intake_proportions():
    assert abs(INTAKE_PROPORTIONS["FCA"] - 0.70) < 0.001
    assert abs(INTAKE_PROPORTIONS["PSD2_15"] - 0.30) < 0.001

def test_intake_distribution_total():
    dist = intake_distribution(300)
    total = sum(count for _, count in dist)
    assert abs(total - 300) < 0.1

def test_age_profile_sums_to_one():
    total = sum(INTAKE_AGE_PROFILE.values())
    assert abs(total - 1.0) < 0.001

def test_seed_pool_unallocated():
    cfg = SimConfig()
    pool = seed_pool(1000, allocated=False, cfg=cfg)
    total = sum(c.count for c in pool)
    assert abs(total - 1000) < 1.0
    assert all(c.allocation_day is None for c in pool)

def test_seed_pool_allocated():
    cfg = SimConfig()
    pool = seed_pool(1000, allocated=True, cfg=cfg)
    total = sum(c.count for c in pool)
    assert abs(total - 1000) < 1.0
    assert all(c.allocation_day is not None for c in pool)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_intake.py -v`
Expected: FAIL

- [ ] **Step 3: Create intake.py**

Extract from prove_maths.py — intake constants, distribution functions, seed_pool:

```python
"""Intake generation, age profiles, and initial pool seeding."""
from __future__ import annotations
from typing import TYPE_CHECKING

from .cohort import Cohort
from .time_utils import make_age
from .effort import case_effort

if TYPE_CHECKING:
    from .config import SimConfig

INTAKE_PROPORTIONS = {"FCA": 0.70, "PSD2_15": 0.30}

SRC_RATES = {"FCA": 0.40, "PSD2_15": 0.40, "PSD2_35": 0.10}

INTAKE_AGE_PROFILE = {
    0: 0.85,
    1: 0.02, 2: 0.02, 3: 0.02, 4: 0.02, 5: 0.02,
    **{age: 0.04 / 15 for age in range(6, 21)},
    40: 0.01,
}

# AM/PM allocation split — drives blended SRC closure distribution
SRC_DIST = (0.22, 0.50, 0.28)


def intake_distribution(total_cases: float) -> list[tuple[int, float]]:
    """Distribute total cases across age profile. Returns [(reg_age, count), ...]."""
    return [(age, total_cases * frac) for age, frac in INTAKE_AGE_PROFILE.items()]


def starting_wip_distribution(total_cases: float) -> list[tuple[int, float]]:
    """Generate pre-aged WIP for simulation seeding."""
    return [(age, total_cases * frac) for age, frac in INTAKE_AGE_PROFILE.items()]


def seed_pool(total_cases: float, allocated: bool, cfg: SimConfig) -> list[Cohort]:
    """Create initial cohort pool for simulation warm-up."""
    pool: list[Cohort] = []
    for case_type, type_frac in INTAKE_PROPORTIONS.items():
        type_total = total_cases * type_frac
        for reg_age, count in starting_wip_distribution(type_total):
            cal_age, biz_age = make_age(reg_age, case_type)
            is_src = reg_age <= cfg.src_window
            alloc_day = -cal_age if allocated else None
            c = Cohort(
                count=count,
                case_type=case_type,
                cal_age=cal_age,
                biz_age=biz_age,
                effort_per_case=0.0,
                is_src=is_src,
                arrival_day=-cal_age,
                allocation_day=alloc_day,
                seeded=True,
                last_worked_day=alloc_day,
            )
            pool.append(c)
    return pool
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_intake.py -v`
Expected: All PASSED

- [ ] **Step 5: Commit**

```bash
git add complaints_model/intake.py tests/test_intake.py
git commit -m "feat: add intake module with age profiles and pool seeding"
```

---

### Task 7: Create allocation.py and work.py

**Files:**
- Create: `complaints_model/allocation.py`
- Create: `complaints_model/work.py`
- Create: `tests/test_allocation.py`
- Create: `tests/test_work.py`

These are the two most complex functions — the core of the simulation engine. They need careful extraction.

- [ ] **Step 1: Write tests for allocation**

```python
"""Tests for allocation logic."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from complaints_model.allocation import allocate_up_to_capacity
from complaints_model.cohort import Cohort
from complaints_model.config import SimConfig

def test_allocate_moves_cases_to_diary():
    cfg = SimConfig(fte=10, diary_limit=7, allocation_strategy="nearest_target")
    unalloc = [Cohort(count=100, case_type="FCA", cal_age=5, biz_age=3,
                      effort_per_case=0, is_src=False, arrival_day=0, allocation_day=None)]
    alloc = []
    max_slots = cfg.max_diary_slots
    new_alloc, remaining, metrics = allocate_up_to_capacity(
        unalloc, alloc, sim_day=7, max_slots=max_slots, cfg=cfg
    )
    total_allocated = sum(c.count for c in new_alloc)
    total_remaining = sum(c.count for c in remaining)
    assert total_allocated > 0
    assert total_allocated + total_remaining == 100

def test_allocate_respects_diary_limit():
    cfg = SimConfig(fte=2, diary_limit=3)  # 2 * 0.85 * 3 = 5.1 slots
    unalloc = [Cohort(count=100, case_type="FCA", cal_age=5, biz_age=3,
                      effort_per_case=0, is_src=False, arrival_day=0, allocation_day=None)]
    alloc = []
    max_slots = cfg.max_diary_slots
    new_alloc, remaining, _ = allocate_up_to_capacity(
        unalloc, alloc, sim_day=7, max_slots=max_slots, cfg=cfg
    )
    total_allocated = sum(c.count for c in new_alloc)
    assert total_allocated <= max_slots + 0.01  # can't exceed diary capacity
```

- [ ] **Step 2: Write tests for work processing**

```python
"""Tests for work/closure logic."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from complaints_model.work import process_work_slice
from complaints_model.cohort import Cohort
from complaints_model.config import SimConfig

def test_process_closes_cases():
    cfg = SimConfig(base_effort=1.5, work_strategy="nearest_target")
    alloc = [Cohort(count=10, case_type="FCA", cal_age=10, biz_age=7,
                    effort_per_case=0, is_src=False, arrival_day=0, allocation_day=1)]
    remaining, closures, _, close_sums, _ = process_work_slice(
        alloc, sim_day=14, work_budget=50.0, cfg=cfg
    )
    assert closures > 0
    total_remaining = sum(c.count for c in remaining)
    assert total_remaining < 10

def test_src_cases_close_faster():
    """SRC cases cost less effort so more close per budget unit."""
    cfg = SimConfig(base_effort=1.5, src_effort_ratio=0.7)
    src = [Cohort(count=10, case_type="FCA", cal_age=2, biz_age=1,
                  effort_per_case=0, is_src=True, arrival_day=0, allocation_day=0)]
    non_src = [Cohort(count=10, case_type="FCA", cal_age=10, biz_age=7,
                      effort_per_case=0, is_src=False, arrival_day=0, allocation_day=0)]
    _, src_closures, _, _, _ = process_work_slice(src, sim_day=3, work_budget=10.0, cfg=cfg)
    _, non_src_closures, _, _, _ = process_work_slice(non_src, sim_day=14, work_budget=10.0, cfg=cfg)
    assert src_closures > non_src_closures
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_allocation.py tests/test_work.py -v`
Expected: FAIL

- [ ] **Step 4: Create allocation.py**

Extract allocate_up_to_capacity from prove_maths.py (lines 523-622), replacing global refs with cfg params and using strategy sort keys:

```python
"""Allocation engine — moves cases from unallocated queue into handler diaries."""
from __future__ import annotations
from typing import TYPE_CHECKING

from .cohort import Cohort
from .time_utils import regulatory_age, is_workday
from .effort import case_effort
from .strategies import get_sort_key
from .intake import SRC_RATES, SRC_DIST

if TYPE_CHECKING:
    from .config import SimConfig


def allocate_up_to_capacity(
    unallocated: list[Cohort],
    allocated: list[Cohort],
    sim_day: int,
    max_slots: float,
    cfg: SimConfig,
    avg_alloc_delay: float = 1.0,
) -> tuple[list[Cohort], list[Cohort], dict]:
    """Move cases from unallocated pool into diary slots.

    Returns: (newly_allocated, remaining_unallocated, metrics_dict)
    """
    current_allocated = sum(c.count for c in allocated)
    free_slots = max(0, max_slots - current_allocated)

    if free_slots <= 0 or not unallocated:
        return [], unallocated, {"allocated": 0, "weighted_delay": 0}

    sort_fn = get_sort_key(cfg.allocation_strategy)
    sorted_unalloc = sorted(unallocated, key=lambda c: sort_fn(c, sim_day, cfg))

    newly_allocated: list[Cohort] = []
    remaining: list[Cohort] = []
    total_allocated = 0.0
    weighted_delay_total = 0.0

    # Dynamic SRC boost based on allocation delay
    src_boost = cfg.src_boost_max * (0.5 ** (avg_alloc_delay / cfg.src_boost_decay_days))

    for cohort in sorted_unalloc:
        if total_allocated >= free_slots:
            remaining.append(cohort)
            continue

        can_take = min(cohort.count, free_slots - total_allocated)
        leftover = cohort.count - can_take

        if can_take > 0:
            reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
            base_src_rate = SRC_RATES.get(cohort.case_type, 0.0)
            effective_src_rate = min(base_src_rate + src_boost, 0.95) if reg_age <= cfg.src_window else 0.0
            src_count = can_take * effective_src_rate
            non_src_count = can_take - src_count

            delay = cohort.cal_age  # days since arrival = allocation delay
            weighted_delay_total += can_take * delay

            if src_count > 0:
                # Schedule SRC closures across SRC_DIST days
                for offset, frac in enumerate(SRC_DIST):
                    close_day = sim_day + offset
                    close_count = src_count * frac
                    if close_count > 0:
                        newly_allocated.append(Cohort(
                            count=close_count, case_type=cohort.case_type,
                            cal_age=cohort.cal_age, biz_age=cohort.biz_age,
                            effort_per_case=0.0, is_src=True,
                            arrival_day=cohort.arrival_day, allocation_day=sim_day,
                            seeded=cohort.seeded, last_worked_day=sim_day,
                        ))

            if non_src_count > 0:
                newly_allocated.append(Cohort(
                    count=non_src_count, case_type=cohort.case_type,
                    cal_age=cohort.cal_age, biz_age=cohort.biz_age,
                    effort_per_case=0.0, is_src=False,
                    arrival_day=cohort.arrival_day, allocation_day=sim_day,
                    seeded=cohort.seeded, last_worked_day=sim_day,
                ))

            total_allocated += can_take

        if leftover > 0:
            remaining.append(Cohort(
                count=leftover, case_type=cohort.case_type,
                cal_age=cohort.cal_age, biz_age=cohort.biz_age,
                effort_per_case=cohort.effort_per_case, is_src=cohort.is_src,
                arrival_day=cohort.arrival_day, allocation_day=cohort.allocation_day,
                seeded=cohort.seeded, last_worked_day=cohort.last_worked_day,
            ))

    return newly_allocated, remaining, {
        "allocated": total_allocated,
        "weighted_delay": weighted_delay_total,
    }
```

**IMPORTANT:** This is a skeleton showing the structure. The actual implementation MUST be extracted line-for-line from prove_maths.py lines 523-622 (and strategy_model.py lines 215-317 for strategy-aware sorting), preserving every calculation exactly. The engineer should diff against the original to ensure zero logic changes.

- [ ] **Step 5: Create work.py**

Extract process_work_slice from prove_maths.py (lines 625-732), replacing global refs with cfg params:

```python
"""Work engine — handlers pick cases from diary and close them."""
from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING

from .cohort import Cohort
from .time_utils import regulatory_age, is_workday
from .effort import case_effort
from .strategies import get_sort_key
from .regulatory import REGULATORY_DEADLINES

if TYPE_CHECKING:
    from .config import SimConfig


def process_work_slice(
    allocated: list[Cohort],
    sim_day: int,
    work_budget: float,
    cfg: SimConfig,
) -> tuple[list[Cohort], float, dict, dict, dict]:
    """Process one work slice: close cases from diary within budget.

    Returns: (remaining_allocated, total_closures, closures_by_type, close_sums, breached_closures_by_type)
    """
    sort_fn = get_sort_key(cfg.work_strategy)

    # Separate SRC-eligible (close first) from non-SRC
    src_eligible = []
    non_src = []
    for c in allocated:
        reg_age = regulatory_age(c.case_type, c.cal_age, c.biz_age)
        if c.is_src and reg_age <= cfg.src_window:
            # Check min diary days for SRC (= min_diary_days, typically 0)
            if c.allocation_day is not None:
                days_in_diary = sim_day - c.allocation_day
                biz_days_in_diary = sum(1 for d in range(c.allocation_day, sim_day) if is_workday(d))
                if biz_days_in_diary >= cfg.min_diary_days:
                    src_eligible.append(c)
                else:
                    non_src.append(c)
            else:
                src_eligible.append(c)
        else:
            non_src.append(c)

    # Sort each group by work strategy
    src_eligible.sort(key=lambda c: sort_fn(c, sim_day, cfg))
    non_src.sort(key=lambda c: sort_fn(c, sim_day, cfg))

    # Process SRC first, then non-SRC
    work_order = src_eligible + non_src

    remaining: list[Cohort] = []
    closures_total = 0.0
    closures_by_type: dict[str, float] = defaultdict(float)
    close_sums: dict[str, dict] = defaultdict(lambda: {"count": 0.0, "age_sum": 0.0, "sys_sum": 0.0, "src_count": 0.0})
    breached_closures_by_type: dict[str, float] = defaultdict(float)
    budget_left = work_budget

    for cohort in work_order:
        if budget_left <= 0:
            remaining.append(cohort)
            continue

        # Check minimum diary days for non-SRC
        if not cohort.is_src and cohort.allocation_day is not None:
            biz_days_in_diary = sum(1 for d in range(cohort.allocation_day, sim_day) if is_workday(d))
            if biz_days_in_diary < cfg.min_diary_days_non_src:
                remaining.append(cohort)
                continue

        effort = case_effort(cohort, cfg.base_effort, cfg.src_effort_ratio, cfg.src_window)

        # Apply handoff overhead
        handoff_effort = cfg.handoff_overhead * cfg.handoff_effort_hours
        effective_effort = effort + handoff_effort

        can_close = min(cohort.count, budget_left / effective_effort) if effective_effort > 0 else cohort.count
        leftover = cohort.count - can_close

        if can_close > 0:
            budget_left -= can_close * effective_effort
            closures_total += can_close
            closures_by_type[cohort.case_type] += can_close

            reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
            sys_time = sim_day - cohort.arrival_day if cohort.arrival_day >= 0 else cohort.cal_age
            close_sums[cohort.case_type]["count"] += can_close
            close_sums[cohort.case_type]["age_sum"] += can_close * reg_age
            close_sums[cohort.case_type]["sys_sum"] += can_close * sys_time
            if cohort.is_src:
                close_sums[cohort.case_type]["src_count"] += can_close

            deadline = REGULATORY_DEADLINES.get(cohort.case_type, 999)
            if reg_age > deadline:
                breached_closures_by_type[cohort.case_type] += can_close

        if leftover > 0:
            remaining.append(Cohort(
                count=leftover, case_type=cohort.case_type,
                cal_age=cohort.cal_age, biz_age=cohort.biz_age,
                effort_per_case=cohort.effort_per_case, is_src=cohort.is_src,
                arrival_day=cohort.arrival_day, allocation_day=cohort.allocation_day,
                seeded=cohort.seeded, last_worked_day=cohort.last_worked_day,
            ))

    return remaining, closures_total, dict(closures_by_type), close_sums, dict(breached_closures_by_type)
```

**IMPORTANT:** Same as allocation.py — this is a structural skeleton. The actual implementation MUST be extracted line-for-line from prove_maths.py lines 625-732, preserving every calculation. Diff against original to verify.

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_allocation.py tests/test_work.py -v`
Expected: All PASSED

- [ ] **Step 7: Commit**

```bash
git add complaints_model/allocation.py complaints_model/work.py tests/test_allocation.py tests/test_work.py
git commit -m "feat: add allocation and work engines with strategy support"
```

---

### Task 8: Create simulation.py — the main loop

**Files:**
- Create: `complaints_model/simulation.py`
- Create: `tests/test_simulation.py`

- [ ] **Step 1: Write tests for simulation**

```python
"""Tests for main simulation loop."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from complaints_model.simulation import simulate
from complaints_model.config import SimConfig

def test_simulate_returns_daily_records():
    cfg = SimConfig(days=30, fte=148)
    result = simulate(cfg)
    assert len(result) == 30
    assert all("day" in r for r in result)
    assert all("wip" in r for r in result)

def test_simulate_wip_positive():
    cfg = SimConfig(days=100, fte=148)
    result = simulate(cfg)
    assert all(r["wip"] > 0 for r in result)

def test_simulate_with_strategy():
    cfg = SimConfig(days=100, fte=148, allocation_strategy="youngest_first", work_strategy="oldest_first")
    result = simulate(cfg)
    assert len(result) == 100

def test_simulate_max_wip_circuit_breaker():
    """Very low FTE should eventually hit circuit breaker or produce huge WIP."""
    cfg = SimConfig(days=200, fte=50)
    result = simulate(cfg, max_wip=10000)
    # Should either stop early or have large final WIP
    final = result[-1]
    assert final["wip"] > 1000 or len(result) < 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_simulation.py -v`
Expected: FAIL

- [ ] **Step 3: Create simulation.py**

Extract simulate() from prove_maths.py (lines 735-932). This is the main loop — Parkinson's Law pressure calc, daily intake injection, age advancement, work slices with allocate+process+refill, and daily metrics recording. All global references become `cfg.field_name`:

```python
"""Main simulation loop — orchestrates daily complaint flow."""
from __future__ import annotations
from collections import defaultdict
from statistics import mean

from .config import SimConfig
from .cohort import Cohort, merge_cohorts
from .time_utils import is_workday, regulatory_age, make_age
from .effort import case_effort
from .regulatory import apply_psd2_extensions, REGULATORY_DEADLINES
from .intake import (
    intake_distribution, seed_pool,
    INTAKE_PROPORTIONS, SRC_RATES, SRC_DIST,
)
from .allocation import allocate_up_to_capacity
from .work import process_work_slice
from .metrics import count_by_type, count_breaches, count_over_target, count_age_bands


def simulate(cfg: SimConfig, util_override: float | None = None, max_wip: float = 50_000) -> list[dict]:
    """Run the discrete-event simulation.

    Args:
        cfg: All simulation parameters.
        util_override: Override max utilisation (for testing).
        max_wip: Circuit breaker — stop if WIP exceeds this.

    Returns:
        List of daily metric dicts, one per simulated day.
    """
    max_utilisation = util_override if util_override is not None else cfg.utilisation
    on_desk_productive = cfg.productive_fte
    max_slots = cfg.max_diary_slots
    desired_wip = max_slots + cfg.unallocated_buffer
    full_pace_queue = cfg.parkinson_full_pace_queue

    unallocated = seed_pool(2500 * 0.25, allocated=False, cfg=cfg)
    allocated = seed_pool(2500 * 0.75, allocated=True, cfg=cfg)
    src_schedule: dict[int, dict[str, float]] = {}
    results: list[dict] = []
    workday_num = 0

    for day in range(cfg.days):
        workday = is_workday(day)

        # Parkinson's Law pressure
        current_unalloc = sum(c.count for c in unallocated)
        pressure = min(current_unalloc / full_pace_queue, 1.0) if full_pace_queue > 0 else 1.0
        effective_util = cfg.parkinson_floor + (max_utilisation - cfg.parkinson_floor) * pressure
        productive_hours = on_desk_productive * cfg.hours_per_day * effective_util * cfg.proficiency * (1 - cfg.late_demand_rate)
        slice_budget = productive_hours / cfg.slices_per_day if cfg.slices_per_day > 0 else 0.0

        # Age all cohorts
        for cohort in unallocated + allocated:
            cohort.cal_age += 1
            if workday:
                cohort.biz_age += 1

        # Inject daily intake on workdays
        if workday:
            for case_type, proportion in INTAKE_PROPORTIONS.items():
                for reg_age, count in intake_distribution(cfg.daily_intake * proportion):
                    cal_age, biz_age = make_age(reg_age, case_type)
                    unallocated.append(Cohort(
                        count=count, case_type=case_type,
                        cal_age=cal_age, biz_age=biz_age,
                        effort_per_case=0.0, is_src=False,
                        arrival_day=day, allocation_day=None, seeded=False,
                    ))

        # PSD2 extensions
        if workday:
            unallocated = apply_psd2_extensions(unallocated, cfg.psd2_extension_rate)
            allocated = apply_psd2_extensions(allocated, cfg.psd2_extension_rate)

        # Work slices (allocate, work, refill)
        allocations_total = 0.0
        weighted_delay_total = 0.0
        closures_total = 0.0
        closures_by_type = defaultdict(float)
        close_sums = defaultdict(lambda: {"count": 0.0, "age_sum": 0.0, "sys_sum": 0.0, "src_count": 0.0})
        breached_closures_by_type = defaultdict(float)

        if workday:
            workday_num += 1
            # Calculate avg allocation delay for SRC boost
            recent_delays = [r.get("avg_alloc_delay", 1.0) for r in results[-5:]] if results else [1.0]
            avg_alloc_delay = mean(recent_delays)

            for _ in range(cfg.slices_per_day):
                # Allocate
                new_alloc, unallocated, alloc_metrics = allocate_up_to_capacity(
                    unallocated, allocated, sim_day=day,
                    max_slots=max_slots, cfg=cfg,
                    avg_alloc_delay=avg_alloc_delay,
                )
                allocated.extend(new_alloc)
                allocations_total += alloc_metrics["allocated"]
                weighted_delay_total += alloc_metrics["weighted_delay"]

                # Work
                allocated, slice_closures, slice_by_type, slice_sums, slice_breached = process_work_slice(
                    allocated, sim_day=day, work_budget=slice_budget, cfg=cfg,
                )
                closures_total += slice_closures
                for k, v in slice_by_type.items():
                    closures_by_type[k] += v
                for k, v in slice_sums.items():
                    for mk, mv in v.items():
                        close_sums[k][mk] += mv
                for k, v in slice_breached.items():
                    breached_closures_by_type[k] += v

            # Merge to keep list sizes manageable
            allocated = merge_cohorts(allocated)
            unallocated = merge_cohorts(unallocated)

        # Record daily metrics
        total_wip = sum(c.count for c in unallocated) + sum(c.count for c in allocated)
        total_unalloc = sum(c.count for c in unallocated)
        total_alloc = sum(c.count for c in allocated)

        by_type = count_by_type(unallocated + allocated)
        breaches = count_breaches(unallocated + allocated)
        over_target = count_over_target(unallocated + allocated)
        age_bands, age_bands_by_type = count_age_bands(unallocated + allocated)

        fca_total = by_type.get("FCA", 0) + by_type.get("PSD2_35", 0) * 0  # FCA only
        fca_total = by_type.get("FCA", 0)
        psd2_total = by_type.get("PSD2_15", 0) + by_type.get("PSD2_35", 0)

        fca_breach_pct = breaches.get("FCA", 0) / fca_total if fca_total > 0 else 0.0
        psd2_breach = breaches.get("PSD2_15", 0) + breaches.get("PSD2_35", 0)
        psd2_breach_pct = psd2_breach / psd2_total if psd2_total > 0 else 0.0

        avg_alloc_delay_today = weighted_delay_total / allocations_total if allocations_total > 0 else 0.0

        results.append({
            "day": day,
            "workday": workday,
            "workday_num": workday_num,
            "wip": total_wip,
            "unallocated": total_unalloc,
            "allocated": total_alloc,
            "desired_wip": desired_wip,
            "effective_util": effective_util,
            "pressure": pressure,
            "allocations": allocations_total,
            "closures": closures_total,
            "closures_by_type": dict(closures_by_type),
            "close_sums": dict(close_sums),
            "breached_closures_by_type": dict(breached_closures_by_type),
            "by_type": by_type,
            "breaches": breaches,
            "over_target": over_target,
            "fca_breach_pct": fca_breach_pct,
            "psd2_breach_pct": psd2_breach_pct,
            "age_bands": age_bands,
            "age_bands_by_type": age_bands_by_type,
            "avg_alloc_delay": avg_alloc_delay_today,
            "diary_slots": max_slots,
        })

        # Circuit breaker
        if total_wip > max_wip:
            break

    return results
```

**IMPORTANT:** This is the structural skeleton. The actual implementation MUST be extracted from prove_maths.py lines 735-932, preserving every metric calculation, SRC scheduling logic, and edge case handling. The engineer must diff line-by-line to ensure nothing is lost.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_simulation.py -v`
Expected: All PASSED

- [ ] **Step 5: Commit**

```bash
git add complaints_model/simulation.py tests/test_simulation.py
git commit -m "feat: add main simulation loop with Parkinson's Law and strategy support"
```

---

### Task 9: Create metrics.py and reporting.py

**Files:**
- Create: `complaints_model/metrics.py`
- Create: `complaints_model/reporting.py`
- Create: `tests/test_metrics.py`

- [ ] **Step 1: Write tests for metrics**

```python
"""Tests for metric computation functions."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from complaints_model.metrics import (
    count_by_type, count_breaches, count_over_target, count_age_bands,
    average_breach_rates, average_flow_breach_rates, is_stable,
    last_n_days, last_n_workdays,
)
from complaints_model.cohort import Cohort

def test_count_by_type():
    cohorts = [
        Cohort(count=10, case_type="FCA", cal_age=5, biz_age=3,
               effort_per_case=0, is_src=False, arrival_day=0, allocation_day=0),
        Cohort(count=5, case_type="PSD2_15", cal_age=5, biz_age=3,
               effort_per_case=0, is_src=False, arrival_day=0, allocation_day=0),
    ]
    result = count_by_type(cohorts)
    assert result["FCA"] == 10
    assert result["PSD2_15"] == 5

def test_count_breaches_fca():
    """FCA breach at 56 calendar days."""
    cohorts = [
        Cohort(count=10, case_type="FCA", cal_age=60, biz_age=42,
               effort_per_case=0, is_src=False, arrival_day=0, allocation_day=0),
    ]
    result = count_breaches(cohorts)
    assert result["FCA"] == 10

def test_last_n_days():
    records = [{"day": i, "workday": True} for i in range(100)]
    last10 = last_n_days(records, 10)
    assert len(last10) == 10
    assert last10[0]["day"] == 90

def test_is_stable_constant_wip():
    """Constant WIP should be stable."""
    records = [{"day": i, "workday": True, "wip": 1000} for i in range(100)]
    assert is_stable(records)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_metrics.py -v`
Expected: FAIL

- [ ] **Step 3: Create metrics.py**

Extract from prove_maths.py — all counting, breach rate, stability, and closure summary functions (lines 406-447, 934-1027):

```python
"""KPI computation — breach rates, age bands, stability checks, closure summaries."""
from __future__ import annotations
from collections import defaultdict
from statistics import mean

from .cohort import Cohort
from .time_utils import regulatory_age
from .regulatory import SERVICE_TARGETS, REGULATORY_DEADLINES

AGE_BANDS = [
    ("0-3", 0, 3),
    ("4-15", 4, 15),
    ("16-35", 16, 35),
    ("36-56", 36, 56),
    ("57+", 57, 9999),
]


def count_by_type(cohorts: list[Cohort]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for c in cohorts:
        totals[c.case_type] += c.count
    return dict(totals)


def count_breaches(cohorts: list[Cohort]) -> dict[str, float]:
    breaches: dict[str, float] = defaultdict(float)
    for c in cohorts:
        reg_age = regulatory_age(c.case_type, c.cal_age, c.biz_age)
        deadline = REGULATORY_DEADLINES.get(c.case_type, 999)
        if reg_age > deadline:
            breaches[c.case_type] += c.count
    return dict(breaches)


def count_over_target(cohorts: list[Cohort]) -> dict[str, float]:
    over: dict[str, float] = defaultdict(float)
    for c in cohorts:
        reg_age = regulatory_age(c.case_type, c.cal_age, c.biz_age)
        target = SERVICE_TARGETS.get(c.case_type, 999)
        if reg_age > target:
            over[c.case_type] += c.count
    return dict(over)


def count_age_bands(cohorts: list[Cohort]) -> tuple[dict, dict]:
    total: dict[str, float] = defaultdict(float)
    by_type: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for cohort in cohorts:
        reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
        for label, lo, hi in AGE_BANDS:
            if lo <= reg_age <= hi:
                total[label] += cohort.count
                by_type[cohort.case_type][label] += cohort.count
                break
    return dict(total), dict(by_type)


def last_n_days(result: list[dict], n: int) -> list[dict]:
    return result[-n:]


def last_n_workdays(result: list[dict], n_workdays: int) -> list[dict]:
    workdays = [r for r in result if r.get("workday", False)]
    return workdays[-n_workdays:]


def average_breach_rates(result: list[dict], last_days: int = 60) -> tuple[dict, dict]:
    """Compute average stock breach % over last N days."""
    recent = last_n_days(result, last_days)
    if not recent:
        return {}, {}
    fca_rates = [r["fca_breach_pct"] for r in recent]
    psd2_rates = [r["psd2_breach_pct"] for r in recent]
    return (
        {"FCA": mean(fca_rates), "PSD2": mean(psd2_rates)},
        {"FCA_min": min(fca_rates), "FCA_max": max(fca_rates),
         "PSD2_min": min(psd2_rates), "PSD2_max": max(psd2_rates)},
    )


def average_flow_breach_rates(result: list[dict], last_days: int = 30) -> tuple[dict, dict]:
    """Compute average flow breach % (breached closures / total closures) over last N workdays."""
    recent = last_n_workdays(result, last_days)
    if not recent:
        return {}, {}

    total_closures: dict[str, float] = defaultdict(float)
    breached_closures: dict[str, float] = defaultdict(float)
    for r in recent:
        for ct, count in r.get("closures_by_type", {}).items():
            total_closures[ct] += count
        for ct, count in r.get("breached_closures_by_type", {}).items():
            breached_closures[ct] += count

    fca_total = total_closures.get("FCA", 0)
    psd2_total = total_closures.get("PSD2_15", 0) + total_closures.get("PSD2_35", 0)
    fca_breached = breached_closures.get("FCA", 0)
    psd2_breached = breached_closures.get("PSD2_15", 0) + breached_closures.get("PSD2_35", 0)

    rates = {
        "FCA": fca_breached / fca_total if fca_total > 0 else 0.0,
        "PSD2": psd2_breached / psd2_total if psd2_total > 0 else 0.0,
    }
    return rates, {}


def is_stable(result: list[dict], last_days: int = 60, tolerance: float = 0.05) -> bool:
    """Check if WIP variance is within tolerance over recent days."""
    recent = last_n_days(result, last_days)
    if len(recent) < last_days:
        return False
    wips = [r["wip"] for r in recent]
    avg_wip = mean(wips)
    if avg_wip == 0:
        return True
    max_dev = max(abs(w - avg_wip) for w in wips)
    return max_dev / avg_wip < tolerance


def summarise_closure_metrics(result: list[dict], case_type: str, last_days: int = 60) -> dict:
    """Compute average closure age, SRC %, count for a case type."""
    recent = last_n_workdays(result, last_days)
    total_count = 0.0
    total_age = 0.0
    total_sys = 0.0
    total_src = 0.0
    for r in recent:
        sums = r.get("close_sums", {}).get(case_type, {})
        total_count += sums.get("count", 0)
        total_age += sums.get("age_sum", 0)
        total_sys += sums.get("sys_sum", 0)
        total_src += sums.get("src_count", 0)
    return {
        "count": total_count,
        "avg_reg_age": total_age / total_count if total_count > 0 else 0.0,
        "avg_sys_time": total_sys / total_count if total_count > 0 else 0.0,
        "src_pct": total_src / total_count if total_count > 0 else 0.0,
    }
```

- [ ] **Step 4: Create reporting.py**

Extract print_stable_pack, print_fte_sweep, main from prove_maths.py (lines 1029-1275):

```python
"""CLI reporting — prints tabular output for FTE sweep and detailed packs."""
from __future__ import annotations
from statistics import mean

from .config import SimConfig
from .simulation import simulate
from .metrics import (
    last_n_days, last_n_workdays, average_breach_rates, average_flow_breach_rates,
    is_stable, summarise_closure_metrics, count_age_bands, AGE_BANDS,
)
from .intake import INTAKE_PROPORTIONS


def print_stable_pack(cfg: SimConfig, result: list[dict]) -> None:
    """Print detailed metrics report for a single FTE level."""
    # Extract from prove_maths.py lines 1029-1190 — replace all global refs with cfg.field
    # This is a pure display function with no simulation logic
    final = result[-1]
    on_desk_present = cfg.present_fte

    print(f"\n{'=' * 70}")
    print(f"DETAILED PACK — {cfg.fte} FTE")
    print(f"{'=' * 70}")
    print(f"Present FTE: {on_desk_present:.1f}, diary slots: {cfg.max_diary_slots:.0f}, "
          f"desired WIP: {cfg.max_diary_slots + cfg.unallocated_buffer:.0f}")
    # ... (full implementation extracted line-for-line from prove_maths.py)


def print_fte_sweep(rows: list[dict]) -> None:
    """Print comparison table across FTE range."""
    # Extract from prove_maths.py lines 1191-1215
    # ... (full implementation extracted line-for-line)


def main() -> None:
    """CLI entry point: runs FTE sweep and prints detailed pack."""
    cfg = SimConfig()
    rows = []

    for fte in range(135, 155):
        test_cfg = SimConfig(fte=fte)  # frozen — create new for each
        result = simulate(test_cfg)
        final = result[-1]
        stable = is_stable(result)
        stock_breach, _ = average_breach_rates(result)
        flow_breach, _ = average_flow_breach_rates(result)
        rows.append({
            "fte": fte,
            "wip": final["wip"],
            "unallocated": final["unallocated"],
            "allocated": final["allocated"],
            "util": final["effective_util"],
            "closures": final["closures"],
            "fca_breach": stock_breach.get("FCA", 0),
            "psd2_breach": stock_breach.get("PSD2", 0),
            "fca_flow_breach": flow_breach.get("FCA", 0),
            "psd2_flow_breach": flow_breach.get("PSD2", 0),
            "stable": stable,
            "diary_slots": test_cfg.max_diary_slots,
        })

    print_fte_sweep(rows)

    # Detailed pack for default FTE
    result = simulate(cfg)
    print_stable_pack(cfg, result)


if __name__ == "__main__":
    main()
```

**NOTE:** print_stable_pack and print_fte_sweep are long display functions (~160 lines combined). Extract them line-for-line from prove_maths.py, replacing every global reference (e.g., `ABSENCE_SHRINKAGE` → `cfg.absence_shrinkage`). They contain no simulation logic, only formatting.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_metrics.py -v`
Expected: All PASSED

- [ ] **Step 6: Commit**

```bash
git add complaints_model/metrics.py complaints_model/reporting.py tests/test_metrics.py
git commit -m "feat: add metrics computation and CLI reporting modules"
```

---

### Task 10: Wire up __init__.py public API

**Files:**
- Modify: `complaints_model/__init__.py`

- [ ] **Step 1: Write the public API exports**

```python
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
```

- [ ] **Step 2: Verify imports work**

Run: `cd "C:/Users/ROG/Projects/Complaints Planning - KISS" && python -c "from complaints_model import SimConfig, simulate; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add complaints_model/__init__.py
git commit -m "feat: wire up public API in complaints_model __init__"
```

---

### Task 11: Regression test — verify zero divergence

**Files:**
- Modify: `tests/test_regression.py`

This is the critical validation step. We run the old prove_maths and new complaints_model side-by-side.

- [ ] **Step 1: Add regression comparison test**

Add to `tests/test_regression.py`:

```python
from complaints_model import SimConfig, simulate as new_simulate
from complaints_model.metrics import is_stable as new_is_stable, average_breach_rates as new_breach_rates

def test_regression_new_matches_old():
    """New modular package must produce identical output to prove_maths."""
    # Run old
    old_result = _run_baseline()
    old_final = old_result[-1]

    # Run new with identical defaults
    cfg = SimConfig(fte=148)
    new_result = new_simulate(cfg)
    new_final = new_result[-1]

    # Must have same number of days
    assert len(new_result) == len(old_result), f"Day count: {len(new_result)} vs {len(old_result)}"

    # Compare key metrics with tight tolerance
    assert abs(new_final["wip"] - old_final["wip"]) < 1.0, \
        f"WIP: {new_final['wip']:.2f} vs {old_final['wip']:.2f}"
    assert abs(new_final["unallocated"] - old_final["unallocated"]) < 1.0, \
        f"Unalloc: {new_final['unallocated']:.2f} vs {old_final['unallocated']:.2f}"
    assert abs(new_final["effective_util"] - old_final["effective_util"]) < 0.001, \
        f"Util: {new_final['effective_util']:.4f} vs {old_final['effective_util']:.4f}"
    assert abs(new_final["fca_breach_pct"] - old_final["fca_breach_pct"]) < 0.001, \
        f"FCA breach: {new_final['fca_breach_pct']:.4f} vs {old_final['fca_breach_pct']:.4f}"
    assert abs(new_final["psd2_breach_pct"] - old_final["psd2_breach_pct"]) < 0.001, \
        f"PSD2 breach: {new_final['psd2_breach_pct']:.4f} vs {old_final['psd2_breach_pct']:.4f}"

def test_regression_stability_matches():
    """Both implementations should agree on stability."""
    old_result = _run_baseline()
    cfg = SimConfig(fte=148)
    new_result = new_simulate(cfg)
    assert pm.is_stable(old_result) == new_is_stable(new_result)

def test_regression_trajectory_matches():
    """Day-by-day WIP trajectory should match closely."""
    old_result = _run_baseline()
    cfg = SimConfig(fte=148)
    new_result = new_simulate(cfg)

    max_wip_diff = 0
    for old_day, new_day in zip(old_result, new_result):
        diff = abs(old_day["wip"] - new_day["wip"])
        max_wip_diff = max(max_wip_diff, diff)

    assert max_wip_diff < 1.0, f"Max day-to-day WIP difference: {max_wip_diff:.2f}"
```

- [ ] **Step 2: Run regression tests**

Run: `python -m pytest tests/test_regression.py -v`
Expected: All PASSED (old and new match)

If any test fails, the implementation has diverged from prove_maths. Debug by comparing daily metrics day-by-day to find where divergence starts.

- [ ] **Step 3: Commit**

```bash
git add tests/test_regression.py
git commit -m "test: add regression comparison between prove_maths and complaints_model"
```

---

### Task 12: Migrate consumers — dashboard, run_scenarios, compare_staffing

**Files:**
- Modify: `dashboard.py`
- Modify: `run_scenarios.py`
- Modify: `compare_staffing.py`

- [ ] **Step 1: Migrate dashboard.py**

Replace the globals-mutation pattern with SimConfig:

```python
# OLD (lines 84-106):
# pm.SHRINKAGE = p_shrinkage
# pm.ABSENCE_SHRINKAGE = p_absence_shrinkage
# ...
# return pm.simulate(p_fte)

# NEW:
from complaints_model import SimConfig, simulate
from complaints_model.metrics import (
    last_n_days, last_n_workdays, average_breach_rates,
    average_flow_breach_rates, is_stable, summarise_closure_metrics,
)

@st.cache_data(show_spinner="Running simulation...")
def run_simulation(
    p_fte, p_shrinkage, p_absence_shrinkage, p_hours_per_day, p_utilisation,
    p_proficiency, p_daily_intake, p_base_effort, p_diary_limit, p_min_diary_days,
    p_handoff_overhead, p_handoff_effort_hours, p_late_demand_rate,
    p_parkinson_floor, p_parkinson_fpq, p_unallocated_buffer,
    p_src_window, p_src_effort_ratio, p_src_boost_max, p_src_boost_decay,
    p_psd2_extension_rate, p_slices_per_day,
):
    cfg = SimConfig(
        fte=p_fte, shrinkage=p_shrinkage, absence_shrinkage=p_absence_shrinkage,
        hours_per_day=p_hours_per_day, utilisation=p_utilisation,
        proficiency=p_proficiency, daily_intake=p_daily_intake,
        base_effort=p_base_effort, diary_limit=p_diary_limit,
        min_diary_days=p_min_diary_days, handoff_overhead=p_handoff_overhead,
        handoff_effort_hours=p_handoff_effort_hours,
        late_demand_rate=p_late_demand_rate, parkinson_floor=p_parkinson_floor,
        parkinson_full_pace_queue=p_parkinson_fpq,
        unallocated_buffer=p_unallocated_buffer,
        src_window=p_src_window, src_effort_ratio=p_src_effort_ratio,
        src_boost_max=p_src_boost_max, src_boost_decay_days=p_src_boost_decay,
        psd2_extension_rate=p_psd2_extension_rate,
        slices_per_day=p_slices_per_day, days=365,
    )
    return simulate(cfg)
```

Also update any `pm.is_stable()`, `pm.last_n_workdays()`, etc. calls throughout dashboard.py to use the new imports.

Remove `import prove_maths as pm` and the `sys.path.insert` hack.

- [ ] **Step 2: Migrate run_scenarios.py**

Update to import from complaints_model and use SimConfig:

```python
from complaints_model import SimConfig, simulate, STRATEGIES
from complaints_model.metrics import is_stable, average_breach_rates, average_flow_breach_rates
```

Replace global mutation with SimConfig construction. Each subprocess run creates a fresh SimConfig with the strategy set.

- [ ] **Step 3: Migrate compare_staffing.py**

Update to import from complaints_model and use SimConfig:

```python
from complaints_model import SimConfig, simulate
from complaints_model.metrics import is_stable, average_breach_rates, last_n_workdays
```

Replace `pm.DAYS = 365` / `pm.simulate(fte)` with `simulate(SimConfig(fte=fte, days=365))`.

- [ ] **Step 4: Run dashboard smoke test**

Run: `cd "C:/Users/ROG/Projects/Complaints Planning - KISS" && python -c "from dashboard import run_simulation; print('Dashboard import OK')"`
Expected: `Dashboard import OK` (or streamlit import error which is fine — the import path is clean)

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All PASSED

- [ ] **Step 6: Commit**

```bash
git add dashboard.py run_scenarios.py compare_staffing.py
git commit -m "refactor: migrate dashboard, scenarios, and comparison to complaints_model"
```

---

### Task 13: Delete old files and update CLAUDE.md

**Files:**
- Delete: `prove_maths.py` (keep git history)
- Delete: `strategy_model.py`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Verify no remaining imports of old modules**

Run: `grep -r "import prove_maths\|from prove_maths\|import strategy_model\|from strategy_model" --include="*.py" .`
Expected: No matches (only in tests/test_regression.py which uses it for comparison — update that test to remove old dependency)

- [ ] **Step 2: Update test_regression.py to be self-contained**

Remove the `_run_baseline()` function that imports prove_maths. Replace with hardcoded expected values captured in Task 1 Step 4. The regression test now checks the new package against known-good numbers.

- [ ] **Step 3: Delete old files**

```bash
git rm prove_maths.py strategy_model.py
```

- [ ] **Step 4: Update CLAUDE.md**

Replace the Key Files table and Architecture section to reflect the new structure:

```markdown
## Key files

| File | Purpose |
|------|---------|
| `complaints_model/` | Core simulation package |
| `complaints_model/config.py` | SimConfig dataclass — all tuneable parameters |
| `complaints_model/simulation.py` | Main simulation loop (730-day discrete-event) |
| `complaints_model/allocation.py` | Allocation engine — queue → diary |
| `complaints_model/work.py` | Work engine — handlers close cases |
| `complaints_model/strategies.py` | 8 allocation + work prioritisation strategies |
| `complaints_model/metrics.py` | KPI computation, breach rates, stability |
| `complaints_model/config.py` | SimConfig frozen dataclass |
| `complaints_model/cohort.py` | Cohort dataclass |
| `complaints_model/regulatory.py` | Deadlines, targets, PSD2 extensions |
| `complaints_model/effort.py` | Burden bands, case effort calculation |
| `complaints_model/intake.py` | Intake profiles, pool seeding |
| `complaints_model/reporting.py` | CLI output formatting |
| `dashboard.py` | Streamlit interactive dashboard |
| `run_scenarios.py` | CLI: all 36 strategy combos |
| `compare_staffing.py` | Side-by-side FTE comparison |
| `tests/` | Regression and unit tests |

## Running

```bash
# Run simulation (console)
python -m complaints_model.reporting

# Run dashboard
pip install -r requirements.txt
streamlit run dashboard.py

# Run all tests
python -m pytest tests/ -v
```

## Architecture

### Package (`complaints_model/`)
- `SimConfig` frozen dataclass holds all parameters — no globals mutation
- `simulate(cfg)` returns list of daily metric dicts
- Strategy support built-in: `cfg.allocation_strategy` and `cfg.work_strategy`
- Each module <200 lines, one responsibility, one-directional dependencies
```

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All PASSED

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: delete monoliths, update docs for complaints_model package"
```

---

### Task 14: Final validation — end-to-end

- [ ] **Step 1: Run FTE sweep from new package**

Run: `cd "C:/Users/ROG/Projects/Complaints Planning - KISS" && python -m complaints_model.reporting`
Expected: FTE sweep table + detailed pack matching original prove_maths output

- [ ] **Step 2: Run strategy scenarios**

Run: `python run_scenarios.py --fte 148`
Expected: All 36 strategy combos run successfully

- [ ] **Step 3: Verify dashboard starts**

Run: `streamlit run dashboard.py` (manual check — sliders work, charts render)

- [ ] **Step 4: Run full test suite one final time**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All PASSED

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: final validation of modular refactor — all tests pass"
```
