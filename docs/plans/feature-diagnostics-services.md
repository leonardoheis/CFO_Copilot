# Diagnostics and features as injected services — Implementation Plan

> **No commit steps.** CLAUDE.md forbids `git commit`/`push`/PR without explicit
> permission for that action. Each task ends at green tests and stages nothing.

**Spec:** [`docs/specs/feature-diagnostics-services.md`](../specs/feature-diagnostics-services.md).
**Replaces:** the function API built by [`eda-feature-engineering.md`](eda-feature-engineering.md)
Tasks 2–7, and rewrites that plan's Task 8 cells (Task 12 here).

**Goal:** Each package gets a `service.py` entry point and a complete
`exceptions.py`, like `services/prediction/`. Tunables become constructor
state with today's values as defaults. NB01 receives every collaborator from
the container.

**Precondition:** the uncommitted Tasks 2–7 work is committed first, so this
reshape reviews as its own diff.

## Global Constraints

- mypy strict; `uv run poe check` green at the end of every task.
- No `# noqa`, `# ruff: ignore`, `# type: ignore`, `@staticmethod`, or
  `except … : continue`.
- **A class must hold state.** A method that reads no `self` fails `PLR6301`;
  such helpers stay module-level private functions (spec D3).
- Configuration: frozen Pydantic, `extra="forbid"`, keyword-only, validators
  for S3. Exceptions: `@dataclass`, data as fields, a `__str__` that builds the
  message. A dataclass exception does not pass its fields to
  `Exception.__init__`, so `str(error)` is empty without `__str__`, and
  `pytest.raises(match=…)` relies on it.
- Collaborators arrive through `__init__`; nothing instantiates a collaborator
  inside a class. Value objects (`TargetTransformer` per call) are not
  collaborators.
- Tests are rewritten against the new API case by case; expected values do
  not change (spec S9). Test count may only grow.

## File Structure

| File | After |
|---|---|
| `services/features/exceptions.py` | `FeatureError` base + six `@dataclass` errors with fields |
| `services/features/transforms.py` | `TargetArm`, `TargetTransformer`; functions `log_level`, `yoy_log_growth` |
| `services/features/builder.py` | `FeatureGroup`, `FeatureSpec`, `FeatureBuilder` |
| `services/features/leakage.py` | `LeakageSettings`, `LookaheadGuard` |
| `services/features/service.py` | `FeatureService` (assemble + lookahead check) |
| `services/features/dataset.py` | deleted (D4) |
| `services/diagnostics/exceptions.py` | new: `DiagnosticsError`, `TooFewCompaniesError` |
| `services/diagnostics/models.py` | `SeriesDiagnostics` (+ `constant` status), `DiagnosticsSettings`, `RegimeSettings` |
| `services/diagnostics/series.py` | `SeriesDiagnostician`; function `observed_since_last_gap` |
| `services/diagnostics/panel.py` | `SeasonalityRegimeClusterer`, `MacroCorrelator` |
| `services/diagnostics/service.py` | `DiagnosticsService` |
| `data/feature_store.py` | `FeatureStore` |
| `settings.py` | `features_output_path` removed (D6) |
| `injections/production.py` | three new providers |
| `tests/services/{features,diagnostics}/`, `tests/data/test_feature_store.py`, `tests/injections/test_container.py` | rewritten / new |

Order: 1 → 2 → 3 → 4 → 5 → 6 (features done) → 7 → 8 → 9 → 10 (diagnostics
done) → 11 → 12 → 13. Features first because diagnostics imports
`log_level` and `yoy_log_growth` from it.

---

### Task 1: Feature exceptions carry their data

**Files:** `services/features/exceptions.py`, `tests/services/features/test_exceptions.py` (new)

| Exception | Fields | Message |
|---|---|---|
| `NonPositiveValueError` | `count: int` | `log is undefined for {count} non-positive values` |
| `InvalidHorizonError` | `horizon: int`, `max_horizon: int` | `horizon must be 1 to {max_horizon}, got {horizon}` |
| `MissingFlagsError` | `columns: tuple[str, ...]` | `group F needs the NB00 flag columns: a, b` |
| `MissingRegimeError` | `ticker: str` | `no seasonality regime for {ticker}; run the EDA regimes first` |
| `MixedTickerPanelError` | `tickers: tuple[str, ...]` | `features take one company's panel at a time, got: …` |
| `LeakageError` | `origin: int`, `columns: tuple[str, ...]` | `features at origin row {origin} changed with later quarters: …` |

```python
class FeatureError(Exception):
    """Base error for feature engineering."""


@dataclass
class InvalidHorizonError(FeatureError):
    horizon: int
    max_horizon: int

    def __str__(self) -> str:
        return f"horizon must be 1 to {self.max_horizon}, got {self.horizon}"
```

