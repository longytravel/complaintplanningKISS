# Complaints Demand Model — POC Design Spec

**Version:** 2 (revised after GPT-5.4 mathematical review)

## Purpose

Prove that a mathematical stock-and-flow model can calculate FTE demand for a complaints operation, capturing the burden-age spiral, allocation dynamics, and regulatory deadlines. The model must produce a daily FTE demand number for today and projected forward over 365 days.

This is a proof-of-concept for a single product (PCA BAU). If the maths works here, we layer in complexity: multiple products, cross-skilling, detailed shrinkage, hiring pipelines.

## Modelling Approach

**Cohort-level System Dynamics (stocks and flows).** Not individual case or handler simulation.

The research base supports this choice:
- SD is the recommended approach for proving feedback loops like the burden-age spiral
- Cohort models can represent the two-pool allocation structure, diary constraints, and non-linear burden without simulating individual entities
- Queueing theory and analytical models serve as sanity checks, not the primary engine
- Individual-level DES/ABM comes later once the aggregate maths is validated

The model runs in discrete daily time steps over a 365-day horizon.

---

## System Structure

### The Two Pools

The system has two stocks of open cases:

```
INTAKE → [UNALLOCATED POOL] → [ALLOCATED POOL (DIARIES)] → CLOSED
              ↑                        ↑
          cases age               cases age + work applied
          no work done            remaining effort decrements
          waiting for slot        closes when remaining effort = 0
```

**Unallocated pool:** Cases waiting to be given to a handler. They age every day but receive no work. The pool drains when handlers have free diary slots. Cases are drained in priority order (most urgent first).

**Allocated pool (diaries):** Cases assigned to handlers. They age, receive work each day (productive hours applied against their remaining effort), and close when their remaining effort reaches zero. A closed case frees a diary slot, allowing a new case to be allocated.

### The Feedback Loop (Burden-Age Spiral)

This is the core dynamic the model must capture:

```
Fewer FTE → fewer productive hours → cases progress slower → diary slots don't free up
→ unallocated cases age → higher effort when finally allocated
→ more hours per case → even slower progress → even fewer closures
```

The reverse (virtuous cycle) also holds: more FTE → faster closures → younger cases → less effort → even more closures.

The model does not use a one-shot formula. It iterates daily: each day's closures depend on today's WIP age distribution and available capacity, which determines tomorrow's WIP age distribution.

---

## Case Types and Regulatory Deadlines

| Case Type | % of Intake | Deadline | Clock Type | Breach Rate (validation target) |
|-----------|-------------|----------|------------|-------------------------------|
| FCA Standard | 70% | 56 calendar days | Calendar (ages 7 days/week) | ~3% |
| PSD2-15 | 30% | 15 business days | Business (ages 5 days/week) | ~10% |
| PSD2-35 | 5% of PSD2-15 escalate | 35 business days | Business (ages 5 days/week) | ~10% |

PSD2-35 cases are not separate intake — they are PSD2-15 cases that prove too complex and are extended. They retain their original age but get a new deadline. Extension happens exactly once, at the 15-business-day boundary, before breach status is checked.

### Regulatory Age Bands

Age bands align with regulatory reporting requirements, not arbitrary groupings:

| Band | Days | Significance |
|------|------|-------------|
| Band 1 | 0-3 calendar days | FCA "summary resolution communication" window. Cases closeable by phone without a letter. Fastest, cheapest resolution. |
| Band 2 | 4-15 business days | PSD2 standard deadline zone. These cases must be prioritised. |
| Band 3 | 16-35 business days | PSD2 extended deadline zone (complex cases only). |
| Band 4 | 36-56 calendar days | FCA 8-week deadline approaching. |
| Band 5 | 56+ calendar days | Breached. Regulatory failure. |

The model tracks cases at **daily granularity** within these bands — bands are for reporting and priority logic, not for aggregating the maths.

### Weekend/Weekday Asymmetry

- **FCA cases** age every calendar day (7 days/week). Over a weekend with no processing, they age 2 days.
- **PSD2 cases** age only on business days (5 days/week). Weekends do not count toward their deadline.
- **Processing** happens Monday-Friday only (5 days/week).
- This creates a **Monday bulge**: FCA cases that were in band 1 on Friday may have crossed into band 2 by Monday morning, with zero work done. The model must simulate this explicitly — not average it out.

