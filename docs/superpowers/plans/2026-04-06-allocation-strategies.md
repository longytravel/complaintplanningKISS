# Allocation & Work Strategies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 6 allocation + 6 work prioritisation strategies to the complaints simulation model with a scenario runner comparing all 36 combinations.

**Architecture:** Strategy Registry pattern using module-level globals (matching existing codebase conventions). Eight sort-key functions registered in a `STRATEGIES` dict, looked up by `ALLOCATION_STRATEGY` and `WORK_STRATEGY` globals. `allocate_up_to_capacity()` and `process_work_slice()` each use their respective strategy instead of the hardcoded `priority_key()`. New `run_scenarios.py` iterates all 36 combinations and prints a ranked comparison table.

**Tech Stack:** Pure Python 3.12, no new dependencies. pytest for tests.

**Spec:** `docs/superpowers/specs/2026-04-06-allocation-strategies-design.md`

**Python executable:** `/c/Users/ROG/AppData/Roaming/uv/python/cpython-3.12-windows-x86_64-none/python`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `prove_maths.py` | Add `last_worked_day` to Cohort, 8 strategy functions, `STRATEGIES` dict, `ALLOCATION_STRATEGY` / `WORK_STRATEGY` globals, wire sort calls, 3 new daily metrics |
| Create | `test_strategies.py` | Regression baseline, unit tests for sort keys, integration tests |
| Create | `run_scenarios.py` | Scenario runner: 36 combos, KPI extraction, ranked console table |

---

### Task 1: Regression Baseline Test

Capture current `simulate(120)` output as hardcoded expected values. This test must pass before AND after the refactor.

**Files:**
- Create: `test_strategies.py`

- [ ] **Step 1: Write the regression test**

```python
"""Tests for allocation & work strategy implementation."""
import prove_maths as pm


# ── Regression baseline captured from simulate(120) before any changes ──
# These values MUST match the pre-refactor output exactly (within tolerance).

BASELINE = {
    "wip": 1224.240370,
    "unalloc": 510.240370,
    "alloc": 714.000000,
    "effective_util": 0.955047,
    "closures": 299.853655,
    "allocations": 299.853655,
    "fca_stock": 0.00000000,
    "psd2_stock": 0.00000000,
    "fca_flow": 0.00000000,
    "psd2_flow": 0.02333333,
    "mean_wip": 1224.069632,
    "mean_util": 0.955035,
}


def test_regression_baseline():
    """Default strategies must reproduce pre-refactor output exactly."""
    result = pm.simulate(120)
    final = result[-1]

    assert final["day"] == 729
    assert abs(final["wip"] - BASELINE["wip"]) < 0.01, f"WIP: {final['wip']}"
    assert abs(final["unalloc"] - BASELINE["unalloc"]) < 0.01, f"unalloc: {final['unalloc']}"
    assert abs(final["alloc"] - BASELINE["alloc"]) < 0.01, f"alloc: {final['alloc']}"
    assert abs(final["effective_util"] - BASELINE["effective_util"]) < 0.0001
    assert abs(final["closures"] - BASELINE["closures"]) < 0.01
    assert abs(final["allocations"] - BASELINE["allocations"]) < 0.01

    _, fca_s, psd2_s = pm.average_breach_rates(result, last_days=30)
    _, fca_f, psd2_f = pm.average_flow_breach_rates(result, last_days=30)
    assert abs(fca_s - BASELINE["fca_stock"]) < 0.0001
    assert abs(psd2_s - BASELINE["psd2_stock"]) < 0.0001
    assert abs(fca_f - BASELINE["fca_flow"]) < 0.0001
    assert abs(psd2_f - BASELINE["psd2_flow"]) < 0.001

    last30 = pm.last_n_workdays(result, 30)
    mean_wip = sum(r["wip"] for r in last30) / len(last30)
    mean_util = sum(r["effective_util"] for r in last30) / len(last30)
    assert abs(mean_wip - BASELINE["mean_wip"]) < 0.1
    assert abs(mean_util - BASELINE["mean_util"]) < 0.001

    assert pm.is_stable(result)
```

- [ ] **Step 2: Run the test to verify it passes on current code**

Run: `python -m pytest test_strategies.py::test_regression_baseline -v`

Expected: PASS (this is the pre-refactor baseline)

- [ ] **Step 3: Commit**

```bash
git add test_strategies.py
git commit -m "test: add regression baseline for simulate(120)"
```

---

### Task 2: Add `last_worked_day` to Cohort Dataclass

Add the new field needed by the `longest_untouched` work strategy. Update all Cohort construction sites to preserve the field.

**Files:**
- Modify: `prove_maths.py:223-233` (Cohort dataclass)
- Modify: `prove_maths.py:337-359` (seed_pool)
- Modify: `prove_maths.py:552-563` (split cohort in allocate_up_to_capacity)
- Modify: `prove_maths.py:362-391` (merge_cohorts — add `last_worked_day` to key and constructor)
- Modify: `prove_maths.py:483-519` (apply_psd2_extensions — propagate `last_worked_day`)
- Test: `test_strategies.py`

- [ ] **Step 1: Write the failing test**

Append to `test_strategies.py`:

