# Code smells wave 2

Second remediation wave, from a fresh code-smell scan of the whole codebase on
2026-10-26. Every high-severity finding was checked against the code before it
was listed. Items already tracked elsewhere stay there:

- [output-sensitive-catalog.md](output-sensitive-catalog.md): #8, #9, #16b,
  #17, #25, #26 and #28;
- [template-scaffold-replacement.md](template-scaffold-replacement.md): the
  deferred template scaffold.

## Global constraints

Same as [wave 1](code-smells-remediation.md):

- Stored parquets stay byte-identical, and no notebook is rerun.
- Phase 3 items change outputs, so they get a spec with measured evidence and
  stop there; a fix needs approval and the reruns it names.
- Each item: search callers (notebooks included), add a characterization test
  if it touches a computation, change, run `uv run poe check`, record the
  status here.
- An item I disagree with moves to the catalog instead of being forced through.

## Phase 1: Test integrity

### T1 yfinance tests call Yahoo live
- **Smell:** Mystery Guest (hidden network dependency).
- **Where:** `tests/data/sources/test_yfinance_source.py` (five
  `@pytest.mark.vcr` tests), the end-to-end test in `tests/data/test_pipeline.py`.
- **Fix:** replace the Yahoo client with a fake patched at
  `app.data.sources.yfinance_source.source.yf.Ticker`; block the network in
  pytest so an unrecorded call fails.
- **Tests:** the suite passes offline.
- **Status:** done. A shared `FakeYahooTicker` in `tests/data/conftest.py`
  replaces the five live tests and feeds the end-to-end test; `--block-network`
  is on, with `127.0.0.1` allowed for the Windows asyncio self-pipe. It patches
  Python sockets only, so it cannot catch yfinance's curl-cffi transport; the
  fake is what keeps Yahoo out.
- **Rerun:** No.

### T2 The `--quiet` test cannot fail
- **Smell:** Vacuous assertion.
- **Where:** `tests/data/test_runner.py`.
- **Fix:** assert on a real stage name, present without `--quiet` and absent
  with it.
- **Status:** done. Asserts `fetching sources` is printed normally and not
  with `--quiet`.
- **Rerun:** No.

### T3 Tautological EPS test
- **Smell:** Fallacious test name.
- **Where:** `test_merge_panel_adjusts_eps_to_current_share_basis` in
  `tests/data/test_pipeline.py`.
- **Fix:** test what `merge_panel` actually does: pass the market source's
  splits to the SEC fetch.
- **Status:** done. Replaced by
  `test_merge_panel_hands_the_market_splits_to_the_sec_fetch`.
- **Rerun:** No.

### T4 Tests read the real FRED key
- **Smell:** Hidden dependency on `.env`.
- **Where:** `tests/data/sources/test_fred.py`, `tests/data/test_pipeline.py`.
- **Fix:** a `fred_source` fixture with a placeholder key.
- **Status:** done. `fred_source` in `tests/data/conftest.py` uses
  `test-key`; cassettes replay without a key.
- **Rerun:** No.

### T5 Shared random generator across tests
- **Smell:** Interacting tests.
- **Where:** `tests/services/diagnostics/test_series.py`.
- **Fix:** a fresh, seeded generator per test.
- **Status:** done. An `rng` fixture seeded with 0 per test.
- **Rerun:** No.

### T6 Duplicated test setup
- **Smell:** Duplicate Code.
- **Where:** inline `fake_fetch_concept` copies in the SEC tests; repeated
  `IngestionSources` construction in `tests/data/test_pipeline.py`.
- **Fix:** shared fixtures.
- **Status:** done. `serve_concepts` in `tests/data/conftest.py` replaces 14
  inline SEC fakes and returns the requested tags; `fake_sources` in
  `tests/data/test_pipeline.py` replaces 12 `IngestionSources` constructions,
  with variants built by `dataclasses.replace`.
- **Rerun:** No.

## Phase 2: Structure (output-neutral)

### S1 Declared-gap rule written twice
- **Smell:** Shotgun Surgery / Data Clumps.
- **Where:** `data/pipeline.py` (`merge_panel`), `data/missing.py`,
  `data/companies.py`.
- **Fix:** the company's panel metadata names its declared empty columns once;
  the pipeline and the missing-value ledger both read it.
- **Status:** done. `CompanyPanelMetadata.declared_empty_columns()` is the
  one rule; `merge_panel` blanks those columns and `missing_value_ledger(panel_long,
  registry)` explains them. The registry's three ticker-set accessors went with
  the old signature. The ledger over the stored `panel_long` is identical before
  and after (1,057 rows). NB00 changed in one code cell, not rerun.
- **Rerun:** No.

### S2 SEC-only XBRL modules outside their package
- **Smell:** Vendor names leaking out of the anti-corruption layer.
- **Where:** `data/xbrl.py`, `data/xbrl_facts.py`.
- **Fix:** move both into `data/sources/sec_edgar/`.
- **Status:** done. Both modules now live in `sources/sec_edgar/` (imported
  relatively), `test_xbrl.py` moved to `tests/data/sources/test_sec_edgar_xbrl.py`,
  and CLAUDE.md, AGENTS.md and the optimal-scaffold skill no longer list XBRL as
  shared.
- **Rerun:** No.

