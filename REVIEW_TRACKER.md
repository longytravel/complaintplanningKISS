# Complaints Demand Model — Review Tracker

Track fixes and open items across context clears.

## Completed Fixes

### 1. Rename FTC -> SRC (Summary Resolution Communication)
- [x] All code identifiers renamed (FTC_RATES -> SRC_RATES, is_ftc -> is_src, etc.)
- [x] Docstring updated to describe SRC mechanism

### 2. PSD2 Extension Weekend Bug
- [x] `apply_psd2_extensions` gated behind `if workday:` in simulate loop
- **Was:** Extensions fired every day including weekends. Cases hitting biz_age=15 on Friday got checked 3 times (Fri/Sat/Sun), inflating effective rate from 5% to ~14.3%
- **Now:** Extensions only checked on workdays when biz_age actually changes

### 3. Same-Day Closure Guard
- [x] Changed `closeable()` from `cal_days <= 0` to `cal_days < 0`
- **Was:** Cases allocated today could never close today (contradicted `MIN_DIARY_DAYS = 0` comment)
- **Now:** Same-day closure allowed; SRC_DIST controls how many actually close same-day

### 4. 5th Allocation Pass — FTC Schedule + AM/PM Split
- [x] Moved `src_schedule[workday_num]` save to AFTER the 5th allocation pass
- [x] Added AM/PM allocation constants: AM_ALLOCATION_SHARE=0.70, PM_ALLOCATION_SHARE=0.30
- [x] Blended SRC_DIST = (0.22, 0.50, 0.28) from AM=(0.30,0.50,0.20) and PM=(0.05,0.475,0.475)
- **Was:** SRC cases from end-of-day refill had no scheduled closure quota
- **Now:** All SRC allocations (including refill) are in the schedule

### 5. Dynamic Burden at Closure Time
- [x] Added `case_effort()` helper — computes effort from live `reg_age` at closure
- [x] `process_work_slice` uses `case_effort()` instead of frozen `effort_per_case`
- [x] `calculate_instantaneous_fte_demand` uses `case_effort()` for allocated cases
- [x] Newly allocated cases get `effort_per_case=0.0` and `seeded=False`
- [x] Seeded cases (initial WIP) still use stored effort (work-already-done discount)
- [x] Fixed `eff <= 0` from `break` to `continue` in regular candidate loop
- **Was:** Effort frozen at allocation age — a case allocated at age 5 stayed at burden 1.0 even if it aged to 30 in the diary
- **Now:** Burden recalculated from current age at every closure attempt

### 6. SRC Window-Aware Split
- [x] Added `SRC_WINDOW = 3` constant
- [x] At allocation, only the fraction of `SRC_DIST` that falls within 0-3 reg days becomes SRC
- [x] Cases allocated at age 2: 72% of SRC rate eligible (days 0,1 fit; day 2 = age 4)
- [x] Cases allocated at age 3: 22% eligible (only same-day fits)
- [x] Cases aged past SRC_WINDOW lose the 0.7x effort discount in `case_effort()`

### 7. SRC Effort Ratio
- [x] Changed `SRC_EFFORT_RATIO` from 1.0 to 0.7
- **Was:** SRC cases cost same effort as regular (no discount for simpler resolution)
- **Now:** SRC cases within 0-3 day window get 0.7x effort multiplier

### 8. FTE Demand Metric Consistency
- [x] Added `(1 - LATE_DEMAND_RATE)` to `calculate_instantaneous_fte_demand`
- **Was:** Demand calc assumed 8% more capacity per FTE than simulation delivered
- **Now:** Demand and simulation use same throughput assumptions

## Verified Output (120 FTE, 730 days)

| Metric | Before | After |
|--------|--------|-------|
| Steady-state WIP | ~1,000 | 1,224 |
| FCA avg age at close | ~7.6 | 9.2 |
| FCA system time | — | 7.9 |
| Effective utilisation | 86-88% | 95.5% |
| Allocation delay | ~1 day | 2.4 days |
| FCA stock breach | 0% | 0% |
| PSD2 stock breach | ~2% | 0% |
| FCA flow breach | — | 0% |
| PSD2 flow breach | — | 2.33% (pre-aged intake) |
| Min stable FTE | 120 | 119 |
| Settles by | Day 90 | Day 60 |

## Stress Test Output (105 vs 125 FTE, 365 days)

| Metric | 105 FTE (understaffed) | 125 FTE (overstaffed) |
|--------|----------------------|---------------------|
| Final WIP | 44,700 (growing) | 1,177 (stable) |
| Unallocated | 44,076 | 433 |
| Closures/day | 102.5 | 300.0 |
| Effective utilisation | 100% (pegged) | 91.6% (Parkinson) |
| Allocation delay | 178 days | 2.0 days |
| FCA avg age at close | 184.2 days | 8.8 days |
| Stock breach rate | 77% | 0% |
| Flow breach rate | 100% | 0.7% |
| Stable? | NO | YES |
| WIP delta (last 30d) | +4,147 | 0 |

**Burden death spiral confirmed:** at 105 FTE, closures fall from 201→102.5/day as cases age into the 2.5× burden band. The system can never recover — it closes 34% of intake while running at 100% utilisation.

## Still To Discuss

