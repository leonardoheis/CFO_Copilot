# NB00 — consolidate, flag and track the panels — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **No commit steps.** This repo forbids `git commit`/`push`/PR without explicit permission for that action (CLAUDE.md). Each task ends at green tests and stages nothing; the last task proposes a commit and waits.

**Goal:** Turn the 60 ingested per-company panels into `panel_long` and `macro_q` with `covid`, `structural_break`, `outlier_flag` and `is_projected` flags and a missing-value ledger, tracked in W&B, so the EDA notebook has a finished dataset to read.

**Architecture:** Stateful collaborators (panel store, tracker, structural-break registry) are constructor-injected through the existing `dependency-injector` `Container`. Consolidation, flags and the ledger are pure functions under `app/data/`, imported directly, because a class with no state fails `PLR6301`. W&B is imported lazily inside `WandbTracker.start_run`, so the Docker image, which never installs the `research` group, still boots.

**Tech Stack:** pandas, scikit-learn (IsolationForest), pyyaml, pydantic v2, dependency-injector, wandb (new, `research` group), pytest.

**Spec:** [`docs/specs/nb00-ingest-and-consolidate.md`](../specs/nb00-ingest-and-consolidate.md). Parent: [`docs/CFO_COPILOT_MASTER_PLAN.md`](../CFO_COPILOT_MASTER_PLAN.md). Next: [`docs/plans/eda-feature-engineering.md`](eda-feature-engineering.md).

## Global Constraints

- mypy strict; `uv run poe check` (lint + typecheck + test) green before finishing; coverage gate 80%.
- No `# noqa`, `# ruff: ignore`, `# type: ignore`, `@staticmethod`, and no `except … : continue` in loops.
- Config and result types: Pydantic `ConfigDict(frozen=True, extra="forbid")`, keyword-only.
- Docstrings: one line plus the `Returns:` block pydoclint requires; explain *why* in comments, never *what*; expressive names.
- Ruff runs `extend-select = ["ALL"]`: `ANN401` forbids `Any` in signatures, so type the W&B module as `ModuleType` and use small Protocols.
- Paths, credentials and the last reported quarter come from `Settings`; no module-level state.
- Only `__init__.py` defines a package's public names; names crossing a module boundary drop the leading underscore.
- Do not run ingestion, hit W&B online, or write into `data/processed/`. Executing the notebook is the user's decision (memory: ask-before-acting).
- No new scripts; anything batch-like is a loop in the notebook.

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml`, `.pre-commit-config.yaml`, `.env.example` | `research` group; mypy hook deps; W&B settings docs |
| `src/app/settings.py` | `WANDB_*`, `LAST_REPORTED_QUARTER`, `STRUCTURAL_BREAKS_PATH`, `PANEL_LONG_PATH`, `MACRO_Q_PATH` |
| `src/app/data/exceptions.py` | `PanelStoreError` family, `ConsolidationError`, `MacroMismatchError` |
| `src/app/data/panel_store.py` | `PanelStore`: validated read of `*_panel.parquet` |
| `src/app/data/consolidation.py` | `consolidate_panels` → `panel_long`, `macro_q` |
| `src/app/data/flags.py` | `covid_flag`, `is_projected`, `structural_break_flag`, `outlier_flag`, `add_flags` |
| `src/app/data/structural_breaks.py`, `config/structural_breaks.yaml` | hand-entered break quarters and their validated loader |
| `src/app/data/missing.py` | `missing_value_ledger` |
| `src/app/services/tracking/` | `exceptions.py`, `config.py` (`RunConfig`, `WandbSettings`, `run_name`), `wandb_tracker.py` |
| `src/app/injections/production.py` | `panel_store`, `experiment_tracker`, `structural_breaks` providers |
| `tests/conftest.py` | shared `make_panel` fixture |
| `tests/data/`, `tests/services/tracking/` | tests; each new directory gets an `__init__.py` |
| `src/app/playground/00_ingest_and_consolidate.ipynb` | orchestration cells only |

Task order follows dependencies: 0 → 1 → 2 → 3 → 4 → 5 → 6.

---

### Task 0: Dependencies, settings, shared fixture

**Files:**
- Modify: `pyproject.toml` (via `uv add`), `.pre-commit-config.yaml`, `.env.example`, `src/app/settings.py`, `tests/conftest.py`

**Interfaces:**
- Produces: `Settings.WANDB_PROJECT: str`, `WANDB_ENTITY: str`, `WANDB_API_KEY: str`, `WANDB_MODE: Literal["online","offline","disabled"]`, `LAST_REPORTED_QUARTER: date`, `STRUCTURAL_BREAKS_PATH`, `PANEL_LONG_PATH`, `MACRO_Q_PATH` (all `Path`); fixture `make_panel(*, ticker="AAA", quarters=24, sector="Technology") -> pd.DataFrame`.

- [ ] **Step 1: Add dependencies.** `uv` pins the versions.

```bash
uv add --group research wandb ipykernel
uv add scipy
```

`research` is not in `default-groups` and the Dockerfile uses `--no-default-groups`, so the image is unaffected. Then `uv sync --group research` locally.

- [ ] **Step 2: Add `wandb`, `statsmodels`, `scipy`, `scikit-learn`, `pandas` to the mypy hooks.** In `.pre-commit-config.yaml`, append to `additional_dependencies` of both `mypy` and `nbqa-mypy` any of these not already listed (the `mypy` list is already partly there; check each).

- [ ] **Step 3: Settings.** In `_Settings` add (with `from datetime import date` and `from typing import Literal`):

```python
    LAST_REPORTED_QUARTER: date = date(2026, 6, 30)
    WANDB_PROJECT: str = "cfo-copilot"
    WANDB_ENTITY: str = ""
    WANDB_API_KEY: str = ""
    WANDB_MODE: Literal["online", "offline", "disabled"] = "offline"
```

and, beside `COMPANY_REGISTRY_PATH`:

```python
@property
def STRUCTURAL_BREAKS_PATH(self) -> Path:
    return self.ROOT_PATH / "config" / "structural_breaks.yaml"


@property
def PANEL_LONG_PATH(self) -> Path:
    return self.DATA_DIRECTORY / "processed" / "panel_long.parquet"


@property
def MACRO_Q_PATH(self) -> Path:
    return self.DATA_DIRECTORY / "processed" / "macro_q.parquet"
```

`LAST_REPORTED_QUARTER` is E1's answer as data: 2026-Q2 is reported. Bump it deliberately when a newer quarter is ingested. pydantic-settings reads `.env` but does not export it to `os.environ`, so the tracker must pass the key to `wandb.login` itself (Task 2).

- [ ] **Step 4: `.env.example`.** Append:

```
# --- Experiment tracking (Weights & Biases) ---

# offline (default): runs are written locally, `wandb sync` uploads them later.
# online: needs WANDB_API_KEY. disabled: no tracking at all.
WANDB_MODE=offline
WANDB_API_KEY=
WANDB_ENTITY=
WANDB_PROJECT=cfo-copilot
```

- [ ] **Step 5: Shared fixture** in `tests/conftest.py` (add imports `Callable`, `numpy as np`, `pandas as pd`, `pytest`, and `FINANCIAL_COLUMNS`, `MACRO_COLUMNS`, `MARKET_COLUMNS` from `app.data.schema`):

```python
PanelFactory = Callable[..., pd.DataFrame]


