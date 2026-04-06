# Modular Refactor Design Spec

## Goal

Refactor the complaints simulation from two monolithic files (prove_maths.py 1275 lines + strategy_model.py 671 lines) into a clean `complaints_model/` package with:
- **SimConfig dataclass** replacing global mutation
- **One file per responsibility**, each <200 lines
- **Strategy support merged in** (delete strategy_model.py)
- **Zero regression** — identical simulation output for identical inputs

## Architecture

```
complaints_model/
├── __init__.py          # Public API: SimConfig, simulate, STRATEGIES
├── config.py            # SimConfig dataclass + defaults + validation
├── cohort.py            # Cohort dataclass + merge_cohorts
├── time_utils.py        # is_workday, count_business_days_*, make_age
├── regulatory.py        # regulatory_age, remaining_workdays_to_*, deadlines, PSD2 extensions
├── effort.py            # burden_mult, case_effort, BURDEN bands
├── intake.py            # intake_distribution, starting_wip_distribution, seed_pool, INTAKE_AGE_PROFILE
├── strategies.py        # Strategy registry, sort-key functions for allocation + work
├── allocation.py        # allocate_up_to_capacity (strategy-aware)
├── work.py              # process_work_slice (strategy-aware)
├── simulation.py        # simulate() main loop + Parkinson's Law pressure calc
├── metrics.py           # count_by_type, count_breaches, count_age_bands, breach rates, stability, closure summaries
└── reporting.py         # print_stable_pack, print_fte_sweep, main() CLI entry point

dashboard.py             # Updated: builds SimConfig from sliders, no globals mutation
run_scenarios.py          # Updated: imports from complaints_model
compare_staffing.py       # Updated: imports from complaints_model
```

## Key Design Decisions

### 1. SimConfig replaces globals

All 30+ module-level constants become fields on a frozen dataclass with defaults matching current values:

```python
@dataclass(frozen=True)
class SimConfig:
    fte: int = 148
    shrinkage: float = 0.42
    absence_shrinkage: float = 0.15
    hours_per_day: float = 7.0
    utilisation: float = 1.00
    proficiency: float = 1.0
    diary_limit: int = 7
    daily_intake: int = 300
    base_effort: float = 1.5
    min_diary_days: int = 0
    min_diary_days_non_src: int = 3
    handoff_overhead: float = 0.15
    handoff_effort_hours: float = 0.5
    late_demand_rate: float = 0.08
    days: int = 730
    slices_per_day: int = 4
    unallocated_buffer: int = 300
    parkinson_floor: float = 0.70
    parkinson_full_pace_queue: int = 600
    src_boost_max: float = 0.15
    src_boost_decay_days: int = 5
    src_window: int = 3
    src_effort_ratio: float = 0.7
    psd2_extension_rate: float = 0.05
    allocation_strategy: str = "nearest_target"
    work_strategy: str = "nearest_target"
```

Dict constants (SERVICE_TARGETS, REGULATORY_DEADLINES, BREACH_TARGETS, INTAKE_PROPORTIONS, SRC_RATES, BURDEN, AGE_BANDS, SRC_DIST, AM/PM shares) stay as module-level constants in their respective files — they are structural/regulatory and not tunable via dashboard sliders.

**Why frozen?** Prevents accidental mutation mid-simulation. If you need different params, create a new config.

### 2. Cohort uses strategy_model's version

The merged Cohort includes `last_worked_day: int | None = None` from strategy_model. This is the superset — supports both basic and strategy-aware simulation.

### 3. Strategy support is built-in

The STRATEGIES dict from strategy_model.py moves to `strategies.py`. `allocate_up_to_capacity` and `process_work_slice` accept a strategy name from config and look up the sort key. Default "nearest_target" reproduces current prove_maths behaviour exactly.

### 4. All functions receive config explicitly

Every function that currently reads globals gets `cfg: SimConfig` as its first parameter. Pure functions that only do math on their inputs (e.g. `is_workday`, `regulatory_age`) don't need config.

### 5. Dependency flow (no circular imports)

```
config.py
    ↓
cohort.py ← time_utils.py
    ↓
regulatory.py ← time_utils.py
    ↓
effort.py ← regulatory.py
    ↓
strategies.py ← regulatory.py, effort.py
    ↓
intake.py ← cohort.py, effort.py, time_utils.py
    ↓
allocation.py ← strategies.py, regulatory.py, effort.py, cohort.py
    ↓
work.py ← strategies.py, regulatory.py, effort.py, cohort.py
    ↓
simulation.py ← all above
    ↓
metrics.py ← regulatory.py, time_utils.py
    ↓
reporting.py ← simulation.py, metrics.py
```

### 6. Public API

```python
# complaints_model/__init__.py
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
```

### 7. Dashboard migration

Before (globals mutation):
```python
pm.SHRINKAGE = slider_val
pm.DAILY_INTAKE = slider_val
result = pm.simulate(fte)
```

After (config object):
```python
from complaints_model import SimConfig, simulate
cfg = SimConfig(fte=fte, shrinkage=slider_val, daily_intake=slider_val, days=365)
result = simulate(cfg)
```

### 8. Regression validation

The refactor MUST produce identical output. Validation approach:
- Run prove_maths.simulate(148) before refactor, capture final-day metrics
- Run complaints_model.simulate(SimConfig()) after refactor
- Assert all KPIs match to 6 decimal places
- Run strategy combos through run_scenarios.py and compare

### 9. What gets deleted

- `prove_maths.py` — replaced entirely by `complaints_model/`
- `strategy_model.py` — merged into `complaints_model/`

### 10. What stays unchanged

- `dashboard.py` — updated imports/API, same charts and layout
- `run_scenarios.py` — updated imports/API, same subprocess isolation pattern
- `compare_staffing.py` — updated imports/API, same comparison logic
- All regulatory constants, SRC rates, burden bands, intake profiles — values unchanged
