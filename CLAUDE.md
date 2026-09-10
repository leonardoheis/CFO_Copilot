# CFO Copilot — Agent Guide

Financial forecasting app combining GenAI data extraction with ML time-series models. This document describes the repository layout, layer boundaries, and conventions agents should follow.

## Tech stack

| Layer | Technology |
|-------|------------|
| API | FastAPI, Pydantic, dependency-injector |
| UI | Streamlit |
| ML | scikit-learn (LinearRegression pipeline) |
| Package manager | uv (Python 3.12) |
| Tests | pytest, syrupy, pytest-recording |
| CI/CD | GitHub Actions → Render.com (Docker) |

## Directory structure

```
CFO_Copilot/
├── .github/workflows/       # CI: lint_and_test, publish, deploy
├── src/app/
│   ├── __init__.py          # configure_container() on import; __version__
│   ├── __main__.py          # Runs API + Streamlit in parallel processes
│   ├── settings.py          # Pydantic settings (ports, paths, .env)
│   ├── api/                 # FastAPI backend
│   │   ├── app.py           # create_app() — registers routers + exception handlers
│   │   ├── schema.py        # BaseSchema (camelCase aliases, ExamplerMixIn)
│   │   ├── dependencies.py  # FastAPI Depends() wrappers for services
│   │   ├── error_handlers/  # Maps domain/service exceptions → HTTP responses
│   │   └── routes/          # One subpackage per feature
│   │       ├── health/      # GET /health
│   │       ├── prediction/  # POST /prediction/predict
│   │       └── train/       # POST /prediction/train
│   ├── domain/              # Business entities (no HTTP concerns)
│   │   ├── base.py          # BaseEntity
│   │   ├── ml_model.py      # MLModel protocol (fit, predict)
│   │   ├── prediction_input.py
│   │   └── prediction_output.py
│   ├── services/            # Application logic
│   │   ├── training/        # TrainingService, DimensionalityMismatchError
│   │   ├── prediction/      # PredictionService, NoTrainedModelError
│   │   └── helper.py        # load_model / save_model (joblib)
│   ├── injections/          # DI containers
│   │   ├── production.py    # Container — service + data-source factories
│   │   └── test.py          # TestContainer (overrides for tests)
│   ├── frontend/            # Streamlit UI
│   │   ├── home.py          # Navigation entrypoint
│   │   └── pages/           # health.py, test.py
│   ├── data/                # SEC, Yahoo Finance, FRED, Alpha Vantage ingestion
│   │   ├── companies.py     # CompanyRegistry (loads config/companies.yaml)
│   │   ├── dates.py         # Shared quarter/date helpers
│   │   ├── splits.py        # Shared split-adjustment helpers
│   │   ├── xbrl.py          # Shared XBRL fact handling
│   │   └── sources/         # One package per external source
│   │       ├── alpha_vantage/   # source.py, parsing.py
│   │       ├── fred/            # source.py
│   │       ├── sec_edgar/       # source.py, parsing.py, concepts.py
│   │       └── yfinance_source/ # source.py, fetching.py
│   ├── utils/               # ExamplerMixIn (OpenAPI example generation)
│   ├── ml_binaries/         # Runtime model artifacts (model.joblib)
│   └── playground/          # Notebooks (not in coverage)
├── tests/
│   ├── api/                 # Route/integration tests
│   └── services/            # Service unit tests
├── pyproject.toml           # deps, poe tasks, ruff, mypy, pytest, coverage
├── Dockerfile               # Multi-stage uv build; CMD python -m app
└── project-details.md       # ML project scoping questionnaire (planning)
```

## Layer responsibilities

Follow this flow when adding features:

```
HTTP JSON  →  API schemas  →  endpoints  →  domain entities  →  services  →  persistence
```

| Layer | Path | Responsibility |
|-------|------|----------------|
| **Routes** | `api/routes/<feature>/` | HTTP endpoints, request/response schemas, OpenAPI examples |
| **Schemas** | `api/routes/<feature>/schemas.py` | Validate/serialize JSON; inherit `BaseSchema` |
| **Domain** | `domain/` | Business types with domain naming (e.g. `age`, not `input`) |
| **Services** | `services/<feature>/` | ML and business logic; raise domain exceptions |
| **Injections** | `injections/production.py` | Wire services via `dependency-injector` |
| **Frontend** | `frontend/pages/` | Streamlit pages calling the API |

### Route package layout

