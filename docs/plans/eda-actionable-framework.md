# Actionable EDA and feature framework — Implementation Plan

> **No commit steps.** CLAUDE.md forbids `git commit`/`push`/PR without explicit
> permission for that action. Each task ends at green checks and stages nothing.

**Spec:** [`docs/specs/eda-actionable-framework.md`](../specs/eda-actionable-framework.md)
(F1–F17, B1–B12, D1–D8). **Builds on:**
[`eda-feature-engineering.md`](eda-feature-engineering.md) (Tasks 0–8 built,
Task 10 built; its Task 9 is superseded by Task 1 here).

**Goal:** NB01 starts with three automated profiles and ends with a decision
table per target variable; the user picks one of five variables to forecast.

**Already in place:** ydata-profiling 4.18.4, seaborn 0.13.2, `setuptools<81`
in the research group; matplotlib 3.10; `WandbRun.log_html`; W&B run names
timestamped and grouped.

## Global Constraints

- Classes with injected collaborators; pure helpers stay module functions
  (`PLR6301`); the notebook defines no `def`/`class` (R10, F17).
- mypy strict; `uv run poe check` green at the end of every task; no `# noqa`,
  `# type: ignore`, `# pyright: ignore`.
- Configuration types are frozen Pydantic with today's value as default;
  exceptions are `@dataclass` with fields and `__str__`.
- Tests before implementation; every spec check B1–B12 maps to a test or a
  named manual step.
- Do not run NB01 or write under `data/`: executing the notebook is the user's.

## File Structure

| File | Change |
|---|---|
| `config/ingestion_defects.yaml` | new: excluded companies and blocked targets, each with its spec |
| `src/app/data/report_store.py` | new: `ReportStore` |
| `src/app/data/ingestion_defects.py` | new: `IngestionDefects` model + loader |
| `src/app/data/feature_store.py` | paths per variable and horizon |
| `src/app/services/features/transforms.py` | `TargetVariable`, revenue-scaled change, arm per variable |
| `src/app/services/features/builder.py` | growth groups from the variable's own transform |
| `src/app/services/diagnostics/` | `AutoProfiler`, `DataDictionary`, `OutlierRegister`, `CorrelationAnalyzer`, `SegmentProfiler`, `FeatureAuditor`, `DecisionTableBuilder` |
| `src/app/injections/production.py` | providers for the above |
| `.gitignore` | `data/reports/` |
| `.pre-commit-config.yaml` | ydata-profiling and seaborn in nbqa-pylint deps |
| `src/app/playground/01_eda_feature_engineering.ipynb` | rebuilt as § 0–9 |

Order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11. Task 1 first because the
automated profile needs nothing else.

---

### Task 1: Automated profile (§ 0; F4 a–b, F1 skeleton)

**Interfaces**
- `ReportStore(directory).path_for(name) -> Path`: creates the directory, returns `directory / name`. Container `report_store` at `DATA_DIRECTORY / "reports"`; `data/reports/` git-ignored.
- `ProfileSettings` (frozen): `interactions: bool = False`.
- `AutoProfiler(store, settings)`:
  - `profile(frame, *, title, name) -> Path` — one ydata report written through the store;
  - `compare(before, after, *, title, name) -> Path` — ydata's comparison of two frames.
- Container `auto_profiler`.

**Steps**
- [x] Tests: `path_for` creates the directory; `profile` writes an HTML file for a small frame and it is under 5 MB; `compare` writes one file; settings reject unknown keys.
- [x] Implement; ydata calls go behind a Protocol + `cast` like statsmodels'.
- [x] Notebook: rebuild headings to § 0–9 (F1) with a question/answer markdown frame each; § 0 pools the panels (date dropped), writes reports (a) and (b) (split at 2020-01-01), logs each in its own run (`nb01-autoeda-panel`, `nb01-autoeda-drift`) with `log_html`.
- [x] `.gitignore`; `uv run poe check`. nbqa-pylint deps deferred to the first task whose notebook cells import seaborn (§ 0 only calls the service).

### Task 2: Selectable target variable and blocked choices (F2, F16)

**Interfaces**
- `TargetVariable` (`StrEnum`): `REVENUE`, `GROSS_PROFIT`, `OPEX`, `EBITDA`, `FREE_CASH_FLOW`, values the panel column names.
- `config/ingestion_defects.yaml`:
  ```yaml
  excluded_companies:
    COP: docs/specs/ingestion-defects-cop-ge.md
  blocked_targets:
    opex_usd_m: docs/specs/ingestion-defects-cop-ge.md
  ```