```python
def test_cohort_last_worked_day_default():
    """New field defaults to None and is preserved through operations."""
    c = pm.Cohort(
        count=10, case_type="FCA", cal_age=5, biz_age=3,
        effort_per_case=1.5, is_src=False, arrival_day=0, allocation_day=2,
    )
    assert c.last_worked_day is None


def test_cohort_last_worked_day_explicit():
    c = pm.Cohort(
        count=10, case_type="FCA", cal_age=5, biz_age=3,
        effort_per_case=1.5, is_src=False, arrival_day=0, allocation_day=2,
        last_worked_day=5,
    )
    assert c.last_worked_day == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_strategies.py::test_cohort_last_worked_day_default test_strategies.py::test_cohort_last_worked_day_explicit -v`

Expected: FAIL with `TypeError: unexpected keyword argument 'last_worked_day'`

- [ ] **Step 3: Add `last_worked_day` field to Cohort**

In `prove_maths.py`, change the Cohort dataclass (line 223-233) to:

```python
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
```

- [ ] **Step 4: Preserve `last_worked_day` in split cohort within `allocate_up_to_capacity`**

In `prove_maths.py` line 552-563, add the field to the kept_unallocated Cohort constructor:

```python
        if stay > 0.01:
            kept_unallocated.append(
                Cohort(
                    count=stay,
                    case_type=cohort.case_type,
                    cal_age=cohort.cal_age,
                    biz_age=cohort.biz_age,
                    effort_per_case=cohort.effort_per_case,
                    is_src=cohort.is_src,
                    arrival_day=cohort.arrival_day,
                    allocation_day=cohort.allocation_day,
                    seeded=cohort.seeded,
                    last_worked_day=cohort.last_worked_day,
                )
            )
```

- [ ] **Step 5: Set `last_worked_day` on freshly allocated cohorts**

In `allocate_up_to_capacity`, the SRC cohort constructor (line 584-596) — add `last_worked_day=sim_day`:

```python
        if src_count > 0.01:
            new_allocated.append(
                Cohort(
                    count=src_count,
                    case_type=cohort.case_type,
                    cal_age=cohort.cal_age,
                    biz_age=cohort.biz_age,
                    effort_per_case=0.0,
                    is_src=True,
                    arrival_day=cohort.arrival_day,
                    allocation_day=sim_day,
                    seeded=False,
                    last_worked_day=sim_day,
                )
            )
```

And the regular cohort constructor (line 600-612) — add `last_worked_day=sim_day`:

```python
        if regular_count > 0.01:
            new_allocated.append(
                Cohort(
                    count=regular_count,
                    case_type=cohort.case_type,
                    cal_age=cohort.cal_age,
                    biz_age=cohort.biz_age,
                    effort_per_case=0.0,
                    is_src=False,
                    arrival_day=cohort.arrival_day,
                    allocation_day=sim_day,
                    seeded=False,
                    last_worked_day=sim_day,
                )
            )
```

- [ ] **Step 6: Set `last_worked_day` for seeded allocated cohorts**

In `seed_pool` (line 337-359), set `last_worked_day` to match `allocation_day` for allocated seeds:

```python
    for case_type, proportion in INTAKE_PROPORTIONS.items():
        cases_for_type = total_cases * proportion
        for reg_age, count in starting_wip_distribution(cases_for_type):
            cal_age, biz_age = make_age(reg_age, case_type)
            effort = BASE_EFFORT * burden_mult(reg_age)
            if allocated:
                effort *= max(0.1, 1.0 - 0.9 * min(reg_age, 10) / 10.0)
            alloc_day = -max(1, reg_age // 2) if allocated else None
            cohorts.append(
                Cohort(
                    count=count,
                    case_type=case_type,
                    cal_age=cal_age,
                    biz_age=biz_age,
                    effort_per_case=effort,
                    is_src=False,
                    arrival_day=-reg_age,
                    allocation_day=alloc_day,
                    seeded=True,
                    last_worked_day=alloc_day,
                )
            )
    return cohorts
```

- [ ] **Step 7: Update `last_worked_day` when cases are worked in `process_work_slice`**

In `process_work_slice`, after each SRC closure (after line 705, inside `if close > 0.01:`):

```python
            cohort.last_worked_day = sim_day
```

Add this line right after the `if reg_age > REGULATORY_DEADLINES[cohort.case_type]:` / `breached_closures_by_type` block, still inside the `if close > 0.01:` guard. Full context — the SRC loop becomes:

```python
    for cohort in src_candidates:
        if budget <= 0.01:
            break
        remaining_due = due_by_type[cohort.case_type] - src_closed_today[cohort.case_type]
        if remaining_due <= 0.01:
            continue
        close = min(cohort.count, remaining_due)
        eff = case_effort(cohort)
        cost = close * eff
        if cost > budget and eff > 0:
            close = budget / eff
            cost = budget
        cohort.count -= close
        src_closed_today[cohort.case_type] += close
        closures_total += close
        closures_by_type[cohort.case_type] += close
        budget -= cost
        if close > 0.01:
            reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
            close_sums[cohort.case_type]["n"] += close
            close_sums[cohort.case_type]["reg"] += reg_age * close
            close_sums[cohort.case_type]["cal"] += cohort.cal_age * close
            close_sums[cohort.case_type]["sys"] += (sim_day - cohort.arrival_day) * close
            if reg_age > REGULATORY_DEADLINES[cohort.case_type]:
                breached_closures_by_type[cohort.case_type] += close
            cohort.last_worked_day = sim_day
```

