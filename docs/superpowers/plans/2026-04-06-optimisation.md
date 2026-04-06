# FTE Pool Optimisation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find the optimal FTE split across case-age bands with per-band strategies to minimise customer harm, using Optuna for hyperparameter search.

**Architecture:** Six new files extend `complaints_model/` without modifying existing code. `bands.py` defines age-based case pools; `pool_config.py` holds the optimisation config; `harm.py` scores customer harm; `pool_simulation.py` runs the multi-pool simulation reusing existing allocation/work engines with per-band strategy overrides; `optimise.py` orchestrates Optuna trials; `pages/3_Optimisation.py` provides the dashboard UI.

**Tech Stack:** Python 3.12, optuna, existing complaints_model package, Streamlit + Plotly for dashboard

**Design Spec:** `docs/superpowers/specs/2026-04-06-optimisation-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `complaints_model/bands.py` | Create | Band definitions (FCA/PSD2/Combined/Hybrid), case-to-band assignment, transition detection |
| `complaints_model/pool_config.py` | Create | `OptimConfig` dataclass — band FTE splits, per-band strategies, pooling model, harm weights |
| `complaints_model/harm.py` | Create | Per-case-per-day harm scoring with configurable weights |
| `complaints_model/pool_simulation.py` | Create | `simulate_pooled()` — multi-pool simulation loop reusing existing engines |
| `optimise.py` | Create | CLI runner — Optuna study creation, trial objective, output |
| `pages/3_Optimisation.py` | Create | Streamlit dashboard page for optimisation |
| `complaints_model/__init__.py` | Modify | Add new exports |
| `requirements.txt` | Modify | Add `optuna` dependency |
| `tests/test_bands.py` | Create | Band assignment and transition tests |
| `tests/test_harm.py` | Create | Harm scoring tests |
| `tests/test_pool_simulation.py` | Create | Pool simulation integration tests |
| `tests/test_optimise.py` | Create | Optuna objective function tests |

---

## Task 1: Band Definitions (`bands.py`)

**Files:**
- Create: `complaints_model/bands.py`
- Test: `tests/test_bands.py`

### Key knowledge for implementer

Case types in this system: `"FCA"`, `"PSD2_15"`, `"PSD2_35"`. FCA uses calendar age (`cal_age`), PSD2 uses business age (`biz_age`). PSD2_15 breaches at 15 biz days; PSD2_35 is extended and breaches at 35 biz days. A PSD2_15 case that hasn't been extended cannot enter the P4 band (15-35 biz days) — it's already breached at 15 and goes to P5. Only PSD2_35 cases enter P4.

Regulatory deadlines are in `complaints_model/regulatory.py`: `REGULATORY_DEADLINES = {"FCA": 56, "PSD2_15": 15, "PSD2_35": 35}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bands.py
"""Tests for band definitions and case-to-band assignment."""
import pytest
from complaints_model.cohort import Cohort
from complaints_model.bands import (
    Band, FCA_BANDS, PSD2_BANDS, COMBINED_BANDS,
    get_bands_for_model, assign_band, detect_transitions,
)


def _make_cohort(case_type: str, cal_age: int, biz_age: int) -> Cohort:
    return Cohort(
        count=1.0, case_type=case_type, cal_age=cal_age, biz_age=biz_age,
        effort_per_case=1.0, is_src=False, arrival_day=0,
        allocation_day=None, seeded=False, last_worked_day=None,
    )


class TestFCABandAssignment:
    def test_fresh_case_goes_to_f1(self):
        c = _make_cohort("FCA", cal_age=1, biz_age=1)
        assert assign_band(c, FCA_BANDS) == "F1"

    def test_day3_goes_to_f2(self):
        c = _make_cohort("FCA", cal_age=3, biz_age=3)
        assert assign_band(c, FCA_BANDS) == "F2"

    def test_day20_goes_to_f3(self):
        c = _make_cohort("FCA", cal_age=20, biz_age=15)
        assert assign_band(c, FCA_BANDS) == "F3"

    def test_day40_goes_to_f4(self):
        c = _make_cohort("FCA", cal_age=40, biz_age=29)
        assert assign_band(c, FCA_BANDS) == "F4"

    def test_day56_goes_to_f5(self):
        c = _make_cohort("FCA", cal_age=56, biz_age=40)
        assert assign_band(c, FCA_BANDS) == "F5"

    def test_day100_goes_to_f5(self):
        c = _make_cohort("FCA", cal_age=100, biz_age=72)
        assert assign_band(c, FCA_BANDS) == "F5"


class TestPSD2BandAssignment:
    def test_fresh_psd2_goes_to_p1(self):
        c = _make_cohort("PSD2_15", cal_age=1, biz_age=1)
        assert assign_band(c, PSD2_BANDS) == "P1"

    def test_biz3_goes_to_p2(self):
        c = _make_cohort("PSD2_15", cal_age=5, biz_age=3)
        assert assign_band(c, PSD2_BANDS) == "P2"

    def test_biz10_goes_to_p3(self):
        c = _make_cohort("PSD2_15", cal_age=14, biz_age=10)
        assert assign_band(c, PSD2_BANDS) == "P3"

    def test_psd2_15_at_biz15_goes_to_p5_not_p4(self):
        """PSD2_15 (not extended) skips P4, goes straight to P5."""
        c = _make_cohort("PSD2_15", cal_age=21, biz_age=15)
        assert assign_band(c, PSD2_BANDS) == "P5"

    def test_psd2_35_at_biz15_goes_to_p4(self):
        """PSD2_35 (extended) enters P4."""
        c = _make_cohort("PSD2_35", cal_age=21, biz_age=15)
        assert assign_band(c, PSD2_BANDS) == "P4"

    def test_psd2_35_at_biz35_goes_to_p5(self):
        c = _make_cohort("PSD2_35", cal_age=49, biz_age=35)
        assert assign_band(c, PSD2_BANDS) == "P5"


class TestCombinedBandAssignment:
    def test_fresh_fca_goes_to_c1(self):
        c = _make_cohort("FCA", cal_age=2, biz_age=2)
        assert assign_band(c, COMBINED_BANDS) == "C1"

    def test_mid_fca_goes_to_c3(self):
        c = _make_cohort("FCA", cal_age=35, biz_age=25)
        assert assign_band(c, COMBINED_BANDS) == "C3"

    def test_breached_fca_goes_to_c5(self):
        c = _make_cohort("FCA", cal_age=60, biz_age=43)
        assert assign_band(c, COMBINED_BANDS) == "C5"

    def test_fresh_psd2_goes_to_c1(self):
        c = _make_cohort("PSD2_15", cal_age=1, biz_age=1)
        assert assign_band(c, COMBINED_BANDS) == "C1"

    def test_breached_psd2_goes_to_c5(self):
        c = _make_cohort("PSD2_15", cal_age=21, biz_age=16)
        assert assign_band(c, COMBINED_BANDS) == "C5"


class TestGetBandsForModel:
    def test_separate_returns_10_bands(self):
        bands = get_bands_for_model("separate")
        assert len(bands) == 10
        names = [b.name for b in bands]
        assert names == ["F1", "F2", "F3", "F4", "F5", "P1", "P2", "P3", "P4", "P5"]

    def test_combined_returns_5_bands(self):
        bands = get_bands_for_model("combined")
        assert len(bands) == 5
        names = [b.name for b in bands]
        assert names == ["C1", "C2", "C3", "C4", "C5"]

    def test_hybrid_returns_6_bands(self):
        bands = get_bands_for_model("hybrid")
        assert len(bands) == 6
        names = [b.name for b in bands]
        assert names == ["F1", "F2", "F3", "F4", "F5", "PSD2"]