### S3 Processed-file layout declared twice
- **Smell:** Duplicate Code.
- **Where:** `settings.py` and `data/panel_store.py`.
- **Fix:** one owner of the file names.
- **Status:** done. Settings keeps only `PROCESSED_DIRECTORY`; the batch and
  single-ticker CLIs ask `container.panel_store().path_for(ticker)`, and NB00's
  writer cell asks the store for `panel_long_path` and `macro_q_path`. A test
  pins the three file names to the stored files.
- **Rerun:** No.

### S4 "Four quarters a year" in four places
- **Smell:** Duplicate rule.
- **Where:** `SEASONAL_LAG`, `DiagnosticsSettings.seasonal_period`,
  `segments.py`, `figures.py`.
- **Fix:** one constant.
- **Status:** done. `QUARTERS_PER_YEAR` in `app/data/dates.py` feeds
  `SEASONAL_LAG`, the `seasonal_period` default, `segments.py`, the figure
  axes and the year-over-year lag in `flags.py`.
- **Rerun:** No.

### S5 String contracts between register and decisions
- **Smell:** Primitive Obsession.
- **Where:** `diagnostics/audit.py`, `diagnostics/decisions.py`,
  `diagnostics/panel.py`.
- **Fix:** `StrEnum`s with the same values.
- **Status:** done. `Direction` and `SeriesStatus` in `diagnostics/models.py`;
  `use_enum_values=True` keeps the frames holding plain strings, and tests
  assert that.
- **Rerun:** No.

### S6 SEC chain duplication
- **Smell:** Duplicate Code / Special Case.
- **Where:** `sec_edgar/chains.py`.
- **Fix:** one share-chain helper; component chains read by name without
  mutating a shared dict.
- **Status:** done. One share-count closure inside `_shares_chain`; the
  cost-of-revenue and D&A components are typed models
  (`COST_OF_REVENUE_PARTS`, `D_AND_A_PARTS`) outside `TAG_CHAINS`. The SEC frame
  snapshot is unchanged.
- **Rerun:** No.

### S7 Unsafe YAML template in `add_company`
- **Smell:** Duplicate schema, unescaped templating.
- **Where:** `data/add_company.py`.
- **Fix:** `yaml.safe_dump`, then reload the registry.
- **Status:** done. The entry is dumped with `yaml.safe_dump` and the
  registry reloaded; a `ConfigError` restores the original file. Tests cover a
  name with YAML syntax and the rollback.
- **Rerun:** No.

### S8 Series preparation written twice
- **Smell:** Duplicate Code.
- **Where:** `diagnostics/series.py`, `diagnostics/transform_comparison.py`.
- **Fix:** one public function.
- **Status:** done. `prepared_for_diagnosis` returns a `PreparedSeries`;
  `TransformComparer` prepares each series once.
- **Rerun:** No.

### S9 Misleading `regimes=None` default
- **Smell:** Fallacious docs.
- **Where:** `features/builder.py`, `features/service.py`.
- **Fix:** make `regimes` required.
- **Status:** done. `regimes` is required in `FeatureBuilder.build` and in
  every `FeatureService` entry point; NB01 already passes it.
- **Rerun:** No.

### S10 Small items
- **Where and fix:** listed in the status.
- **Status:** done.
  - `ConfigError` raised by the three YAML loaders.
  - `app/data/cli.py` shares the date options, date resolution and panel
    fetch across the three CLIs.
  - `XBRL_HISTORY_START` lives in `sec_edgar/concepts.py`.
  - `IngestionSources.yfinance` is now `market`.
  - The Alpha Vantage loop raises on its last rate-limited attempt, so the
    unreachable branch is gone.
  - `CorrelationAnalyzer.redundancy_threshold`, `SecEdgarSource.resolve_cik`
    and `CompanyRegistry.primary_sec_cik` are deleted; tests use
    `resolve_ciks`. `merge_raw_financial_frames` is no longer re-exported.
  - `_quarter_timestamp`, `report_as_dict` and `_comma_separated` are inlined.
  - `_usable` asks `target_family`; `flags.py` has `OUTLIER_CONTAMINATION`.
- **Rerun:** No.

## Phase 3: Output-sensitive defects (spec only)

| # | Defect | Spec | Measured (2026-10-27) |
|---|---|---|---|
| O1 | EPS repair skipped when a panel has no gaps | `docs/specs/eps-split-restatement-repair.md` | Latent: 0 stored rows affected; every panel ran the fallback. No rerun. |
| O2 | Dividend yield excludes quarter-end days | `docs/specs/dividend-yield-window.md` | 49 of 60 first-quarter yields wrongly 0; 57 of 81 quarters use the previous day's close; TSLA's 16 pre-listing yields 0.0, not missing. Re-ingest, NB00 onward. |
| O3 | FRED columns `gdp_yoy` and `dxy` misnamed | `docs/specs/fred-series-naming.md` | Confirmed (2020 Q2 = −28.0). Needs a decision: rename or switch series. |
| O4 | Ljung-Box uses a lag-d difference | `docs/specs/ljung-box-differencing.md` | 47 d = 2 series change p-value; no forecastable verdict flips. NB01 rerun. |

Status: all four implemented (2026-10-27) per
`docs/plans/output-sensitive-fixes.md`; O3 took the mixed option. The re-ingest
(O2, O3) and the NB00/NB01 reruns (O2, O3, O4) are still to run by hand.

Also catalogued: segment columns named `lower_quartile` / `upper_quartile`
while the quantiles are configurable, and the regime column named both
`regime` and `seasonality_regime`. Renaming either changes NB01 headers.