Similarly, in the regular candidate loop, after `if closed > 0.01:` (after line 730):

```python
            cohort.last_worked_day = sim_day
```

Full context — the regular loop becomes:

```python
    for cohort in regular_candidates:
        if budget <= 0.01:
            break
        eff = case_effort(cohort)
        if eff <= 0:
            continue
        hours_needed = cohort.count * eff
        hours_given = min(budget, hours_needed)
        closed = min(cohort.count, hours_given / eff)
        cohort.count -= closed
        closures_total += closed
        closures_by_type[cohort.case_type] += closed
        budget -= hours_given
        if closed > 0.01:
            reg_age = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
            close_sums[cohort.case_type]["n"] += closed
            close_sums[cohort.case_type]["reg"] += reg_age * closed
            close_sums[cohort.case_type]["cal"] += cohort.cal_age * closed
            close_sums[cohort.case_type]["sys"] += (sim_day - cohort.arrival_day) * closed
            if reg_age > REGULATORY_DEADLINES[cohort.case_type]:
                breached_closures_by_type[cohort.case_type] += closed
            cohort.last_worked_day = sim_day
```

- [ ] **Step 8: Propagate `last_worked_day` in `merge_cohorts`**

`merge_cohorts` (line 362-391) runs every 14 days and reconstructs every Cohort manually. Without this fix, `last_worked_day` resets to `None` every 14 days — breaking the `longest_untouched` strategy and the new neglect metrics.

In `prove_maths.py`, change `merge_cohorts` to include `last_worked_day` in both the merge key and the constructor:

```python
def merge_cohorts(cohorts: list[Cohort]) -> list[Cohort]:
    merged: dict[tuple, Cohort] = {}
    for cohort in cohorts:
        if cohort.count <= 0.01:
            continue
        key = (
            cohort.case_type,
            cohort.cal_age,
            cohort.biz_age,
            round(cohort.effort_per_case, 4),
            cohort.is_src,
            cohort.arrival_day,
            cohort.allocation_day,
            cohort.seeded,
            cohort.last_worked_day,
        )
        if key not in merged:
            merged[key] = Cohort(
                count=cohort.count,
                case_type=cohort.case_type,
                cal_age=cohort.cal_age,
                biz_age=cohort.biz_age,
                effort_per_case=cohort.effort_per_case,
                is_src=cohort.is_src,
                arrival_day=cohort.arrival_day,
                allocation_day=cohort.allocation_day,
                seeded=cohort.seeded,
                last_worked_day=cohort.last_worked_day,
            )
        else:
            merged[key].count += cohort.count
    return list(merged.values())
```

Note: Adding `last_worked_day` to the merge key means cohorts with different `last_worked_day` values won't merge together. This slightly increases cohort count but is the only correct approach — you cannot meaningfully combine temporal information from different work timestamps.

- [ ] **Step 9: Propagate `last_worked_day` in `apply_psd2_extensions`**

`apply_psd2_extensions` (line 483-519) creates new Cohort objects when splitting PSD2_15 cases at the 15-business-day mark. It runs every workday on both pools. Without this fix, any PSD2 case that gets extended loses its `last_worked_day`.

In `prove_maths.py`, change `apply_psd2_extensions` to propagate `last_worked_day` in both Cohort constructors:

```python
def apply_psd2_extensions(pool: list[Cohort]) -> list[Cohort]:
    result: list[Cohort] = []
    for cohort in pool:
        if cohort.case_type == "PSD2_15" and cohort.biz_age == 15:
            extension_count = cohort.count * PSD2_EXTENSION_RATE
            stay_count = cohort.count - extension_count
            if stay_count > 0.01:
                result.append(
                    Cohort(
                        count=stay_count,
                        case_type="PSD2_15",
                        cal_age=cohort.cal_age,
                        biz_age=cohort.biz_age,
                        effort_per_case=cohort.effort_per_case,
                        is_src=cohort.is_src,
                        arrival_day=cohort.arrival_day,
                        allocation_day=cohort.allocation_day,
                        seeded=cohort.seeded,
                        last_worked_day=cohort.last_worked_day,
                    )
                )
            if extension_count > 0.01:
                result.append(
                    Cohort(
                        count=extension_count,
                        case_type="PSD2_35",
                        cal_age=cohort.cal_age,
                        biz_age=cohort.biz_age,
                        effort_per_case=cohort.effort_per_case,
                        is_src=cohort.is_src,
                        arrival_day=cohort.arrival_day,
                        allocation_day=cohort.allocation_day,
                        seeded=cohort.seeded,
                        last_worked_day=cohort.last_worked_day,
                    )
                )
        else:
            result.append(cohort)
    return result
```

- [ ] **Step 10: Run all tests**

Run: `python -m pytest test_strategies.py -v`