class TestDetectTransitions:
    def test_fca_ages_past_band_boundary(self):
        """A case in F1 that aged to cal_age=3 should transition to F2."""
        c = _make_cohort("FCA", cal_age=3, biz_age=3)
        c.allocation_day = 0
        current_band = "F1"
        new_band = assign_band(c, FCA_BANDS)
        assert new_band != current_band
        assert new_band == "F2"

    def test_fca_stays_in_band(self):
        c = _make_cohort("FCA", cal_age=2, biz_age=2)
        assert assign_band(c, FCA_BANDS) == "F1"

    def test_detect_transitions_returns_movers(self):
        """detect_transitions identifies cohorts that need to move."""
        cohorts = [
            _make_cohort("FCA", cal_age=3, biz_age=3),   # should leave F1
            _make_cohort("FCA", cal_age=2, biz_age=2),   # stays in F1
        ]
        bands = FCA_BANDS
        stayers, movers = detect_transitions(cohorts, "F1", bands)
        assert len(stayers) == 1
        assert stayers[0].cal_age == 2
        assert len(movers) == 1
        assert movers[0].cal_age == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_bands.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'complaints_model.bands'`

- [ ] **Step 3: Implement bands.py**

```python
# complaints_model/bands.py
"""Band definitions — case-age ranges for pool-based FTE allocation."""
from __future__ import annotations

from dataclasses import dataclass

from .cohort import Cohort
from .regulatory import REGULATORY_DEADLINES


@dataclass(frozen=True)
class Band:
    name: str
    case_types: tuple[str, ...]   # which case types this band accepts
    age_min: int                   # inclusive lower bound
    age_max: int | None            # exclusive upper bound, None = unbounded
    use_biz_age: bool              # True → compare biz_age; False → compare cal_age
    requires_extension: bool = False  # only PSD2_35 can enter


# --- Separate model: 5 FCA bands + 5 PSD2 bands ---

FCA_BANDS: list[Band] = [
    Band("F1", ("FCA",), 0, 3, False),
    Band("F2", ("FCA",), 3, 20, False),
    Band("F3", ("FCA",), 20, 40, False),
    Band("F4", ("FCA",), 40, 56, False),
    Band("F5", ("FCA",), 56, None, False),
]

PSD2_BANDS: list[Band] = [
    Band("P1", ("PSD2_15", "PSD2_35"), 0, 3, True),
    Band("P2", ("PSD2_15", "PSD2_35"), 3, 10, True),
    Band("P3", ("PSD2_15", "PSD2_35"), 10, 15, True),
    Band("P4", ("PSD2_35",), 15, 35, True, requires_extension=True),
    Band("P5", ("PSD2_15", "PSD2_35"), 15, None, True),  # PSD2_15 jumps here from P3
]

# --- Combined model: 5 urgency tiers based on fraction of deadline elapsed ---
# Urgency = relevant_age / regulatory_deadline
# Thresholds: 0.0–0.2, 0.2–0.5, 0.5–0.8, 0.8–1.0, 1.0+

_ALL_CASE_TYPES = ("FCA", "PSD2_15", "PSD2_35")

COMBINED_BANDS: list[Band] = [
    Band("C1", _ALL_CASE_TYPES, 0, 20, False),   # urgency 0–0.2 (placeholder, actual check uses urgency)
    Band("C2", _ALL_CASE_TYPES, 20, 50, False),
    Band("C3", _ALL_CASE_TYPES, 50, 80, False),
    Band("C4", _ALL_CASE_TYPES, 80, 100, False),
    Band("C5", _ALL_CASE_TYPES, 100, None, False),
]

# --- Hybrid model: dedicated PSD2 single pool + 5 FCA bands ---

_HYBRID_PSD2_BAND = Band("PSD2", ("PSD2_15", "PSD2_35"), 0, None, True)

HYBRID_BANDS: list[Band] = FCA_BANDS + [_HYBRID_PSD2_BAND]


def _urgency_pct(cohort: Cohort) -> int:
    """Return urgency as integer percentage of deadline elapsed (0–999)."""
    deadline = REGULATORY_DEADLINES[cohort.case_type]
    if cohort.case_type == "FCA":
        age = cohort.cal_age
    else:
        age = cohort.biz_age
    if deadline == 0:
        return 999
    return int(age * 100 / deadline)


def assign_band(cohort: Cohort, bands: list[Band]) -> str:
    """Return the band name a cohort belongs to given a list of bands.

    For combined bands (C1-C5), uses urgency-based assignment.
    For separate/hybrid bands, uses raw age-based assignment.
    """
    # Combined model: urgency-based
    if bands and bands[0].name.startswith("C"):
        pct = _urgency_pct(cohort)
        for band in bands:
            if band.age_max is None or pct < band.age_max:
                return band.name
        return bands[-1].name

    # Separate / Hybrid: type + age based
    for band in bands:
        if cohort.case_type not in band.case_types:
            continue
        if band.requires_extension and cohort.case_type != "PSD2_35":
            continue
        age = cohort.biz_age if band.use_biz_age else cohort.cal_age
        if band.age_max is None:
            if age >= band.age_min:
                return band.name
        elif band.age_min <= age < band.age_max:
            return band.name

    # Fallback: last matching-type band
    for band in reversed(bands):
        if cohort.case_type in band.case_types:
            if not band.requires_extension or cohort.case_type == "PSD2_35":
                return band.name
    raise ValueError(f"No band found for {cohort.case_type} age cal={cohort.cal_age} biz={cohort.biz_age}")


def get_bands_for_model(pooling_model: str) -> list[Band]:
    """Return the band list for a given pooling model."""
    if pooling_model == "separate":
        return FCA_BANDS + PSD2_BANDS
    elif pooling_model == "combined":
        return COMBINED_BANDS
    elif pooling_model == "hybrid":
        return HYBRID_BANDS
    raise ValueError(f"Unknown pooling model: {pooling_model}")


