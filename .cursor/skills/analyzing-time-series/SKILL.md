---
name: analyzing-time-series
description: Comprehensive diagnostic analysis of time series data. Use when users provide CSV or Parquet time series data and want to understand its characteristics before forecasting - stationarity, seasonality, trend, forecastability, and transform recommendations.
---

# Time Series Diagnostics

Comprehensive diagnostic toolkit to analyze time series data characteristics before forecasting.

## Input Format

CSV and Parquet are both accepted; the format is chosen by file extension
(`.parquet`/`.pq` → Parquet, anything else → CSV). The file needs:

- **Date column** - Timestamps or dates (e.g., `date`, `timestamp`, `time`).
  A Parquet file whose dates are already the index works too.
- **Value column** - Numeric values to analyze (e.g., `value`, `sales`, `temperature`)

Extra columns are ignored. On a wide panel with many numeric columns, pass
`--value-col` explicitly — otherwise the first numeric column is used and the
script warns about the guess.

```bash
python scripts/diagnose.py data/processed/AMZN_panel.parquet \
    --value-col revenue_usd_m --output-dir results/
```


## Workflow

**Step 1: Run diagnostics**

```bash
python scripts/diagnose.py data.csv --output-dir results/
python scripts/diagnose.py panel.parquet --value-col revenue_usd_m --output-dir results/
```

This runs all statistical tests and analyses. Outputs `diagnostics.json` with all metrics and `summary.txt` with human-readable findings. Column names are auto-detected, or can be specified with `--date-col` and `--value-col` options.

**Step 2: Generate plots (optional)**

```bash
python scripts/visualize.py data.csv --output-dir results/
python scripts/visualize.py panel.parquet --value-col revenue_usd_m --output-dir results/
```

Creates diagnostic plots in `results/plots/` for visual inspection. Run after `diagnose.py` to ensure ACF/PACF plots are synchronized with stationarity results. Column names are auto-detected, or can be specified with `--date-col` and `--value-col` options.

**Step 3: Build the PDF report (required)**

```bash
python scripts/report.py --output-dir results/ \
    --source data/processed/AAPL_panel.parquet --value-col revenue_usd_m
```

Always produce this — it is the deliverable. It assembles `diagnostics.json`
and every plot into `results/report.pdf`: a verdict page with the suggested
model specification, then each measure with the plain-language reason it
matters (why two stationarity tests, what a Box-Cox lambda near 0.5 means,
what the ACF/PACF lags imply about model order), then one page per plot with a
caption saying what to look for, and a closing next-steps list.

`--source` and `--value-col` only label the cover page; run it after
`visualize.py` so the plot pages are included. It reads the JSON rather than
recomputing anything, so the PDF cannot disagree with the other outputs.

**Step 4: Report to user**

Summarize the findings and hand over `report.pdf`. See
`references/interpretation.md` for guidance on:
- Is the data forecastable?
- Is it stationary? How much differencing is needed?
- Is there seasonality? What period?
- Is there a trend? What direction?
- Is a transform needed?

State the caveats the statistics cannot see — projected or future-dated rows,
structural breaks (COVID), and outliers that should be modelled as
interventions rather than fitted.

## Script Options

`diagnose.py` and `visualize.py` accept:
- `--date-col NAME` - Date column (auto-detected if omitted)
- `--value-col NAME` - Value column (auto-detected if omitted)
- `--output-dir PATH` - Output directory (default: `diagnostics/`)
- `--seasonal-period N` - Seasonal period (auto-detected if omitted)

`report.py` accepts:
- `--output-dir PATH` - Directory holding `diagnostics.json` and `plots/`
- `--output-file PATH` - PDF path (default: `<output-dir>/report.pdf`)
- `--source PATH` - Input file, printed on the cover page
- `--value-col NAME` - Series name, printed on the cover page

## Output Files

```
results/
├── report.pdf             # ← the deliverable: full analysis + every measure explained
├── diagnostics.json       # All test results and statistics
├── summary.txt            # Human-readable findings
├── diagnostics_state.json # Internal state for plot synchronization
└── plots/
    ├── timeseries.png
    ├── histogram.png
    ├── rolling_stats.png
    ├── box_by_dayofweek.png  # By day of week (if applicable)
    ├── box_by_month.png      # By month (if applicable)
    ├── box_by_quarter.png    # By quarter (if applicable)
    ├── acf_pacf.png
    ├── decomposition.png
    └── lag_scatter.png
```

## References

See `references/interpretation.md` for:
- Statistical test thresholds and interpretation
- Seasonal period guidelines by data frequency
- Transform recommendations

## Dependencies

`pandas`, `numpy`, `matplotlib`, `statsmodels`, `scipy`

The PDF is written with matplotlib's own `PdfPages` backend, so no PDF
library is needed on top of what the plots already require.