# Optimisation Design: FTE Pool Allocation via Optuna

**Date**: 2026-04-06
**Status**: Approved
**Objective**: Find the optimal way to split FTE across case-age bands and assign strategies per band to minimise customer harm.

---

## 1. Objectives

The optimizer supports five selectable objectives. You pick one per study.

| Objective | What it minimises |
|-----------|-------------------|
| **Composite harm** | Weighted sum of breach overshoot + neglect + WIP across all cases (main objective) |
| **Lowest WIP** | Average steady-state WIP (open cases) |
| **Lowest PSD2 breaches** | PSD2 stock breach rate |
| **Lowest FCA breaches** | FCA stock breach rate |
| **Lowest total breaches** | Combined PSD2 + FCA breach rate |

---

## 2. Composite Harm Score

Accumulated per open case per day, summed across all cases across the steady-state window (days 366–730):

```
daily_harm_per_case = (breach_weight × days_past_deadline)
                    + (neglect_weight × days_since_last_touched)
                    + (wip_weight × 1)

total_harm = Σ daily_harm_per_case  (all cases, all days in window)
```

**Default weights (configurable):**

| Component | Weight | Rationale |
|-----------|--------|-----------|
| `breach_weight` | 3.0 | Breach is the worst outcome for a customer |
| `neglect_weight` | 1.0 | Customer waiting without contact |
| `wip_weight` | 1.0 | Every open case represents an impacted customer |

- Breach overshoot is **linear** — two customers 10 days breached is worse than one customer 20 days breached (because WIP adds +2 vs +1)
- `days_past_deadline` = 0 if case is not breached
- `days_since_last_touched` = days since case was last worked on (or since arrival if never touched)

---

## 3. Decision Space

The optimizer explores three dimensions per band:

### 3.1 FTE Split
- Integer FTE allocation per band
- Must sum to total FTE (e.g. 148)
- Can be zero (cases in that band age into the next band)

### 3.2 Case-Age Bands

**FCA bands (calendar age):**

| Band | Age range | Description |
|------|-----------|-------------|
| F1 | 0–3 days | Fresh intake, SRC window |
| F2 | 3–20 days | Early investigation |
| F3 | 20–40 days | Mid-tier |
| F4 | 40–56 days | Approaching deadline |
| F5 | 56+ days | Breached |

**PSD2 bands (business age):**

| Band | Age range | Description |
|------|-----------|-------------|
| P1 | 0–3 days | Fresh intake |
| P2 | 3–10 days | Early investigation |
| P3 | 10–15 days | Approaching standard deadline |
| P4 | 15–35 days | Extended cases only (must track extension flag) |
| P5 | 35+ days | Breached |

PSD2 cases that have NOT been extended breach at 15 business days — they move to P5 (breached) from P3, skipping P4. Only cases with the extension flag enter P4.

### 3.3 Strategies Per Band
- **Allocation strategy**: one of 6 (nearest_deadline, nearest_target, youngest_first, oldest_first, psd2_priority, longest_wait)
- **Work strategy**: one of 6 (nearest_deadline, nearest_target, youngest_first, oldest_first, lowest_effort, longest_untouched)

### 3.4 Pooling Models

The optimizer explores which pooling model to use:

| Model | Description |
|-------|-------------|
| **Separate** | FCA and PSD2 have independent FTE pools — 10 bands total, FTE split across all 10 |
| **Combined** | Bands defined by distance-to-deadline — 5 urgency tiers, handlers work both case types |
| **Hybrid** | Dedicated PSD2 pool (tighter deadlines) + remaining FTE on FCA bands |

Pooling model is a categorical parameter — Optuna's conditional parameter system handles the different parameter trees per model.

---

## 4. Hard Constraints

1. Total FTE is fixed (default 148) — pool allocations must sum exactly
2. FTE per band must be whole numbers
3. Every case belongs to exactly one band at any point in time
4. Cases age through bands naturally — when a case crosses an age boundary, it moves to the next band's pool
5. Utilisation cannot exceed 100%
6. Diary limit stays at 7 per handler
7. Shrinkage (0.42) and absence (0.15) rates are fixed
8. Daily intake stays at 300
9. SRC window stays at 3 days
10. Band age boundaries are fixed (not tuneable)
11. Simulation runs 730 days; objectives measured on days 366–730 only

---

## 5. Architecture

### 5.1 Existing Code — No Changes

The `complaints_model/` package stays untouched:
- `simulate()` — original single-strategy simulation
- `SimConfig` — original configuration
- All existing modules (allocation, work, strategies, metrics, etc.)
- Dashboard page 1, page 2, `run_scenarios.py`, all tests

