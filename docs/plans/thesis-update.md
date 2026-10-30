# Plan — Update the thesis from a project run (reusable)

Brings `C:\Users\leona\source\repos\cfo-copilot-thesis` (`main.tex`,
`figuras/`, the `RESUMEN_*.md` notes) in line with a finished run of the
project. Run it once per **data freeze**, never after each re-ingest: the
thesis cites one dataset version, and SEC filings keep restating recent
quarters (the 2026-10 Q3 10-Qs changed 14 companies' 2025-Q3 rows).

The first part is the procedure; the last section is a log of rounds, newest
first. Add a round there instead of rewriting the procedure.

## 0. Preconditions

- The notebooks of this round (NB00, NB01, NB01b, later NB02+) were run by the
  author with a restarted kernel and logged to W&B.
- `uv run poe check` is green in `CFO_Copilot`.
- `git status` in the thesis repo is read first. Uncommitted edits there are
  the author's: edit around them, never overwrite or revert them.
- Nothing is committed or pushed in either repo without explicit permission.

## 1. Freeze the dataset

1. Copy `data/processed/`, `data/features/` and `data/reports/` to
   `data/backups/thesis_<YYYY-MM-DD>/` (git-ignored).
2. Record in the round log: the window (`--start`/`--end`), the ingest date,
   the `CFO_Copilot` commit (or "uncommitted"), and the W&B run IDs used.
3. From here on the thesis numbers come only from this copy and these runs.

## 2. Build the change ledger

Compare the frozen outputs with the previous round's frozen copy (or the
copy the last round names). For each quantity the thesis cites, record
old value, new value and cause, in the round log:

| Output | Thesis use |
|---|---|
| `panel_long.parquet` shape, structural-break rows | NB00 section, data dictionary |
| `data/reports/nb01_outlier_register.csv` | register total and per-column counts, top series |
| NB01 decision tables (one per target) | "Decisiones para la etapa de modelado" table |
| NB01 diagnostics (Ljung–Box, seasonality, d) | temporal-behaviour results |
| NB01 correlations, macro sensitivity, feature-group ablation scores | correlations and Feature Engineering results |
| `data/reports/nb01b_transform_comparison.csv` | NB01b table and sector exceptions |
| `src/app/data/sources/fred/source.py`, `data/schema.py` | data dictionary (series IDs, column names) |
| `config/structural_breaks.yaml`, `config/companies.yaml` (withheld quarters) | breaks list, scraper problems, missing-value reasons |

Only a quantity that moved, or a definition that changed, becomes an edit.

## 3. Locate every citation of a changed quantity

For each ledger row, search `main.tex` for the **old** value in the thesis's
formats: decimal comma (`0{,}05`, `1,108`), thin-space thousands (`99\,031`),
percent (`25\,\%`), and the column name with escaped underscores
(`gdp\_yoy`). Also search the conclusions, the appendix and the figure
captions; a number often appears in more than one section. List each hit
(section and line) in the round log before editing.

## 4. Edit `main.tex`

- Spanish, the thesis's existing voice and terms (trimestre `2026-Q2`,
  variable objetivo, quiebre estructural, registro de atípicos).
- One targeted replacement per hit; no rewrites of untouched paragraphs.
- A changed definition (a FRED series, a rule in ingestion) is updated where it
  is defined (method or data dictionary) and wherever a result depends on it.
- A new limitation or accepted defect goes to "Puntos fuertes y limitaciones"
  and, if it changes a modelling decision, to "Decisiones para la etapa de
  modelado".
- Citations through `\parencite{key}`; a new source is added to
  `references.bib`, never inline.

## 5. Refresh the figures

The figures are W&B images logged by the notebooks, stored locally under
`wandb/run-*/files/media/images/<key>_<step>_<hash>.png`. Each run's
`files/config.yaml` holds `target_variable`; take the latest run per
(key, target) from this round's run IDs.