- `IngestionDefects` (frozen) + `load_ingestion_defects(path)`; container Singleton `ingestion_defects`.
- `BlockedTargetError(variable, spec)`, `IngestionDefects.require_selectable(variable)`, `IngestionDefects.without_excluded(panels)`.

**Steps**
- [x] Tests: opex raises naming the spec; revenue passes; COP removed from panels; unknown keys refused; removing a YAML entry lifts it.
- [x] Implement; notebook cell 1 sets `TARGET_VARIABLE = TargetVariable.REVENUE` and replaces `EXCLUDED = ("COP",)` with the registry.
- [x] `uv run poe check`.

### Task 3: Revenue-scaled change and the arm per variable (F3; B4)

**Interfaces**
- `revenue_scaled_yoy_change(values, revenue) -> pd.Series`: `(values − values.shift(4)) / revenue.rolling(4).sum()`; pure.
- `TargetArm.REVENUE_SCALED_YOY`; `TargetTransformer.make(values, *, revenue=None)` and `reconstruct(values, prediction, *, revenue=None)`; the scaled arm without `revenue` raises a typed error.
- `arms_for(variable) -> tuple[TargetArm, ...]`: revenue → the three log arms; others → the scaled arm.
- `FeatureBuilder`: L and R from the variable's transform (`yoy_log_growth` for revenue, the scaled change otherwise).

**Steps**
- [x] Tests: exact round trip of the scaled arm for h = 1…4 on a series crossing zero (B4); scaled arm without revenue raises; `arms_for`; builder growth features for EBITDA equal the scaled change; revenue features unchanged (existing tests stay green).
- [x] Implement; `uv run poe check`. Added beyond the plan: `FeatureService.assemble` refuses an arm foreign to the target (`UnsupportedArmError`), so log growth on EBITDA fails clearly instead of mid-run.

### Task 4: Exports and runs per variable (F15; B11)

- [x] Tests: `FeatureStore.path_for(variable, horizon)` gives `features_{variable}_h{h}.parquet`; two variables write two files; read back per variable.
- [x] Implement; notebook export and run names include the variable. Also: `default_arm(variable)` names the exported arm (seasonal-naive residual for revenue, revenue-scaled otherwise), and Setup builds `feature_service` for `TARGET_VARIABLE` (it defaulted to revenue).
- [x] `uv run poe check`.

### Task 5: Audit — data dictionary and outlier register (§ 1; F5, F6, D9, D10; B5, B6)