def detect_transitions(
    cohorts: list[Cohort],
    current_band_name: str,
    bands: list[Band],
) -> tuple[list[Cohort], list[Cohort]]:
    """Split cohorts into stayers (still in current_band_name) and movers (need reassignment).

    Movers lose their SRC flag and allocation status — they re-enter the new band's queue.
    """
    stayers: list[Cohort] = []
    movers: list[Cohort] = []
    for c in cohorts:
        if assign_band(c, bands) == current_band_name:
            stayers.append(c)
        else:
            # Reset allocation state for band transition
            movers.append(Cohort(
                count=c.count,
                case_type=c.case_type,
                cal_age=c.cal_age,
                biz_age=c.biz_age,
                effort_per_case=c.effort_per_case,
                is_src=False,  # SRC window missed — no longer SRC
                arrival_day=c.arrival_day,
                allocation_day=None,  # must be re-allocated in new band
                seeded=c.seeded,
                last_worked_day=c.last_worked_day,
            ))
    return stayers, movers
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_bands.py -v`
Expected: All 17 tests PASS

- [ ] **Step 5: Commit**

```bash
git add complaints_model/bands.py tests/test_bands.py
git commit -m "feat: add band definitions for pool-based FTE optimisation"
```

---

## Task 2: OptimConfig Dataclass (`pool_config.py`)

**Files:**
- Create: `complaints_model/pool_config.py`
- Test: `tests/test_pool_config.py`

### Key knowledge for implementer

`OptimConfig` holds the full configuration for a pooled simulation trial. It wraps a base `SimConfig` (for shared parameters like shrinkage, diary_limit, SRC settings) plus per-band FTE allocations and strategies. The `SimConfig` is a frozen dataclass in `complaints_model/config.py` — use `dataclasses.replace()` to create per-band copies with overridden strategies.

Valid allocation strategies: `nearest_deadline`, `nearest_target`, `youngest_first`, `oldest_first`, `psd2_priority`, `longest_wait`.
Valid work strategies: `nearest_deadline`, `nearest_target`, `youngest_first`, `oldest_first`, `lowest_effort`, `longest_untouched`.

- [ ] **Step 1: Write the failing tests**

```python
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
        """A band with 0 FTE is valid — cases age through it."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pool_config.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement pool_config.py**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pool_config.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add complaints_model/pool_config.py tests/test_pool_config.py
git commit -m "feat: add OptimConfig dataclass for pool optimisation"
```

---

## Task 3: Harm Scoring (`harm.py`)

**Files:**
- Create: `complaints_model/harm.py`
- Test: `tests/test_harm.py`

### Key knowledge for implementer

Harm is accumulated per open case per day during the steady-state window (days 366–730). Three components:

- **Breach overshoot**: `breach_weight × days_past_deadline` (0 if not breached)
- **Neglect**: `neglect_weight × days_since_last_touched` (days since `last_worked_day`, or since `arrival_day` if never touched)
- **WIP**: `wip_weight × 1` per open case per day

Regulatory deadlines: FCA = 56 calendar days, PSD2_15 = 15 business days, PSD2_35 = 35 business days. Use `regulatory_age()` from `time_utils.py` and `REGULATORY_DEADLINES` from `regulatory.py` to check breach status.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_harm.py
"""Tests for harm score accumulation."""
import pytest
from complaints_model.cohort import Cohort
from complaints_model.harm import score_case_harm, accumulate_daily_harm


def _make_cohort(case_type: str, cal_age: int, biz_age: int,
                 count: float = 1.0, last_worked_day: int | None = None,
                 arrival_day: int = 0) -> Cohort:
    return Cohort(
        count=count, case_type=case_type, cal_age=cal_age, biz_age=biz_age,
        effort_per_case=1.0, is_src=False, arrival_day=arrival_day,
        allocation_day=None, seeded=False, last_worked_day=last_worked_day,
    )


class TestScoreCaseHarm:
    def test_non_breached_fca_no_breach_harm(self):
        """FCA at 30 cal days — not breached (deadline 56)."""
        c = _make_cohort("FCA", cal_age=30, biz_age=22, last_worked_day=95, arrival_day=70)
        harm = score_case_harm(c, sim_day=100, breach_w=3.0, neglect_w=1.0, wip_w=1.0)
        # breach = 0 (not breached), neglect = 100-95=5, wip = 1
        assert harm == pytest.approx(0 + 5.0 + 1.0)

    def test_breached_fca_has_breach_harm(self):
        """FCA at 60 cal days — 4 days past 56 deadline."""
        c = _make_cohort("FCA", cal_age=60, biz_age=43, last_worked_day=95, arrival_day=40)
        harm = score_case_harm(c, sim_day=100, breach_w=3.0, neglect_w=1.0, wip_w=1.0)
        # breach = 3*(60-56)=12, neglect = 100-95=5, wip = 1
        assert harm == pytest.approx(12.0 + 5.0 + 1.0)

    def test_breached_psd2_uses_biz_age(self):
        """PSD2_15 at 18 biz days — 3 days past 15 deadline."""
        c = _make_cohort("PSD2_15", cal_age=25, biz_age=18, last_worked_day=98, arrival_day=75)
        harm = score_case_harm(c, sim_day=100, breach_w=3.0, neglect_w=1.0, wip_w=1.0)
        # breach = 3*(18-15)=9, neglect = 100-98=2, wip = 1
        assert harm == pytest.approx(9.0 + 2.0 + 1.0)

    def test_never_touched_uses_arrival_day(self):
        """Case never worked on — neglect = sim_day - arrival_day."""
        c = _make_cohort("FCA", cal_age=10, biz_age=8, last_worked_day=None, arrival_day=90)
        harm = score_case_harm(c, sim_day=100, breach_w=3.0, neglect_w=1.0, wip_w=1.0)
        # breach = 0, neglect = 100-90=10, wip = 1
        assert harm == pytest.approx(0 + 10.0 + 1.0)

    def test_count_multiplies_harm(self):
        """A cohort of 5 cases produces 5x the harm."""
        c = _make_cohort("FCA", cal_age=10, biz_age=8, count=5.0, last_worked_day=99, arrival_day=90)
        harm = score_case_harm(c, sim_day=100, breach_w=3.0, neglect_w=1.0, wip_w=1.0)
        # per case: breach=0, neglect=1, wip=1 → 2.  × 5 = 10
        assert harm == pytest.approx(10.0)


class TestAccumulateDailyHarm:
    def test_empty_pools_return_zero(self):
        assert accumulate_daily_harm([], 100, 3.0, 1.0, 1.0) == 0.0

    def test_sums_across_all_cohorts(self):
        cohorts = [
            _make_cohort("FCA", cal_age=10, biz_age=8, count=2.0, last_worked_day=99, arrival_day=90),
            _make_cohort("FCA", cal_age=60, biz_age=43, count=1.0, last_worked_day=95, arrival_day=40),
        ]
        total = accumulate_daily_harm(cohorts, 100, 3.0, 1.0, 1.0)
        # cohort 1: per case breach=0 neglect=1 wip=1 → 2 × 2 = 4
        # cohort 2: per case breach=3*4=12 neglect=5 wip=1 → 18 × 1 = 18
        assert total == pytest.approx(22.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_harm.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement harm.py**

```python
# complaints_model/harm.py
"""Harm score accumulation — per-case-per-day customer harm scoring."""
from __future__ import annotations

from .cohort import Cohort
from .regulatory import REGULATORY_DEADLINES


def _days_past_deadline(cohort: Cohort) -> int:
    """Days past regulatory deadline (0 if not breached)."""
    deadline = REGULATORY_DEADLINES[cohort.case_type]
    if cohort.case_type == "FCA":
        overshoot = cohort.cal_age - deadline
    else:
        overshoot = cohort.biz_age - deadline
    return max(0, overshoot)


def score_case_harm(
    cohort: Cohort,
    sim_day: int,
    breach_w: float,
    neglect_w: float,
    wip_w: float,
) -> float:
    """Score total harm for a cohort on a single day.

    Returns harm × cohort.count (not per-case).
    """
    breach = breach_w * _days_past_deadline(cohort)
    touched = cohort.last_worked_day if cohort.last_worked_day is not None else cohort.arrival_day
    neglect = neglect_w * max(0, sim_day - touched)
    wip = wip_w
    return (breach + neglect + wip) * cohort.count


def accumulate_daily_harm(
    all_open: list[Cohort],
    sim_day: int,
    breach_w: float,
    neglect_w: float,
    wip_w: float,
) -> float:
    """Sum harm across all open cases for one day."""
    return sum(
        score_case_harm(c, sim_day, breach_w, neglect_w, wip_w)
        for c in all_open
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_harm.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add complaints_model/harm.py tests/test_harm.py
git commit -m "feat: add harm scoring module for optimisation objective"
```

---

## Task 4: Pool Simulation (`pool_simulation.py`)

**Files:**
- Create: `complaints_model/pool_simulation.py`
- Test: `tests/test_pool_simulation.py`

### Key knowledge for implementer

This is the core of the optimisation system. It runs a 730-day simulation with **multiple handler pools** (one per band) instead of a single global pool.

**Reusing existing engines:** The existing `allocate_up_to_capacity()` and `process_work_slice()` read their strategy from `cfg.allocation_strategy` / `cfg.work_strategy`. Use `dataclasses.replace(base_config, allocation_strategy=..., work_strategy=..., fte=band_fte)` to create per-band config copies. Pass band-specific `max_slots` and `slice_budget`.

**Parkinson's Law per band:** Each band has its own unallocated queue. Parkinson's pressure is computed per-band: `pressure = min(band_unalloc / (band_fte * diary_limit * 0.5), 1.0)`. Use half of band diary capacity as the full-pace threshold (proportional to band size).

**Band transitions:** After aging all cohorts, check each pool. If a cohort's age has moved it past its band boundary, remove it from the current pool (allocated or unallocated) and add it to the next band's unallocated queue. Transitioning cases lose `is_src=True` and `allocation_day` (they must be re-allocated).

**SRC scheduling:** Each band maintains its own `src_schedule`, `src_allocated_today`, and `src_closed_today` dicts. SRC cases that transition bands are no longer SRC.

**Intake:** New cases are assigned to their first band (F1/P1/C1) based on the pooling model.

**Metrics:** Same daily metrics dict as `simulate()`, plus `harm` field. Aggregate across all bands for global metrics.

**Circuit breaker:** If total WIP > `max_wip` (default 50,000), stop early — the configuration is unviable.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pool_simulation.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement pool_simulation.py**

```python
# complaints_model/pool_simulation.py
"""Pool-aware simulation — multiple handler pools with per-band strategies."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from statistics import mean

