# Complaints Workforce Demand Model

## What this is
A discrete-event simulation that answers: "How many FTE do we need to handle X complaints/day without breaching regulatory deadlines?"

Simulates 730 days of complaint flow through a two-pool system (unallocated queue -> handler diaries) with realistic operational behaviour including Parkinson's Law, dynamic SRC resolution, burden scaling, and diary capacity constraints.

## Key files

| File | Purpose |
|------|---------|
| `prove_maths.py` | Core simulation model. Pure Python, no external deps. Entry point: `simulate(fte) -> list[dict]` |
| `strategy_model.py` | Strategy-aware fork of prove_maths. Adds 6 allocation + 6 work strategies, neglect metrics. Imports from prove_maths. |
| `run_scenarios.py` | CLI runner: all 36 strategy combos with ranked output. `--fte`, `--sort-by` args. |
| `dashboard.py` | Streamlit interactive dashboard. Sliders for all params, 13 charts, 12 KPI cards |
| `compare_staffing.py` | Side-by-side comparison of two FTE levels (understaffed vs overstaffed) |
| `requirements.txt` | Dashboard deps: `streamlit`, `plotly` |
| `docs/STRATEGY_DASHBOARD_HANDOVER.md` | Handover doc for integrating strategies into dashboard |
| `REVIEW_TRACKER.md` | Code review findings and dispositions from triple-check validation |
| `Complaints planning research.md` | Background research and assumptions |

## Running

```bash
# Run the simulation (console output)
python prove_maths.py

# Run the interactive dashboard
pip install -r requirements.txt
streamlit run dashboard.py

# Run staffing comparison
python compare_staffing.py
```

## Architecture

### Model (`prove_maths.py`)
- All config is **module-level constants** (e.g. `DAILY_INTAKE = 300`, `SHRINKAGE = 0.42`)
- `simulate(fte)` returns a list of daily metric dicts (one per simulated day)
- The dashboard sets these globals before calling `simulate()` -- no need to modify function signatures
- Key mechanisms: Parkinson's Law pressure, SRC (Summary Resolution Communication) window, PSD2 extensions, burden scaling by case age, non-SRC minimum diary days (3 biz days)
- `MIN_DIARY_DAYS_NON_SRC = 3` — non-SRC cases need 3 business days in diary before closure (SRCs can close same-day). This is a realism constraint: if a case didn't resolve on first contact, it needs investigation time.

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

## Validated
- Manual mathematical verification of all core functions
- GPT-5.4 high-reasoning code review (triple-check)
- Strategy model regression: nearest_target/nearest_target matches prove_maths to 0.000% WIP diff
- Realism review: SRC is ~55% of cases (not 100%), non-SRC requires 3 biz day minimum, pre-aged intake produces ~2.3% PSD2 flow breach baseline
- Stress tests: 133 FTE shows expected death spiral, 150 FTE shows stable overcapacity
