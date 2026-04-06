# Allocation & Work Strategy Scenarios — Design Spec

**Date:** 2026-04-06
**Status:** POC
**Goal:** Prove mathematically the impact of different allocation and work prioritisation strategies on regulatory breaches, WIP, and case neglect.

## Problem Statement

The current simulation model uses a single hardcoded prioritisation strategy (`nearest_target`) for both:
1. **Allocation** — which cases move from the unallocated queue into handler diaries
2. **Work** — which cases in their diary a handler actually picks up next

In reality, management controls allocation policy but colleagues often work their diary differently (cherry-picking easy cases, working nearest-deadline regardless of policy, etc.). We need to model these as **two independent dimensions** and compare all combinations to quantify the impact of each strategy on key outcomes.

## Architecture

### Approach: Strategy Registry (module-level globals)

Follows the existing pattern in `prove_maths.py` where all config is module-level constants. Two new globals select the active strategy:

```python
ALLOCATION_STRATEGY = "nearest_target"   # default = current behaviour
WORK_STRATEGY = "nearest_target"         # default = current behaviour
```

A `STRATEGIES` dict maps names to sort-key functions. The existing `priority_key()` function becomes the `nearest_target` entry. `allocate_up_to_capacity()` and `process_work_slice()` each look up their respective strategy instead of calling `priority_key()` directly.

### Why not pass strategies as function parameters?

Cleaner API, but requires changing function signatures through 3-4 levels. The globals pattern matches how every other config value works in this codebase. We can refactor to parameter-passing later if needed.

## Strategy Definitions

### Allocation Strategies (6)

These control which cases leave the unallocated queue first when diary slots open.

| Name | Sort Key | Rationale |
|------|----------|-----------|
| `nearest_deadline` | Regulatory deadline remaining (ascending) | Minimise breach risk — grab the most urgent cases |
| `nearest_target` | Service target remaining, then deadline, then age (ascending) | **Current behaviour.** Balance target and deadline |
| `youngest_first` | Most recently arrived at the company / FIFO (lowest regulatory age) | Maximise SRC opportunity — young cases resolve faster |
| `oldest_first` | Longest in queue (ascending by age) | Prevent queue rot — nothing sits forever |
| `psd2_priority` | PSD2 cases first, then by deadline | Protect the tighter deadline type |
| `longest_wait` | Longest time since arrival without allocation | Prevent any case sitting forgotten in the queue |

### Work Strategies (6)

These control which cases a handler picks up from their diary to work on.

| Name | Sort Key | Rationale |
|------|----------|-----------|
| `nearest_deadline` | Regulatory deadline remaining (ascending) | Breach prevention — work what's most urgent |
| `nearest_target` | Service target remaining, then deadline, then age (ascending) | **Current behaviour** |
| `youngest_first` | Most recently allocated to diary (lowest regulatory age in diary) | Cherry-picking / SRC chasing behaviour |
| `oldest_first` | Oldest in diary (ascending by age) | Work what's been sat there longest |
| `lowest_effort` | Cheapest cases first (ascending effort) | Volume-chasing — close count looks good on paper |
| `longest_untouched` | Most days since last worked (descending recency) | Prevent diary neglect |

## Data Model Changes

### Cohort dataclass — one new field

```python
last_worked_day: int | None = None
```

- Set to `sim_day` on allocation (in `allocate_up_to_capacity`)
- Updated to `sim_day` whenever a case gets partially or fully worked (in `process_work_slice`)
- Preserved through `merge_cohorts` (included in merge key + constructor — without this, resets to `None` every 14 days)
- Preserved through `apply_psd2_extensions` (propagated when PSD2_15 splits into stay/extend cohorts)
- Preserved through cohort splits in `allocate_up_to_capacity` (kept_unallocated retains original value)
- Used by the `longest_untouched` work strategy and the 3 new neglect metrics

### New daily metrics (added to simulate() output dict)

| Metric | Definition |
|--------|------------|
| `max_unallocated_wait` | Max days since arrival for any case in the unallocated queue |
| `max_diary_untouched` | Max days since `last_worked_day` for any case in diary |
| `avg_diary_untouched` | Weighted average days since `last_worked_day` across diary |

## Code Changes

### `prove_maths.py`