@pytest.fixture
def make_panel() -> PanelFactory:
    def _make(
        *, ticker: str = "AAA", quarters: int = 24, sector: str = "Technology"
    ) -> pd.DataFrame:
        steps = np.arange(quarters)
        panel = pd.DataFrame({
            "date": pd.date_range("2015-03-31", periods=quarters, freq="QE"),
            "company": ticker,
            "ticker": ticker,
            "sector": sector,
            "is_public": True,
        })
        panel["revenue_usd_m"] = 100 * np.exp(
            0.01 * steps + 0.1 * np.sin(steps * np.pi / 2)
        )
        market_columns = (*MARKET_COLUMNS, "market_cap_usd_m", "pe_ratio")
        other_columns = [*FINANCIAL_COLUMNS[1:], *market_columns, *MACRO_COLUMNS]
        for offset, column in enumerate(other_columns):
            panel[column] = np.cos(steps / 3) + offset
        return panel

    return _make
```

- [ ] **Step 6: Verify.**

Run: `uv run python -c "import app; print('ok')"` and `uv run pytest -q`
Expected: `ok`; existing suite still passes.

---

### Task 1: `PanelStore` (R1)

**Files:**
- Modify: `src/app/data/exceptions.py`, `src/app/data/__init__.py`
- Create: `src/app/data/panel_store.py`
- Test: `tests/data/test_panel_store.py`

**Interfaces:**
- Consumes: `make_panel`; `app.data.schema.METADATA_COLUMNS/FINANCIAL_COLUMNS/MACRO_COLUMNS`; `Settings.panel_output_path`.
- Produces: `PanelStore(directory: Path)` with `path_for(ticker) -> Path`, `tickers() -> tuple[str, ...]`, `load(ticker) -> pd.DataFrame`, `load_all() -> dict[str, pd.DataFrame]`; `PanelNotFoundError`, `MalformedPanelError` (both `PanelStoreError`).

- [ ] **Step 1: Write the failing tests**

```python
import pandas as pd
import pytest

from app.data.exceptions import MalformedPanelError, PanelNotFoundError
from app.data.panel_store import PanelStore
from app.settings import Settings


def _write(store: PanelStore, panel: pd.DataFrame) -> None:
    panel.assign(date=panel["date"].dt.date).to_parquet(
        store.path_for(panel["ticker"].iloc[0]), index=False
    )


def test_load_returns_datetime_dates(tmp_path, make_panel) -> None:
    store = PanelStore(tmp_path)
    _write(store, make_panel(ticker="AAA"))

    panel = store.load("aaa")

    assert pd.api.types.is_datetime64_any_dtype(panel["date"])
    assert len(panel) == 24


def test_missing_file_names_the_ticker(tmp_path) -> None:
    with pytest.raises(PanelNotFoundError, match="ZZZ"):
        PanelStore(tmp_path).load("zzz")


def test_missing_column_is_named(tmp_path, make_panel) -> None:
    store = PanelStore(tmp_path)
    _write(store, make_panel(ticker="AAA").drop(columns=["vix"]))

    with pytest.raises(MalformedPanelError, match="vix"):
        store.load("AAA")


def test_gap_in_quarters_is_rejected(tmp_path, make_panel) -> None:
    store = PanelStore(tmp_path)
    _write(store, make_panel(ticker="AAA").drop(index=5))

    with pytest.raises(MalformedPanelError, match="consecutive"):
        store.load("AAA")


def test_duplicate_dates_are_rejected(tmp_path, make_panel) -> None:
    panel = make_panel(ticker="AAA")
    panel.loc[3, "date"] = panel.loc[2, "date"]
    store = PanelStore(tmp_path)
    _write(store, panel)

    with pytest.raises(MalformedPanelError, match="consecutive"):
        store.load("AAA")


def test_load_all_keys_every_panel_on_disk(tmp_path, make_panel) -> None:
    store = PanelStore(tmp_path)
    for ticker in ("BBB", "AAA"):
        _write(store, make_panel(ticker=ticker))

    assert store.tickers() == ("AAA", "BBB")
    assert set(store.load_all()) == {"AAA", "BBB"}


def test_missing_directory_holds_no_tickers(tmp_path) -> None:
    assert PanelStore(tmp_path / "absent").tickers() == ()


def test_file_naming_matches_the_ingestion_writer(tmp_path) -> None:
    store = PanelStore(Settings.panel_output_path("AAPL").parent)

    assert store.path_for("aapl") == Settings.panel_output_path("AAPL")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/data/test_panel_store.py -v`
Expected: FAIL, `ModuleNotFoundError: app.data.panel_store`.

- [ ] **Step 3: Implement.** Append to `data/exceptions.py`:

```python
class PanelStoreError(Exception):
    """Base error for reading stored panels."""


class PanelNotFoundError(PanelStoreError):
    """Raised when no panel file exists for a ticker."""


class MalformedPanelError(PanelStoreError):
    """Raised when a stored panel breaks the schema or the quarterly calendar."""
```

`data/panel_store.py`:

```python
from pathlib import Path
from typing import Final

import pandas as pd

from app.data.exceptions import MalformedPanelError, PanelNotFoundError
from app.data.schema import FINANCIAL_COLUMNS, MACRO_COLUMNS, METADATA_COLUMNS

REQUIRED_COLUMNS: Final = (*METADATA_COLUMNS, *FINANCIAL_COLUMNS, *MACRO_COLUMNS)
_PANEL_SUFFIX: Final = "_panel.parquet"


def _require_columns(ticker: str, panel: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in panel.columns]
    if missing:
        message = f"Panel for {ticker} is missing columns: {', '.join(missing)}"
        raise MalformedPanelError(message)


def _require_consecutive_quarter_ends(ticker: str, dates: pd.Series) -> None:
    expected = pd.date_range(dates.iloc[0], periods=len(dates), freq="QE")
    if not (dates.reset_index(drop=True) == pd.Series(expected)).all():
        message = f"Panel for {ticker} does not hold consecutive calendar quarter-ends"
        raise MalformedPanelError(message)