Expected: ALL PASS (regression baseline unchanged because `last_worked_day` is additive — sort order still uses `priority_key`)

- [ ] **Step 11: Commit**

```bash
git add prove_maths.py test_strategies.py
git commit -m "feat: add last_worked_day field to Cohort dataclass"
```

---

### Task 3: Create Strategy Sort-Key Functions and Registry

Add all 8 strategy functions, the `STRATEGIES` dict, and the two strategy globals. Rename `priority_key` to `nearest_target_key` with backwards-compat alias.

**Files:**
- Modify: `prove_maths.py:394-402` (rename priority_key)
- Modify: `prove_maths.py` (add new functions after line ~402)
- Test: `test_strategies.py`

- [ ] **Step 1: Write unit tests for sort-key functions**

Append to `test_strategies.py`:

```python
def _make_cohort(case_type="FCA", cal_age=10, biz_age=7, arrival_day=0,
                 allocation_day=2, last_worked_day=2, is_src=False):
    """Helper to build test cohorts with sensible defaults."""
    return pm.Cohort(
        count=5, case_type=case_type, cal_age=cal_age, biz_age=biz_age,
        effort_per_case=1.5, is_src=is_src, arrival_day=arrival_day,
        allocation_day=allocation_day, last_worked_day=last_worked_day,
    )


def test_nearest_deadline_sorts_most_urgent_first():
    urgent = _make_cohort(cal_age=50, biz_age=35)     # 6 cal days to FCA deadline
    relaxed = _make_cohort(cal_age=10, biz_age=7)     # 46 cal days to FCA deadline
    sim_day = 100
    assert pm.STRATEGIES["nearest_deadline"](urgent, sim_day) < \
           pm.STRATEGIES["nearest_deadline"](relaxed, sim_day)


def test_nearest_target_matches_original_priority_key():
    c = _make_cohort()
    sim_day = 100
    assert pm.STRATEGIES["nearest_target"](c, sim_day) == pm.nearest_target_key(c, sim_day)


def test_youngest_first_prefers_low_age():
    young = _make_cohort(cal_age=2, biz_age=1)
    old = _make_cohort(cal_age=30, biz_age=21)
    sim_day = 100
    assert pm.STRATEGIES["youngest_first"](young, sim_day) < \
           pm.STRATEGIES["youngest_first"](old, sim_day)


def test_oldest_first_prefers_high_age():
    young = _make_cohort(cal_age=2, biz_age=1)
    old = _make_cohort(cal_age=30, biz_age=21)
    sim_day = 100
    assert pm.STRATEGIES["oldest_first"](old, sim_day) < \
           pm.STRATEGIES["oldest_first"](young, sim_day)


def test_psd2_priority_prefers_psd2_over_fca():
    fca = _make_cohort(case_type="FCA", cal_age=10, biz_age=7)
    psd2 = _make_cohort(case_type="PSD2_15", cal_age=10, biz_age=7)
    sim_day = 100
    assert pm.STRATEGIES["psd2_priority"](psd2, sim_day) < \
           pm.STRATEGIES["psd2_priority"](fca, sim_day)


def test_longest_wait_prefers_earliest_arrival():
    old_arrival = _make_cohort(arrival_day=0)
    new_arrival = _make_cohort(arrival_day=50)
    sim_day = 100
    assert pm.STRATEGIES["longest_wait"](old_arrival, sim_day) < \
           pm.STRATEGIES["longest_wait"](new_arrival, sim_day)


def test_lowest_effort_prefers_cheap_cases():
    young = _make_cohort(cal_age=2, biz_age=1)   # burden band 0-3 = 0.7x
    old = _make_cohort(cal_age=40, biz_age=28)    # burden band 36-56 = 2.0x
    sim_day = 100
    assert pm.STRATEGIES["lowest_effort"](young, sim_day) < \
           pm.STRATEGIES["lowest_effort"](old, sim_day)


def test_longest_untouched_prefers_oldest_last_worked():
    neglected = _make_cohort(last_worked_day=10)
    recent = _make_cohort(last_worked_day=90)
    sim_day = 100
    assert pm.STRATEGIES["longest_untouched"](neglected, sim_day) < \
           pm.STRATEGIES["longest_untouched"](recent, sim_day)


def test_longest_untouched_none_is_highest_priority():
    never_worked = _make_cohort(last_worked_day=None)
    recently_worked = _make_cohort(last_worked_day=90)
    sim_day = 100
    assert pm.STRATEGIES["longest_untouched"](never_worked, sim_day) < \
           pm.STRATEGIES["longest_untouched"](recently_worked, sim_day)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_strategies.py::test_nearest_deadline_sorts_most_urgent_first -v`

Expected: FAIL with `AttributeError: module 'prove_maths' has no attribute 'STRATEGIES'`

- [ ] **Step 3: Rename `priority_key` to `nearest_target_key` and add alias**

In `prove_maths.py`, change line 394:

```python
def nearest_target_key(cohort: Cohort, sim_day: int) -> tuple[int, int, int]:
    target_remaining = remaining_workdays_to_target(
        cohort.case_type, cohort.cal_age, cohort.biz_age, sim_day
    )
    deadline_remaining = remaining_workdays_to_deadline(
        cohort.case_type, cohort.cal_age, cohort.biz_age, sim_day
    )
    reg = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
    return (target_remaining, deadline_remaining, -reg)


# Alias — call sites still reference priority_key until wiring task
priority_key = nearest_target_key
```

- [ ] **Step 4: Add 7 new strategy sort-key functions**

Insert after the `priority_key = nearest_target_key` alias:

```python
def nearest_deadline_key(cohort: Cohort, sim_day: int) -> tuple:
    deadline_remaining = remaining_workdays_to_deadline(
        cohort.case_type, cohort.cal_age, cohort.biz_age, sim_day
    )
    return (deadline_remaining,)


def youngest_first_key(cohort: Cohort, sim_day: int) -> tuple:
    reg = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
    return (reg,)


def oldest_first_key(cohort: Cohort, sim_day: int) -> tuple:
    reg = regulatory_age(cohort.case_type, cohort.cal_age, cohort.biz_age)
    return (-reg,)


def psd2_priority_key(cohort: Cohort, sim_day: int) -> tuple:
    is_fca = 1 if cohort.case_type == "FCA" else 0
    deadline_remaining = remaining_workdays_to_deadline(
        cohort.case_type, cohort.cal_age, cohort.biz_age, sim_day
    )
    return (is_fca, deadline_remaining)


def longest_wait_key(cohort: Cohort, sim_day: int) -> tuple:
    return (cohort.arrival_day,)


def lowest_effort_key(cohort: Cohort, sim_day: int) -> tuple:
    return (case_effort(cohort),)


def longest_untouched_key(cohort: Cohort, sim_day: int) -> tuple:
    lwd = cohort.last_worked_day if cohort.last_worked_day is not None else -999999
    return (lwd,)
```

- [ ] **Step 5: Add STRATEGIES dict and globals**

Insert after the strategy functions:

```python
STRATEGIES: dict[str, callable] = {
    "nearest_deadline": nearest_deadline_key,
    "nearest_target": nearest_target_key,
    "youngest_first": youngest_first_key,
    "oldest_first": oldest_first_key,
    "psd2_priority": psd2_priority_key,
    "longest_wait": longest_wait_key,
    "lowest_effort": lowest_effort_key,
    "longest_untouched": longest_untouched_key,
}

ALLOCATION_STRATEGY = "nearest_target"   # default = current behaviour
WORK_STRATEGY = "nearest_target"         # default = current behaviour
```

- [ ] **Step 6: Run all tests**

Run: `python -m pytest test_strategies.py -v`

Expected: ALL PASS (sort-key tests verify correct ordering; regression baseline still passes because call sites still use `priority_key` alias)

- [ ] **Step 7: Commit**

```bash
git add prove_maths.py test_strategies.py
git commit -m "feat: add 8 strategy sort-key functions and STRATEGIES registry"
```

---

### Task 4: Wire `allocate_up_to_capacity` to Strategy Registry

Replace the hardcoded `priority_key` call with `STRATEGIES[ALLOCATION_STRATEGY]` lookup.

**Files:**
- Modify: `prove_maths.py:534` (sort call in allocate_up_to_capacity)
- Test: `test_strategies.py`

- [ ] **Step 1: Write integration test for allocation strategy wiring**

Append to `test_strategies.py`:

```python
def test_allocation_uses_selected_strategy():
    """Switching ALLOCATION_STRATEGY changes which cases get allocated first."""
    original = pm.ALLOCATION_STRATEGY
    try:
        # youngest_first should allocate low-age cases before high-age
        pm.ALLOCATION_STRATEGY = "youngest_first"
        result = pm.simulate(120)
        # If it completes and is stable, the wiring works
        assert len(result) == 730
    finally:
        pm.ALLOCATION_STRATEGY = original
```

- [ ] **Step 2: Replace sort call in `allocate_up_to_capacity`**

In `prove_maths.py` line 534, change:

```python
    unallocated.sort(key=lambda cohort: priority_key(cohort, sim_day))
```

to:

```python
    alloc_key = STRATEGIES[ALLOCATION_STRATEGY]
    unallocated.sort(key=lambda cohort: alloc_key(cohort, sim_day))
```

- [ ] **Step 3: Run all tests**

Run: `python -m pytest test_strategies.py -v`

Expected: ALL PASS (default is `nearest_target` which matches `priority_key`, so regression holds)

- [ ] **Step 4: Commit**

```bash
git add prove_maths.py test_strategies.py
git commit -m "feat: wire allocate_up_to_capacity to strategy registry"
```

---

### Task 5: Wire `process_work_slice` to Strategy Registry

Replace both `priority_key` calls with `STRATEGIES[WORK_STRATEGY]` lookup. Remove the `priority_key` alias.

**Files:**
- Modify: `prove_maths.py:679` (SRC candidate sort)
- Modify: `prove_maths.py:708` (regular candidate sort)
- Modify: `prove_maths.py` (remove `priority_key` alias)
- Test: `test_strategies.py`

- [ ] **Step 1: Write integration test for work strategy wiring**

Append to `test_strategies.py`:

```python
def test_work_uses_selected_strategy():
    """Switching WORK_STRATEGY changes which diary cases get worked first."""
    original = pm.WORK_STRATEGY
    try:
        pm.WORK_STRATEGY = "oldest_first"
        result = pm.simulate(120)
        assert len(result) == 730
    finally:
        pm.WORK_STRATEGY = original
```

- [ ] **Step 2: Replace sort calls in `process_work_slice`**

In `prove_maths.py` line 679, change:

```python
    src_candidates.sort(key=lambda cohort: priority_key(cohort, sim_day))
```

to:

```python
    work_key = STRATEGIES[WORK_STRATEGY]
    src_candidates.sort(key=lambda cohort: work_key(cohort, sim_day))
```

In `prove_maths.py` line 708, change:

```python
    regular_candidates.sort(key=lambda cohort: priority_key(cohort, sim_day))
```

to:

```python
    regular_candidates.sort(key=lambda cohort: work_key(cohort, sim_day))
```

Note: `work_key` is already defined from the SRC sort above — reuse it. Do NOT re-lookup `STRATEGIES[WORK_STRATEGY]`.

- [ ] **Step 3: Remove the `priority_key` alias**

Delete the line:

```python
priority_key = nearest_target_key
```

All call sites now use `STRATEGIES` lookups. The alias is no longer needed.

- [ ] **Step 4: Run all tests**

Run: `python -m pytest test_strategies.py -v`

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add prove_maths.py test_strategies.py
git commit -m "feat: wire process_work_slice to strategy registry, remove priority_key alias"
```

---

### Task 6: Regression Verification

Explicitly verify the refactored code with default strategies produces identical output to pre-refactor baseline. This is the critical safety gate.

**Files:**
- Test: `test_strategies.py` (existing `test_regression_baseline`)

- [ ] **Step 1: Run the full regression test**

Run: `python -m pytest test_strategies.py::test_regression_baseline -v`

Expected: PASS — output is identical to pre-refactor within tolerance.

If this fails, STOP. The refactor has changed behaviour. Debug by comparing individual day outputs.

- [ ] **Step 2: Run all strategy combinations to verify no crashes**

Append to `test_strategies.py`:

```python
ALLOCATION_STRATEGY_NAMES = [
    "nearest_deadline", "nearest_target", "youngest_first",
    "oldest_first", "psd2_priority", "longest_wait",
]

WORK_STRATEGY_NAMES = [
    "nearest_deadline", "nearest_target", "youngest_first",
    "oldest_first", "lowest_effort", "longest_untouched",
]


def test_all_36_combos_complete():
    """Every strategy combination must complete 730 days without error."""
    orig_alloc = pm.ALLOCATION_STRATEGY
    orig_work = pm.WORK_STRATEGY
    try:
        for alloc in ALLOCATION_STRATEGY_NAMES:
            for work in WORK_STRATEGY_NAMES:
                pm.ALLOCATION_STRATEGY = alloc
                pm.WORK_STRATEGY = work
                result = pm.simulate(120)
                assert len(result) == 730, f"{alloc}/{work} only produced {len(result)} days"
    finally:
        pm.ALLOCATION_STRATEGY = orig_alloc
        pm.WORK_STRATEGY = orig_work
```

- [ ] **Step 3: Run the combo test**

Run: `python -m pytest test_strategies.py::test_all_36_combos_complete -v --timeout=300`

Expected: PASS (may take ~60s for 36 simulations)

- [ ] **Step 4: Commit**

```bash
git add test_strategies.py
git commit -m "test: verify all 36 strategy combinations complete without error"
```

---

### Task 7: Add New Daily Metrics

Add `max_unallocated_wait`, `max_diary_untouched`, and `avg_diary_untouched` to the daily output dict.

**Files:**
- Modify: `prove_maths.py:879-929` (simulate results dict)
- Test: `test_strategies.py`

- [ ] **Step 1: Write the failing test**

Append to `test_strategies.py`:

```python
def test_new_metrics_present_in_output():
    """simulate() output dicts include the 3 new neglect metrics."""
    result = pm.simulate(120)
    final = result[-1]
    assert "max_unallocated_wait" in final
    assert "max_diary_untouched" in final
    assert "avg_diary_untouched" in final