1. **Add `STRATEGIES` dict** — maps strategy names to sort-key lambdas/functions
2. **Add `ALLOCATION_STRATEGY` and `WORK_STRATEGY` globals** — default to `"nearest_target"`
3. **Rename `priority_key()`** to `nearest_target_key()` — becomes one entry in the dict
4. **`allocate_up_to_capacity()`** — change sort from `priority_key` to `STRATEGIES[ALLOCATION_STRATEGY]`
5. **`process_work_slice()`** — change both sorts (SRC candidates + regular candidates) to `STRATEGIES[WORK_STRATEGY]`
6. **`Cohort` dataclass** — add `last_worked_day: int | None = None`
7. **Update `last_worked_day`** in allocation and work functions
8. **`merge_cohorts()`** — add `last_worked_day` to merge key tuple and Cohort constructor (without this, `last_worked_day` resets to `None` every 14 days when cohorts are merged)
9. **`apply_psd2_extensions()`** — propagate `last_worked_day` in both Cohort constructors (PSD2_15 stay and PSD2_35 extension splits)
10. **Add 3 new metrics** to daily output dict in `simulate()`

### New file: `run_scenarios.py`

Separate file for the scenario runner. Does not modify `prove_maths.py` logic — only sets globals and calls `simulate()`.

1. Import `simulate` and strategy globals from `prove_maths`
2. Define the 6×6 = 36 strategy combinations
3. For each combo:
   - Set `ALLOCATION_STRATEGY` and `WORK_STRATEGY`
   - Call `simulate(DEFAULT_FTE)`
   - Extract steady-state KPIs from last 30 workdays
4. Print ranked comparison table
5. Accept optional `--sort-by` argument to rank by any KPI column

### KPIs per scenario (averaged over last 30 workdays)

| KPI | Description |
|-----|-------------|
| Steady-state WIP | Total cases in system (unallocated + diary) |
| FCA breach % (stock) | % of open cases past 56 calendar days |
| PSD2 breach % (stock) | % of open PSD2 cases past deadline |
| FCA breach % (flow) | % of FCA closures in last 30 workdays that were breached at closure |
| PSD2 breach % (flow) | % of PSD2 closures in last 30 workdays that were breached at closure |
| Avg close age (FCA) | Average regulatory age at closure for FCA cases |
| Avg close age (PSD2) | Average regulatory age at closure for PSD2 cases |
| Max unallocated wait | Oldest case in queue (days since arrival) |
| Max diary untouched | Longest neglected diary case (days since last worked) |
| Effective utilisation | Average handler utilisation % |

### Console output format

```
SCENARIO COMPARISON (120 FTE, 300 intake/day)
═══════════════════════════════════════════════════════════════════════════════════
Rank  Alloc Strategy     Work Strategy      WIP   FCA%  PSD2%  MaxWait  Util
─────────────────────────────────────────────────────────────────────────────────
  1   nearest_target     nearest_target    1014   0.0%   2.1%    1.2d   87%
  2   youngest_first     nearest_deadline  1089   0.0%   1.8%    0.8d   86%
 ...
 36   oldest_first       lowest_effort     2841  12.3%  18.7%   14.2d   91%
═══════════════════════════════════════════════════════════════════════════════════

Sorted by: WIP (ascending). Use --sort-by <column> to change.
```

## Multi-touch Model Note

The current model is cohort-based: cases either close fully or not at all in a given work slice. There is no partial progress tracking on individual cases. This means:

- Cases DO persist in diary across multiple days if budget is insufficient
- Older cases cost progressively more effort (burden scaling simulates increasing complexity)
- But a half-worked case doesn't carry forward its partial hours

This is an acceptable simplification for the POC. True multi-touch tracking (individual case state) would require moving from cohort to agent-based simulation and would significantly impact performance.

## Regression Safety

Before any code changes:
1. Capture current output of `simulate(120)` as a numerical baseline
2. After adding strategies, run with `nearest_target` / `nearest_target`
3. Assert identical output to within floating-point tolerance
4. This proves the refactor hasn't changed existing model behaviour

## Scope

### In scope (POC)
- Strategy registry with 6 allocation + 6 work strategies
- `last_worked_day` field on Cohort + 3 new daily metrics
- `run_scenarios.py` — console table output, 36 combos, sortable by any KPI
- Default FTE only (120) — single staffing level per run
- Regression test against current baseline

### Out of scope (future)
- Weighted scoring / blended strategies
- Optuna/scipy black-box optimisation ("find the best strategy for metric X")
- FTE sweep × strategy sweep (360+ combos)
- Dashboard integration (Streamlit dropdowns for strategy selection)
- Individual case tracking / partial progress
- Performance optimisation for sub-second planner interactivity
- Custom user-defined strategy functions
