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
│   │   ├── production.py    # Container — service factories
│   │   └── test.py          # TestContainer (overrides for tests)
│   ├── frontend/            # Streamlit UI
│   │   ├── home.py          # Navigation entrypoint
│   │   └── pages/           # health.py, test.py
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