### 5.2 New Files

| File | Purpose |
|------|---------|
| `complaints_model/bands.py` | Band definitions (FCA + PSD2), case-to-band assignment, ageing/handoff logic between bands |
| `complaints_model/pool_config.py` | `OptimConfig` dataclass — band FTE splits, per-band strategies, pooling model, harm weights |
| `complaints_model/pool_simulation.py` | `simulate_pooled(optim_config)` — the pool-aware simulation loop |
| `complaints_model/harm.py` | Harm score accumulation — per-case-per-day scoring with configurable weights |
| `optimise.py` | CLI runner — select objective, run Optuna study, output best config and results |
| `pages/3_Optimisation.py` | Streamlit dashboard page — configure, run, and visualise optimisation results |

### 5.3 Dependency Flow

```
OptimConfig
    → bands.py (band definitions, case assignment)
    → pool_simulation.py (multi-pool simulation loop)
        → uses existing: cohort, regulatory, effort, strategies, time_utils
        → harm.py (accumulates harm score per day)
    → metrics.py (existing KPI computation — reused)
    → optimise.py / pages/3_Optimisation.py (Optuna orchestration)
```

### 5.4 Pool-Aware Simulation (`simulate_pooled`)

Key differences from `simulate()`:

1. **Multiple handler pools** — each band has N handlers with diary_limit=7
2. **Band-aware allocation** — unallocated cases filtered by age range, sorted by that band's allocation strategy, allocated to that band's handlers
3. **Band transitions** — daily check: if a case has aged past its band boundary, remove from current handler's diary, place in next band's unallocated sub-queue
4. **Per-band work engine** — handlers in each band work their diary cases sorted by that band's work strategy
5. **Harm accumulation** — after each day's work, score every open case and accumulate

Cases that transition between bands reset their "allocation" status — they re-enter the new band's queue and must be allocated to a handler in that band.

---

## 6. Optuna Integration

### 6.1 Study Configuration

```python
study = optuna.create_study(
    direction="minimize",
    sampler=optuna.samplers.TPESampler(),
    pruner=optuna.pruners.MedianPruner(n_startup_trials=20),
    storage="sqlite:///optimisation_results.db",
    study_name=f"{objective}_{fte}fte_{timestamp}"
)
```

### 6.2 Trial Parameter Suggestion

Each trial suggests:
1. Pooling model (categorical: separate/combined/hybrid)
2. FTE split per band (integer, conditional on pooling model)
3. Allocation strategy per band (categorical)
4. Work strategy per band (categorical)

FTE constraint enforced by: suggest N-1 bands freely, last band gets the remainder.

### 6.3 Pruning

Report intermediate values at day checkpoints (e.g. every 50 days). If a trial's WIP is exploding or harm is already worse than the median, Optuna kills it early. This dramatically reduces runtime for bad configurations.

### 6.4 Expected Runtime

- Single simulation: ~1-2 seconds for 730 days
- With pruning: bad trials die at ~200 days (~0.5s)
- 1000 trials: ~20-40 minutes
- SQLite storage: resume studies across sessions

### 6.5 Outputs

Per study:
- **Best configuration**: FTE splits, strategies per band, pooling model
- **Best score**: objective value
- **Parameter importance**: which decisions matter most (Optuna built-in)
- **Optimisation history**: convergence plot
- **Parallel coordinates**: visualise parameter interactions

---

## 7. Dashboard Page 3: Optimisation

### Controls (sidebar):
- Objective dropdown (composite/WIP/PSD2/FCA/total breaches)
- Total FTE input
- Number of trials slider (100–2000)
- Harm weights (breach/neglect/WIP) — only shown for composite objective
- "Run Optimisation" button

### Results display:
- Progress bar during optimisation
- Best configuration table (band → FTE, alloc strategy, work strategy)
- Best score + comparison to baseline (single-strategy best)
- Optuna visualisation charts (importance, history, parallel coordinates)
- "Replay Best Config" button → runs the best config and shows the full 13-chart dashboard for that configuration

---

## 8. Future Extensions (not in scope now)

- FTE sweep across staffing levels
- Tuneable band boundaries
- Multi-skilling (handlers working across bands)
- Shrinkage sensitivity analysis
- Variable intake levels
- Multi-objective Pareto frontiers (trade-off curves between objectives)
- Tuneable harm weights as Optuna parameters

---

## 9. Dependencies

New pip dependency: `optuna` (add to `requirements.txt`)

Optional for dashboard visualisations: `optuna[visualization]` (includes plotly integration)
