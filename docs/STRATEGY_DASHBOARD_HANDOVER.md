# Strategy Scenarios — Dashboard Integration Handover

**Date:** 2026-04-06
**Status:** Ready for dashboard integration
**Author:** Claude (code review validated)

## What was built

A strategy comparison system that tests 36 combinations of allocation and work prioritisation against the existing complaints demand model. Two new files plus one realism fix to `prove_maths.py`.

### New files

| File | Purpose | Lines |
|------|---------|-------|
| `strategy_model.py` | Fork of `prove_maths.py` with strategy registry. Imports constants/helpers from prove_maths, redefines only the functions that create Cohort instances or use strategy lookup. | ~670 |
| `run_scenarios.py` | CLI scenario runner — runs all 36 combos in subprocesses, prints ranked table. Used for validation. | ~230 |

### What changed in prove_maths.py

1. **`MIN_DIARY_DAYS_NON_SRC = 3`** — new constant. Non-SRC cases need at least 3 business days in diary before closure (if it didn't resolve on first contact, it needs investigation). SRC cases still use `MIN_DIARY_DAYS = 0` (same-day close). The `closeable()` function in `process_work_slice` now checks `cohort.is_src` to select the right minimum. **This changes the minimum stable FTE from ~119 to ~138** because non-SRC cases occupy diary slots for 3+ extra days, reducing effective diary throughput. `DEFAULT_FTE` updated to 148. `FTE_SWEEP` updated to `range(135, 155)`.

### What strategy_model.py adds on top

1. **Strategy registry** — `STRATEGIES` dict mapping 8 strategy names to sort-key functions
2. **Two globals** — `ALLOCATION_STRATEGY` and `WORK_STRATEGY` (both default `"nearest_target"` = current behaviour)
3. **Extended Cohort** — adds `last_worked_day: int | None` field for neglect tracking
4. **3 new daily metrics** in simulate() output:
   - `max_unallocated_wait` — max days any case has sat in unallocated queue
   - `max_diary_untouched` — max days since any diary case was last worked on
   - `avg_diary_untouched` — weighted average days since last worked across diary
6. **Circuit breaker** — simulation stops early if WIP > 50,000 (prevents memory crashes on death-spiral strategies)

### Strategies available

**Allocation (6)** — which cases leave the unallocated queue first:

| Name | Behaviour |
|------|-----------|
| `nearest_deadline` | Most urgent deadline first |
| `nearest_target` | **Current behaviour.** Nearest to internal service target |
| `youngest_first` | Freshest cases first — maximises SRC opportunity |
| `oldest_first` | Oldest regulatory age first — causes death spiral, included as a warning |
| `psd2_priority` | PSD2 cases first, then by deadline |
| `longest_wait` | Longest time since arrival — causes death spiral |

**Work (6)** — which cases a handler picks from their diary:

| Name | Behaviour |
|------|-----------|
| `nearest_deadline` | Work what's most urgent |
| `nearest_target` | **Current behaviour** |
| `youngest_first` | Cherry-picking — work easiest/newest first |
| `oldest_first` | Work what's been sat there longest |
| `lowest_effort` | Volume-chasing — close cheapest cases first |
| `longest_untouched` | Neglect prevention — work what hasn't been touched longest |

## Dashboard integration guide

### Architecture decision: import strategy_model, not prove_maths

The dashboard currently does:
```python
import prove_maths as pm
pm.SHRINKAGE = slider_value
# ... set all globals ...
result = pm.simulate(fte)
```

For strategy support, switch to:
```python
import strategy_model as sm
sm.SHRINKAGE = slider_value  # works — strategy_model re-exports all constants
sm.ALLOCATION_STRATEGY = "nearest_target"  # new
sm.WORK_STRATEGY = "nearest_target"        # new
result = sm.simulate(fte)
```

**Simplest approach:** switch the dashboard import to `import strategy_model as pm`. It exports the same `simulate()` API with the same globals pattern, plus the strategy globals. All existing slider → `pm.CONSTANT = value` assignments work unchanged because `strategy_model` imports the same constants. You only need to add `pm.ALLOCATION_STRATEGY` and `pm.WORK_STRATEGY` assignments.

**Note:** `strategy_model` uses `from prove_maths import ...` at import time. After that, setting `pm.DAILY_INTAKE = 500` on the strategy_model module sets it in strategy_model's namespace, which is what `sm.simulate()` reads. This is the same pattern the dashboard already uses with prove_maths.

### Sidebar additions needed

Add a new sidebar section for strategy selection:

```python
st.sidebar.header("Strategy")
alloc_strategy = st.sidebar.selectbox(
    "Allocation Strategy",
    ["nearest_target", "nearest_deadline", "youngest_first",
     "oldest_first", "psd2_priority", "longest_wait"],
    index=1,  # default: nearest_target
    help="Which cases leave the unallocated queue first"
)
work_strategy = st.sidebar.selectbox(
    "Work Strategy",
    ["nearest_target", "nearest_deadline", "youngest_first",
     "oldest_first", "lowest_effort", "longest_untouched"],
    index=0,  # default: nearest_target
    help="Which cases a handler picks from their diary"
)
```

Then pass these to the simulation:
```python
sm.ALLOCATION_STRATEGY = alloc_strategy
sm.WORK_STRATEGY = work_strategy
```

And add them to the `run_simulation` cache key (add as parameters so Streamlit cache invalidates on strategy change).

### New charts to add

The 3 new metrics in simulate() output enable new visualisations:

1. **Neglect metrics chart** (new Section 9):
```python
st.header("Case Neglect")
col1, col2 = st.columns(2)
with col1:
    st.subheader("Max Unallocated Wait")
    # df["max_unallocated_wait"] — all days
with col2:
    st.subheader("Diary Untouched")
    # df["max_diary_untouched"] and df["avg_diary_untouched"] — all days
```

2. **New KPI cards** to add to the existing row:
   - Max Queue Wait (days)
   - Max Diary Neglect (days)
   - Avg Diary Neglect (days)

### Flatten daily records update

The existing `df` dict flattening loop needs the 3 new keys:
```python
df["max_unallocated_wait"] = [r["max_unallocated_wait"] for r in results]
df["max_diary_untouched"] = [r["max_diary_untouched"] for r in results]
df["avg_diary_untouched"] = [r["avg_diary_untouched"] for r in results]
```

### run_simulation cache update

Add strategy parameters to the cache function signature:
```python
@st.cache_data(show_spinner="Running simulation...")
def run_simulation(
    p_alloc_strategy, p_work_strategy,  # NEW
    p_fte, p_shrinkage, ...
):
    sm.ALLOCATION_STRATEGY = p_alloc_strategy  # NEW
    sm.WORK_STRATEGY = p_work_strategy          # NEW
    sm.SHRINKAGE = p_shrinkage
    # ... rest unchanged ...
    return sm.simulate(p_fte)
```

## Key findings for context

At **148 FTE** (comfortable): strategy barely matters — most combos stable with WIP ~1030, ~0% FCA breach.

At **~135 FTE** (stressed — near instability threshold of 138):
- `youngest_first` allocation + `oldest_first` or `longest_untouched` work = best stress-resilient combo
- `oldest_first` or `longest_wait` allocation = instant death spiral (WIP 48,000+)
- `lowest_effort` work = deceptive — great closure numbers but massive hidden breach backlog
- Current `nearest_target / nearest_target` collapses near instability

**Note:** `MIN_DIARY_DAYS_NON_SRC = 3` moved the instability threshold from ~119 to ~138 FTE. This is the realistic staffing cost of non-SRC investigation time.

## Validated

- **Regression:** `nearest_target / nearest_target` matches `prove_maths.simulate()` to 0.000% WIP difference
- **Realism:** SRC is NOT assumed for all cases (~55% max). Non-SRC cases require 1+ business day in diary.
- **Maths reviewed:** All sort keys verified correct. Pre-aged intake correctly produces ~2.3% PSD2 flow breach baseline.
- **32-35/36 scenarios complete** at both 120 and 114 FTE. Missing scenarios are death spirals that crash due to Windows CPython memory limits (circuit breaker catches them now).

## Gotchas for the next developer

1. **`strategy_model` imports FROM `prove_maths`** — helper functions like `case_effort`, `regulatory_age` etc. are the prove_maths versions. They work with our extended Cohort via duck typing. Don't modify prove_maths function signatures without checking strategy_model.

2. **Death spiral strategies crash Windows CPython** — `oldest_first` and `longest_wait` allocation at low FTE produce 50k+ WIP. The circuit breaker stops simulation at WIP > 50,000 but the dashboard should also warn users: "This strategy combination is unstable at this FTE level."

3. **`run_scenarios.py` uses subprocesses** — each scenario runs in its own Python process because running 36 simulations sequentially in one process causes Windows access violations from memory pressure. The dashboard runs ONE simulation at a time so this isn't an issue there.

4. **Streamlit cache key must include strategies** — if strategies aren't in the `run_simulation` parameter list, changing the dropdown won't trigger a re-run.

5. **`last_worked_day` is a cohort-level approximation** — when a handler partially closes a cohort, all remaining cases in that cohort get `last_worked_day = today`. This slightly underestimates neglect for large cohorts.