from .config import SimConfig
from .cohort import Cohort, merge_cohorts
from .time_utils import is_workday, make_age
from .effort import case_effort
from .regulatory import apply_psd2_extensions
from .intake import intake_distribution, seed_pool, INTAKE_PROPORTIONS
from .allocation import allocate_up_to_capacity
from .work import process_work_slice
from .metrics import (
    count_by_type, count_breaches, count_over_target, count_age_bands,
    calculate_instantaneous_fte_demand,
)
from .bands import get_bands_for_model, assign_band, detect_transitions
from .pool_config import OptimConfig, BandAllocation
from .harm import accumulate_daily_harm


def simulate_pooled(
    optim_cfg: OptimConfig,
    max_wip: float = 50_000,
) -> list[dict]:
    """Run 730-day pool-aware simulation.

    Returns list of daily result dicts (same shape as simulate() plus 'harm').
    """
    cfg = optim_cfg.base_config
    bands = get_bands_for_model(optim_cfg.pooling_model)
    band_names = [b.name for b in bands]

    # Build per-band config and capacity
    band_alloc_map: dict[str, BandAllocation] = {
        ba.band_name: ba for ba in optim_cfg.band_allocations
    }
    band_cfgs: dict[str, SimConfig] = {}
    band_max_slots: dict[str, float] = {}
    band_productive: dict[str, float] = {}

    for bname in band_names:
        ba = band_alloc_map[bname]
        band_cfgs[bname] = replace(
            cfg,
            fte=ba.fte,
            allocation_strategy=ba.allocation_strategy,
            work_strategy=ba.work_strategy,
        )
        present = ba.fte * (1 - cfg.absence_shrinkage)
        band_max_slots[bname] = present * cfg.diary_limit
        band_productive[bname] = ba.fte * (1 - cfg.shrinkage)

    # Initialise pools
    pools: dict[str, dict[str, list[Cohort]]] = {
        bname: {"unallocated": [], "allocated": []}
        for bname in band_names
    }

    # Seed initial WIP into bands
    initial_unalloc = seed_pool(2500 * 0.25, allocated=False, cfg=cfg)
    initial_alloc = seed_pool(2500 * 0.75, allocated=True, cfg=cfg)
    for c in initial_unalloc:
        bname = assign_band(c, bands)
        pools[bname]["unallocated"].append(c)
    for c in initial_alloc:
        bname = assign_band(c, bands)
        pools[bname]["allocated"].append(c)

    # Per-band SRC tracking
    band_src_schedule: dict[str, dict[int, dict[str, float]]] = {
        bname: {} for bname in band_names
    }

    results: list[dict] = []
    workday_num = 0
    cumulative_harm = 0.0
    steady_state_start = 366

    for day in range(cfg.days):
        workday = is_workday(day)

        # --- Age all cohorts ---
        for bname in band_names:
            for c in pools[bname]["unallocated"] + pools[bname]["allocated"]:
                c.cal_age += 1
                if workday:
                    c.biz_age += 1

        # --- PSD2 extensions ---
        if workday:
            for bname in band_names:
                pools[bname]["unallocated"] = apply_psd2_extensions(
                    pools[bname]["unallocated"], cfg.psd2_extension_rate
                )
                pools[bname]["allocated"] = apply_psd2_extensions(
                    pools[bname]["allocated"], cfg.psd2_extension_rate
                )

        # --- Band transitions ---
        movers_all: list[Cohort] = []
        for bname in band_names:
            stay_u, move_u = detect_transitions(pools[bname]["unallocated"], bname, bands)
            stay_a, move_a = detect_transitions(pools[bname]["allocated"], bname, bands)
            pools[bname]["unallocated"] = stay_u
            pools[bname]["allocated"] = stay_a
            movers_all.extend(move_u + move_a)

        # Reassign movers to new bands
        for c in movers_all:
            new_band = assign_band(c, bands)
            pools[new_band]["unallocated"].append(c)

        # --- Intake ---
        if workday:
            for case_type, proportion in INTAKE_PROPORTIONS.items():
                for reg_age, count in intake_distribution(cfg.daily_intake * proportion):
                    cal_age, biz_age = make_age(reg_age, case_type)
                    new_cohort = Cohort(
                        count=count, case_type=case_type,
                        cal_age=cal_age, biz_age=biz_age,
                        effort_per_case=0.0, is_src=False,
                        arrival_day=day, allocation_day=None,
                        seeded=False, last_worked_day=None,
                    )
                    bname = assign_band(new_cohort, bands)
                    pools[bname]["unallocated"].append(new_cohort)

        # --- Per-band allocation + work ---
        allocations_total = 0.0
        weighted_delay_total = 0.0
        allocations_by_type: dict[str, float] = defaultdict(float)
        closures_total = 0.0
        closures_by_type: dict[str, float] = defaultdict(float)
        close_sums_total = {
            ct: {"n": 0.0, "reg": 0.0, "cal": 0.0, "sys": 0.0}
            for ct in ["FCA", "PSD2_15", "PSD2_35"]
        }
        breached_closures_total: dict[str, float] = defaultdict(float)
        occupancy_before_work: list[float] = []

        if workday:
            for bname in band_names:
                ba = band_alloc_map[bname]
                if ba.fte == 0:
                    continue

                bcfg = band_cfgs[bname]
                b_max_slots = band_max_slots[bname]
                b_productive = band_productive[bname]

                # Parkinson's Law per band
                band_unalloc_count = sum(c.count for c in pools[bname]["unallocated"])
                full_pace_q = max(1.0, b_max_slots * 0.5)
                pressure = min(band_unalloc_count / full_pace_q, 1.0)
                eff_util = cfg.parkinson_floor + (cfg.utilisation - cfg.parkinson_floor) * pressure
                productive_hours = (
                    b_productive * cfg.hours_per_day * eff_util
                    * cfg.proficiency * (1 - cfg.late_demand_rate)
                )
                b_slice_budget = productive_hours / cfg.slices_per_day if cfg.slices_per_day > 0 else 0.0

                band_src_alloc_today: dict[str, float] = defaultdict(float)
                band_src_closed_today: dict[str, float] = defaultdict(float)

                for _ in range(cfg.slices_per_day):
                    # Allocate
                    (
                        pools[bname]["unallocated"],
                        pools[bname]["allocated"],
                        sl_allocs, sl_delay, sl_abt,
                    ) = allocate_up_to_capacity(
                        pools[bname]["unallocated"],
                        pools[bname]["allocated"],
                        b_max_slots, day,
                        band_src_alloc_today, bcfg,
                    )
                    allocations_total += sl_allocs
                    weighted_delay_total += sl_delay
                    for ct, cnt in sl_abt.items():
                        allocations_by_type[ct] += cnt

                    occupancy_before_work.append(
                        sum(c.count for c in pools[bname]["allocated"])
                    )

                    # Work
                    (
                        pools[bname]["allocated"],
                        sl_closures, sl_cbt, sl_cs, sl_bcbt,
                    ) = process_work_slice(
                        pools[bname]["allocated"],
                        b_slice_budget, day, workday_num,
                        band_src_alloc_today,
                        band_src_schedule[bname],
                        band_src_closed_today, bcfg,
                    )
                    closures_total += sl_closures
                    for ct, cnt in sl_cbt.items():
                        closures_by_type[ct] += cnt
                    for ct in close_sums_total:
                        for key in close_sums_total[ct]:
                            close_sums_total[ct][key] += sl_cs[ct][key]
                    for ct, cnt in sl_bcbt.items():
                        breached_closures_total[ct] += cnt

                    pools[bname]["allocated"] = [
                        c for c in pools[bname]["allocated"] if c.count > 0.01
                    ]

                # End-of-day refill
                (
                    pools[bname]["unallocated"],
                    pools[bname]["allocated"],
                    sl_allocs, sl_delay, sl_abt,
                ) = allocate_up_to_capacity(
                    pools[bname]["unallocated"],
                    pools[bname]["allocated"],
                    b_max_slots, day,
                    band_src_alloc_today, bcfg,
                )
                allocations_total += sl_allocs
                weighted_delay_total += sl_delay
                for ct, cnt in sl_abt.items():
                    allocations_by_type[ct] += cnt

                band_src_schedule[bname][workday_num] = dict(band_src_alloc_today)

            workday_num += 1

        # --- Cleanup + merge ---
        for bname in band_names:
            pools[bname]["allocated"] = [
                c for c in pools[bname]["allocated"] if c.count > 0.01
            ]
            pools[bname]["unallocated"] = [
                c for c in pools[bname]["unallocated"] if c.count > 0.01
            ]
            if day % 14 == 0:
                pools[bname]["allocated"] = merge_cohorts(pools[bname]["allocated"])
                pools[bname]["unallocated"] = merge_cohorts(pools[bname]["unallocated"])

        # --- Aggregate metrics ---
        all_unalloc = []
        all_alloc = []
        for bname in band_names:
            all_unalloc.extend(pools[bname]["unallocated"])
            all_alloc.extend(pools[bname]["allocated"])

        all_open = all_unalloc + all_alloc
        total_wip = sum(c.count for c in all_open)
        total_unallocated = sum(c.count for c in all_unalloc)
        total_allocated = sum(c.count for c in all_alloc)

        open_by_type = count_by_type(all_open)
        breaches_by_type = count_breaches(all_open)
        over_target_by_type = count_over_target(all_open)
        age_bands_metric, age_bands_by_type = count_age_bands(all_open)

        instantaneous_fte_demand = calculate_instantaneous_fte_demand(
            all_unalloc, all_alloc, day, cfg,
        )
        avg_allocation_delay = (
            weighted_delay_total / allocations_total if allocations_total > 0 else 0.0
        )

        all_slots = sum(band_max_slots[bn] for bn in band_names)
        occupancy_start = occupancy_before_work[0] if occupancy_before_work else total_allocated
        occupancy_avg = mean(occupancy_before_work) if occupancy_before_work else total_allocated
        occupancy_end = total_allocated

        max_unallocated_wait = max(
            (day - c.arrival_day for c in all_unalloc), default=0,
        )
        max_diary_untouched = max(
            (day - c.last_worked_day for c in all_alloc if c.last_worked_day is not None),
            default=0,
        )
        alloc_with_lwd = [c for c in all_alloc if c.last_worked_day is not None]
        total_alloc_lwd = sum(c.count for c in alloc_with_lwd)
        avg_diary_untouched = (
            sum((day - c.last_worked_day) * c.count for c in alloc_with_lwd)
            / total_alloc_lwd
            if total_alloc_lwd > 0.01 else 0.0
        )

        # --- Harm ---
        daily_harm = 0.0
        if day >= steady_state_start:
            daily_harm = accumulate_daily_harm(
                all_open, day,
                optim_cfg.harm_breach_weight,
                optim_cfg.harm_neglect_weight,
                optim_cfg.harm_wip_weight,
            )
            cumulative_harm += daily_harm

        # Effective utilisation (weighted across bands)
        effective_util = cfg.parkinson_floor  # fallback
        if workday:
            total_prod = sum(band_productive[bn] for bn in band_names if band_alloc_map[bn].fte > 0)
            if total_prod > 0:
                weighted_util = 0.0
                for bname in band_names:
                    if band_alloc_map[bname].fte == 0:
                        continue
                    bu = sum(c.count for c in pools[bname]["unallocated"])
                    fpq = max(1.0, band_max_slots[bname] * 0.5)
                    pr = min(bu / fpq, 1.0)
                    eu = cfg.parkinson_floor + (cfg.utilisation - cfg.parkinson_floor) * pr
                    weighted_util += eu * band_productive[bname]
                effective_util = weighted_util / total_prod

        results.append({
            "day": day,
            "workday": workday,
            "wip": total_wip,
            "unalloc": total_unallocated,
            "alloc": total_allocated,
            "open_by_type": open_by_type,
            "breaches_by_type": breaches_by_type,
            "over_target_by_type": over_target_by_type,
            "age_bands": age_bands_metric,
            "age_bands_by_type": age_bands_by_type,
            "allocations": allocations_total,
            "allocations_by_type": dict(allocations_by_type),
            "avg_allocation_delay": avg_allocation_delay,
            "closures": closures_total,
            "closures_by_type": dict(closures_by_type),
            "breached_closures_by_type": dict(breached_closures_total),
            "close_sums": close_sums_total,
            "demand_fte": instantaneous_fte_demand,
            "effective_util": effective_util,
            "desired_wip": sum(band_max_slots[bn] for bn in band_names) + cfg.unallocated_buffer,
            "occupancy_start": occupancy_start,
            "occupancy_avg": occupancy_avg,
            "occupancy_end": occupancy_end,
            "slot_capacity": all_slots,
            "max_unallocated_wait": max_unallocated_wait,
            "max_diary_untouched": max_diary_untouched,
            "avg_diary_untouched": avg_diary_untouched,
            "harm": daily_harm,
            "cumulative_harm": cumulative_harm,
        })

        if total_wip > max_wip:
            break

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pool_simulation.py -v -x`
Expected: All 5 tests PASS (the 730-day tests may take ~3-5 seconds each)

- [ ] **Step 5: Commit**

```bash
git add complaints_model/pool_simulation.py tests/test_pool_simulation.py
git commit -m "feat: add pool-aware multi-band simulation engine"
```

---

## Task 5: Optuna CLI Runner (`optimise.py`)

**Files:**
- Create: `optimise.py`
- Modify: `requirements.txt`
- Test: `tests/test_optimise.py`

### Key knowledge for implementer

`optimise.py` is the CLI entry point. It creates an Optuna study, defines an objective function that builds `OptimConfig` from trial parameters, runs `simulate_pooled()`, and extracts the objective value.

**FTE constraint:** Suggest N-1 bands freely with `trial.suggest_int()`, last band = `total_fte - sum(others)`. Clamp to 0 minimum.

**Conditional parameters:** Optuna's `trial.suggest_categorical("pooling_model", ...)` determines which bands exist. Use Optuna's built-in conditional parameter support — parameters for bands that don't exist in a given model are simply not suggested.

**Pruning:** Report cumulative harm at every 50-day checkpoint after day 366. Call `trial.report(value, step)` and `trial.should_prune()`.

**Objectives:** `composite_harm` uses cumulative harm score. `lowest_wip` uses mean WIP over days 366–730. `lowest_psd2` / `lowest_fca` / `lowest_total_breaches` use mean breach rates over days 366–730.

**Storage:** SQLite at `optimisation_results.db` — enables resume across sessions.

**CLI args:** `--objective`, `--fte`, `--trials`, `--breach-weight`, `--neglect-weight`, `--wip-weight`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_optimise.py
"""Tests for Optuna optimisation runner."""
import pytest
from optimise import build_optim_config, compute_objective


class TestBuildOptimConfig:
    def test_builds_valid_config_combined(self):
        """Simulates what a trial would produce for combined model."""
        # Fake trial params as a dict
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
        # Set some harm in steady state
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
        # Should be mean of WIP from day 366 onward
        expected = sum(r["wip"] for r in results[366:]) / len(results[366:])
        assert val == pytest.approx(expected)

    def test_death_spiral_returns_infinity(self):
        """If simulation stopped early (< 730 days), return infinity."""
        results = [{"day": d, "wip": 50000, "harm": 0, "cumulative_harm": 0,
                     "breaches_by_type": {}, "open_by_type": {}} for d in range(200)]
        val = compute_objective(results, "composite_harm")
        assert val == float("inf")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_optimise.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Update requirements.txt**

```
streamlit
plotly
optuna
```

- [ ] **Step 4: Install optuna**

Run: `pip install optuna`

- [ ] **Step 5: Implement optimise.py**

```python
# optimise.py
"""CLI runner — Optuna-based FTE pool optimisation."""
from __future__ import annotations

