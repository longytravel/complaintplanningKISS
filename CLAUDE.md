# Complaints Workforce Demand Model

## What this is
A discrete-event simulation that answers: "How many FTE do we need to handle X complaints/day without breaching regulatory deadlines?"

Simulates 730 days of complaint flow through a two-pool system (unallocated queue -> handler diaries) with realistic operational behaviour including Parkinson's Law, dynamic SRC resolution, burden scaling, and diary capacity constraints.

## Key files

| File | Purpose |
|------|---------|
| `complaints_model/` | Core simulation package (modular, no external deps) |
| `complaints_model/config.py` | `SimConfig` frozen dataclass — all tuneable parameters |
| `complaints_model/simulation.py` | Main 730-day simulation loop |
| `complaints_model/allocation.py` | Allocation engine — queue → diary (strategy-aware) |
| `complaints_model/work.py` | Work engine — handlers close cases (strategy-aware) |
| `complaints_model/strategies.py` | 8 allocation + work prioritisation strategies |
| `complaints_model/metrics.py` | KPI computation, breach rates, stability check |
| `complaints_model/cohort.py` | Cohort dataclass — atomic simulation unit |
| `complaints_model/regulatory.py` | Deadlines, targets, PSD2 extensions |
| `complaints_model/effort.py` | Burden bands, case effort calculation |
| `complaints_model/intake.py` | Intake profiles, pool seeding, SRC rates |
| `complaints_model/time_utils.py` | Business day calculations, age conversion |
| `complaints_model/reporting.py` | CLI output formatting, FTE sweep |
| `dashboard.py` | Streamlit interactive dashboard. Sliders for all params, 13 charts, 12 KPI cards |
| `pages/2_Strategy_Comparison.py` | Strategy comparison dashboard page — heatmaps + drill-down |
| `run_scenarios.py` | CLI runner: all 36 strategy combos with ranked output. `--fte`, `--sort-by` args. |
| `compare_staffing.py` | Side-by-side comparison of two FTE levels (understaffed vs overstaffed) |
| `complaints_model/bands.py` | Band definitions (FCA/PSD2/Combined/Hybrid), case-to-band assignment |
| `complaints_model/pool_config.py` | `OptimConfig` dataclass — per-band FTE splits, strategies, harm weights |
| `complaints_model/harm.py` | Per-case-per-day harm scoring (breach overshoot + neglect + WIP) |
| `complaints_model/pool_simulation.py` | `simulate_pooled()` — multi-pool simulation with per-band strategies |
| `optimise.py` | CLI: Optuna study runner. `--objective`, `--fte`, `--trials`, weight flags |
| `pages/3_Optimisation.py` | Optimisation dashboard — run Optuna, view best config, replay results |
| `tests/` | Regression and unit tests (63 total) |
| `requirements.txt` | Deps: `streamlit`, `plotly`, `optuna` |
| `docs/STRATEGY_DASHBOARD_HANDOVER.md` | Handover doc for integrating strategies into dashboard |
| `docs/superpowers/specs/2026-04-06-optimisation-design.md` | Optimisation design spec |
| `docs/superpowers/plans/2026-04-06-optimisation.md` | Implementation plan |

## Running

```bash
# Run the simulation (console output)
python -m complaints_model.reporting

# Run the interactive dashboard (3 pages: main, strategy comparison, optimisation)
pip install -r requirements.txt
streamlit run dashboard.py

# Run all tests
python -m pytest tests/ -v

# Run staffing comparison
python compare_staffing.py

# Run strategy scenarios
python run_scenarios.py

# Run FTE pool optimisation (Optuna)
python optimise.py --objective composite_harm --fte 148 --trials 200
```

## Architecture

### Package (`complaints_model/`)
- `SimConfig` frozen dataclass holds all 27 tuneable parameters with sensible defaults
- `simulate(cfg)` returns a list of daily metric dicts (one per simulated day)
- Dashboard builds a `SimConfig` from slider values — no global mutation
- Strategy support is built-in: `cfg.allocation_strategy` and `cfg.work_strategy`
- Key mechanisms: Parkinson's Law pressure, SRC (Summary Resolution Communication) window, PSD2 extensions, burden scaling by case age, non-SRC minimum diary days (3 biz days)
- Dependency flow is one-directional: config → cohort → regulatory → effort → strategies → intake → allocation/work → simulation → metrics → reporting
- **Pool optimisation** extends this with: bands → pool_config → harm → pool_simulation → optimise

### Dashboard (`dashboard.py`)
- Single-file Streamlit app
- Sidebar sliders grouped: Staffing, Demand, Parkinson's Law, SRC, Regulatory
- `@st.cache_data` on simulation wrapper -- same slider combo = instant cache hit
- Charts use Plotly. Flow metrics (closures, allocations) filter to workdays only; stock metrics (WIP, breaches) show all days

### Regulatory deadlines
- **FCA**: 56 calendar days
- **PSD2**: 15 business days (40% extend to 35 business days)

### KPI definitions
- **Stock breach %**: % of currently open cases past their regulatory deadline
- **Flow breach %**: % of cases *closed* in last 30 workdays that were breached at closure

## Key finding
148 FTE handles 300 complaints/day at steady state with ~0% FCA breaches and ~2% PSD2 breaches. The minimum viable staffing is ~138 FTE before instability sets in.

Previous finding (with MIN_DIARY_DAYS_NON_SRC=0) was 120 FTE / 119 minimum. The 3-day non-SRC investigation constraint increases minimum staffing by 16% because non-SRC cases occupy diary slots for 3+ days before they can close, reducing effective diary throughput.

### Strategy findings
Under stress (~135 FTE), allocation strategy is the critical lever:
- `youngest_first` allocation is the only strategy that survives — maximises SRC throughput
- `oldest_first` / `longest_wait` allocation causes instant death spirals
- `youngest_first` alloc + `oldest_first` work is the best stress-resilient combo
- `lowest_effort` work produces deceptive metrics — great closures but hides breach backlog

See `docs/STRATEGY_DASHBOARD_HANDOVER.md` for full results and dashboard integration guide.

### Pool Optimisation (`optimise.py` / `pool_simulation.py`)
- Splits FTE across case-age bands (5 FCA + 5 PSD2 bands, or 5 combined urgency tiers, or hybrid)
- Each band has its own allocation strategy, work strategy, and FTE count
- Optuna TPE sampler explores the decision space; median pruner kills bad configs early
- 5 objectives: composite harm, lowest WIP, lowest PSD2/FCA/total breaches
- Composite harm = `Σ(breach_weight × days_past_deadline + neglect_weight × days_untouched + wip_weight)` per case per day, days 366–730
- SQLite storage enables study resume across sessions
- Dashboard page 3 provides interactive Optuna controls and replay of best configs

## Validated
- Manual mathematical verification of all core functions
- GPT-5.4 high-reasoning code review (triple-check)
- Modular refactor regression: complaints_model output matches original prove_maths.py to 0 diff across all KPIs (WIP, breach rates, flow breach rates, closures, utilisation)
- Realism review: SRC is ~55% of cases (not 100%), non-SRC requires 3 biz day minimum, pre-aged intake produces ~2.3% PSD2 flow breach baseline
- Stress tests: 133 FTE shows expected death spiral, 150 FTE shows stable overcapacity
