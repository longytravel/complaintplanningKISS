# Strategy Comparison Dashboard Page — Design Spec

**Date:** 2026-04-06
**Status:** Draft

## Overview

A second Streamlit page dedicated to strategy comparison. Page 1 (existing dashboard) establishes system parameters — the "facts." Page 2 uses those same parameters and adds allocation/work strategy selection to show how different strategies perform under those conditions.

## Page Architecture

### Page 1 — System Dashboard (existing, unchanged)
- All parameter sliders in sidebar (staffing, demand, Parkinson's, SRC, regulatory)
- Single simulation run with full chart suite
- Parameters stored in `st.session_state` so Page 2 can read them

### Page 2 — Strategy Comparison (new)
- **No parameter sliders** — reads all params from session state (set on Page 1)
- Displays current params as a read-only summary strip at top so user knows what conditions are active
- Adds only: allocation strategy + work strategy controls

## Page 2 Layout (top to bottom)

### Section 1: Parameter Summary
- Compact read-only display of key params inherited from Page 1 (FTE, daily intake, shrinkage, etc.)
- If Page 1 hasn't been visited yet, use module defaults
- Link/note directing user to Page 1 to change system parameters

### Section 2: Heatmap Screening — "Run All 36"
- Button to trigger batch simulation of all 36 strategy combos under current params
- Progress bar during execution (~2-3 min first run, cached after)
- **9 heatmaps** arranged in a 3x3 grid (3 per row):

| Row | Metric 1 | Metric 2 | Metric 3 |
|-----|----------|----------|----------|
| 1   | Final WIP | FCA Stock Breach % | PSD2 Stock Breach % |
| 2   | FCA Flow Breach % | PSD2 Flow Breach % | Avg Closures/Day |
| 3   | Max Unallocated Wait | Max Diary Neglect | Avg Diary Neglect |

- Each heatmap is a 6x6 grid:
  - Y-axis: Allocation strategies (nearest_deadline, nearest_target, youngest_first, oldest_first, psd2_priority, longest_wait)
  - X-axis: Work strategies (nearest_deadline, nearest_target, youngest_first, oldest_first, lowest_effort, longest_untouched)
- **Annotated values** on each cell (the actual number) with colour scale (green = good, red = bad)
- Colour scale direction flips per metric (low WIP = green, high closures = green)
- Death spiral combos (WIP > 50,000 or circuit breaker hit) shown as dark red with "UNSTABLE" label

### Section 3: Combo Picker
- Multiselect dropdown listing all 36 combos formatted as "allocation / work" (e.g. "youngest_first / oldest_first")
- User picks 2-3 combos to compare in detail
- Simulations for selected combos already cached from the batch run

### Section 4: Drill-Down Time-Series — "Strategy Deep Dive"
- Only visible once combos are selected
- 6 chart groups, each with overlaid lines (one colour per selected combo, consistent colour across all charts):

1. **WIP over time** — total WIP trajectory for each combo
2. **Closures per day** — workday-only throughput comparison
3. **FCA Breach % over time** — stock breach trend
4. **PSD2 Breach % over time** — stock breach trend
5. **Unallocated queue size** — backlog pressure comparison
6. **Age profile** — side-by-side stacked area charts (one per selected combo, not overlaid)

## Technical Approach

### Streamlit Multipage
- Convert to Streamlit multipage app structure: create `pages/` directory
- `dashboard.py` stays as the main page (or becomes `pages/1_System_Dashboard.py`)
- New file: `pages/2_Strategy_Comparison.py`

### Session State for Parameter Sharing
- Page 1 writes all slider values to `st.session_state` (e.g. `st.session_state.fte = fte`)
- Page 2 reads from `st.session_state` with fallbacks to module defaults
- No duplication of slider logic

### Batch Simulation
- Import `strategy_model as sm`
- Loop through all 36 combos, setting `sm.ALLOCATION_STRATEGY` and `sm.WORK_STRATEGY` before each `sm.simulate()` call
- Cache the full batch result keyed on all params + "batch" flag
- Extract endpoint KPIs for heatmaps; store full time-series for drill-down
- Use `st.progress()` bar during batch run
- Handle circuit breaker / death spiral combos gracefully — mark as unstable, don't crash

### Heatmaps
- Plotly `go.Heatmap` with `text` parameter for annotated values
- Custom colorscale per metric (diverging: green-yellow-red)
- Reverse scale for metrics where high = good (closures)

### Drill-Down Charts
- Reuse chart helper pattern from Page 1
- Consistent colour assignment per combo across all charts
- Age profile: `st.columns(n)` with one stacked area per selected combo

## What This Does NOT Include
- No new strategies beyond the existing 6+6
- No parameter sliders on Page 2
- No auto-selection of "best" strategy — user screens via heatmaps and picks
- No export/download functionality (can add later)

## Dependencies
- `strategy_model.py` — must be working and importable
- `prove_maths.py` — base model (imported by strategy_model)
- `plotly` — already a dependency
- `streamlit` — already a dependency