import argparse
import time
from statistics import mean

import optuna

from complaints_model.config import SimConfig
from complaints_model.pool_config import (
    OptimConfig, BandAllocation, ALLOC_STRATEGIES, WORK_STRATEGIES,
)
from complaints_model.bands import get_bands_for_model
from complaints_model.pool_simulation import simulate_pooled


OBJECTIVES = [
    "composite_harm", "lowest_wip",
    "lowest_psd2", "lowest_fca", "lowest_total_breaches",
]

POOLING_MODELS = ["separate", "combined", "hybrid"]


def build_optim_config(params: dict, total_fte: int, **harm_kwargs) -> OptimConfig:
    """Build OptimConfig from a flat parameter dict (as produced by suggest_params)."""
    pooling_model = params["pooling_model"]
    bands = get_bands_for_model(pooling_model)
    band_names = [b.name for b in bands]

    allocations = []
    fte_used = 0
    for i, bname in enumerate(band_names):
        if i < len(band_names) - 1:
            fte = params[f"{bname}_fte"]
            fte_used += fte
        else:
            fte = max(0, total_fte - fte_used)
        alloc_strat = params[f"{bname}_alloc"]
        work_strat = params[f"{bname}_work"]
        allocations.append(BandAllocation(bname, fte, alloc_strat, work_strat))

    return OptimConfig(
        total_fte=total_fte,
        pooling_model=pooling_model,
        band_allocations=allocations,
        **harm_kwargs,
    )