**Interfaces**
- `OutlierSettings` (frozen): `z_threshold = 10.0`, `hampel_window = 8`, `hampel_mad_floor = 0.25` (fraction of the company's overall MAD), `min_changes = 8`, `positive_columns` (revenue, stock price, market cap), `ratio_columns` (margins, dividend yield, P/E, EPS).
- `OutlierRegister(settings).register(panels, columns) -> pd.DataFrame` with `ticker, date, column, value, change, robust_z, hampel_z, direction`, sorted by |robust_z| descending; size-relative change per F5.
- `DataDictionary(settings).describe(pooled, columns, *, register) -> pd.DataFrame` with `column, dtype, missing_share, unique, min, max, invalid_sign, register_count`.
- `SeriesDiagnostician` fills isolated single interior gaps before diagnosing (`DiagnosticsSettings.max_interpolated_gap = 1`, 0 disables); `SeriesDiagnostics.interpolated` counts them.
- Both behind `DiagnosticsService`; register written as CSV through `ReportStore.write_csv`, both logged as W&B tables.

**Steps**
- [x] Tests: B5 (jump, negative revenue, smooth and seasonal series clean, ranking, finite Hampel on a flat window); B6; interpolation fills one-quarter gaps only and counts them.
- [x] Implement; notebook § 1 (top 30 of the register, counts per column and company, the dictionary; CSV and W&B); update NB01's A2 counts to the interpolated truth; `uv run poe check`.

*As built:* when over half a company's changes are identical the MAD collapses to ~0, so the robust scale falls back to the mean absolute deviation (Iglewicz & Hoaglin); only a series with no spread at all is left unjudged. Real panel: 1,063 entries (1.48%).

### Task 6: Target section (§ 2; F7)

**Interfaces**
- `FeatureService.target_frame(panels, *, variable, horizons) -> pd.DataFrame`: long table `ticker, date, arm, horizon, y` using `arms_for`.
- Extremes: `OutlierRegister` applied to `y` per ticker.

**Steps**
- [x] Tests: one row per company-quarter per arm per horizon; `y` equals `TargetTransformer.make` for a sample; known share = labelled rows.
- [x] Implement; notebook § 2: seaborn histogram+KDE per arm × horizon (the article's Step 2 figure), skewness/kurtosis table, extremes table; `uv run poe check`.

*As built:* `FeatureService.target_frame(panels, *, horizons)` (the builder already knows the variable); extremes by `OutlierRegister.register_target`, robust z on `y` itself per company, arm and horizon. Real revenue panel: 57,348 target rows, 301 extremes, IBM 2019–2021 on top (Kyndryl spin-off, not in `structural_breaks.yaml`). seaborn added to nbqa-pylint.

### Task 7: Numeric, categorical and correlations (§ 3, § 4, § 5; F8, F9, F12; B7)

**Interfaces**
- `yoy_changes(panel, columns) -> pd.DataFrame`: log change for columns positive throughout, revenue-scaled change otherwise; pure.
- `CorrelationSettings` (frozen): `method: Literal["spearman"] = "spearman"`, `redundancy_threshold: float = 0.85`.
- `CorrelationAnalyzer(settings)`: `matrix(changes) -> pd.DataFrame`, `redundant_pairs(matrix) -> pd.DataFrame` (`left, right, rho`).

**Steps**
- [x] Tests: planted pair with ρ > 0.85 listed, one below not (B7); `yoy_changes` picks the family by sign.
- [x] Implement; notebook § 3 (histogram+KDE and box plots of changes, skew/kurtosis table — the article's Step 3 figure), § 4 (count plots per sector and regime; sectors under 3 companies flagged), § 5 (annotated `coolwarm` heatmap centred at 0 — the article's Step 5 figure — and the redundancy list); `uv run poe check`.

*As built:*
- Column families moved to the schema (`POSITIVE_COLUMNS`, `RATIO_COLUMNS`); the register and `yoy_changes` share them. Macro columns change by their plain difference.
- `pooled_yoy_changes` is a module function (it holds no configuration); `CorrelationAnalyzer` has its own container provider instead of more `DiagnosticsService` pass-throughs.
- The series-diagnostics cell moved into Setup: § 4 counts the regimes and § 6 compares them.
- **`EdaFigures`** (decided 2026-09-30): every notebook figure is built by a tested service method (register counts, top series, target grid, change distributions and box plots, categories, correlation and sector heatmaps, seasonal strength), styled locally, never globally. The notebook's code fell from 414 to 282 lines, back under pylint's module limit. Box plots use matplotlib directly (seaborn 0.13 passes matplotlib 3.10 a deprecated argument) with one panel per column, since EPS is in dollars and the rest in shares of revenue.
- Real panel: 5 redundant pairs (stock price–market cap 0.97, net income–net margin 0.91, operating income–operating margin 0.88, net income–EPS 0.86, operating income–EBITDA 0.86); no sector below three companies (Materials, Utilities at three).

### Task 8: Segments and time (§ 6, § 7; F10, F11; B8)

**Interfaces**
- `SegmentProfiler`:
  - `by_segment(target_frame, segments) -> pd.DataFrame`: per segment and value, median, IQR, count;
  - `seasonal_profile(target_frame, regimes) -> pd.DataFrame`: mean target by calendar quarter per regime;
  - `median_timeline(target_frame) -> pd.DataFrame`: panel-median target per quarter.
- Period segment from NB00's `covid` flag: before, flagged, after (D7).

**Steps**
- [x] Tests: one row per segment value for sector, regime and period (B8); the seasonal profile has four quarters per regime.
- [x] Implement; notebook § 6 (box plots per segment — the article's Step 6 figure — and the table), § 7 (existing diagnostics + seasonal profile line plot + timeline with covid and break quarters shaded); `uv run poe check`.

*As built:* `segment_frame`, `seasonal_profile` and `median_timeline` are module functions (no configuration); `SegmentProfiler.by_segment` holds the spread quartiles. Figures in `EdaFigures` (segment box plots drawn with matplotlib for the same seaborn deprecation). Real revenue panel, default arm, h = 1: covid-period median +0.044 against ~0 elsewhere; the 2008–09 swing (−0.10 to +0.095) carries no flag, a decision-table candidate.

### Task 9: Features — build, audit, export (§ 8; F13, F4 c; B9)

**Interfaces**
- `AuditSettings` (frozen): `redundancy_threshold: float = 0.85`, `seed: int = 42`.
- `FeatureAuditor(settings).audit(dataset, *, groups) -> FeatureAudit` with per-feature `missing_share, spearman, mutual_information, group`, the redundant pairs, and a per-group summary; mutual information from scikit-learn's `mutual_info_regression` over labelled rows.

**Steps**
- [x] Tests: a planted informative feature outranks planted noise (B9); a fully missing feature reports share 1.0; per-group summary has one row per group present.
- [x] Implement; notebook § 8: build and export per variable (Task 4), auditor tables, ranked mutual-information bar chart, report (c) on the exported dataset in `nb01-autoeda-features-{variable}`; `uv run poe check`.

**As built**
- `AuditSettings` holds only `seed`; redundancy reuses the injected `CorrelationAnalyzer` (Task 7), so the threshold lives in one place. Container: `feature_auditor`.
- `feature_groups_by_column()` in the builder maps every emitted column to its group from the same name constants the builder uses; a test pins the two together.
- Categorical and boolean features are scored as discrete mutual information, with no Spearman; constant features score NaN.
- `EdaFigures.feature_ranking`; the audit tables, figures and report (c) share one run, `nb01-autoeda-features-{variable}`. The export's `feature_columns` table was dropped as redundant with `feature_scores` (notebook line budget).
- Dry run (revenue): `growth_yoy_lag1` leads (mutual information 0.13 at h1, 0.39 at h4; Spearman −0.32 and −0.60, mean reversion). Macro mutual information is inflated, since each macro value is shared by every company in a quarter and acts as a date label; NB02 ablation decides.

### Task 10: Summary and decision table (§ 9; F14; B10)

**Interfaces**
- `DecisionSettings` (frozen): `mutual_information_floor: float = 0.005` (D3), `significance: float = 0.05` (D4), `forecastable_share: float = 0.5` (D5).
- `DecisionRow` (frozen): `decision, finding, evidence, action, applies_to`.
- `DecisionTableBuilder(settings).build(*, variable, defects, register, audit, target_frame, regimes) -> tuple[DecisionRow, ...]`, one row per decision type:
  - transform — from `arms_for`;
  - exclusions — `IngestionDefects` plus sign-rule register entries on the target;
  - feature groups — groups whose best mutual information is below the floor;
  - pooled or segmented — Kruskal-Wallis across regimes (`scipy.stats.kruskal`);
  - forecastable — share of companies with Ljung-Box p < 0.05 on the target.

**Steps**
- [x] Tests: five rows per variable (B10); each rule on a planted case both ways (a noise group flagged, an informative one not; differing regimes → segmented; white-noise target → not forecastable).
- [x] Implement; notebook § 9: markdown summary in the article's Step 8 six parts, the decision table rendered and logged; `uv run poe check`.

**As built**
- `DecisionTableBuilder(settings).build(DecisionInputs)`: the six inputs travel as one `DecisionInputs` NamedTuple. It reads the excluded companies (not the whole `IngestionDefects`), the audit's group summary, the h1 dataset (Kruskal-Wallis over `seasonality_regime`) and per-company Ljung-Box p-values. Container: `decision_table_builder`.
- An all-missing group (NaN score) counts as below the floor. A single-arm variable's transform row does not ask for an arm comparison.
- `TARGETS` always includes the chosen variable, so the forecastable rule has p-values for gross profit too.
- Dry run (h1): revenue: no drop candidate (F scores 0.009); pooled (Kruskal-Wallis p = 0.83); forecastable 53/59. EBITDA: F, C; pooled (p = 0.078); 51/58. FCF: C, F, XD; pooled (p = 0.13); 56/59.
- D3 lowered to 0.005 and D4, D5 confirmed by the user (2026-10-01).

### Task 11: Verify and hand over

- [x] B12: `uv run poe check` green; no `def`/`class` in NB01.
- [x] Mark the parent plan's Task 9 superseded by Task 1 here; point the parent spec's R12 to this spec's F4.
- [x] Summarize files, B1–B12 status (B2, B3-run, B10-run need the user's NB01 run), propose a commit. Stage nothing.

## Self-review

**Spec coverage.** F1 → Tasks 1 (skeleton) and 5–10. F2, F16 → Task 2. F3 →
Task 3. F4 → Tasks 1 and 9. F5, F6 → Task 5. F7 → Task 6. F8, F9, F12 → Task 7.
F10, F11 → Task 8. F13 → Task 9. F14 → Task 10. F15 → Task 4. F17 → every task.

**Risks.**
- ydata's comparison report needs both frames to share columns; the drift
  split keeps one schema by construction.
- Mutual information is estimated with noise; D3's floor (0.005) was set from
  the dry run's ranking, not tuned; revisit it if NB02's ablation disagrees.
- `revenue.rolling(4).sum()` is NaN for each company's first three quarters, so
  the scaled target starts a year later than the log arms; the known-share
  column of F7 makes that visible.