The bound travels as a field so `exceptions.py` imports nothing from
`transforms.py`, which keeps the import one-way.

- [x] Step 1: test each exception's `str()` and fields, and that each is a
  `FeatureError`.
- [x] Step 2: run, expect failure (constructor signatures differ).
- [x] Step 3: implement; update the six `raise` sites to pass fields.
- [x] Step 4: `uv run pytest tests/services/features -q` green; existing
  `match=` strings still match.

### Task 2: `TargetTransformer`

**Files:** `services/features/transforms.py`, `tests/services/features/test_transforms.py`

```python
class TargetTransformer(BaseModel):
    """Build and invert one arm's target at one horizon.

    Usage::

        transformer = TargetTransformer(arm=TargetArm.LOG_DIFF4, horizon=2)
        y = transformer.make(revenue)
        level = transformer.reconstruct(revenue, prediction)
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    arm: TargetArm
    horizon: int

    @field_validator("horizon")
    @classmethod
    def _supported_horizon(cls, horizon: int) -> int: ...  # raises InvalidHorizonError

    def make(self, values: pd.Series) -> pd.Series: ...
    def reconstruct(
        self, values: pd.Series, prediction: pd.Series, *, shrinkage: float = 1.0
    ) -> pd.Series: ...
```

`make_target`, `reconstruct_level` and `_require_supported_horizon` are
removed; `log_level` and `yoy_log_growth` stay functions (D3). Checked:
a non-`ValueError` raised in a Pydantic v2 validator propagates unwrapped.

- [x] Step 1: port the 23 cases; the horizon test becomes "construction with
  horizon 0 or 5 raises `InvalidHorizonError` whose `.horizon` is that value".
- [x] Steps 2–4: fail, implement, pass.

### Task 3: `FeatureBuilder`

**Files:** `services/features/builder.py`, `tests/services/features/test_builder.py`

```python
class FeatureBuilder:
    """Build one company's features for a fixed feature spec.

    Usage::

        builder = FeatureBuilder(spec=FeatureSpec(groups=frozenset(FeatureGroup)))
        features = builder.build(panel, horizon=2, regimes=regimes)
    """

    def __init__(self, spec: FeatureSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> FeatureSpec: ...

    def build(
        self, panel: pd.DataFrame, *, horizon: int, regimes: pd.Series | None = None
    ) -> pd.DataFrame: ...
```

The `if FeatureGroup.MACRO in groups` chain stays as it is (decided 2026-09-28);
`_lag_features`, `_rolling_features`, `_static_features`, `_flag_features`
stay module functions. `FeatureSpec` gets a default of all eight groups so
the container can build a builder with no arguments.

- [x] Port the 18 cases (`_spec(group)` → `FeatureBuilder(spec=_spec(group))`);
  fail, implement, pass.

### Task 4: `LookaheadGuard`

**Files:** `services/features/leakage.py`, `tests/services/features/test_leakage.py`

```python
class LeakageSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scramble_scale: float = 3.0
    scramble_shift: float = 1.0

    # scale 1 and shift 0 would scramble nothing and pass every builder
    @model_validator(mode="after")
    def _scrambles_something(self) -> Self: ...


class LookaheadGuard:
    def __init__(self, settings: LeakageSettings) -> None: ...

    def check(
        self,
        build: Callable[[pd.DataFrame], pd.DataFrame],
        panel: pd.DataFrame,
        *,
        origins: Sequence[int],
    ) -> None: ...
```

- [x] Port the 5 cases; add "scale 1, shift 0 is refused". Fail, implement, pass.

### Task 5: `FeatureService`

**Files:** `services/features/service.py` (new), delete `dataset.py`,
`tests/services/features/test_service.py` (from `test_dataset.py`)

```python
class FeatureService:
    """Assemble pooled feature datasets and prove they do not look ahead.

    Usage::

        service = container.feature_service()
        dataset = service.assemble(panels, horizon=2, arm=TargetArm.LOG_DIFF4, regimes=r)
        service.check_lookahead(panel, horizon=2, regimes=r, origins=[3, 8, 15])
    """

    def __init__(self, builder: FeatureBuilder, guard: LookaheadGuard) -> None: ...

    def assemble(
        self,
        panels: Mapping[str, pd.DataFrame],
        *,
        horizon: int,
        arm: TargetArm,
        regimes: pd.Series | None = None,
    ) -> pd.DataFrame: ...

    def check_lookahead(
        self,
        panel: pd.DataFrame,
        *,
        horizon: int,
        origins: Sequence[int],
        regimes: pd.Series | None = None,
    ) -> None: ...
```

`assemble` builds one `TargetTransformer(arm=arm, horizon=horizon)` per call
(D7). `check_lookahead` passes the guard a closure over its own builder, so
the notebook never writes a lambda (EDA R10).