class PanelStore:
    """Read the per-company panel parquet files that ``write_panel`` produces."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def path_for(self, ticker: str) -> Path:
        return self._directory / f"{ticker.upper()}{_PANEL_SUFFIX}"

    def tickers(self) -> tuple[str, ...]:
        names = (path.name for path in self._directory.glob(f"*{_PANEL_SUFFIX}"))
        return tuple(sorted(name.removesuffix(_PANEL_SUFFIX) for name in names))

    def load(self, ticker: str) -> pd.DataFrame:
        """Load and validate one company's panel.

        Returns:
            The panel with ``date`` as datetime, one row per quarter.
        """
        path = self.path_for(ticker)
        if not path.exists():
            message = f"No panel for {ticker.upper()} at {path}"
            raise PanelNotFoundError(message)
        panel = pd.read_parquet(path)
        _require_columns(ticker.upper(), panel)
        panel["date"] = pd.to_datetime(panel["date"])
        _require_consecutive_quarter_ends(ticker.upper(), panel["date"])
        return panel

    def load_all(self) -> dict[str, pd.DataFrame]:
        return {ticker: self.load(ticker) for ticker in self.tickers()}
```

In `data/__init__.py` add `from app.data.panel_store import PanelStore` and `"PanelStore"` to `__all__`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/data/test_panel_store.py -v`
Expected: 8 passed.

---

### Task 2: Tracking service (R9)

**Files:**
- Create: `src/app/services/tracking/{__init__,exceptions,config,wandb_tracker}.py`, `tests/services/tracking/{__init__,test_config,test_wandb_tracker}.py`
- Modify: `src/app/injections/production.py`

**Interfaces:**
- Produces:
  - `run_name(*, notebook: str, model: str, variable: str, protocol: Literal["A","B"] | None = None, history_len: int | None = None) -> str`
  - `RunConfig(panel_size: int, n_rows: int, target_variable: str | None = None, target_transform: str | None = None, feature_groups: tuple[str, ...] = (), n_features: int | None = None, protocol: Literal["A","B"] | None = None, history_len: int | None = None, horizon: int | None = None, macro_source: Literal["final_revised","point_in_time"] = "final_revised", harness_version: str | None = None, seed: int = 42)`
  - `WandbSettings(project: str, entity: str | None, mode: Literal["online","offline","disabled"], api_key: str, run_directory: Path)`
  - `WandbTracker(settings: WandbSettings)` (Pydantic model): `start_run(name: str, config: RunConfig, *, job_type: str)` yields a `WandbRun` with `log_metrics`, `log_table`, `log_figure`, `log_dataset`; tests install a fake `wandb` in `sys.modules`
  - `TrackingUnavailableError`, `MissingApiKeyError`, `InvalidRunNameError`

- [ ] **Step 1: Write the failing config tests** (`tests/services/tracking/test_config.py`)

```python
import pytest
from pydantic import ValidationError

from app.services.tracking import InvalidRunNameError, RunConfig, run_name


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            {"notebook": "nb01", "model": "eda", "variable": "revenue_usd_m"},
            "nb01-eda-revenue",
        ),
        (
            {
                "notebook": "nb04",
                "model": "lgbm_resid",
                "variable": "revenue_usd_m",
                "protocol": "A",
            },
            "nb04-lgbm_resid-revenue-A",
        ),
        (
            {
                "notebook": "nb04",
                "model": "lgbm_resid",
                "variable": "revenue_usd_m",
                "protocol": "B",
                "history_len": 12,
            },
            "nb04-lgbm_resid-revenue-B-H12",
        ),
    ],
)
def test_run_name_follows_master_plan(kwargs, expected) -> None:
    assert run_name(**kwargs) == expected


def test_history_length_needs_protocol_b() -> None:
    with pytest.raises(InvalidRunNameError):
        run_name(
            notebook="nb04",
            model="m",
            variable="revenue_usd_m",
            protocol="A",
            history_len=8,
        )


def test_run_config_dumps_master_plan_keys() -> None:
    config = RunConfig(panel_size=60, n_rows=4860, target_variable="revenue_usd_m")

    assert config.model_dump(mode="json") == {
        "panel_size": 60,
        "n_rows": 4860,
        "target_variable": "revenue_usd_m",
        "target_transform": None,
        "feature_groups": [],
        "n_features": None,
        "protocol": None,
        "history_len": None,
        "horizon": None,
        "macro_source": "final_revised",
        "harness_version": None,
        "seed": 42,
    }


def test_run_config_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        RunConfig(panel_size=1, n_rows=1, target_variable="x", surprise=1)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/services/tracking/test_config.py -v`
Expected: FAIL, import error.

- [ ] **Step 3: Implement config and exceptions**

`exceptions.py`:

```python
class TrackingError(Exception):
    """Base error for experiment tracking."""


class TrackingUnavailableError(TrackingError):
    """Raised when the tracking backend is not installed."""


class MissingApiKeyError(TrackingError):
    """Raised when online tracking is requested without an API key."""


class InvalidRunNameError(TrackingError):
    """Raised when run-name parts contradict each other."""
```

`config.py`:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict

Protocol = Literal["A", "B"]


def run_name(
    *,
    notebook: str,
    model: str,
    variable: str,
    protocol: Protocol | None = None,
    history_len: int | None = None,
) -> str:
    """Build the W&B run name of master plan §2.3.

    Returns:
        ``{notebook}-{model}-{variable}[-{protocol}[-H{history_len}]]``.
    """
    if history_len is not None and protocol != "B":
        message = "history_len only applies to protocol B"
        raise InvalidRunNameError(message)
    parts = [notebook, model, variable.removesuffix("_usd_m")]
    if protocol is not None:
        parts.append(protocol)
    if history_len is not None:
        parts.append(f"H{history_len}")
    return "-".join(parts)


class RunConfig(BaseModel):
    """The config logged on every run so results stay comparable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    panel_size: int
    n_rows: int
    target_variable: str | None = None
    target_transform: str | None = None
    feature_groups: tuple[str, ...] = ()
    n_features: int | None = None
    protocol: Protocol | None = None
    history_len: int | None = None
    horizon: int | None = None
    macro_source: Literal["final_revised", "point_in_time"] = "final_revised"
    harness_version: str | None = None
    seed: int = 42
```

(add `from app.services.tracking.exceptions import InvalidRunNameError`). `__init__.py` re-exports `RunConfig`, `run_name`, the four exceptions, `WandbSettings`, `WandbTracker`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/services/tracking/test_config.py -v`
Expected: 6 passed.

- [ ] **Step 5: Write the failing tracker tests** (`tests/services/tracking/test_wandb_tracker.py`). The fake stands in for the `wandb` module; nothing needs installing.

```python
import sys
from types import ModuleType

import pandas as pd
import pytest

from app.injections.production import Container
from app.services.tracking import (
    MissingApiKeyError,
    RunConfig,
    TrackingUnavailableError,
    WandbTracker,
)

CONFIG = RunConfig(panel_size=2, n_rows=48, target_variable="revenue_usd_m")


class _FakeRun:
    def __init__(self) -> None:
        self.logged: list[dict[str, object]] = []
        self.artifacts: list[object] = []
        self.finished = False

    def log(self, data: dict[str, object]) -> None:
        self.logged.append(data)

    def log_artifact(self, artifact: object) -> None:
        self.artifacts.append(artifact)

    def finish(self) -> None:
        self.finished = True


class _FakeArtifact:
    def __init__(self, name: str, kind: str) -> None:
        self.name, self.type, self.files = name, kind, []

    def add_file(self, path: str) -> None:
        self.files.append(path)


def _fake_wandb() -> tuple[ModuleType, _FakeRun, dict[str, object]]:
    module, run, seen = ModuleType("wandb"), _FakeRun(), {}

    def init(**kwargs: object) -> _FakeRun:
        seen["init"] = kwargs
        return run

    def login(*, key: str) -> None:
        seen["login"] = key

    module.init, module.login = init, login
    module.Artifact = lambda name, type: _FakeArtifact(name, type)
    module.Table = lambda dataframe: ("table", len(dataframe))
    module.Image = lambda figure: ("image", figure)
    return module, run, seen


def _tracker(module: ModuleType, *, mode="offline", api_key="") -> WandbTracker:
    return WandbTracker(
        project="cfo-copilot",
        entity=None,
        mode=mode,
        api_key=api_key,
        load_wandb=lambda: module,
    )
```

The fake `wandb.Artifact` takes the real keyword `type`; the lambda forwards it to a class whose parameter is `kind`, so no builtin is shadowed in a `def`. The tests:

```python
def test_run_receives_name_config_and_mode() -> None:
    module, _, seen = _fake_wandb()

    with _tracker(module).start_run("nb01-eda-revenue", CONFIG, job_type="eda"):
        pass

    assert seen["init"] == {
        "project": "cfo-copilot",
        "entity": None,
        "name": "nb01-eda-revenue",
        "job_type": "eda",
        "config": CONFIG.model_dump(mode="json"),
        "mode": "offline",
    }


def test_run_finishes_when_the_body_raises() -> None:
    module, run, _ = _fake_wandb()

    with (
        pytest.raises(RuntimeError),
        _tracker(module).start_run("r", CONFIG, job_type="eda"),
    ):
        raise RuntimeError

    assert run.finished


def test_table_and_metrics_are_logged() -> None:
    module, run, _ = _fake_wandb()

    with _tracker(module).start_run("r", CONFIG, job_type="eda") as tracked:
        tracked.log_table("diagnostics", pd.DataFrame({"a": [1, 2]}))
        tracked.log_metrics({"n_ok": 3.0})

    assert run.logged == [{"diagnostics": ("table", 2)}, {"n_ok": 3.0}]


def test_dataset_is_logged_as_an_artifact(tmp_path) -> None:
    module, run, _ = _fake_wandb()
    path = tmp_path / "features_h1.parquet"

    with _tracker(module).start_run("r", CONFIG, job_type="features") as tracked:
        tracked.log_dataset("features_h1", path)

    (artifact,) = run.artifacts
    assert (artifact.name, artifact.type, artifact.files) == (
        "features_h1",
        "dataset",
        [str(path)],
    )


def test_online_without_key_fails_before_any_run() -> None:
    module, _, seen = _fake_wandb()

    with pytest.raises(MissingApiKeyError, match="WANDB_API_KEY"):
        _tracker(module, mode="online").start_run(
            "r", CONFIG, job_type="eda"
        ).__enter__()

    assert "init" not in seen


def test_online_logs_in_with_the_configured_key() -> None:
    module, _, seen = _fake_wandb()

    with _tracker(module, mode="online", api_key="secret").start_run(
        "r", CONFIG, job_type="eda"
    ):
        pass

    assert seen["login"] == "secret"


def test_offline_never_logs_in() -> None:
    module, _, seen = _fake_wandb()

    with _tracker(module).start_run("r", CONFIG, job_type="eda"):
        pass

    assert "login" not in seen


def test_container_builds_the_tracker_without_wandb_installed(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "wandb", None)

    tracker = Container().experiment_tracker()

    assert isinstance(tracker, WandbTracker)
    with pytest.raises(TrackingUnavailableError, match="research"):
        tracker.start_run("r", CONFIG, job_type="eda").__enter__()
```

- [ ] **Step 6: Run to verify failure**

Run: `uv run pytest tests/services/tracking/test_wandb_tracker.py -v`
Expected: FAIL, `cannot import name 'WandbTracker'`.

- [ ] **Step 7: Implement.** No tracker Protocols: nothing consumed them, and the
lazy import alone keeps the Docker image booting. `WandbTracker` is a frozen
Pydantic model holding `WandbSettings`; the shipped code in
`src/app/services/tracking/wandb_tracker.py` supersedes the sketch below.

`wandb_tracker.py`:

```python
import importlib
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Literal, Protocol

import pandas as pd
from matplotlib.figure import Figure

from app.services.tracking.config import RunConfig
from app.services.tracking.exceptions import (
    MissingApiKeyError,
    TrackingUnavailableError,
)


class _RawRun(Protocol):
    def log(self, data: dict[str, object]) -> None: ...
    def log_artifact(self, artifact: object) -> None: ...
    def finish(self) -> None: ...


def import_wandb() -> ModuleType:
    """Import wandb on first use so the image runs without the research group.

    Returns:
        The imported ``wandb`` module.
    """
    try:
        return importlib.import_module("wandb")
    except ImportError as error:
        message = "wandb is not installed; run `uv sync --group research`"
        raise TrackingUnavailableError(message) from error


class WandbRun:
    def __init__(self, run: _RawRun, wandb: ModuleType) -> None:
        self._run = run
        self._wandb = wandb

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        self._run.log(dict(metrics))

    def log_table(self, name: str, table: pd.DataFrame) -> None:
        self._run.log({name: self._wandb.Table(dataframe=table)})

    def log_figure(self, name: str, figure: Figure) -> None:
        self._run.log({name: self._wandb.Image(figure)})

    def log_dataset(self, name: str, path: Path) -> None:
        artifact = self._wandb.Artifact(name, type="dataset")
        artifact.add_file(str(path))
        self._run.log_artifact(artifact)


class WandbTracker:
    """Start W&B runs; offline mode keeps a tracking outage from blocking work."""

    def __init__(
        self,
        *,
        project: str,
        entity: str | None,
        mode: Literal["online", "offline", "disabled"],
        api_key: str,
        load_wandb: Callable[[], ModuleType] = import_wandb,
    ) -> None:
        self._project = project
        self._entity = entity
        self._mode = mode
        self._api_key = api_key
        self._load_wandb = load_wandb

    @contextmanager
    def start_run(
        self, name: str, config: RunConfig, *, job_type: str
    ) -> Iterator[WandbRun]:
        wandb = self._load_wandb()
        self._login_when_online(wandb)
        run = wandb.init(
            project=self._project,
            entity=self._entity,
            name=name,
            job_type=job_type,
            config=config.model_dump(mode="json"),
            mode=self._mode,
        )
        try:
            yield WandbRun(run, wandb)
        finally:
            run.finish()

    def _login_when_online(self, wandb: ModuleType) -> None:
        if self._mode != "online":
            return
        if not self._api_key:
            message = "WANDB_MODE is online but WANDB_API_KEY is empty; set it in .env"
            raise MissingApiKeyError(message)
        wandb.login(key=self._api_key)
```

`_login_when_online` has no `self` use beyond attributes, so `PLR6301` is satisfied. Production wiring, in `injections/production.py`:

```python
from app.data.panel_store import PanelStore
from app.services.tracking import WandbTracker
...
    panel_store = providers.Factory(
        PanelStore, directory=Settings.DATA_DIRECTORY / "processed"
    )
    experiment_tracker = providers.Factory(
        WandbTracker,
        project=Settings.WANDB_PROJECT,
        entity=Settings.WANDB_ENTITY or None,
        mode=Settings.WANDB_MODE,
        api_key=Settings.WANDB_API_KEY,
    )
```

`panel_store` is wired here because it is the notebook's other collaborator; its behaviour was tested in Task 1.

- [ ] **Step 8: Run to verify pass**

Run: `uv run pytest tests/services/tracking -v && uv run poe typecheck`
Expected: all pass; mypy clean.

---

### Task 3: Consolidation (R2, R3)

**Files:**
- Modify: `src/app/data/exceptions.py`, `src/app/data/__init__.py`
- Create: `src/app/data/consolidation.py`
- Test: `tests/data/test_consolidation.py`

**Interfaces:**
- Consumes: `make_panel`; `MACRO_COLUMNS`.
- Produces: `consolidate_panels(panels: Mapping[str, pd.DataFrame]) -> ConsolidatedPanels`, where `ConsolidatedPanels(NamedTuple)` has `panel_long: pd.DataFrame` and `macro_q: pd.DataFrame`; `ConsolidationError`, `MacroMismatchError(ConsolidationError)`; `DROPPED_CONSTANT_COLUMNS = ("is_public",)`.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from app.data.consolidation import consolidate_panels
from app.data.exceptions import ConsolidationError, MacroMismatchError
from app.data.schema import MACRO_COLUMNS