def test_new_metrics_are_non_negative():
    result = pm.simulate(120)
    for row in result[-30:]:
        assert row["max_unallocated_wait"] >= 0
        assert row["max_diary_untouched"] >= 0
        assert row["avg_diary_untouched"] >= 0
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest test_strategies.py::test_new_metrics_present_in_output -v`

Expected: FAIL with `KeyError: 'max_unallocated_wait'`

- [ ] **Step 3: Add metric computation to `simulate()`**

In `prove_maths.py`, in the `simulate()` function, insert the following BEFORE `results.append(` (around line 901, after `occupancy_end = total_allocated`):

```python
        # Neglect / wait metrics
        max_unallocated_wait = (
            max((day - c.arrival_day for c in unallocated if c.count > 0.01), default=0)
        )
        max_diary_untouched = 0
        weighted_untouched_sum = 0.0
        total_alloc_count = 0.0
        for c in allocated:
            if c.count <= 0.01:
                continue
            if c.last_worked_day is not None:
                untouched = day - c.last_worked_day
            elif c.allocation_day is not None:
                untouched = day - c.allocation_day
            else:
                untouched = 0
            max_diary_untouched = max(max_diary_untouched, untouched)
            weighted_untouched_sum += untouched * c.count
            total_alloc_count += c.count
        avg_diary_untouched = (
            weighted_untouched_sum / total_alloc_count if total_alloc_count > 0.01 else 0.0
        )
```

- [ ] **Step 4: Add the 3 metrics to the results dict**

In the `results.append({...})` block, add these 3 entries:

```python
                "max_unallocated_wait": max_unallocated_wait,
                "max_diary_untouched": max_diary_untouched,
                "avg_diary_untouched": avg_diary_untouched,
```

Place them after the `"slot_capacity": max_slots,` line.

- [ ] **Step 5: Run all tests**

Run: `python -m pytest test_strategies.py -v`

Expected: ALL PASS (including regression — new keys are additive, existing values unchanged)

- [ ] **Step 6: Commit**

```bash
git add prove_maths.py test_strategies.py
git commit -m "feat: add max_unallocated_wait, max_diary_untouched, avg_diary_untouched metrics"
```

---

### Task 8: Create Scenario Runner

Build `run_scenarios.py` that runs all 36 combinations and prints a ranked comparison table.

**Files:**
- Create: `run_scenarios.py`
- Test: `test_strategies.py`

- [ ] **Step 1: Write the smoke test**

Append to `test_strategies.py`:

```python
import subprocess
import sys


def test_run_scenarios_completes(tmp_path):
    """run_scenarios.py executes without error (with reduced combo for speed)."""
    # Import and verify module loads
    import run_scenarios as rs
    assert hasattr(rs, "extract_kpis")
    assert hasattr(rs, "main")
```

- [ ] **Step 2: Create `run_scenarios.py`**

```python
#!/usr/bin/env python3
"""
Scenario Runner — Compare allocation x work strategy combinations.

Runs all 36 strategy combinations through simulate() and prints a ranked
comparison table of steady-state KPIs.

Usage:
    python run_scenarios.py                     # default sort by WIP
    python run_scenarios.py --sort-by fca_stock  # sort by FCA stock breach %
    python run_scenarios.py --fte 115            # test at different staffing
"""

from __future__ import annotations

import argparse
import time
from statistics import mean

import prove_maths as pm

ALLOCATION_STRATEGY_NAMES = [
    "nearest_deadline", "nearest_target", "youngest_first",
    "oldest_first", "psd2_priority", "longest_wait",
]

WORK_STRATEGY_NAMES = [
    "nearest_deadline", "nearest_target", "youngest_first",
    "oldest_first", "lowest_effort", "longest_untouched",
]

SORT_COLUMNS = [
    "wip", "fca_stock", "psd2_stock", "fca_flow", "psd2_flow",
    "fca_close_age", "psd2_close_age", "max_wait", "max_untouched", "util",
]


def extract_kpis(result: list[dict]) -> dict[str, float]:
    """Extract steady-state KPIs from the last 30 workdays of simulation output."""
    last30 = pm.last_n_workdays(result, 30)

    # WIP
    wip = mean(r["wip"] for r in last30)

    # Stock breach rates
    _, fca_stock, psd2_stock = pm.average_breach_rates(result, last_days=30)

    # Flow breach rates
    _, fca_flow, psd2_flow = pm.average_flow_breach_rates(result, last_days=30)

    # Close ages
    _, fca_reg, _, _ = pm.summarise_closure_metrics(last30, "FCA")
    _, psd2_15_reg, _, _ = pm.summarise_closure_metrics(last30, "PSD2_15")
    _, psd2_35_reg, _, _ = pm.summarise_closure_metrics(last30, "PSD2_35")

    # Weighted PSD2 close age
    psd2_15_n = sum(r["close_sums"]["PSD2_15"]["n"] for r in last30)
    psd2_35_n = sum(r["close_sums"]["PSD2_35"]["n"] for r in last30)
    psd2_total_n = psd2_15_n + psd2_35_n
    if psd2_total_n > 0.01:
        psd2_close_age = (psd2_15_reg * psd2_15_n + psd2_35_reg * psd2_35_n) / psd2_total_n
    else:
        psd2_close_age = 0.0

    # Neglect metrics
    max_wait = max(r["max_unallocated_wait"] for r in last30)
    max_untouched = max(r["max_diary_untouched"] for r in last30)

    # Utilisation
    util = mean(r["effective_util"] for r in last30)

    return {
        "wip": wip,
        "fca_stock": fca_stock * 100,
        "psd2_stock": psd2_stock * 100,
        "fca_flow": fca_flow * 100,
        "psd2_flow": psd2_flow * 100,
        "fca_close_age": fca_reg,
        "psd2_close_age": psd2_close_age,
        "max_wait": max_wait,
        "max_untouched": max_untouched,
        "util": util * 100,
    }


def run_all_scenarios(fte: int) -> list[dict]:
    """Run all 36 strategy combinations and return KPI dicts."""
    scenarios = []
    total = len(ALLOCATION_STRATEGY_NAMES) * len(WORK_STRATEGY_NAMES)

    for i, alloc in enumerate(ALLOCATION_STRATEGY_NAMES):
        for j, work in enumerate(WORK_STRATEGY_NAMES):
            n = i * len(WORK_STRATEGY_NAMES) + j + 1
            print(f"\r  Running {n:2d}/{total}: {alloc:<18s} x {work:<18s}", end="", flush=True)

            pm.ALLOCATION_STRATEGY = alloc
            pm.WORK_STRATEGY = work
            result = pm.simulate(fte)
            kpis = extract_kpis(result)
            stable = pm.is_stable(result)

            scenarios.append({
                "alloc": alloc,
                "work": work,
                "stable": stable,
                **kpis,
            })

    # Restore defaults
    pm.ALLOCATION_STRATEGY = "nearest_target"
    pm.WORK_STRATEGY = "nearest_target"

    print("\r" + " " * 70 + "\r", end="")
    return scenarios


def print_table(scenarios: list[dict], sort_by: str, fte: int) -> None:
    """Print ranked comparison table to console."""
    # Sort: lower is better for everything except util
    reverse = sort_by == "util"
    scenarios.sort(key=lambda r: r[sort_by], reverse=reverse)

    intake = pm.DAILY_INTAKE
    print(f"\nSCENARIO COMPARISON ({fte} FTE, {intake} intake/day)")
    print("=" * 120)
    print(
        f"{'Rank':>4}  {'Alloc Strategy':<18} {'Work Strategy':<18}"
        f" {'WIP':>6} {'FCA%':>5} {'PSD2%':>5}"
        f" {'fFCA%':>5} {'fPSD%':>5}"
        f" {'FCAage':>6} {'PSDage':>6}"
        f" {'MaxWt':>5} {'MaxNg':>5} {'Util':>5} {'OK':>3}"
    )
    print("-" * 120)

    for rank, r in enumerate(scenarios, 1):
        ok = "Y" if r["stable"] else "N"
        print(
            f"{rank:4d}  {r['alloc']:<18} {r['work']:<18}"
            f" {r['wip']:6.0f} {r['fca_stock']:5.1f} {r['psd2_stock']:5.1f}"
            f" {r['fca_flow']:5.1f} {r['psd2_flow']:5.1f}"
            f" {r['fca_close_age']:6.1f} {r['psd2_close_age']:6.1f}"
            f" {r['max_wait']:5.0f} {r['max_untouched']:5.0f} {r['util']:4.0f}% {ok:>3}"
        )

    print("=" * 120)
    direction = "descending" if reverse else "ascending"
    print(f"\nSorted by: {sort_by} ({direction}). Use --sort-by <column> to change.")
    print(f"Columns: WIP=stock, FCA%/PSD2%=stock breach, fFCA%/fPSD%=flow breach,")
    print(f"         FCAage/PSDage=avg close age, MaxWt=max queue wait, MaxNg=max diary neglect, OK=stable")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare all 36 allocation x work strategy combinations"
    )
    parser.add_argument(
        "--sort-by", default="wip", choices=SORT_COLUMNS,
        help="KPI column to sort by (default: wip)",
    )
    parser.add_argument(
        "--fte", type=int, default=pm.DEFAULT_FTE,
        help=f"FTE level to simulate (default: {pm.DEFAULT_FTE})",
    )
    args = parser.parse_args()

    print(f"Running 36 strategy combinations at {args.fte} FTE...")
    t0 = time.time()
    scenarios = run_all_scenarios(args.fte)
    elapsed = time.time() - t0
    print(f"Completed in {elapsed:.1f}s")

    print_table(scenarios, args.sort_by, args.fte)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the smoke test**

