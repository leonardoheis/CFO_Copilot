# Spec — Diagnostics and features as injected services

Reshape of `app/services/diagnostics/` and `app/services/features/`, built as
module functions by the [EDA and feature engineering plan](../plans/eda-feature-engineering.md)
(Tasks 2–7), into class-based services that follow the `prediction/` and
`training/` template and reach the notebook through the DI container.

## Problem

The two packages expose a flat set of functions. Three consequences:

1. **Configuration is hard-coded.** The 16-observation floor, the 5% test
   level, the seasonal period, the Ljung-Box lag, the regime count and seed,
   and the leakage scramble factors are module constants. No caller can vary
   them and no test can pin them.
2. **The notebook would reach past the container.** Task 8 as planned imports
   the functions directly and passes `Settings.features_output_path(h)` to
   `write_panel`, so NB01 would talk to settings and persistence itself instead
   of receiving collaborators the way NB00 does
   (`container.panel_store()`, `container.experiment_tracker()`).
3. **Failures escape as bare vendor errors.** Two were reproduced against the
   current code:

   | Input | Current result |
   |---|---|
   | A series constant for its whole analysed run, e.g. 40 zeros | `ValueError: cannot convert float NaN to integer` from inside statsmodels |
   | Two fully diagnosed companies, three regimes requested | `ValueError: n_samples=2 should be >= n_clusters=3` from sklearn |

   The first breaks the existing contract (EDA spec R2: diagnostics "never
   raise for a bad series"). It is live data, not a hypothetical: in the real
   NB00 panels, `dividend_yield` is constant for ADBE, AMZN, NFLX and TSLA
   (4 of 60 companies). NB01's current target list is financial columns only,
   none constant, so the crash is dormant until a market column is diagnosed.

## Scope

In: both packages under `app/services/`, their tests, the production
container, the feature export path, and the EDA plan's Task 8 cells that call
them.

Out:

- The statistics themselves. Every number the current functions produce stays
  identical; this is a structural change plus the two failure fixes.
- `FeatureGroup` membership and column names (EDA spec R6).
- `load_consolidated` (see decision D5).

## Evidence

- Template: `services/prediction/` and `services/training/` each hold
  `service.py` (one `*Service` class) and `exceptions.py` (every exception of
  the package, as `@dataclass` types carrying their data as fields), re-exported
  from `__init__.py`, and are registered as `providers.Factory` in
  `injections/production.py`.
- Stateless classes fail lint: ruff `PLR6301` rejects methods that never read
  `self`, and CLAUDE.md bans `@staticmethod`. A class is therefore justified
  only where it holds configuration or collaborators; pure helpers stay
  module-level functions (the `python-oop` rule, and CLAUDE.md "Static helpers").
- No caller outside the two packages and their tests imports them today
  (`grep services.features|services.diagnostics` over `src/`), and
  `01_eda_feature_engineering.ipynb` has no cells yet, so the function API can
  be replaced, not deprecated.
- `Settings.features_output_path` is used by nothing but the unwritten Task 8.

## Required behaviour

**S1. One service class per package is the entry point.**
`diagnostics/service.py` holds `DiagnosticsService`; `features/service.py`
holds `FeatureService`. Each is what the container provides and what NB01
calls. Other classes in the package are its collaborators, received through
its constructor, never instantiated inside it.

**S2. Every tunable value is constructor state, with today's value as the
default.** Diagnostics: observation floor 16, significance 0.05, seasonal
period 4, Ljung-Box lag 8, maximum differencing order 2, regime count 3,
clustering seed 42, macro columns `MACRO_COLUMNS`. Features: the feature spec
(default all eight groups), the leakage scramble scale 3.0 and shift 1.0.
Configuration types are frozen Pydantic models that reject unknown keys.

**S3. Invalid configuration is refused at construction, not at first use.** A
horizon outside 1–4, a significance outside (0, 1), a regime count below 2,
an observation floor that does not cover two full seasonal cycles (STL's
minimum), or leakage scramble factors that leave values unchanged (scale 1,
shift 0) raises when the object is built.

**S4. Each package's `exceptions.py` describes every error it raises**, as
`@dataclass` exceptions carrying the offending data (count, horizon, ticker,
columns) as fields, all under one package base class (`FeatureError`,
`DiagnosticsError`). Callers can catch the base or read the fields; no
vendor `ValueError` leaves either package.

**S5. A constant series yields a record, not an exception.** Its status is
`constant`; observation count and `log_defined` are filled, statistical fields
are empty. This completes EDA spec R2.

**S6. Too few companies to cluster is a named error.** When fewer fully
diagnosed companies exist than regimes requested, clustering raises the
diagnostics package's own error naming both counts.

**S7. The notebook receives every collaborator from the container.** It
obtains the diagnostics service, the feature service and a feature store from
`configure_container()`, and never calls a persistence function or builds an
output path itself. The one remaining `Settings` use is the input paths passed
to `load_consolidated`, which D5 leaves in place. A different feature spec for one call
is a container override (`builder__spec=…`), not a new import.

**S8. Feature export is a store.** A feature store, constructed with its
directory, writes one parquet per horizon and returns the path, mirroring
`PanelStore`. It creates its directory on write, not on construction.

**S9. Behaviour is preserved.** Every behavioural case in today's 68 feature
and diagnostics tests survives as a test against the new API with the same
expected values: gap handling, differencing order, STL strengths, regime
ordering and determinism, perfect correlation, round-trip reconstruction,
shrinkage, NaN propagation, lag and rolling columns, target dates, static and
flag groups, leakage pass and catch, dataset row counts and target columns.

**S10. Project rules hold.** mypy strict; `uv run poe check` green; no
`# noqa`, `# ruff: ignore`, `# type: ignore`, `@staticmethod`, or exception-driven
loop control. The existing pyright directives for untyped statsmodels and
sklearn stay as they are.

## Acceptance criteria

| # | Check | How |
|---|---|---|
| A1 | Both packages have `service.py` and `exceptions.py`; `__init__.py` exports the service, its configuration and its exceptions | file listing, import test |
| A2 | Container resolves `diagnostics_service`, `feature_service`, `feature_store` to working objects | test calling each provider |
| A3 | `container.feature_service(builder__spec=…)` builds only the requested groups | test |
| A4 | A constant series returns status `constant` | test with 40 zeros |
| A5 | Two companies, three regimes raises the package error with both counts | test |
| A6 | Horizon 5, significance 1.5, regime count 1 each raise at construction | parametrized test |
| A7 | All S9 cases pass with unchanged expected values | test suite |
| A8 | Feature store writes `features_h{h}.parquet` and reads it back equal | `tmp_path` test |
| A9 | `grep -En "write_panel|features_output_path|build_features|assemble_dataset" src/app/playground/01_*.ipynb` finds nothing | shell |
| A10 | `uv run poe check` passes | shell |

## Decisions taken by default — confirm or override

| # | Decision | Reason |
|---|---|---|
| D1 | `DiagnosticsService` and `FeatureService` are facades over collaborators (`SeriesDiagnostician`, `SeasonalityRegimeClusterer`, `MacroCorrelator`; `FeatureBuilder`, `LookaheadGuard`), not one class each | One class holding STL, ADF/KPSS, KMeans and correlation would have four reasons to change (SRP). The cost: two facade methods per package are one-line delegations |
| D2 | Collaborators are typed as concrete classes, not Protocols | Each has one implementation; the only substitution a test needs (a leaky builder for the guard) is a `Callable` argument already. Add a Protocol when a second implementation exists |
| D3 | `log_level`, `yoy_log_growth` and `observed_since_last_gap` stay module functions | They read no configuration; as methods they would fail `PLR6301` |
| D4 | The dataset assembly moves into `FeatureService.assemble`; `dataset.py` is deleted | Assembly is the package's main use case, which is what `service.py` holds in the template |
| D5 | `load_consolidated` stays a function in `panel_store.py`; NB01 keeps calling it with `Settings` paths | It is data-layer work outside these packages. Moving it to `PanelStore.load_consolidated()` would complete S7 and is a small follow-up |
| D6 | `Settings.features_output_path` is removed, replaced by the store's injected directory | Its only intended caller is replaced by S8; keeping it leaves two ways to find the same path |
| D7 | The target arm and horizon are per-call arguments, not service state | NB01 loops over four horizons and three arms with one service; making them state would mean twelve container resolutions |