def suggest_params(trial: optuna.Trial, total_fte: int) -> dict:
    """Have Optuna suggest all parameters for a trial."""
    params: dict = {}
    pooling_model = trial.suggest_categorical("pooling_model", POOLING_MODELS)
    params["pooling_model"] = pooling_model

    bands = get_bands_for_model(pooling_model)
    band_names = [b.name for b in bands]

    fte_remaining = total_fte
    for i, bname in enumerate(band_names):
        if i < len(band_names) - 1:
            max_fte = min(fte_remaining, total_fte)
            fte = trial.suggest_int(f"{bname}_fte", 0, max_fte)
            fte_remaining -= fte
            fte_remaining = max(0, fte_remaining)
            params[f"{bname}_fte"] = fte
        params[f"{bname}_alloc"] = trial.suggest_categorical(
            f"{bname}_alloc", ALLOC_STRATEGIES,
        )
        params[f"{bname}_work"] = trial.suggest_categorical(
            f"{bname}_work", WORK_STRATEGIES,
        )

    return params


def compute_objective(results: list[dict], objective: str) -> float:
    """Extract the objective value from simulation results."""
    if len(results) < 730:
        return float("inf")

    steady = results[366:]

    if objective == "composite_harm":
        return results[-1]["cumulative_harm"]

    if objective == "lowest_wip":
        return mean(r["wip"] for r in steady)

    if objective == "lowest_psd2":
        def psd2_breach_pct(r: dict) -> float:
            total = r["open_by_type"].get("PSD2_15", 0) + r["open_by_type"].get("PSD2_35", 0)
            breached = r["breaches_by_type"].get("PSD2_15", 0) + r["breaches_by_type"].get("PSD2_35", 0)
            return (breached / total * 100) if total > 0 else 0.0
        return mean(psd2_breach_pct(r) for r in steady)

    if objective == "lowest_fca":
        def fca_breach_pct(r: dict) -> float:
            total = r["open_by_type"].get("FCA", 0)
            breached = r["breaches_by_type"].get("FCA", 0)
            return (breached / total * 100) if total > 0 else 0.0
        return mean(fca_breach_pct(r) for r in steady)

    if objective == "lowest_total_breaches":
        def total_breach_pct(r: dict) -> float:
            total = sum(r["open_by_type"].values())
            breached = sum(r["breaches_by_type"].values())
            return (breached / total * 100) if total > 0 else 0.0
        return mean(total_breach_pct(r) for r in steady)

    raise ValueError(f"Unknown objective: {objective}")


def objective(
    trial: optuna.Trial,
    total_fte: int,
    obj_name: str,
    harm_kwargs: dict,
) -> float:
    """Optuna objective function — one trial."""
    params = suggest_params(trial, total_fte)
    optim_cfg = build_optim_config(params, total_fte, **harm_kwargs)

    results = simulate_pooled(optim_cfg, max_wip=50_000)

    # Pruning: report at checkpoints after steady-state start
    for checkpoint in range(400, 730, 50):
        if checkpoint < len(results):
            r = results[checkpoint]
            if obj_name == "composite_harm":
                trial.report(r["cumulative_harm"], checkpoint)
            else:
                trial.report(r["wip"], checkpoint)
            if trial.should_prune():
                raise optuna.TrialPruned()

    return compute_objective(results, obj_name)


def run_study(
    obj_name: str = "composite_harm",
    total_fte: int = 148,
    n_trials: int = 200,
    harm_breach_weight: float = 3.0,
    harm_neglect_weight: float = 1.0,
    harm_wip_weight: float = 1.0,
) -> optuna.Study:
    """Create and run an Optuna study."""
    timestamp = int(time.time())
    study_name = f"{obj_name}_{total_fte}fte_{timestamp}"

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=20),
        storage=f"sqlite:///optimisation_results.db",
        study_name=study_name,
    )

    harm_kwargs = {
        "harm_breach_weight": harm_breach_weight,
        "harm_neglect_weight": harm_neglect_weight,
        "harm_wip_weight": harm_wip_weight,
    }

    study.optimize(
        lambda trial: objective(trial, total_fte, obj_name, harm_kwargs),
        n_trials=n_trials,
        show_progress_bar=True,
    )

    return study


