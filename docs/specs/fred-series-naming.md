# Spec — FRED series match their column names

Wave 2, item O3 (`docs/plans/code-smells-wave-2.md`). Plan:
`docs/plans/output-sensitive-fixes.md`.

**Decision (2026-10-27): mixed.** `dxy` is renamed `usd_broad_index` and keeps
`DTWEXBGS`; `gdp_yoy` keeps its name and switches to `A191RO1Q156NBEA`.

## Problem

Two macro columns say something other than what they hold:

| Column | FRED series | What it is |
|---|---|---|
| `gdp_yoy` | `A191RL1Q225SBEA` | Real GDP, percent change from the **previous quarter, annualized** |
| `dxy` | `DTWEXBGS` | Nominal **broad** trade-weighted dollar index, January 2006 = 100 |

A reader, or a model card, takes `gdp_yoy` as year-over-year growth and `dxy`
as the ICE dollar index (six currencies, euro-heavy). Neither is true.

## Evidence

Measured 2026-10-27 from `data/processed/macro_q.parquet` (81 quarters).

- `gdp_yoy` reads **−28.0** for 2020 Q2 and **+34.9** for 2020 Q3, the
  annualized quarter-over-quarter figures. Compounding the stored rates over
  four quarters gives the year-over-year growth: **−7.4** and **−1.4**. Stored
  series: std **5.54**, range −28.0 to 34.9; the compounded year-over-year
  series: std 2.28, range −7.4 to 12.6.
- `dxy` starts at **98.2** (2006-06-30) and ends at **120.9** (2026-06-30),
  mean 106.6, range 86.5–129.3, consistent with an index based at 100 in
  January 2006, which is how FRED documents `DTWEXBGS`.
- The ICE DXY itself is not on FRED (licensed).
- Both names appear in the schema, the column snapshots, the FRED test, the
  feature-service test, NB01 (19 references), all **16** feature datasets in
  `data/features/`, and the master plan (D13, macro list, E.3).
- `cpi_yoy` is correct: it requests FRED's `pc1` (year-over-year percent)
  units.

## Options

**A. Keep the series, rename the columns.** `gdp_yoy` → `gdp_qoq_saar`,
`dxy` → `usd_broad_index`.

- Values unchanged; only names move.
- Touches the schema, both column snapshots, two tests, NB01's text and
  headers, the feature datasets' column names, and the master plan.
- Reruns: NB00's writer and NB01 for the renamed outputs. No re-ingest of
  values is needed, though rerunning NB00 is the simplest way to rewrite the
  stored files.

**B. Keep the names, switch the series.** `gdp_yoy` → `A191RO1Q156NBEA` (real
GDP, percent change from one year ago); `dxy` → `DTWEXAFEGS` (dollar against
advanced foreign economies, the nearest FRED match to the ICE index's
composition).

- Values change: year-over-year GDP is smoother (std about 2.3 instead of
  5.5, from the compounding above), and the advanced-economy index is closer
  to the ICE DXY in composition but still is not it, so `dxy` stays an
  approximate name.
- Touches the series map and the master plan; the snapshots stay.
- Reruns: re-ingest macro (every panel), then NB00 onward. NB01's macro
  correlations and the macro feature group change.

## Recommendation

**A** for `dxy`: no FRED series is the ICE index, so a name that says
"broad index" is the only accurate one. Either for `gdp_yoy`; B gives the
quantity the name promises, and year-over-year growth matches how the
financial targets are compared (`cpi_yoy` is already year-over-year).

## Acceptance criteria

- Every macro column's name states its quantity and unit, checked against the
  FRED series notes.
- The column snapshots, the schema, NB01 and the master plan use the same
  names.
- For B, the stored 2020 Q2 GDP value is year-over-year (near −7.4, subject to
  BEA revisions), not −28.0.

## Out of scope

- ALFRED point-in-time vintages (master plan D13, E.3).
- The other macro series.
