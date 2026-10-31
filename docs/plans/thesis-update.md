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
| `target_by_segment_boxplots` | `objetivo_por_segmento<suffix>.png` |
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
Confirmed on the 2026-10-30 round.

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

Freeze (step 1, 2026-10-30): `data/backups/thesis_2026-10-30/` (processed,
features, reports; 96 files). Window 2006-06-30 → 2026-06-30; ingest
2026-10-28, HON re-ingested 2026-10-30; `CFO_Copilot` at `f37208f` plus
uncommitted O1–O4 and H1. W&B runs: NB00 `5qo4anfj`; NB01 `fk4v1k3k` →
`160gjfh2` (2026-10-30 18:13–18:19); NB01b `l3gnhk3v`, `q2pf4aoq`,
`2tbrq4ec`, `4fqj30o4`.

Decision-table values of this freeze, for the thesis table: weak groups —
revenue none, operating income F and C, EBITDA none (C on the floor), FCF F
and C; Kruskal–Wallis p — operating income 0.636, EBITDA 0.296, FCF 0.849
(revenue unchanged from 2026-10-28); forecastable 52, 51, 54, 57 of 60. NB01b
scores 58 companies for the revenue-scaled targets (HON and OXY drop out,
see the HON plan).

Status: steps 1–7 done 2026-10-30; nothing committed in either repo. Summary
for the author: `cfo-copilot-thesis/RESUMEN_ACTUALIZACION_2026-10-30.md`.

Edits made in `main.tex`. Line numbers are approximate, taken after the edit.

| Location | Old → new |
|---|---|
| Problemas encontrados (≈L620) | two new items: dividend-yield window, HON separation and reverse split |
| Results intro (≈L792) | run date 12 → 30 Oct 2026 |
| NB00 missing values (≈L800) | three → four withheld quarters, adding HON 2025-Q3 |
| NB01 intro (≈L825) | HON added to the companies with 80 quarters |
| Audit, missing (≈L828) | 0,2 % → 0,3 % (13 of 4 860); opex 5,2 → 5,3 % |
| Register paragraph (≈L838) | 817 → 796; opex 157 → 155; dividend yield now balanced (15 up, 14 down) |
| Top-series paragraph (≈L847) | top four are now GOOGL EPS, HON EPS, COST dividend yield, SLB net margin; OXY dividend yield is sixth |
| `tab:objetivo` | available share 93,4/94,5/94,4/90,8/94,5 → 93,3/94,4/94,3/90,7/94,4; FCF h4 kurtosis 203,7 → 203,6 |
| Macro by sector (≈L977) | GDP added (Energy 0,51 revenue, 0,46 OI/EBITDA, 0,39 FCF; Industrials 0,28); Healthcare "least sensitive" |
| `tab:diferenciacion` | OI 8/40/12 → 8/41/11; EBITDA 8/43/9 → 8/42/10 |
| `tab:export` | every count, from the frozen `export_summary` |
| FE text | FCF h1 ρ −0,28 → −0,29 |
| `tab:grupos-res` | seven values; OI F 0,004 bold; EBITDA C 0,005 not bold; margins order "(0,10 y 0,09)" |
| NB01b intro and caption | 59 → 58 companies (HON and OXY); 15 → 16 % |
| `tab:transformaciones` and text | every value from the frozen `transform_summary` |
| `tab:decisiones` | EBITDA C → Ninguno; Kruskal–Wallis 0,726 / 0,636 / 0,296 / 0,849 |
| Pendientes and the limits paragraph | HON withheld; four limits instead of two; hypothesis drops "solo el calendario en el EBITDA" |
| Data dictionary | `gdp\_yoy` series A191RO1Q156NBEA; `dxy` → `usd\_broad\_index` |

Checked against the freeze and left unchanged:

- the correlation paragraph (recomputed: 0,71, −0,30, −0,53; maxima 0,30, 0,20, 0,08);
- seasonal strength;
- the h1 and h4 rankings;
- provenance 77/12/11 %;
- the flag table;
- Ford's seven unexplained cells.

Figures: all 42 in `figuras/eda/` were copied from this round's runs by the
step 5 mapping, and 39 changed. The mapping held except for one key: the
segment figure is logged as `target_by_segment_boxplots`. Compile: 93 pages,
no undefined references; the three overfull boxes are in the bibliography.

Candidates listed before the search, kept for the record:

| Thesis location | Old | New or change |
|---|---|---|
| Data dictionary, `gdp\_yoy` | "anualizado (A191RL1Q225SBEA)" | year-over-year growth, `A191RO1Q156NBEA` |
| Data dictionary, `dxy` | `dxy` | `usd\_broad\_index` (same series, DTWEXBGS) |
| Atributos del modelo (macro list) | `gdp\_yoy` … | check the column list still matches the feature files |
| Registro de atípicos, result | 817 entries; per-column counts | 807; recount per column (revenue 5, operating income 43, EBITDA 42, FCF 3); dividend-yield entries of 2006-09-30 gone |
| Correlaciones, result | dollar and macro correlations, "como máximo 0,30 … 0,08" | recompute from the new run (GDP moved most) |
| Sensibilidad macro por sector | text and figures | GDP correlations rose (revenue, Energy 0.08 → 0.51); two FCF signs flipped |
| Diagnóstico temporal / decision table | Ljung–Box p-values, if quoted | decisions unchanged (52, 51, 54, 57 of 60); p-values of the 46 d = 2 series changed |
| NB01b table and sector exceptions | shares and λ quoted in the text | recheck against the 2026-10-30 NB01b tables; decisions unchanged, 59 companies for the revenue-scaled targets |
| Decision table (`tab:decisiones`) | EBITDA "C"; Kruskal–Wallis 0,638 / 0,294 / 0,861 | EBITDA none; 0,636 / 0,296 / 0,849 |
| Scraper problems / Mercado y macro | dividend yield description | the quarter-end fix: no false zero in 2006-Q3; missing, not zero, without a price |
| Limitations | — | HON 2025-Q3 (withheld or accepted) and the data-freeze rule |
| Figures | `correlacion_spearman`, `sensibilidad_macro_sector*`, `registro_atipicos_*`, `transformaciones_*` | refresh per step 5 |