Each feature under `api/routes/` typically contains:

- `endpoints.py` — FastAPI router and handler functions
- `schemas.py` — `*Request` / `*Response` Pydantic models
- `__init__.py` — exports router and schemas
- Optional: `examples.py`, `responses.py` (OpenAPI metadata)

## API endpoints

| Method | Path | Handler | Service |
|--------|------|---------|---------|
| GET | `/health` | health | — |
| POST | `/prediction/train` | train | `TrainingService.train(X, y)` |
| POST | `/prediction/predict` | predict | `PredictionService.predict(input)` |

OpenAPI docs: `http://localhost:8000/docs`

## Key conventions

- **Schemas vs domain**: API uses client-friendly names (`input` → `PredictionRequest.input_`); domain uses business names (`PredictionInput.age`).
- **CamelCase JSON**: `BaseSchema` applies `to_camel` alias generator.
- **DI wiring**: Services injected via `@inject` + `Provide["service_name"]` in endpoints. Container wired in `app/injections/__init__.py`.
- **Model persistence**: `Settings.MODEL_PATH` → `ml_binaries/model.joblib`.
- **Company registry**: ingestion rules live in `config/companies.yaml`, loaded
  into a `CompanyRegistry` by a `Singleton` provider and injected into
  `YfinanceSource`, `SecEdgarSource`, and `IngestionSources`. Never read the
  registry from module-level state; accept it as a constructor argument.
  Add a company by editing the YAML file only.
- **Strict typing**: mypy strict mode enabled; all new code must type-check.
- **Coverage**: CI expects high coverage; `frontend/` and `settings.py` are omitted from coverage.

## Commands

```bash
uv sync --all-groups          # Install dependencies
uv run poe serve              # API (8000) + Streamlit UI
uv run poe serve-api          # API only
uv run poe serve-ui           # Streamlit only
uv run poe test               # pytest with coverage
uv run poe format             # pre-commit on all files
uv run poe check              # lint + typecheck + test (run before every commit)
uv run poe docker-build       # Build Docker image
uv run poe docker-run         # Run container (.env required)
```

## Typing conventions

- **Do not use `# type: ignore[no-any-return]`.**
  Fix the underlying issue instead:
  - Add an explicit cast: `return cast("pd.Series", value)`
  - Correct the return type annotation on the function
  - If the value genuinely can be `None`, guard with an `if` check and raise
    a typed exception before returning
  - Only use `# type: ignore` as a last resort for an untyped third-party
    return that cannot be cast, and always name a specific error code
    (e.g. `# type: ignore[return-value]`) with a comment explaining why

## External source packages

Each external data source is a **package** under `src/app/data/sources/`, not a
single module. The split separates the stateful adapter from pure translation:

| File | Holds | May touch |
|------|-------|-----------|
| `source.py` | The `*Source` class | HTTP, cache, credentials, instance state |
| `parsing.py` | Pure payload → panel translation | Only its arguments |
| `concepts.py` | Vendor tag/field declarations (`sec_edgar`) | Nothing |
| `fetching.py` | Calls against an injected client (`yfinance_source`) | The injected object only |
| `__init__.py` | Re-exports the public names | — |

Rules:

- **Import direction is one-way**: `source.py` imports from `parsing.py`, never
  the reverse. Keep it acyclic.
- **Vendor field names stay inside the package.** This is an Anti-Corruption
  Layer: `fiscalDateEnding`, `totalRevenue` and us-gaap tags must not appear
  outside their own source package. Logic genuinely shared across sources goes
  in `app/data/` (`dates.py`, `splits.py`, `xbrl.py`), never a vendor's quirks.
- **Names crossing a module boundary drop the leading underscore.** Ruff's
  `import-private-name` rejects importing `_foo` from a sibling module, so
  package-internal helpers are public within the package and kept out of the
  public API by simply not being re-exported in `__init__.py`.
- **Only `__init__.py` defines the public surface.** Outside code imports
  `from app.data.sources import SecEdgarSource`, never a submodule path.
- **Tests patch the submodule that owns the import**, e.g.
  `app.data.sources.yfinance_source.source.yf.Ticker` — not the package root.
- `fred/` has no `parsing.py` because it has nothing pure to separate; add one
  only when there is real translation logic, not for symmetry.

## Static helpers and model types