def print_results(study: optuna.Study) -> None:
    """Print study results to stdout."""
    best = study.best_trial
    print(f"\n{'='*60}")
    print(f"Best trial: #{best.number}")
    print(f"Best value: {best.value:,.2f}")
    print(f"{'='*60}")
    print("\nBest parameters:")
    for key, val in sorted(best.params.items()):
        print(f"  {key}: {val}")

    try:
        importances = optuna.importance.get_param_importances(study)
        print(f"\nParameter importance:")
        for param, imp in sorted(importances.items(), key=lambda x: -x[1])[:10]:
            print(f"  {param}: {imp:.3f}")
    except Exception:
        pass

    print(f"\nCompleted trials: {len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])}")
    print(f"Pruned trials: {len([t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED])}")
    print(f"Failed trials: {len([t for t in study.trials if t.state == optuna.trial.TrialState.FAIL])}")


def main():
    parser = argparse.ArgumentParser(description="FTE Pool Optimisation via Optuna")
    parser.add_argument("--objective", choices=OBJECTIVES, default="composite_harm")
    parser.add_argument("--fte", type=int, default=148)
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--breach-weight", type=float, default=3.0)
    parser.add_argument("--neglect-weight", type=float, default=1.0)
    parser.add_argument("--wip-weight", type=float, default=1.0)
    args = parser.parse_args()

    study = run_study(
        obj_name=args.objective,
        total_fte=args.fte,
        n_trials=args.trials,
        harm_breach_weight=args.breach_weight,
        harm_neglect_weight=args.neglect_weight,
        harm_wip_weight=args.wip_weight,
    )
    print_results(study)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_optimise.py -v`
Expected: All 5 tests PASS

- [ ] **Step 7: Commit**

```bash
git add optimise.py requirements.txt tests/test_optimise.py
git commit -m "feat: add Optuna CLI runner for FTE pool optimisation"
```

---

## Task 6: Dashboard Page (`pages/3_Optimisation.py`)

**Files:**
- Create: `pages/3_Optimisation.py`

### Key knowledge for implementer

This follows the same pattern as `pages/2_Strategy_Comparison.py`: reads shared parameters from `st.session_state`, has sidebar controls, and displays results. Uses `@st.cache_data` to cache simulation runs.

The page needs to:
1. Show optimisation controls in sidebar (objective, FTE, trials, weights)
2. Run Optuna in a way that updates a Streamlit progress bar
3. Display best configuration as a table
4. Show Optuna visualisation charts (optimisation history, parameter importance, parallel coordinates)
5. "Replay Best Config" button — run `simulate_pooled` with the best config and show full charts

**Important:** Optuna's `study.optimize()` blocks — use `optuna.study.optimize()` with a callback for progress updates. Alternatively, run trial-by-trial in a loop for progress bar control.

**Optuna Plotly integration:** `optuna.visualization.plot_optimization_history(study)`, `plot_param_importances(study)`, `plot_parallel_coordinate(study)` return Plotly figures directly.

- [ ] **Step 1: Create the dashboard page**

```python
# pages/3_Optimisation.py
"""Streamlit page — FTE pool optimisation via Optuna."""
from __future__ import annotations

import streamlit as st
import optuna
import plotly.graph_objects as go

from complaints_model.config import SimConfig
from complaints_model.pool_config import (
    OptimConfig, BandAllocation, ALLOC_STRATEGIES, WORK_STRATEGIES,
)
from complaints_model.bands import get_bands_for_model
from complaints_model.pool_simulation import simulate_pooled
from optimise import (
    suggest_params, build_optim_config, compute_objective,
    OBJECTIVES, POOLING_MODELS,
)

st.set_page_config(page_title="FTE Optimisation", layout="wide")
st.title("FTE Pool Optimisation")

# ── Sidebar controls ─────────────────────────────────────────────
st.sidebar.header("Optimisation Settings")

obj_name = st.sidebar.selectbox(
    "Objective", OBJECTIVES,
    format_func=lambda x: x.replace("_", " ").title(),
)
total_fte = st.sidebar.number_input("Total FTE", 100, 300, 148, step=1)
n_trials = st.sidebar.slider("Trials", 50, 2000, 200, step=50)
pooling_model = st.sidebar.selectbox("Pooling Model", POOLING_MODELS + ["all"],
                                      format_func=lambda x: x.title())

show_weights = obj_name == "composite_harm"
if show_weights:
    st.sidebar.subheader("Harm Weights")
    breach_w = st.sidebar.slider("Breach weight", 0.0, 10.0, 3.0, 0.5)
    neglect_w = st.sidebar.slider("Neglect weight", 0.0, 10.0, 1.0, 0.5)
    wip_w = st.sidebar.slider("WIP weight", 0.0, 10.0, 1.0, 0.5)
else:
    breach_w, neglect_w, wip_w = 3.0, 1.0, 1.0

run_btn = st.sidebar.button("Run Optimisation", type="primary")

# ── State ─────────────────────────────────────────────────────────
if "optim_study" not in st.session_state:
    st.session_state.optim_study = None
if "optim_best_results" not in st.session_state:
    st.session_state.optim_best_results = None

# ── Run optimisation ──────────────────────────────────────────────
if run_btn:
    progress = st.progress(0, text="Starting optimisation...")
    status = st.empty()

    harm_kwargs = {
        "harm_breach_weight": breach_w,
        "harm_neglect_weight": neglect_w,
        "harm_wip_weight": wip_w,
    }

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=min(20, n_trials // 5)),
    )

    best_val = float("inf")

    def trial_callback(study: optuna.Study, trial: optuna.trial.FrozenTrial) -> None:
        nonlocal best_val
        pct = min(1.0, (trial.number + 1) / n_trials)
        if trial.value is not None and trial.value < best_val:
            best_val = trial.value
        progress.progress(pct, text=f"Trial {trial.number+1}/{n_trials} — best: {best_val:,.1f}")

    def make_objective(pm: str | None):
        def obj(trial: optuna.Trial) -> float:
            if pm is not None:
                params = {"pooling_model": pm}
                bands = get_bands_for_model(pm)
            else:
                pm_chosen = trial.suggest_categorical("pooling_model", POOLING_MODELS)
                params = {"pooling_model": pm_chosen}
                bands = get_bands_for_model(pm_chosen)

            band_names = [b.name for b in bands]
            fte_remaining = total_fte
            for i, bname in enumerate(band_names):
                if i < len(band_names) - 1:
                    fte = trial.suggest_int(f"{bname}_fte", 0, min(fte_remaining, total_fte))
                    fte_remaining = max(0, fte_remaining - fte)
                    params[f"{bname}_fte"] = fte
                params[f"{bname}_alloc"] = trial.suggest_categorical(f"{bname}_alloc", ALLOC_STRATEGIES)
                params[f"{bname}_work"] = trial.suggest_categorical(f"{bname}_work", WORK_STRATEGIES)

            oc = build_optim_config(params, total_fte, **harm_kwargs)
            results = simulate_pooled(oc, max_wip=50_000)

            # Pruning
            for cp in range(400, 730, 50):
                if cp < len(results):
                    val = results[cp]["cumulative_harm"] if obj_name == "composite_harm" else results[cp]["wip"]
                    trial.report(val, cp)
                    if trial.should_prune():
                        raise optuna.TrialPruned()

            return compute_objective(results, obj_name)
        return obj

    pm_arg = None if pooling_model == "all" else pooling_model
    study.optimize(make_objective(pm_arg), n_trials=n_trials, callbacks=[trial_callback])

    progress.progress(1.0, text="Optimisation complete!")
    st.session_state.optim_study = study