---

## Service Targets and Priority

Regulatory deadlines are backstops, not operational targets. The model uses **internal service targets** to drive priority:

| Case Type | Regulatory Deadline | Service Target (default) |
|-----------|--------------------|-----------------------|
| FCA Standard | 56 calendar days | 21 calendar days |
| PSD2-15 | 15 business days | 10 business days |
| PSD2-35 | 35 business days | 25 business days |

The service target is the primary tuneable parameter. Moving it out (e.g., 21 → 28 days) reduces concurrent active WIP and FTE demand, but increases average case age at closure and therefore effort per case (burden). There is a **sweet spot** — the bottom of a U-curve — where FTE demand is minimised. The model must find and display this.

### Priority: Remaining Workdays to Deadline (Common Clock)

Priority must be comparable across case types that use different clocks (calendar vs business days). Raw slack (`service_target - age`) is **not comparable** because 5 calendar days of FCA slack is not the same as 5 business days of PSD2 slack.

Instead, priority is based on **remaining workdays to the service target deadline**:

```
For FCA cases:
    due_date = start_date + service_target (in calendar days)
    remaining_workdays = count_business_days(today, due_date)

For PSD2 cases:
    due_date = start_date + service_target (in business days, counting only Mon-Fri)
    remaining_workdays = due_date_in_business_days - current_business_day_age
```

Both are expressed in **workdays remaining** — the number of actual processing days available before the target is missed.

Cases are ranked by `remaining_workdays` ascending. Ties broken by secondary sort on `remaining_workdays_to_regulatory_deadline` ascending (regulatory deadline is the hard backstop).

This ensures:
- A PSD2 case with 3 workdays to its 15-day deadline outranks an FCA case with 10 workdays to its 21-day target
- An FCA case at day 19 (2 workdays to 21-day target) outranks a PSD2 case at day 5 (5 workdays to 10-day target)
- No case is ignored until the last minute — the service target drives early attention

---

## Intake

### Daily Volume

```
new_cases(t) = daily_intake_rate
```

Default: 300 cases/day, arriving on workdays. This is a parameter that can be made variable (e.g., seasonal pattern, day-of-week pattern) but starts as a constant.

For POC, we start with a flat daily rate on workdays. Weekend arrivals and day-of-week shaping are deferred.

### Intake Age Distribution

Not all cases arrive at age 0. Some have been bounced around the bank and arrive pre-aged. This is modelled as a **shape function**:

```
intake_age_shape: age → proportion
```

Default shape (parameterised, tuneable):

| Age at Arrival | Proportion |
|---------------|-----------|
| Day 0 | 85% |
| Day 1-5 | 10% |
| Day 6-20 | 4% |
| Day 40+ (pre-breached) | 1% |

This can be modelled as an exponential decay or a discrete lookup. Must sum to 1.0.

### Type Distribution

Of the 300 daily intake:
- 210 (70%) are FCA Standard
- 90 (30%) are PSD2-15
- PSD2-35 cases arise from PSD2-15 escalation (5% of PSD2-15), not from intake directly

---

## Starting WIP

The model needs an initial state. This must be split by **pool, case type, and age** because FCA and PSD2 use different clocks and have different deadline profiles.

### Total WIP: 2,500 cases

### Pool Split
- **Unallocated:** 25% (625 cases)
- **Allocated (in diaries):** 75% (1,875 cases)

### Type Split (within each pool)
- 70% FCA Standard
- 30% PSD2 (of which ~5% are PSD2-35, rest PSD2-15)

### WIP Age Distribution (shape function, per case type)

Based on the operational picture provided:

| Age Band | Cumulative % | Implied Shape |
|----------|-------------|--------------|
| 0-3 days | ~40% | High volume, many fresh cases |
| 0-7 days | ~70% | Steep drop-off after first week |
| 8-28 days | ~20% | Steady thinning |
| 29-56 days | ~7% | Small tail approaching deadline |
| 56+ days (breached) | ~3% | Tiny breached tail |