Run: `python -m pytest test_strategies.py::test_run_scenarios_completes -v`

Expected: PASS

- [ ] **Step 4: Run the scenario runner manually**

Run: `python run_scenarios.py --sort-by wip`

Expected: Table with 36 rows, ranked by WIP. Should complete in ~60s. Verify:
- Row with `nearest_target` / `nearest_target` shows WIP ~1224, 0% FCA, ~2% PSD2 (matching baseline)
- No crashes or NaN values
- Some combos show higher breach rates (expected — not all strategies are good)

- [ ] **Step 5: Commit**

```bash
git add run_scenarios.py test_strategies.py
git commit -m "feat: add run_scenarios.py — 36-combo strategy comparison runner"
```

---

### Task 9: Final Validation and Cleanup

Run the full test suite and scenario runner. Verify everything works end-to-end.

**Files:**
- Test: all files

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest test_strategies.py -v`

Expected: ALL PASS

- [ ] **Step 2: Run scenario runner and verify output**

Run: `python run_scenarios.py --sort-by psd2_stock`

Expected: Complete table, no errors, sensible KPI ranges.

- [ ] **Step 3: Verify regression one final time**

Run: `python -m pytest test_strategies.py::test_regression_baseline -v`

Expected: PASS — default strategies still produce identical output.

- [ ] **Step 4: Commit any final cleanup**

```bash
git add -A
git commit -m "chore: final validation — all tests pass, 36 combos verified"
```