| W&B key | Thesis file (`figuras/eda/`) |
|---|---|
| `target_distribution` | `objetivo_distribucion<suffix>.png` |
| `target_by_segment` | `objetivo_por_segmento<suffix>.png` |
| `seasonal_strength` | `fuerza_estacional<suffix>.png` |
| `seasonal_profile` | `perfil_estacional<suffix>.png` |
| `median_timeline` | `mediana_temporal<suffix>.png` |
| `feature_ranking_h1`, `feature_ranking_h4` | `ranking_features_h1<suffix>.png`, `ranking_features_h4<suffix>.png` |
| `macro_sensitivity_heatmap` | `sensibilidad_macro_sector<suffix>.png` |
| `change_distributions`, `change_boxplots` | `cambios_interanuales_hist.png`, `cambios_interanuales_box.png` |
| `correlation_heatmap` | `correlacion_spearman.png` |
| `register_counts`, `register_top_series` | `registro_atipicos_conteo.png`, `registro_atipicos_series.png` |
| `categories` | `sectores_regimenes.png` |
| `transform_comparison_boxplots` (NB01b) | `transformaciones_{ingresos,operating_income,ebitda,fcf}.png` |

`<suffix>`: none for revenue, `_operating_income`, `_ebitda`, `_fcf`.
The mapping is inferred from the names; on the first round that uses it, open
each pair once and correct the table if a figure does not match.

Replace only figures whose underlying output changed (step 2), keeping
the file names, so `\includegraphics` lines do not move.

## 6. Compile and check

```bash
cd /c/Users/leona/source/repos/cfo-copilot-thesis
latexmk -pdf -interaction=nonstopmode -file-line-error main.tex
```

- No `undefined` references or citations in `main.log`; no overfull box new
  to this round in a table that was edited.
- Page count and table/figure lists (`main.lof`, `main.lot`) as expected.
- Search `main.tex` once more for every old value of the ledger: none left,
  unless the text cites it on purpose as "before" (as the register paragraph
  does for corrected defects).

## 7. Write the round summary

A `RESUMEN_<topic>.md` in the thesis repo, in Spanish and in the style of
`RESUMEN_CORRECCIONES_DATOS_Y_EDA.md`: what changed in the data, why, what it
implies for the modelling, and what changed in `main.tex`. Then summarize the
edited files to the author and wait; the author commits.

## Round log

### 2026-10-30 — Wave 2 O1–O4 and the Q3 2026 filings

Inputs: re-ingest of 2026-10-28 (window 2006-06-30 → 2026-06-30) and the
author's NB00, NB01 and NB01b runs of 2026-10-28; ledger already measured in
`docs/plans/output-sensitive-fixes.md` ("Verification record (2026-10-28)").
H1 of `docs/specs/hon-separation-and-reverse-split.md` was applied on
2026-10-30 (HON 2025-Q3 withheld, HON re-ingested); the notebooks must be
rerun **before** step 1, and their runs replace the 2026-10-28 ones. H2 is
deferred: no model feature uses EPS, market cap or P/E, so it goes to the
limitations.

Status: not started. Known candidates for step 3 (to be confirmed by the
search, not edited blindly):

| Thesis location | Old | New or change |
|---|---|---|
| Data dictionary, `gdp\_yoy` | "anualizado (A191RL1Q225SBEA)" | year-over-year growth, `A191RO1Q156NBEA` |
| Data dictionary, `dxy` | `dxy` | `usd\_broad\_index` (same series, DTWEXBGS) |
| Atributos del modelo (macro list) | `gdp\_yoy` … | check the column list still matches the feature files |
| Registro de atípicos, result | 817 entries; per-column counts | 807; recount per column (revenue 5, operating income 43, EBITDA 42, FCF 3); dividend-yield entries of 2006-09-30 gone |
| Correlaciones, result | dollar and macro correlations, "como máximo 0,30 … 0,08" | recompute from the new run (GDP moved most) |
| Sensibilidad macro por sector | text and figures | GDP correlations rose (revenue, Energy 0.08 → 0.51); two FCF signs flipped |
| Diagnóstico temporal / decision table | Ljung–Box p-values, if quoted | decisions unchanged (52, 51, 54, 57 of 60); p-values of the 46 d = 2 series changed |
| NB01b table and sector λ | Industrials λ 1,108 | 1,100 (HON-driven; changes again if H1 is applied) |
| Scraper problems / Mercado y macro | dividend yield description | the quarter-end fix: no false zero in 2006-Q3; missing, not zero, without a price |
| Limitations | — | HON 2025-Q3 (withheld or accepted) and the data-freeze rule |
| Figures | `correlacion_spearman`, `sensibilidad_macro_sector*`, `registro_atipicos_*`, `transformaciones_*` | refresh per step 5 |