@pytest.fixture
def panels(make_panel):
    return {
        "BBB": make_panel(ticker="BBB", quarters=8),
        "AAA": make_panel(ticker="AAA", quarters=8),
    }


def test_panel_long_holds_every_row_sorted_by_ticker_then_date(panels) -> None:
    panel_long = consolidate_panels(panels).panel_long

    assert len(panel_long) == 16
    assert panel_long["ticker"].tolist() == ["AAA"] * 8 + ["BBB"] * 8
    assert panel_long.equals(
        panel_long.sort_values(["ticker", "date"], ignore_index=True)
    )


def test_macro_lives_once_in_macro_q(panels) -> None:
    result = consolidate_panels(panels)

    assert list(result.macro_q.columns) == ["date", *MACRO_COLUMNS]
    assert len(result.macro_q) == 8
    assert not set(MACRO_COLUMNS) & set(result.panel_long.columns)


def test_is_public_is_dropped(panels) -> None:
    assert "is_public" not in consolidate_panels(panels).panel_long.columns


def test_a_varying_is_public_is_refused(panels) -> None:
    panels["AAA"].loc[0, "is_public"] = False

    with pytest.raises(ConsolidationError, match="is_public"):
        consolidate_panels(panels)


def test_differing_macro_names_the_company(panels) -> None:
    panels["BBB"].loc[3, "vix"] += 1.0

    with pytest.raises(MacroMismatchError, match="BBB"):
        consolidate_panels(panels)


def test_no_panels_is_refused() -> None:
    with pytest.raises(ConsolidationError):
        consolidate_panels({})
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/data/test_consolidation.py -v`
Expected: FAIL, `ModuleNotFoundError: app.data.consolidation`.

- [ ] **Step 3: Implement.** Append to `data/exceptions.py`:

```python
class ConsolidationError(Exception):
    """Base error for building the consolidated panel and its flags."""


class MacroMismatchError(ConsolidationError):
    """Raised when companies disagree on the shared macro block."""
```

`data/consolidation.py`:

```python
from collections.abc import Mapping
from typing import Final, NamedTuple

import pandas as pd

from app.data.exceptions import ConsolidationError, MacroMismatchError
from app.data.schema import MACRO_COLUMNS

DROPPED_CONSTANT_COLUMNS: Final = ("is_public",)
_MACRO_FRAME_COLUMNS: Final = ["date", *MACRO_COLUMNS]


class ConsolidatedPanels(NamedTuple):
    panel_long: pd.DataFrame
    macro_q: pd.DataFrame