This shape is applied **separately per case type** (using each type's clock). The shape should approximate an exponential decay with a small fat tail. Parameterised so real MI data can replace defaults later.

### Initial Remaining Effort for Allocated Cases

Allocated cases in the starting WIP already have work in progress. Their remaining effort is estimated as:

```
initial_remaining_effort(age) = effort(age) × remaining_fraction(age)
```

Where `remaining_fraction` estimates how much work remains — freshly allocated cases have ~100% remaining, cases that have been in the diary for a while have less. Default: a linear decay from 1.0 to 0.1 based on proportion of expected diary time elapsed.

---

## Allocation Model

### Diary Limit

Each handler has a maximum diary size of **7 cases**. This is a hard constraint — a load-bearing parameter that gates the flow between pools.

Diary slot capacity is based on **on-desk FTE** (handlers physically present), NOT productive FTE. A handler at 85% utilisation or 0.88 proficiency still has 7 diary slots — those parameters affect throughput, not physical capacity for open cases.

```
on_desk_FTE(t) = total_FTE × (1 - absence_rate)
max_diary_slots(t) = on_desk_FTE(t) × diary_limit
available_slots(t) = MAX(0, max_diary_slots(t) - allocated_WIP_count(t))
```

Where `absence_rate` is the fraction of FTE not at their desk on a given day (sickness, leave, training). For POC, this is a subset of shrinkage — the portion that removes bodies from desks, not the portion that reduces productive hours for present staff.

Default: `absence_rate = 0.15` (15% absent on any given day). The remaining shrinkage (meetings, coaching, breaks) reduces productive hours but not diary slots.

If `available_slots = 0`, no cases can be allocated. The unallocated pool grows and ages.

### Allocation Rate

```
allocation(t) = MIN(unallocated_pool_count(t), available_slots(t))
```

Cases are allocated in **priority order** — lowest remaining workdays to service target first (see Priority section above).

### Allocation Delay

The average time a case spends in the unallocated pool is ~1.5 days. This is not a hardcoded delay — it **emerges** from the model as a function of:
- Intake rate (how fast cases enter the pool)
- Available diary slots (how fast cases leave the pool)
- Priority ordering (which cases leave first)

If allocation slows down (e.g., fewer slots available because handlers have full diaries, or higher absence), the average delay increases, cases age, and burden rises. This is a key feedback mechanism.

---

## Effort Model (Remaining-Work Stock)

### Core Principle: No Double-Counting

Previous draft had separate "effort drain" and "closure effort," which double-counts work. The corrected model uses a **remaining-work stock**: each case has a total effort set at allocation, and productive hours are applied against that stock until it reaches zero.

### Total Effort at Allocation

When a case is allocated at age `a`, it receives a total effort requirement:

```
total_effort(a) = base_effort × burden_multiplier(a)
```

**Base effort:** 90 minutes (1.5 hours). This is the baseline for a case at baseline age.

**Burden multiplier by age** (non-linear shape function):

| Age Band | Multiplier | Effective Effort | Rationale |
|----------|-----------|-----------------|-----------|
| 0-3 days | 0.7x | 63 mins | Simple phone resolution, no letter needed |
| 4-15 days | 1.0x | 90 mins | Baseline complexity |
| 16-35 days | 1.5x | 135 mins | Correspondence, follow-ups, re-reading |
| 36-56 days | 2.0x | 180 mins | Significant rework, customer escalation |
| 56+ days | 2.5x+ | 225+ mins | Full regulatory response, potential FOS referral |

This is modelled as a continuous curve (piecewise linear, exponential, or logistic) fitted through these anchor points. The shape function is tuneable and will be calibrated to real handle-time data later.

### Why Effort Is Set at Allocation

The dominant driver of the burden-age spiral is ageing in the **unallocated pool** — cases age there with zero work done, crossing into higher effort bands before a handler ever touches them. Once allocated, the diary limit of 7 means handlers typically work cases within a few days.

For the POC, fixing effort at allocation is sufficient. If needed later, we can add an "in-diary aging penalty" that increases remaining effort for cases that stall in the diary without progress. This is a refinement, not a structural change.

### Remaining-Work Stock

Each cohort in the allocated pool carries a remaining-work stock:

```
State: remaining_effort(case_type, allocation_day) = total remaining hours for this cohort
       count(case_type, allocation_day) = number of cases in this cohort
```

Each workday, productive hours are distributed to cohorts. The remaining-work stock decrements:

```
remaining_effort(t+1) = remaining_effort(t) - hours_applied(t)
```

Cases close when their per-case remaining effort reaches zero:

```
avg_remaining = remaining_effort / count
IF avg_remaining <= 0: entire cohort closes
```

In practice, cases within a cohort have varying remaining effort. We handle this by allowing fractional closure: if a cohort of 10 cases has 5 hours remaining and receives 3 hours of work, ~6 cases close (3 / 0.5 hours each) and 4 remain with proportional remaining effort.

```
hours_per_case = remaining_effort / count
cases_closed = MIN(count, FLOOR(hours_applied / hours_per_case))
remaining_effort -= cases_closed × hours_per_case
count -= cases_closed
```

### How Productive Hours Are Distributed

Each workday, productive hours are allocated to cohorts in **priority order** (lowest remaining workdays to service target first):

```
productive_hours(t) = on_desk_FTE(t) × hours_per_day × (1 - non_absence_shrinkage) × utilisation_cap × proficiency_blend
budget = productive_hours(t)

Sort allocated cohorts by remaining_workdays_to_service_target ASC
FOR each cohort in priority order:
    hours_needed = remaining_effort(cohort)
    hours_given = MIN(budget, hours_needed)
    Apply hours_given to cohort (close cases, reduce remaining effort)
    budget -= hours_given
    IF budget <= 0: BREAK
```

This means:
- The most urgent cases get worked first
- If there aren't enough hours, lower-priority cases receive no work and age
- The total hours consumed never exceed productive capacity
- No effort is double-counted — hours are applied once and consumed once

---

## First Touch Close (FTC)

FTC is an **outcome within the diary**, not a bypass. Cases must be allocated (take a diary slot) before they can be resolved.

### FTC as Subcohort

When cases are allocated, a known fraction are FTC-eligible: simple cases that will close within 0-3 days. Rather than using a random draw (which produces incorrect cumulative probabilities in a cohort model), we model FTC as a **deterministic subcohort**:

```
On allocation day:
    ftc_count = newly_allocated × ftc_rate(case_type)
    non_ftc_count = newly_allocated × (1 - ftc_rate(case_type))
```

The FTC subcohort closes over days 0-2 after allocation, with a distribution:

```
ftc_closure_distribution = [g0, g1, g2]    where g0 + g1 + g2 = 1.0
```

Default: `[0.3, 0.5, 0.2]` — 30% close same day, 50% close day 1, 20% close day 2.

```
ftc_closures(t) = g0 × ftc_allocated_today(t) + g1 × ftc_allocated_yesterday(t) + g2 × ftc_allocated_2_days_ago(t)
```

FTC closures:
- **Consume effort** from the productive hours budget (at the 0-3 day burden rate: 0.7x base = ~63 mins)
- **Free diary slots** on the day they close
- The FTC hours come from the same `productive_hours` budget — no separate accounting

For PCA BAU, the FTC rate is ~40% because many are simple queries. The rate is a parameter per case type.

### Why FTC Matters for Demand

High FTC means diary slots turn over quickly, keeping the unallocated pool small and cases young. Low FTC means slots are blocked longer, the pool grows, cases age, and burden increases. FTC rate is a lever that directly affects the spiral.

---

## Supply Side (Simplified for POC)

### Two Concepts of FTE

The model separates **on-desk FTE** (for diary slot capacity) from **productive hours** (for work throughput):

```
on_desk_FTE(t) = total_FTE × (1 - absence_rate)
productive_hours(t) = on_desk_FTE(t) × hours_per_day × (1 - non_absence_shrinkage) × utilisation_cap × proficiency_blend
```

| Parameter | Default | Notes |
|-----------|---------|-------|
| total_FTE | Input parameter | The number we're solving for |
| hours_per_day | 7.0 | 35 hours/week ÷ 5 days = 7.0 hours/day |
| absence_rate | 0.15 | 15% — leave, sickness, training days. Removes bodies from desks. |
| non_absence_shrinkage | 0.18 | 18% — meetings, coaching, breaks, admin for present staff. Reduces productive hours but not diary slots. |
| utilisation_cap | 0.85 | 85% max utilisation. Buffer against variability. Research strongly warns against staffing to >90%. |
| proficiency_blend | 0.88 | Blended team proficiency. 1.0 = fully competent baseline. |

**Note:** Total shrinkage = `1 - (1 - absence_rate) × (1 - non_absence_shrinkage)` = `1 - 0.85 × 0.82` = `1 - 0.697` = ~30%. This matches the 30% total shrinkage figure but correctly splits the effect: absence reduces slots AND hours, non-absence shrinkage only reduces hours.

```
on_desk_FTE = FTE × 0.85
productive_hours_per_on_desk_fte = 7.0 × 0.82 × 0.85 × 0.88 = 4.29 hours/day
productive_hours_per_total_fte = 7.0 × 0.82 × 0.85 × 0.88 × 0.85 = 3.65 hours/day
```

Each total FTE delivers ~3.65 productive hours per day against complaint work.

---

## FTE Demand Calculation

### The Circularity Problem

FTE demand is inherently circular: closures depend on FTE, but FTE demand depends on the WIP state, which depends on closures. This is not a formula — it is a **simulation that converges**.

### How It Works

The model runs as a simulation with a **given FTE count** as input. The outputs tell you whether that FTE level is sustainable:

- Is WIP stable or growing?
- What are the breach rates?
- What is the average age at closure?
- What is the actual utilisation?

**FTE demand** is found by running the model at multiple FTE levels and finding the one that achieves the target:

```
FOR fte_level in search_range:
    results = run_simulation(fte=fte_level, days=365)
    record: fte_level, steady_state_breach_rate, wip_trajectory, avg_age_at_close

FTE_demand = fte_level where breach_rate <= target AND wip is stable
```

This can be automated via binary search or displayed as a curve (FTE vs breach rate) for the user to read.

### Daily Demand Hours (Instantaneous)

As a secondary output, the model also reports the daily demand hours — the total hours of work required to close all cases at the target pace:

```
daily_demand_hours(t) = SUM over all allocated cohorts: remaining_effort(cohort) / target_days_to_close(cohort)
instantaneous_FTE_demand(t) = daily_demand_hours(t) / productive_hours_per_total_fte
```

This gives a day-by-day "how many FTE would we need right now" signal, useful for spotting trends and spikes.

---

## Diary Size and Productivity

### The Slowdown Function

Handler productivity degrades non-linearly as diary size increases beyond the optimal point, due to context switching and re-familiarisation overhead.

```
effective_productivity(diary_size) = base_productivity × slowdown(diary_size)
```

Where `slowdown` is:

```
slowdown(d) = 1.0                                       if d <= d_optimal
slowdown(d) = 1 / (1 + alpha × (d - d_optimal)^2)      if d > d_optimal
```

- `d_optimal` = 7 (the diary limit)
- `alpha` controls how sharply productivity drops if handlers are overloaded

Under normal operation with a hard diary limit of 7, handlers should be at or below optimal. The slowdown function becomes relevant when we model stress scenarios (e.g., "what if we push diary limits to 10?") or when we later add individual handler variation.

For the POC, the diary limit is a hard cap — handlers cannot exceed 7 cases. The slowdown function is included in the maths so we can test "what if we change the diary limit?" as a scenario.

---

## Shape Functions

All tuneable parameters use **parameterised shape functions** that can be:
1. Set by eye using sensible defaults (POC phase)
2. Fitted to real MI data (calibration phase)

| Shape Function | What It Controls | Default Form |
|---------------|-----------------|-------------|
| `intake_age_shape(age)` | Age distribution of arriving cases | Exponential decay with fat tail |
| `wip_age_shape(case_type, age)` | Starting WIP age distribution per case type | Exponential decay, 40% in 0-3 days |
| `burden_multiplier(age)` | Effort increase with case age at allocation | Piecewise linear through anchor points |
| `ftc_closure_distribution` | How FTC cases close over days 0-2 | [0.3, 0.5, 0.2] |
| `slowdown(diary_size)` | Productivity loss from overloaded diary | Quadratic penalty above optimal |
| `ftc_rate(case_type)` | Proportion of allocations that are FTC | Single parameter per type (~40% for PCA BAU) |

Each shape function exposes 2-4 tuneable parameters (e.g., decay rate, inflection point, floor/ceiling). The dashboard allows adjusting these and seeing the effect on demand in real time.

---

## Outputs and Graphs

The model produces daily time series over 365 days. The following graphs are core deliverables — they ARE the proof that the model works.

### Primary Outputs

| Graph | X-Axis | Y-Axis | What It Proves |
|-------|--------|--------|---------------|
| **FTE demand over time** | Day (1-365) | FTE needed | Forward demand projection — the headline number |
| **FTE demand vs service target** | Service target (7-56 days) | FTE needed | The sweet spot U-curve |
| **WIP age profile over time** | Day (1-365) | Cases by age band | Is backlog draining or ageing out? |
| **Breach rate vs FTE headcount** | FTE | Breach % | How many people before breaches are acceptable? |
| **Utilisation vs breach rate** | Utilisation % | Breach % | The non-linear explosion approaching 100% |

### Scenario Outputs (Interactive)

| Scenario | What You Change | What You See |
|----------|----------------|-------------|
| **Allocation team illness** | Increase absence_rate | Fewer diary slots, WIP ages, demand rises, breaches spike |
| **Service target change** | Move target 21 → 28 days | FTE drops but burden increases — where's the sweet spot? |
| **Diary limit change** | Move limit 7 → 10 | More allocation throughput but productivity drops |
| **Demand spike** | Intake 300 → 500 for 2 weeks | How long to recover? Does the spiral kick in? |
| **Understaffing** | Reduce FTE by 10% | How fast does backlog grow? When does it tip? |
| **Utilisation change** | Cap 85% → 95% | Short-term gain, long-term collapse |

### Dashboard

An interactive UI where you can adjust parameters via sliders and see curves respond:
- FTE count
- Service target (days)
- Utilisation cap (%)
- Diary limit
- Absence rate (%)
- Intake rate
- Burden curve shape
- FTC rate

---

## Daily Simulation Loop (Pseudocode)

This is the core engine — one iteration per day. The ordering is critical to avoid bias.

```
FOR each day t from 1 to 365:

    is_workday = (day_of_week(t) is Monday-Friday)

    # ============================================================
    # STEP 1: AGE CARRIED-OVER STOCK (overnight, before anything else)
    # ============================================================
    # Only cases from previous days age. New arrivals today start at their intake age.

    FOR each case in unallocated_pool (from previous day):
        IF case_type is FCA:
            age += 1                    # Calendar day — ages every day including weekends
        ELIF is_workday:
            age += 1                    # Business day — ages only on workdays

    FOR each case in allocated_pool (from previous day):
        Same ageing logic as above

    # ============================================================
    # STEP 2: INTAKE (new cases arrive at their intake age)
    # ============================================================
    IF is_workday:    # POC: intake on workdays only
        FOR each case_type:
            new_cases = daily_intake × type_proportion(case_type)
            FOR each age in intake_age_shape:
                add (new_cases × intake_age_shape(age)) to unallocated_pool(case_type, age)

    # ============================================================
    # STEP 3: PSD2-15 → PSD2-35 EXTENSION (before breach check)
    # ============================================================
    # One-off at the 15-business-day boundary. Applied exactly once per case.
    IF is_workday:
        eligible = PSD2-15 cases in allocated_pool at exactly business_day_age == 15
        extensions = eligible × psd2_extension_rate (5%)
        Reclassify extensions as PSD2-35 (retain age, new deadline of 35 biz days)

    # ============================================================
    # STEP 4: ALLOCATION (workdays only)
    # ============================================================
    IF is_workday:
        # Diary slots based on ON-DESK FTE, not productive FTE
        on_desk = total_FTE × (1 - absence_rate)
        max_slots = on_desk × diary_limit
        available_slots = MAX(0, max_slots - allocated_WIP_count)
        cases_to_allocate = MIN(unallocated_pool_count, available_slots)

        Sort unallocated pool by remaining_workdays_to_service_target ASC
            (ties broken by remaining_workdays_to_regulatory_deadline ASC)

        FOR top cases_to_allocate cases:
            Move from unallocated → allocated
            Set remaining_effort = base_effort × burden_multiplier(current_age)
            Tag FTC subcohort: ftc_count = ftc_rate(case_type) fraction

    # ============================================================
    # STEP 5: WORK AND CLOSURES (workdays only)
    # ============================================================
    IF is_workday:
        productive_hours = on_desk × hours_per_day × (1 - non_absence_shrinkage) × util_cap × proficiency
        budget = productive_hours

        # --- FTC closures first (from recent allocations) ---
        ftc_due_today = (g0 × ftc_allocated_today) + (g1 × ftc_allocated_yesterday)
                        + (g2 × ftc_allocated_2_days_ago)
        ftc_hours = ftc_due_today × ftc_effort_per_case
        ftc_hours = MIN(ftc_hours, budget)
        actual_ftc_closures = ftc_hours / ftc_effort_per_case
        budget -= ftc_hours
        Remove ftc_closures from allocated pool, free diary slots

        # --- Regular closures (remaining budget to priority cases) ---
        Sort remaining allocated cohorts by remaining_workdays_to_service_target ASC

        FOR each cohort in priority order:
            IF budget <= 0: BREAK
            hours_per_case = remaining_effort(cohort) / count(cohort)
            hours_given = MIN(budget, remaining_effort(cohort))
            cases_closed = MIN(count(cohort), FLOOR(hours_given / hours_per_case))
            remaining_effort(cohort) -= hours_given
            count(cohort) -= cases_closed
            budget -= hours_given
            Record: closures, age at closure

    # ============================================================
    # STEP 6: BREACH CHECK (after all processing)
    # ============================================================
    FOR each case in both pools:
        IF case_type == FCA AND calendar_age > 56: mark breached
        IF case_type == PSD2-15 AND business_day_age > 15: mark breached
        IF case_type == PSD2-35 AND business_day_age > 35: mark breached

    # ============================================================
    # STEP 7: RECORD OUTPUTS
    # ============================================================
    Record: total_WIP, WIP_by_age_band, WIP_by_case_type, unallocated_count,
            allocated_count, closures_today (ftc + regular), breach_count,
            breach_rate, avg_age_at_close, avg_allocation_delay, utilisation,
            instantaneous_FTE_demand, remaining_effort_total, diary_occupancy
```

### Why This Ordering Matters

| Step | Rationale |
|------|-----------|
| Age first | Carried-over cases age overnight. New arrivals don't age on arrival day. |
| Intake after ageing | Day-0 arrivals enter at age 0, not age 1. |
| PSD2 extension before breach | Cases get extended before being marked breached. One-off, not repeated. |
| Allocation before work | Newly allocated cases can receive work the same day. |
| FTC before regular closures | FTC cases free diary slots that become available for the NEXT day's allocation (not same-day reuse, to avoid overcomplication). |
| Breach after closures | Cases closed today are removed before breach check. |

---

## What Emerges vs What Is Input

A critical design principle: key operational metrics should **emerge from the model**, not be hardcoded. This is how we prove the maths works.

| Emerges (output) | Input (parameter) |
|-------------------|-------------------|
| Average age at closure | Service target, FTE count |
| Breach rate | FTE count, burden curve, priority policy |
| Average allocation delay | Diary limit, FTE count, intake rate, absence rate |
| Utilisation (actual) | Utilisation cap, WIP state, FTE count |
| FTE demand | Found by iterating FTE until targets met |
| The sweet spot | Service target sweep |
| Tipping point | FTE reduction scenarios |

If the model produces breach rates and allocation delays that match operational reality (~3% FCA breaches, ~1.5 day allocation delay, ~10% PSD2 breaches), the maths is validated.

---

## Technology

- **Language:** Python
- **Engine:** Pure numerical computation (NumPy/SciPy). No simulation framework needed for cohort model.
- **Dashboard:** Interactive web UI (e.g., Streamlit, Plotly Dash, or similar) with sliders for parameters and real-time graph updates.
- **Shape functions:** Parameterised curves using scipy interpolation or simple piecewise functions.

---

## What Is Deferred (Not In POC)

| Component | Why Deferred | When It Comes In |
|-----------|-------------|-----------------|
| Individual handler simulation | Cohort model proves the maths first | Layer 5+ (DES/ABM) |
| Detailed shrinkage breakdown | Absence/non-absence split is sufficient for POC | Layer 3 |
| Seasonal leave / sickness patterns | Shape function, but not needed to prove maths | Layer 3 |
| Cross-skilling / overflow | Single product first | Multi-product phase |
| Hiring pipeline / ramp-up time | Strategic planning layer | Layer 5 |
| Reopens / rework | Secondary feedback loop | Layer 4 |
| In-diary ageing penalty | Main spiral driven by unallocated ageing; add if needed | Layer 2 |
| Day-of-week intake variation | Flat rate sufficient for POC | Layer 2 |
| Handler attrition / turnover | Strategic planning concern | Layer 5 |
| Weekend intake volumes | Start with workday-only intake | Layer 2 |

---

## Validation Criteria

The model is "working" when:

1. **Steady state sanity:** Given sufficient FTE, WIP stabilises and breach rates match expectations (~3% FCA, ~10% PSD2)
2. **Spiral behaviour:** Reducing FTE by 10-15% triggers visible backlog growth and accelerating breach rates — not linear degradation but exponential
3. **Service target response:** Moving target from 21 → 28 days reduces FTE demand but increases average age and burden — the U-curve is visible
4. **Allocation feedback:** Increasing absence rate (simulating ill allocation team / absences) visibly increases demand and breaches
5. **Weekend effect:** Monday shows higher WIP in older bands than Friday (FCA cases only — PSD2 unaffected)
6. **Diary constraint:** When diary slots are full, unallocated pool grows and ages
7. **Sweet spot exists:** The FTE vs service target curve has a visible minimum
8. **FTC impact:** Reducing FTC rate from 40% to 20% visibly increases WIP and demand
9. **Priority correctness:** PSD2 cases with tight deadlines are worked before younger FCA cases; no case is ignored until the last minute
10. **Remaining work conserved:** Total hours applied across all closures ≈ total effort assigned at allocation (energy conservation check)

---

## Layered Build Roadmap

| Layer | What It Adds | Purpose |
|-------|-------------|---------|
| **1. Demand engine** | WIP, intake, ageing, burden curve, allocation with diary limit, FTC subcohort, remaining-work stock, closures from assumed FTE, priority by remaining workdays | Prove the maths: does demand respond correctly to parameters? |
| **2. Supply match + scenarios** | Run at multiple FTE levels, find sweet spot, interactive dashboard with sliders, all graphs | See trade-offs, find optimal FTE, stress-test scenarios |
| **3. Realistic supply** | Detailed shrinkage (leave, sickness, training), seasonal patterns, in-diary ageing penalty | Make supply realistic, capture secondary effects |
| **4. Closed loop** | Supply determines closures, closures determine ageing, ageing determines demand — fully coupled with automatic FTE search | The spiral in action. This is the real model. |
| **5. Policy levers** | Prioritisation strategies, diary limit optimisation, overtime, cross-skilling | What can operations actually change? |
| **6. Strategic** | Hiring pipeline, attrition, training ramp, multi-product | Workforce planning decisions |

**The POC delivers Layers 1-2 with the interactive dashboard.** Layers 3-4 follow immediately to close the loop.

---

## Revision Log

| Version | Date | Changes |
|---------|------|---------|
| 1 | 2026-04-05 | Initial spec |
| 2 | 2026-04-05 | Fixed 9 issues from GPT-5.4 review: (1) replaced drain+closure with remaining-work stock to eliminate double-counting, (2) added remaining effort tracking per cohort, (3) fixed priority to use remaining workdays on common clock instead of raw slack, (4) replaced random FTC with deterministic subcohort model, (5) corrected simulation loop ordering to prevent ageing bias, (6) separated on-desk FTE (diary slots) from productive FTE (throughput), (7) moved PSD2 extension before breach check as one-off event, (8) clarified FTE demand as iterative search not formula, (9) split initial WIP by pool/type/age. Also corrected hours_per_day from 7.5 to 7.0 (35 hrs/week). |