- [x] Port the 5 dataset cases; the leakage-at-every-horizon case moves here
  as `check_lookahead`. Fail, implement, pass.

### Task 6: `FeatureStore` and the features `__init__`

**Files:** `data/feature_store.py` (new), `data/__init__.py`, `settings.py`,
`services/features/__init__.py`, `tests/data/test_feature_store.py` (new)

```python
class FeatureStore:
    """Read and write one pooled feature parquet per horizon."""

    def __init__(self, directory: Path) -> None: ...
    def path_for(self, horizon: int) -> Path: ...  # features_h{h}.parquet
    def write(self, dataset: pd.DataFrame, horizon: int) -> Path: ...  # mkdir here
    def read(self, horizon: int) -> pd.DataFrame: ...
```

Remove `Settings.features_output_path` (D6). Features `__init__` exports:
`FeatureService`, `FeatureBuilder`, `FeatureSpec`, `FeatureGroup`,
`LookaheadGuard`, `LeakageSettings`, `TargetTransformer`, `TargetArm`,
`SEASONAL_LAG`, `log_level`, `yoy_log_growth`, and every exception.

- [x] Round-trip test in `tmp_path` (A8); `sector` category survives. Then
  `uv run poe check`.

### Task 7: Diagnostics exceptions and settings

**Files:** `services/diagnostics/exceptions.py` (new), `models.py`,
`tests/services/diagnostics/test_models.py` (new)

```python
class DiagnosticsError(Exception):
    """Base error for series and panel diagnostics."""


@dataclass
class TooFewCompaniesError(DiagnosticsError):
    companies: int
    regimes: int
```

```python
class DiagnosticsSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_observations: int = 16
    significance: float = 0.05
    seasonal_period: int = 4
    ljung_box_lag: int = 8
    max_differencing_order: int = 2
    # validators: 0 < significance < 1; min_observations > 2 * seasonal_period
    # (STL needs two full cycles)


class RegimeSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    n_regimes: int = 3  # validator: >= 2
    seed: int = 42
```

`SeriesDiagnostics.status` becomes `Literal["ok", "insufficient_data", "constant"]`.

- [x] Tests for each validator (A6) and the exception message. Fail,
  implement, pass.

### Task 8: `SeriesDiagnostician`

**Files:** `services/diagnostics/series.py`, `tests/services/diagnostics/test_series.py`

```python
class SeriesDiagnostician:
    def __init__(self, settings: DiagnosticsSettings) -> None: ...
    def differencing_order(self, series: pd.Series) -> int: ...
    def seasonal_and_trend_strength(self, series: pd.Series) -> tuple[float, float]: ...
    def diagnose(
        self, ticker: str, variable: str, series: pd.Series
    ) -> SeriesDiagnostics: ...
```

A constant run is detected before any statistic and returns status
`constant` (S5). `observed_since_last_gap` stays a function; `_strength`,
`_ljung_box_p` stay module functions taking the lag as an argument.

- [x] Port the 12 series cases; add "40 zeros → `constant`, `n_obs` 40, no
  exception" (A4). Fail, implement, pass.

### Task 9: `SeasonalityRegimeClusterer` and `MacroCorrelator`

**Files:** `services/diagnostics/panel.py`, `tests/services/diagnostics/test_panel.py`

```python
class SeasonalityRegimeClusterer:
    def __init__(self, settings: RegimeSettings) -> None: ...
    def assign(self, diagnostics: pd.DataFrame, *, variable: str) -> pd.Series: ...

    # raises TooFewCompaniesError before KMeans sees too few rows (S6)


class MacroCorrelator:
    def __init__(self, macro_columns: Sequence[str]) -> None: ...
    def correlate(
        self, panels: Mapping[str, pd.DataFrame], *, variable: str
    ) -> pd.DataFrame: ...
```

`macro_columns` is injected (default in the container: `MACRO_COLUMNS`), so a
test can correlate against one column.

- [x] Port the 4 cases; add "2 companies, 3 regimes → `TooFewCompaniesError`
  with `companies=2, regimes=3`" (A5). Fail, implement, pass.

### Task 10: `DiagnosticsService`

**Files:** `services/diagnostics/service.py` (new), `__init__.py`,
`tests/services/diagnostics/test_service.py` (new)

```python
class DiagnosticsService:
    def __init__(
        self,
        diagnostician: SeriesDiagnostician,
        clusterer: SeasonalityRegimeClusterer,
        correlator: MacroCorrelator,
    ) -> None: ...

    def diagnose_panel(
        self, panels: Mapping[str, pd.DataFrame], variables: Sequence[str]
    ) -> pd.DataFrame: ...
    def seasonality_regimes(
        self, diagnostics: pd.DataFrame, *, variable: str
    ) -> pd.Series: ...
    def growth_macro_correlations(
        self, panels: Mapping[str, pd.DataFrame], *, variable: str
    ) -> pd.DataFrame: ...
```

