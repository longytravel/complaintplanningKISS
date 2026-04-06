# Complaints Workforce Demand Model

## What this is
A discrete-event simulation that answers: "How many FTE do we need to handle X complaints/day without breaching regulatory deadlines?"

Simulates 730 days of complaint flow through a two-pool system (unallocated queue -> handler diaries) with realistic operational behaviour including Parkinson's Law, dynamic SRC resolution, burden scaling, and diary capacity constraints.

## Key files

| File | Purpose |
|------|---------|
| `prove_maths.py` | Core simulation model. Pure Python, no external deps. Entry point: `simulate(fte) -> list[dict]` |
| `dashboard.py` | Streamlit interactive dashboard. Sliders for all params, 13 charts, 12 KPI cards |
| `compare_staffing.py` | Side-by-side comparison of two FTE levels (understaffed vs overstaffed) |
| `requirements.txt` | Dashboard deps: `streamlit`, `plotly` |
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
- Key mechanisms: Parkinson's Law pressure, SRC (Summary Resolution Communication) window, PSD2 extensions, burden scaling by case age

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
120 FTE handles 300 complaints/day at steady state with 0% FCA breaches and ~2% PSD2 breaches. The minimum viable staffing is ~119 FTE before instability sets in.

## Validated
- Manual mathematical verification of all core functions
- GPT-5.4 high-reasoning code review (triple-check)
- Stress tests: 105 FTE shows expected death spiral, 125 FTE shows stable overcapacity