### ~~A. Breach Rate: Stock vs Flow~~ RESOLVED
- [x] Added `average_flow_breach_rates()` — breached closures / total closures over workdays
- [x] Both stock and flow shown in detailed pack and FTE sweep table (StockBr / FlowBr)
- [x] `is_stable()` now checks both stock and flow breach rates against targets
- [x] Flow breach reveals 2.33% PSD2 breaches from pre-aged intake (day 40 arrivals)
- [x] Stock hides these because breached cases close quickly; flow catches the customer outcome

### ~~B. Parkinson's Pressure Timing~~ RESOLVED — kept as-is
- Pressure measured before intake: equilibrium unalloc = 510 (conservative)
- Alternative (after intake) gives 210 unalloc but identical util/throughput/breaches
- Decision: keep 510 — models realistic lag (handlers pace off yesterday's queue)

### ~~C. Minor Items~~ RESOLVED
- [x] `make_age`: removed redundant `max()` — `(reg_age // 5) * 2` is always >= 0
- [x] `count_business_days_forward`: replaced O(n) loop with O(1) divmod arithmetic
- [x] `is_stable`: threshold now `DAILY_INTAKE / 12` — scales with intake (~25 at 300/day)
- [x] `last_n_workdays`: fixed to return actual last N workdays (was returning ~43 from 60 cal days)
- Kept as-is: 3% pre-breached seed WIP (intentional — models legacy stock)
- Kept as-is: merge key includes `arrival_day`/`allocation_day` (needed for delay/system-time metrics; biweekly merge keeps lists manageable)

### D. GPT-5.4 Code Review (Codex, 2026-04-06)
Findings reviewed and dispositioned:
1. **SRC in regular pass** (Codex: critical → disagreed): SRC cases sort to bottom of regular pass by priority (youngest = furthest from target). At steady state, no excess budget leaks. Models reality — handlers close what's in diary.
2. **Refill SRC same-day miss** (Codex: medium → known): End-of-day refill cases realistically have no time for same-day closure. Already addressed in fix #4.
3. **`last_n_workdays` bug** (Codex: medium → agreed, fixed): Function now returns actual last N workdays.
4. **`make_age` PSD2 cal_age approx** (Codex: low → cosmetic): Only affects display metric; PSD2 uses biz_age for all regulatory logic.
5. **`is_stable` at low intake** (Codex: low → YAGNI): Threshold < 1 at intake < 12/day; irrelevant at 300/day.

### E. Triple-Check Validation (Claude + GPT-5.4, 2026-04-06)

Stress test: 105 FTE (understaffed) vs 125 FTE (overstaffed), 365 days.

**Both reviewers independently confirmed model is mathematically correct.**

#### Arithmetic Verification
| Calculation | Value | Confirmed by |
|-------------|-------|--------------|
| Productive hrs/day at 105 FTE | 105 × 0.58 × 7.0 × 0.92 = 392.2 | Claude + GPT-5.4 |
| Effort per case (57+ burden) | 1.5 × 2.5 + 0.15 × 0.5 = 3.825 | Claude + GPT-5.4 |
| Closures/day at steady state | 392.2 / 3.825 = 102.5 | Matches simulation |
| Total intake (261 workdays) | 78,300 | GPT-5.4 (exact) |
| Total closures | 36,100 | GPT-5.4 (exact) |
| Final WIP | 78,300 − 36,100 + 2,500 = 44,700 | GPT-5.4 verified to decimal |

#### Sanity Checks (all passed at 105 vs 125)
- [x] WIP higher when understaffed (44,700 vs 1,177)
- [x] Unallocated higher when understaffed (44,076 vs 433)
- [x] Utilisation higher when understaffed (100% vs 91.6%)
- [x] Allocation delay higher when understaffed (178 vs 2.0 days)
- [x] Breach rate higher when understaffed (100% flow vs 0.7%)
- [x] WIP growing when understaffed (+4,147/month vs stable)
- [x] Understaffed unstable, overstaffed stable

#### GPT-5.4 Findings Dispositioned
1. **`demand_fte` misleading at extreme understaffing** (high → noted, no change): Shows 38,533 because `max(1, target_remaining)` forces all overdue work into one day. Mathematically correct — it's the scale of the hole, not a hiring number. Useful as a "how bad is it" indicator.
2. **SRC spill into regular pass** (medium → accepted, no change): SRC cases can close in regular pass after their scheduled quota. Biases closures *upward* (optimistic), meaning real death spiral could be slightly worse. At steady state with backlog, old cases consume budget first so spill is minimal. Models reality — handlers work what's in their diary.
3. **`MIN_DIARY_DAYS` off-by-one** (medium → comment added): `closeable()` counts allocation day as a business day. Would be wrong at `MIN_DIARY_DAYS > 0`. Currently masked at default 0. Added warning comment in code.
4. **Seeded WIP discount** (low → accepted, no change): `seed_pool()` gives allocated seed cases a work-already-done discount via `case_effort()` returning frozen value. Makes early dynamics optimistic but irrelevant to steady state (seeded cases gone by day 60).
5. **Parkinson ceiling at 1.0** (info → agreed): Correct not to exceed 1.0. Overtime would need a separate parameter. No change.
6. **Pressure from unallocated only** (info → design choice): Diary age/complexity doesn't raise pace. Intentional — handlers pace off visible queue, not case difficulty. No change.
7. **Stale `compare_staffing.py` docstring** (low → fixed): Updated to be parameter-driven.