`diagnose_panel` owns the loop over companies and variables (moved from
`series.py`); the other two delegate (D1).

- [x] Move the panel-diagnostics case here; add one case per delegating
  method. `__init__` exports the service, `SeriesDiagnostics`, both settings
  types, the collaborators, `observed_since_last_gap`, and both exceptions.
  `uv run poe check`.

### Task 11: Container

**Files:** `injections/production.py`, `tests/injections/test_container.py` (new)

```python
diagnostics_service = providers.Factory(
    DiagnosticsService,
    diagnostician=providers.Factory(
        SeriesDiagnostician, settings=DiagnosticsSettings()
    ),
    clusterer=providers.Factory(SeasonalityRegimeClusterer, settings=RegimeSettings()),
    correlator=providers.Factory(MacroCorrelator, macro_columns=MACRO_COLUMNS),
)
feature_service = providers.Factory(
    FeatureService,
    builder=providers.Factory(FeatureBuilder, spec=FeatureSpec()),
    guard=providers.Factory(LookaheadGuard, settings=LeakageSettings()),
)
feature_store = providers.Factory(
    FeatureStore, directory=Settings.DATA_DIRECTORY / "features"
)
```

Checked on dependency-injector 4.48.1: `container.feature_service(builder__spec=spec)`
overrides the nested factory's argument for that call only.

- [x] Tests: each provider resolves to its type (A2); a `builder__spec`
  override builds only group L (A3); `feature_store` points under
  `DATA_DIRECTORY` without creating the directory.

### Task 12: Rewrite the EDA plan's Task 8 cells

**Files:** `docs/plans/eda-feature-engineering.md` (Task 8 only)

- Imports shrink to `configure_container`, `TargetArm`, `FeatureGroup`,
  `FeatureSpec`, tracking, and `load_consolidated` (D5).
- `diagnose_panel(...)` → `container.diagnostics_service().diagnose_panel(...)`;
  same for regimes and correlations.
- `assemble_dataset(...)` → `container.feature_service().assemble(...)`;
  group ablations use `container.feature_service(builder__spec=...)`.
- `write_panel(dataset, Settings.features_output_path(h))` →
  `container.feature_store().write(dataset, h)`.
- Step 5's static check adds A9: no `Settings` or `write_panel` in the notebook.

- [x] Edit; re-read the cells against spec S7.

### Task 13: Verify and hand over

- [x] `uv run pytest tests/services/features tests/services/diagnostics tests/data/test_feature_store.py tests/injections -q`:
  count ≥ 68 + the new cases.
- [x] `uv run poe check` green.
- [x] Mark the EDA plan's Tasks 2–7 as superseded by this plan in their
  headings (their checkboxes stay ticked; the code they describe no longer
  exists).
- [x] Summarize files changed, A1–A10 status, and propose a commit. Stage nothing.

### Task 14: `PanelStore.load_consolidated` (D5 follow-up)

**Files:** `data/panel_store.py`, `tests/data/test_panel_store.py`, `docs/plans/eda-feature-engineering.md` (Task 8 cell 1)

The module function becomes a method reading `panel_long.parquet` and
`macro_q.parquet` from the store's own directory; behaviour and errors are
unchanged. A test pins both names to `Settings.PANEL_LONG_PATH` and
`Settings.MACRO_Q_PATH`, the paths NB00 writes, as
`test_file_naming_matches_the_ingestion_writer` already does for per-ticker files.

- [x] Port the four `load_consolidated` cases to `PanelStore(tmp_path).load_consolidated()`; add the naming case. Fail, implement, pass.
- [x] EDA Task 8 cell 1: `panels = container.panel_store().load_consolidated()`; drop the `Settings` and `load_consolidated` imports.
- [x] `uv run poe check`.

## Self-review

**Spec coverage.** S1 → Tasks 5, 10. S2 → Tasks 2, 4, 7, 9. S3 → Tasks 2, 4, 7.
S4 → Tasks 1, 7. S5 → Task 8. S6 → Task 9. S7 → Tasks 11, 12. S8 → Task 6.
S9 → every porting step, counted in Task 13. D5 → Task 14. S10 → every task's `poe check`.

**Risks.**
- `FeatureSpec()` with a default of all groups changes nothing for existing
  callers but makes "no groups" impossible to express by omission; an explicit
  empty `frozenset()` still builds keys only.
- `pd.DataFrame` fields cannot live on a Pydantic model without
  `arbitrary_types_allowed`, so the services are plain classes and only the
  configuration is Pydantic (CLAUDE.md "Keep `@dataclass`" reasoning).
- The facade methods that only delegate are the price of D1; if they grow to
  more than a third of the service, revisit exposing the collaborators from
  the container directly.