def _shared_macro(panels: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    reference_ticker, reference = next(iter(panels.items()))
    reference_macro = reference[_MACRO_FRAME_COLUMNS].reset_index(drop=True)
    differing = [
        ticker
        for ticker, panel in panels.items()
        if not panel[_MACRO_FRAME_COLUMNS]
        .reset_index(drop=True)
        .equals(reference_macro)
    ]
    if differing:
        message = (
            f"macro block differs from {reference_ticker} for: {', '.join(differing)}"
        )
        raise MacroMismatchError(message)
    return reference_macro


def _require_constant(panel: pd.DataFrame, columns: tuple[str, ...]) -> None:
    varying = [column for column in columns if panel[column].nunique(dropna=False) != 1]
    if varying:
        message = f"refusing to drop columns that vary: {', '.join(varying)}"
        raise ConsolidationError(message)


def consolidate_panels(panels: Mapping[str, pd.DataFrame]) -> ConsolidatedPanels:
    """Stack the per-company panels and split the shared macro block out.

    Returns:
        ``panel_long`` sorted by ticker and date without macro or constant
        columns, and ``macro_q`` with one row per quarter.
    """
    if not panels:
        message = "no panels to consolidate"
        raise ConsolidationError(message)
    macro_q = _shared_macro(panels)
    stacked = pd.concat(panels.values(), ignore_index=True)
    _require_constant(stacked, DROPPED_CONSTANT_COLUMNS)
    panel_long = stacked.drop(columns=[*MACRO_COLUMNS, *DROPPED_CONSTANT_COLUMNS])
    return ConsolidatedPanels(
        panel_long=panel_long.sort_values(["ticker", "date"], ignore_index=True),
        macro_q=macro_q,
    )
```

Add `from app.data.consolidation import consolidate_panels` and the name to `data/__init__.py`'s `__all__`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/data/test_consolidation.py -v`
Expected: 6 passed.

---

### Task 4: Flags and structural breaks (R4–R7)

**Files:**
- Create: `src/app/data/flags.py`, `src/app/data/structural_breaks.py`, `config/structural_breaks.yaml`
- Modify: `src/app/data/__init__.py`, `src/app/injections/production.py`
- Test: `tests/data/test_flags.py`, `tests/data/test_structural_breaks.py`

**Interfaces:**
- Consumes: `consolidate_panels` (to build a `panel_long` in tests), `ConsolidationError`, `Settings.STRUCTURAL_BREAKS_PATH`.
- Produces:
  - `load_structural_breaks(path: Path) -> dict[str, tuple[date, ...]]`
  - `covid_flag(dates: pd.Series) -> pd.Series`
  - `is_projected(dates: pd.Series, *, last_reported_quarter: date) -> pd.Series`
  - `structural_break_flag(dates: pd.Series, break_quarters: Sequence[date]) -> pd.Series`
  - `outlier_flag(panel: pd.DataFrame, *, contamination: float = 0.03, seed: int = 42) -> pd.Series`
  - `add_flags(panel_long: pd.DataFrame, breaks: Mapping[str, Sequence[date]], *, last_reported_quarter: date, contamination: float = 0.03, seed: int = 42) -> pd.DataFrame`, adding boolean columns `covid`, `structural_break`, `outlier_flag`, `is_projected`, same index as the input
  - constants `BREAK_WINDOW_QUARTERS = 4`, `MIN_OUTLIER_ROWS = 16`

- [ ] **Step 1: Write the failing structural-break loader tests** (`tests/data/test_structural_breaks.py`)

```python
from datetime import date

import pytest
from pydantic import ValidationError

from app.data.structural_breaks import load_structural_breaks
from app.settings import Settings


def _write(tmp_path, text: str):
    path = tmp_path / "breaks.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_sorted_quarters_by_ticker(tmp_path) -> None:
    path = _write(
        tmp_path, "breaks:\n  ABT: [2013-03-31]\n  GE: [2024-06-30, 2023-03-31]\n"
    )

    assert load_structural_breaks(path) == {
        "ABT": (date(2013, 3, 31),),
        "GE": (date(2023, 3, 31), date(2024, 6, 30)),
    }


def test_a_date_that_is_not_a_quarter_end_is_refused(tmp_path) -> None:
    with pytest.raises(ValidationError, match="quarter"):
        load_structural_breaks(_write(tmp_path, "breaks:\n  ABT: [2013-03-15]\n"))


def test_unknown_keys_are_refused(tmp_path) -> None:
    with pytest.raises(ValidationError):
        load_structural_breaks(_write(tmp_path, "breaks: {}\nsurprise: 1\n"))


def test_the_shipped_file_names_only_registry_tickers(company_registry) -> None:
    breaks = load_structural_breaks(Settings.STRUCTURAL_BREAKS_PATH)
    registry_tickers = {
        ticker for company in company_registry.companies for ticker in company.tickers
    }

    assert set(breaks) <= registry_tickers
```

- [ ] **Step 2: Write the failing flag tests** (`tests/data/test_flags.py`)

```python
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.data.consolidation import consolidate_panels
from app.data.exceptions import ConsolidationError
from app.data.flags import (
    add_flags,
    covid_flag,
    is_projected,
    outlier_flag,
    structural_break_flag,
)


def _dates(quarters: int, start: str = "2019-03-31") -> pd.Series:
    return pd.Series(pd.date_range(start, periods=quarters, freq="QE"))


def _margin_panel(quarters: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "revenue_usd_m": 100 * np.exp(0.02 * np.arange(quarters)),
        "gross_margin": 0.4 + 0.01 * rng.normal(size=quarters),
        "operating_margin": 0.2 + 0.01 * rng.normal(size=quarters),
        "net_margin": 0.1 + 0.01 * rng.normal(size=quarters),
    })


def test_covid_marks_exactly_the_three_2020_quarters() -> None:
    dates = _dates(12)

    flagged = dates[covid_flag(dates)]

    assert flagged.dt.strftime("%Y-%m-%d").tolist() == [
        "2020-06-30",
        "2020-09-30",
        "2020-12-31",
    ]


def test_projected_means_after_the_last_reported_quarter() -> None:
    dates = _dates(4, start="2026-03-31")

    projected = is_projected(dates, last_reported_quarter=date(2026, 6, 30))

    assert projected.tolist() == [False, False, True, True]


def test_a_break_covers_its_quarter_and_the_next_three() -> None:
    flagged = structural_break_flag(_dates(12), [date(2020, 3, 31)])

    assert flagged.to_numpy().nonzero()[0].tolist() == [4, 5, 6, 7]


def test_two_breaks_flag_both_windows() -> None:
    flagged = structural_break_flag(_dates(12), [date(2019, 6, 30), date(2021, 3, 31)])

    assert flagged.to_numpy().nonzero()[0].tolist() == [1, 2, 3, 4, 8, 9, 10, 11]


def test_an_extreme_margin_is_flagged() -> None:
    panel = _margin_panel()
    panel.loc[35, "net_margin"] = 0.9

    assert outlier_flag(panel).loc[35]


def test_only_a_small_share_is_flagged() -> None:
    assert outlier_flag(_margin_panel()).sum() <= math.ceil(0.03 * 36) + 1


def test_a_short_history_gets_no_flags() -> None:
    assert outlier_flag(_margin_panel(quarters=10)).sum() == 0


def test_rows_missing_an_input_are_never_flagged() -> None:
    panel = _margin_panel()
    panel.loc[20, "net_margin"] = np.nan

    assert not outlier_flag(panel).loc[20]


def test_the_same_seed_gives_the_same_flags() -> None:
    panel = _margin_panel()

    pd.testing.assert_series_equal(outlier_flag(panel), outlier_flag(panel))


@pytest.fixture
def panel_long(make_panel) -> pd.DataFrame:
    panels = {"AAA": make_panel(ticker="AAA"), "BBB": make_panel(ticker="BBB")}
    return consolidate_panels(panels).panel_long


def test_add_flags_adds_four_boolean_columns_and_keeps_the_index(panel_long) -> None:
    flagged = add_flags(panel_long, {}, last_reported_quarter=date(2100, 1, 1))

    assert flagged.index.equals(panel_long.index)
    assert (
        flagged[["covid", "structural_break", "outlier_flag", "is_projected"]]
        .dtypes.eq(bool)
        .all()
    )
    assert flagged["covid"].sum() == 6


def test_a_break_applies_to_its_own_company_only(panel_long) -> None:
    flagged = add_flags(
        panel_long,
        {"AAA": (date(2015, 12, 31),)},
        last_reported_quarter=date(2100, 1, 1),
    )

    assert flagged.groupby("ticker")["structural_break"].sum().to_dict() == {
        "AAA": 4,
        "BBB": 0,
    }


def test_a_break_for_an_unknown_company_is_refused(panel_long) -> None:
    with pytest.raises(ConsolidationError, match="ZZZ"):
        add_flags(
            panel_long,
            {"ZZZ": (date(2015, 12, 31),)},
            last_reported_quarter=date(2100, 1, 1),
        )
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/data/test_structural_breaks.py tests/data/test_flags.py -v`
Expected: FAIL, import errors.

- [ ] **Step 4: Implement.** `config/structural_breaks.yaml`:

```yaml
# Quarter in which a spin-off, merger or reorganisation broke the comparability
# of year-over-year figures. Master plan §3.4. Add a company by editing this file.
# GE: master says "2023-24"; these two quarters are proposed, please confirm.
breaks:
  ABT: [2013-03-31]
  BMY: [2019-12-31]
  PFE: [2020-12-31]
  MRK: [2021-06-30]
  T: [2022-06-30]
  GE: [2023-03-31, 2024-06-30]
```

`data/structural_breaks.py`:

```python
from datetime import date
from pathlib import Path
from typing import Annotated

import pandas as pd
import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict


def _require_quarter_ends(
    breaks: dict[str, tuple[date, ...]],
) -> dict[str, tuple[date, ...]]:
    off_calendar = [
        f"{ticker} {quarter}"
        for ticker, quarters in breaks.items()
        for quarter in quarters
        if not pd.Timestamp(quarter).is_quarter_end
    ]
    if off_calendar:
        message = f"not a calendar quarter end: {', '.join(off_calendar)}"
        raise ValueError(message)
    return breaks


_QuarterEndBreaks = Annotated[
    dict[str, tuple[date, ...]], AfterValidator(_require_quarter_ends)
]


class _BreaksConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    breaks: _QuarterEndBreaks


def load_structural_breaks(path: Path) -> dict[str, tuple[date, ...]]:
    """Load the hand-entered break quarters.

    Returns:
        Sorted break quarters keyed by upper-case ticker.
    """
    config = _BreaksConfig.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    return {
        ticker.upper(): tuple(sorted(quarters))
        for ticker, quarters in config.breaks.items()
    }
```

The `ValueError` inside the validator is pydantic's contract for reporting a bad field (it becomes a `ValidationError`); it is not the data-layer error the project rule forbids.

`data/flags.py`:

```python
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Final

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.data.exceptions import ConsolidationError

BREAK_WINDOW_QUARTERS: Final = 4
MIN_OUTLIER_ROWS: Final = 16
_COVID_QUARTERS: Final = tuple(
    pd.to_datetime(["2020-06-30", "2020-09-30", "2020-12-31"])
)
_MARGIN_INPUTS: Final = ["gross_margin", "operating_margin", "net_margin"]
_YOY_LAG: Final = 4


def covid_flag(dates: pd.Series) -> pd.Series:
    return dates.isin(_COVID_QUARTERS)


def is_projected(dates: pd.Series, *, last_reported_quarter: date) -> pd.Series:
    return dates > pd.Timestamp(last_reported_quarter)


def structural_break_flag(
    dates: pd.Series, break_quarters: Sequence[date]
) -> pd.Series:
    """Flag each break quarter and the next three, where YoY spans the break.

    Returns:
        A boolean series aligned to ``dates``.
    """
    flagged = pd.Series(data=False, index=dates.index)
    for quarter in break_quarters:
        window_start = pd.Timestamp(quarter)
        window_end = window_start + pd.offsets.QuarterEnd(BREAK_WINDOW_QUARTERS - 1)
        flagged |= dates.between(window_start, window_end)
    return flagged


def outlier_flag(
    panel: pd.DataFrame, *, contamination: float = 0.03, seed: int = 42
) -> pd.Series:
    """Flag unusual quarters with an Isolation Forest; the flag removes nothing.

    Fitted on the whole history, so it depends on later quarters and must not
    be used as a model feature.

    Returns:
        A boolean series aligned to ``panel``; rows missing an input are False.
    """
    revenue = panel["revenue_usd_m"]
    revenue_yoy_growth = np.log(revenue.where(revenue > 0)).diff(_YOY_LAG)
    inputs = (
        panel[_MARGIN_INPUTS].assign(revenue_yoy_growth=revenue_yoy_growth).dropna()
    )
    flagged = pd.Series(data=False, index=panel.index)
    if len(inputs) < MIN_OUTLIER_ROWS:
        return flagged
    standardized = (inputs - inputs.mean()) / inputs.std()
    labels = IsolationForest(
        contamination=contamination, random_state=seed
    ).fit_predict(standardized)
    flagged.loc[inputs.index[labels == -1]] = True
    return flagged


def _flag_company(
    company: pd.DataFrame,
    break_quarters: Sequence[date],
    *,
    last_reported_quarter: date,
    contamination: float,
    seed: int,
) -> pd.DataFrame:
    return company.assign(
        covid=covid_flag(company["date"]),
        structural_break=structural_break_flag(company["date"], break_quarters),
        outlier_flag=outlier_flag(company, contamination=contamination, seed=seed),
        is_projected=is_projected(
            company["date"], last_reported_quarter=last_reported_quarter
        ),
    )


def add_flags(
    panel_long: pd.DataFrame,
    breaks: Mapping[str, Sequence[date]],
    *,
    last_reported_quarter: date,
    contamination: float = 0.03,
    seed: int = 42,
) -> pd.DataFrame:
    """Add the four NB00 flag columns company by company.

    Returns:
        ``panel_long`` with ``covid``, ``structural_break``, ``outlier_flag``
        and ``is_projected``, in the original row order.
    """
    unknown = sorted(set(breaks) - set(panel_long["ticker"]))
    if unknown:
        message = (
            f"structural breaks for tickers not in the panel: {', '.join(unknown)}"
        )
        raise ConsolidationError(message)
    return pd.concat([
        _flag_company(
            company,
            breaks.get(str(ticker), ()),
            last_reported_quarter=last_reported_quarter,
            contamination=contamination,
            seed=seed,
        )
        for ticker, company in panel_long.groupby("ticker", sort=False)
    ]).loc[panel_long.index]
```

In `production.py` add `from app.data.structural_breaks import load_structural_breaks` and inside `Container`:

```python
    structural_breaks = providers.Singleton(
        load_structural_breaks, Settings.STRUCTURAL_BREAKS_PATH
    )
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/data/test_structural_breaks.py tests/data/test_flags.py -v && uv run poe lint`
Expected: all pass. `flagged |= …` on a bool Series and the final `.loc[panel_long.index]` reorder are the two places most likely to need a small typing fix; fix the code, not the test. If ruff reports `PLR0913` on `add_flags`, collect `contamination` and `seed` into a small frozen Pydantic `OutlierSettings` model rather than suppressing.

---

### Task 5: Missing-value ledger (R8)

**Files:**
- Create: `src/app/data/missing.py`
- Modify: `src/app/data/__init__.py`
- Test: `tests/data/test_missing.py`

**Interfaces:**
- Consumes: `consolidate_panels` (to build a `panel_long`), `FINANCIAL_COLUMNS`.
- Produces: `missing_value_ledger(panel_long: pd.DataFrame) -> pd.DataFrame` with columns `ticker`, `date`, `column`, `reason`; `reason` is one of `pe_undefined_by_rule`, `pre_listing`, `no_filing_data`, `unexplained`. `CHECKED_COLUMNS`.

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np
import pandas as pd
import pytest

from app.data.consolidation import consolidate_panels
from app.data.missing import missing_value_ledger
from app.data.schema import FINANCIAL_COLUMNS


@pytest.fixture
def panel_long(make_panel) -> pd.DataFrame:
    return consolidate_panels({"AAA": make_panel(ticker="AAA", quarters=12)}).panel_long


def _reasons(ledger: pd.DataFrame, column: str) -> list[str]:
    return ledger.loc[ledger["column"] == column, "reason"].tolist()


def test_a_complete_panel_has_an_empty_ledger(panel_long) -> None:
    assert missing_value_ledger(panel_long).empty


def test_pe_with_non_positive_eps_is_explained_by_rule(panel_long) -> None:
    panel_long.loc[4, ["eps", "pe_ratio"]] = [-1.0, np.nan]

    assert _reasons(missing_value_ledger(panel_long), "pe_ratio") == [
        "pe_undefined_by_rule"
    ]


def test_rows_before_the_first_price_are_pre_listing(panel_long) -> None:
    panel_long.loc[:2, ["stock_price_usd", "eps", "market_cap_usd_m", "pe_ratio"]] = (
        np.nan
    )

    ledger = missing_value_ledger(panel_long)

    assert set(ledger.loc[ledger["column"] != "pe_ratio", "reason"]) == {"pre_listing"}


def test_a_row_without_revenue_is_no_filing_data(panel_long) -> None:
    panel_long.loc[5, [*FINANCIAL_COLUMNS, "market_cap_usd_m"]] = np.nan

    assert set(missing_value_ledger(panel_long)["reason"]) == {"no_filing_data"}


def test_an_eps_gap_with_price_and_revenue_is_unexplained(panel_long) -> None:
    panel_long.loc[7, "eps"] = np.nan

    ledger = missing_value_ledger(panel_long)

    assert ledger[["column", "reason"]].to_numpy().tolist() == [["eps", "unexplained"]]
    assert ledger.loc[ledger.index[0], "ticker"] == "AAA"
    assert ledger.loc[ledger.index[0], "date"] == panel_long.loc[7, "date"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/data/test_missing.py -v`
Expected: FAIL, import error.

- [ ] **Step 3: Implement** `data/missing.py`:

```python
from typing import Final

import pandas as pd

from app.data.schema import FINANCIAL_COLUMNS

CHECKED_COLUMNS: Final = (
    *FINANCIAL_COLUMNS,
    "stock_price_usd",
    "dividend_yield",
    "market_cap_usd_m",
    "pe_ratio",
)
_PRE_LISTING_COLUMNS: Final = (
    "stock_price_usd",
    "dividend_yield",
    "market_cap_usd_m",
    "pe_ratio",
    "eps",
)
_FILING_COLUMNS: Final = (*FINANCIAL_COLUMNS, "market_cap_usd_m")


def _reasons(
    column: str, company: pd.DataFrame, first_price_date: pd.Timestamp
) -> pd.Series:
    eps = company["eps"]
    rules = (
        ("pe_undefined_by_rule", column == "pe_ratio", eps.isna() | (eps <= 0)),
        (
            "pre_listing",
            column in _PRE_LISTING_COLUMNS,
            company["date"] < first_price_date,
        ),
        ("no_filing_data", column in _FILING_COLUMNS, company["revenue_usd_m"].isna()),
    )
    reason = pd.Series("unexplained", index=company.index)
    for name, applies, mask in reversed(rules):
        reason = reason.mask(mask & applies, name)
    return reason


def _company_ledger(company: pd.DataFrame) -> pd.DataFrame:
    first_price_date = company.loc[company["stock_price_usd"].notna(), "date"].min()
    frames = []
    for column in CHECKED_COLUMNS:
        missing = company[column].isna()
        reasons = _reasons(column, company, first_price_date)
        frames.append(
            company.loc[missing, ["ticker", "date"]].assign(
                column=column, reason=reasons[missing]
            )
        )
    return pd.concat(frames)


def missing_value_ledger(panel_long: pd.DataFrame) -> pd.DataFrame:
    """List every NaN cell with the reason it is missing.

    Returns:
        One row per NaN cell; ``unexplained`` rows need review or a waiver.
    """
    return pd.concat(
        [
            _company_ledger(company)
            for _, company in panel_long.groupby("ticker", sort=True)
        ],
        ignore_index=True,
    )
```

The rules are ordered: the first that applies wins, which is why the loop runs over `reversed(rules)` and earlier rules overwrite later ones. Export `missing_value_ledger` from `data/__init__.py`.

- [ ] **Step 4: Run to verify pass, then the whole data suite**

Run: `uv run pytest tests/data tests/services/tracking -v`
Expected: all pass.

---

### Task 6: Notebook, acceptance run, hand-over

**Files:**
- Create: `src/app/playground/00_ingest_and_consolidate.ipynb` (markdown boundaries exist already; add the code cells below with `NotebookEdit`)
- Modify (done outside this plan): `docs/CFO_COPILOT_MASTER_PLAN.md` §0.3 records E1's answer

No unit tests for the notebook; the helpers it calls are tested and its cells hold no logic. **Do not execute the notebook yourself.** It reads the real panels and, with `WANDB_MODE=online`, publishes runs; that is the user's call (memory: ask-before-acting).

- [ ] **Step 1: Cell "1. Load panels"**

```python
from app.data import write_panel
from app.data.consolidation import consolidate_panels
from app.data.flags import add_flags
from app.data.missing import missing_value_ledger
from app.injections import configure_container
from app.services.tracking import RunConfig, run_name
from app.settings import Settings

container = configure_container()
tracker = container.experiment_tracker()
panels = container.panel_store().load_all()

n_rows = sum(len(panel) for panel in panels.values())
assert len(panels) == 60 and all(len(panel) == 81 for panel in panels.values())  # A1
```

- [ ] **Step 2: Cell "2. Consolidate and flag"**

```python
consolidated = consolidate_panels(panels)
macro_q = consolidated.macro_q
panel_long = add_flags(
    consolidated.panel_long,
    container.structural_breaks(),
    last_reported_quarter=Settings.LAST_REPORTED_QUARTER,
)

assert len(panel_long) == n_rows and len(macro_q) == 81  # A2
assert "is_public" not in panel_long.columns
assert not panel_long["is_projected"].any()  # A3
assert panel_long["covid"].sum() == 180  # A4
assert panel_long["structural_break"].sum() == 28  # A5
amzn_latest = panel_long.query("ticker == 'AMZN' and date == '2026-06-30'")
assert amzn_latest["outlier_flag"].item()  # A6
```

- [ ] **Step 3: Cell "3. Missing-value ledger"**

```python
ledger = missing_value_ledger(panel_long)
ledger.groupby(["column", "reason"]).size()  # A7
ledger.query("reason == 'unexplained'")
```

Follow with a markdown cell listing each `unexplained` row and its resolution (fixed by re-ingestion, or waived and why). Expected today: COST EPS (9 quarters) and COST EBITDA (2026-06-30).

- [ ] **Step 4: Cell "4. Save and track"**

```python
config = RunConfig(panel_size=len(panels), n_rows=n_rows)
flag_counts = (
    panel_long[["covid", "structural_break", "outlier_flag", "is_projected"]]
    .sum()
    .rename("rows")
    .reset_index(names="flag")
)
with tracker.start_run(
    run_name(notebook="nb00", model="ingest", variable="panel"),
    config,
    job_type="consolidate",
) as run:
    run.log_table("missing_value_ledger", ledger)
    run.log_table("flag_counts", flag_counts)
    run.log_dataset("panel_long", write_panel(panel_long, Settings.PANEL_LONG_PATH))
    run.log_dataset("macro_q", write_panel(macro_q, Settings.MACRO_Q_PATH))
```

- [ ] **Step 5: Markdown cell "E1 and known limitation"**, stating (A10): E1 answered on 2026-09-23 — 2026-Q2 is reported, 2026-Q3 is the forecast quarter, `LAST_REPORTED_QUARTER = 2026-06-30`; and the fiscal-calendar limitation from the spec (dates snapped within 46 days of a calendar quarter end; macro alignment inherits that margin).

- [ ] **Step 6: Static checks (A9, A10)**

Run:

```bash
uv run python -c "import json,sys; nb=json.load(open('src/app/playground/00_ingest_and_consolidate.ipynb', encoding='utf-8')); bad=[c for c in nb['cells'] if c['cell_type']=='code' and any(l.startswith(('def ','class ')) for l in c['source'])]; sys.exit(len(bad))"
uv run poe check
```

Expected: exit 0, then lint, typecheck and tests green at the 80% gate.

- [ ] **Step 7: Prove the image path.**

Run: `uv sync --locked --no-default-groups && uv run python -c "from app.injections import configure_container; c = configure_container(); c.experiment_tracker(); c.structural_breaks(); print('boots without wandb')"`
Expected: `boots without wandb`. Restore the dev environment with `uv sync --all-groups`.

- [ ] **Step 8: Hand over.** Summarize files added and modified, the `poe check` result, and which acceptance criteria are verified by tests (A9, A10, the unit behaviour behind A2–A7) versus by the notebook run the user has not yet done (A1–A8). Stage nothing. Propose a commit message and wait for explicit approval.

---

## Self-review

**Spec coverage.** R1 → Task 1. R2, R3 → Task 3. R4–R7 → Task 4. R8 → Task 5. R9 → Task 6 step 4. R10 → Tasks 0 and 2. R11 → Task 6 step 6. R12 → Global Constraints, enforced by `poe check`. A1–A8 → Task 6 cells; A9 → Task 6 steps 6–7; A10 → Task 6 steps 5–6.

**Soft spots to watch during execution.**
- `structural_break_flag` starts from `pd.Series(data=False, index=dates.index)` (dtype bool); if `|=` upcasts to object in the installed pandas, build the mask with `np.zeros(len(dates), dtype=bool)` instead.
- `add_flags` ends with `.loc[panel_long.index]`; it restores the input row order after the per-company concat.
- A5 (28 rows) assumes the GE quarters in `config/structural_breaks.yaml`; if they change, the count changes with them.
- A6 depends on Isolation Forest behaviour; it flagged AMZN 2026-06-30 at contamination 0.02, 0.03 and 0.05 when checked on 2026-09-23. If a library upgrade changes that, record it in the notebook rather than raising the contamination.

**Type consistency.** `add_flags` takes `last_reported_quarter` as a `date`, the same type as `Settings.LAST_REPORTED_QUARTER`; `consolidate_panels` returns the `ConsolidatedPanels` fields the notebook reads; `RunConfig.target_variable` is optional because NB00 has no target.