- **Do not use `@staticmethod`.** A helper that never reads `self` belongs at
  **module level** as a private function, not on the class. Ruff's
  `no-self-use` (PLR6301) enforces the same thing from the other direction, so
  a self-less method fails lint either way.
  - Extraction cascades: once a helper moves out, callers that only used `self`
    to reach it become self-less too. Re-run lint after each extraction.
  - Exception: **public** methods on a source class must stay methods even when
    they ignore `self`. Mark them `# noqa: PLR6301` with a short reason.
- **Prefer Pydantic over `@dataclass`** for types that are validated,
  configured, or serialized. Use `ConfigDict(frozen=True, extra="forbid")` and
  add `@field_validator` guards for invariants the type system cannot express.
  Serialize with `model_dump(mode="json")`, never `dataclasses.asdict`.
- **Keep `@dataclass`** in three cases:
  - fields typed as a `Protocol` (`IngestionSources`) or holding live service
    objects (`ProbeContext`) — Pydantic needs `arbitrary_types_allowed`, which
    is a weaker guarantee than mypy already gives;
  - exception types — `BaseModel` does not subclass `Exception` cleanly;
  - domain types in `companies.py`, which are deliberately kept separate from
    the `_*Config` Pydantic models that validate the YAML shape.
- Pydantic models are **keyword-only** at construction.

## Error-handling conventions

- **Never use exceptions as control flow in loops.**
  Catching an exception just to `continue` to the next iteration — even with
  logging — is still wrong. Exceptions signal unexpected failures; using them
  to drive iteration hides the real logic and couples control flow to error
  handling.

  ```python
  # ✗ bad — exception used to skip to next iteration (silent)
  except TickerNotFoundError:
      continue

  # ✗ still bad — logged, but exception is still driving the loop
  except TickerNotFoundError as error:
      logger.warning("Skipping %s: %s", ticker, error)
      continue

  # ✓ good — no exception; check the return value instead
  result = _try_fetch(ticker)     # returns empty Series on "not found"
  if result.empty:
      logger.warning("No data available for %s", ticker)
      continue
  ```

  Rules:
  - Private helpers that support fallback loops should return **empty / sentinel
    values** (empty `Series`, empty `DataFrame`) when no data is found. They
    raise only for genuine API failures (`DataSourceUnavailableError`).
  - Public methods raise domain exceptions (`TickerNotFoundError`) when **all**
    fallback options are exhausted.
  - Log with `logger.warning` before any intentional `continue`.
  - Use `logger.error` or re-raise for unexpected failures that indicate a bug.
  - Module-level logger: `logger = logging.getLogger(__name__)`.
  - For external payload parsing, warn and return `None` for an unusable field,
    raise `MalformedPayloadError` for an unusable record or structurally invalid
    payload, and never let a bare `ValueError`, `KeyError`, or `TypeError`
    escape the data layer.

## Pre-commit quality gate

Before finishing work or creating a commit, run:

```bash
uv run poe check
```

This runs `lint`, `typecheck`, and `test` in sequence (defined in `pyproject.toml`). Fix any failures before committing — do not commit with a failing check.

## Adding a new API feature

1. Create `api/routes/<feature>/` with `endpoints.py`, `schemas.py`, `__init__.py`.
2. Add domain entities in `domain/` if new business types are needed.
3. Implement logic in `services/<feature>/`.
4. Register service in `injections/production.py`.
5. Add `Depends()` alias in `api/dependencies.py`.
6. Register router in `api/routes/__init__.py` (`ROUTERS` tuple).
7. Add exception handlers in `api/error_handlers/` if needed.
8. Write tests under `tests/api/` and `tests/services/`.

## Planned extensions (from README)

Not yet implemented; place new code in dedicated packages when added:

- **Data ingestion**: SEC EDGAR, FRED, financial APIs → parquet/CSV data lake
- **Training pipeline**: EDA, ARIMA/LSTM, MLflow/W&B registry
- **GenAI Q&A**: LangChain + OpenAI/Gemini/Claude for document queries

For financial panel data (e.g. quarterly Amazon variables), add under `src/app/data/` with separate scrapers and a merge pipeline.

## Testing

- Snapshots: `tests/api/routes/**/__snapshots__/`
- Service tests: `tests/services/<feature>/`
- Use `TestContainer` in `injections/test.py` to override production bindings.

## CI/CD

- **PR**: lint + test (SonarQube)
- **master merge**: lint + test → semantic-release → deploy to Render
- Default branch deploys via `.github/workflows/deploy.yml`