# ── Display results ───────────────────────────────────────────────
study = st.session_state.optim_study

if study is None:
    st.info("Configure settings in the sidebar and click **Run Optimisation** to start.")
    st.stop()

best = study.best_trial
col1, col2, col3 = st.columns(3)
col1.metric("Best Score", f"{best.value:,.2f}")
completed = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])
pruned = len([t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED])
col2.metric("Completed / Pruned", f"{completed} / {pruned}")
col3.metric("Best Trial", f"#{best.number}")

# Best configuration table
st.subheader("Best Configuration")
pm = best.params.get("pooling_model", "combined")
bands = get_bands_for_model(pm)
band_names = [b.name for b in bands]

rows = []
fte_used = 0
for i, bname in enumerate(band_names):
    if i < len(band_names) - 1:
        fte = best.params.get(f"{bname}_fte", 0)
        fte_used += fte
    else:
        fte = max(0, study.best_trial.params.get("total_fte", total_fte) - fte_used)
        fte = max(0, total_fte - fte_used)
    alloc = best.params.get(f"{bname}_alloc", "—")
    work = best.params.get(f"{bname}_work", "—")
    rows.append({"Band": bname, "FTE": fte, "Allocation Strategy": alloc, "Work Strategy": work})

st.table(rows)

# Optuna visualisation charts
st.subheader("Optimisation Charts")
chart_cols = st.columns(2)

try:
    fig_history = optuna.visualization.plot_optimization_history(study)
    chart_cols[0].plotly_chart(fig_history, use_container_width=True)
except Exception:
    chart_cols[0].warning("Could not render optimisation history.")

try:
    fig_importance = optuna.visualization.plot_param_importances(study)
    chart_cols[1].plotly_chart(fig_importance, use_container_width=True)
except Exception:
    chart_cols[1].warning("Could not render parameter importance.")

try:
    fig_parallel = optuna.visualization.plot_parallel_coordinate(study)
    st.plotly_chart(fig_parallel, use_container_width=True)
except Exception:
    st.warning("Could not render parallel coordinate plot.")

# Replay best config
st.subheader("Replay Best Configuration")
if st.button("Replay Best Config"):
    with st.spinner("Running simulation with best config..."):
        best_params = dict(best.params)
        if "pooling_model" not in best_params:
            best_params["pooling_model"] = pooling_model if pooling_model != "all" else "combined"
        harm_kw = {
            "harm_breach_weight": breach_w,
            "harm_neglect_weight": neglect_w,
            "harm_wip_weight": wip_w,
        }
        oc = build_optim_config(best_params, total_fte, **harm_kw)
        replay_results = simulate_pooled(oc)
        st.session_state.optim_best_results = replay_results

replay = st.session_state.optim_best_results
if replay is not None:
    import plotly.express as px

    days = [r["day"] for r in replay]
    wips = [r["wip"] for r in replay]
    harms = [r["harm"] for r in replay]
    closures = [r["closures"] for r in replay if r["workday"]]
    work_days = [r["day"] for r in replay if r["workday"]]

    rc1, rc2 = st.columns(2)
    rc1.plotly_chart(
        px.line(x=days, y=wips, labels={"x": "Day", "y": "WIP"}, title="WIP Over Time"),
        use_container_width=True,
    )
    rc2.plotly_chart(
        px.line(x=days, y=harms, labels={"x": "Day", "y": "Daily Harm"}, title="Daily Harm Score"),
        use_container_width=True,
    )

    # Breach rates
    fca_breach = [
        r["breaches_by_type"].get("FCA", 0) / max(r["open_by_type"].get("FCA", 1), 1) * 100
        for r in replay
    ]
    psd2_breach = [
        (r["breaches_by_type"].get("PSD2_15", 0) + r["breaches_by_type"].get("PSD2_35", 0))
        / max(r["open_by_type"].get("PSD2_15", 0) + r["open_by_type"].get("PSD2_35", 0), 1) * 100
        for r in replay
    ]
    rc3, rc4 = st.columns(2)
    rc3.plotly_chart(
        px.line(x=days, y=fca_breach, labels={"x": "Day", "y": "%"}, title="FCA Stock Breach %"),
        use_container_width=True,
    )
    rc4.plotly_chart(
        px.line(x=days, y=psd2_breach, labels={"x": "Day", "y": "%"}, title="PSD2 Stock Breach %"),
        use_container_width=True,
    )

    rc5, rc6 = st.columns(2)
    rc5.plotly_chart(
        px.line(x=work_days, y=closures, labels={"x": "Day", "y": "Closures"}, title="Daily Closures"),
        use_container_width=True,
    )
    cum_harm = [r["cumulative_harm"] for r in replay]
    rc6.plotly_chart(
        px.line(x=days, y=cum_harm, labels={"x": "Day", "y": "Cumulative Harm"}, title="Cumulative Harm"),
        use_container_width=True,
    )
```

- [ ] **Step 2: Manually verify dashboard page loads**

Run: `streamlit run dashboard.py`
Navigate to page 3 in the sidebar. Verify controls render without errors.

- [ ] **Step 3: Commit**

```bash
git add pages/3_Optimisation.py
git commit -m "feat: add optimisation dashboard page with Optuna integration"
```

---

## Task 7: Integration, Exports, and Final Validation

**Files:**
- Modify: `complaints_model/__init__.py`
- Modify: `.gitignore` (add `optimisation_results.db`)

### Key knowledge for implementer

Add new module exports to the package `__init__.py`. Add the SQLite database to `.gitignore`. Run all tests to ensure nothing is broken.

- [ ] **Step 1: Update `__init__.py` with new exports**

Add the following imports to the existing exports in `complaints_model/__init__.py`:

```python
from .bands import Band, FCA_BANDS, PSD2_BANDS, COMBINED_BANDS, get_bands_for_model, assign_band
from .pool_config import OptimConfig, BandAllocation, ALLOC_STRATEGIES, WORK_STRATEGIES
from .harm import score_case_harm, accumulate_daily_harm
from .pool_simulation import simulate_pooled
```

- [ ] **Step 2: Add optimisation_results.db to .gitignore**

Append to `.gitignore`:
```
optimisation_results.db
```

- [ ] **Step 3: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests pass (existing regression + new tests)

- [ ] **Step 4: Run a quick CLI smoke test**

Run: `python optimise.py --objective composite_harm --fte 148 --trials 5`
Expected: Completes 5 trials, prints best configuration and score.

- [ ] **Step 5: Commit**

```bash
git add complaints_model/__init__.py .gitignore
git commit -m "feat: integrate pool optimisation into package exports"
```

---

## Summary

| Task | Files | Tests | Estimated complexity |
|------|-------|-------|---------------------|
| 1. Band definitions | `bands.py` | 17 tests | Low |
| 2. OptimConfig | `pool_config.py` | 8 tests | Low |
| 3. Harm scoring | `harm.py` | 7 tests | Low |
| 4. Pool simulation | `pool_simulation.py` | 5 tests | **High** — core engine |
| 5. Optuna CLI | `optimise.py` | 5 tests | Medium |
| 6. Dashboard page | `pages/3_Optimisation.py` | Manual | Medium |
| 7. Integration | `__init__.py`, `.gitignore` | Full suite | Low |
