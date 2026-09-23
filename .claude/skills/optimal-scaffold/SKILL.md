---
name: optimal-scaffold
description: The CFO_Copilot scaffold — where each kind of file goes, what to name it, how to wire it into the DI container, and how to register a router or error handler. Use when adding a feature, endpoint, service, domain entity, or data source to CFO_Copilot. Triggers on "add endpoint", "new service", "new route", "new data source", "register a router", "wire a dependency", "follow the project pattern", or any question about where code goes in CFO_Copilot.
---

# CFO Copilot Scaffold

Reference for the layered ML-API architecture used in CFO_Copilot. Follow these patterns for every new feature.

## Architecture Layers

```
Streamlit UI   (src/app/frontend/)
      ↓
FastAPI Routes (src/app/api/routes/<feature>/)
      ↓
Services       (src/app/services/<feature>/)
      ↓
Domain         (src/app/domain/)
      ↓
ML Binaries    (src/app/ml_binaries/) via services/helper.py
```

Each layer has one job. Never skip layers or import upward.

## Directory Layout

```
src/app/
├── __init__.py          # version + configure_container()
├── __main__.py          # multiprocess launcher (API + UI)
├── settings.py          # Pydantic Settings — ports, paths, env vars
│
├── api/
│   ├── app.py           # FastAPI factory (include_router, add_exception_handler)
│   ├── dependencies.py  # Annotated DI aliases consumed by route functions
│   ├── schema.py        # BaseSchema(BaseModel + ExamplerMixIn + CamelCase)
│   ├── error_handlers/  # One file per exception type → JSONResponse
│   └── routes/
│       └── <feature>/
│           ├── __init__.py
│           ├── endpoints.py   # route functions decorated with @inject
│           ├── schemas.py     # FeatureRequest / FeatureResponse
│           └── examples.py    # EXAMPLES dict for OpenAPI
│
├── domain/
│   ├── base.py          # BaseEntity (Pydantic + ExamplerMixIn + CamelCase)
│   ├── ml_model.py      # MLModel Protocol (@runtime_checkable)
│   └── <entity>.py      # One file per domain entity
│
├── services/
│   ├── helper.py        # load_model / save_model (joblib)
│   └── <feature>/
│       ├── __init__.py
│       ├── service.py       # FeatureService class
│       └── exceptions.py    # Custom exception dataclasses
│
├── injections/
│   ├── __init__.py      # configure_container() with @lru_cache
│   ├── production.py    # Container(DeclarativeContainer) — wires services
│   └── test.py          # TestContainer — overrides for tests
│
├── frontend/
│   ├── __init__.py      # run_streamlit() subprocess launcher
│   ├── home.py          # st.navigation + page router
│   └── pages/
│       └── <page>.py    # One Streamlit page per feature
│
└── utils/
    └── exampler.py      # ExamplerMixIn — create_example() / create_examples()
```

## Adding a New Feature (checklist)

### 1. Domain entity
```python
# src/app/domain/<entity>.py
from app.domain.base import BaseEntity

class MyEntity(BaseEntity):
    field_name: float = Field(gt=0)
```

### 2. Service
```python
# src/app/services/<feature>/service.py
class MyService:
    def do_thing(self, entity: MyEntity) -> MyOutput: ...

# src/app/services/<feature>/exceptions.py
@dataclass
class MyFeatureError(Exception):
    message: str
```

### 3. Wire into container
```python
# src/app/injections/production.py
my_service = providers.Factory(MyService)
```

### 4. DI alias for routes
```python
# src/app/api/dependencies.py
MyServiceDependency = Annotated[MyService, Depends(Provide["my_service"])]
```

### 5. Route schemas
```python
# src/app/api/routes/<feature>/schemas.py
class MyRequest(BaseSchema):
    field_name: float = Field(gt=0)

class MyResponse(BaseSchema):
    result: float
```

### 6. Endpoint
```python
# src/app/api/routes/<feature>/endpoints.py
router = APIRouter(prefix="/my-feature", tags=["My Feature"])

@router.post("/", response_model=MyResponse)
@inject
def my_endpoint(request: MyRequest, service: MyServiceDependency) -> MyResponse:
    result = service.do_thing(request.to_entity())
    return MyResponse(result=result)
```

### 7. Register router
```python
# src/app/api/routes/registry.py  (not __init__.py — that only re-exports)
ROUTERS: Iterable[APIRouter] = (
    health_router,
    prediction_router,
    train_router,
    my_feature_router,   # trailing comma: ROUTERS is a tuple, not a list
)
```

### 8. Error handler (if custom exception)
```python
# src/app/api/error_handlers/my_feature.py
def my_feature_error_handler(request: Request, exc: MyFeatureError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": exc.message})

# src/app/api/error_handlers/registry.py  (not __init__.py)
EXCEPTION_HANDLERS: dict[type[Exception], ExceptionHandler] = {
    ...,
    MyFeatureError: my_feature_error_handler,
}
```

### 9. Test
```python
# tests/services/<feature>/test_my_service.py
# tests/api/routes/<feature>/test_my_endpoint.py
```

## Model Conventions

| Base class | Where | Extras |
|---|---|---|
| `BaseEntity` | `domain/` | ExamplerMixIn, CamelCase aliases |
| `BaseSchema` | `api/schema.py` | ExamplerMixIn, CamelCase aliases |
| `MLModel` | Protocol in `domain/ml_model.py` | `fit()` + `predict()` |

All Pydantic models use `model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)` via the base classes.

Generate test data: `MySchema.create_example()` or `MySchema.create_examples(5)`.

## Testing Patterns

```python
# tests/conftest.py — override container for ALL tests
@pytest.fixture(scope="session", autouse=True)
def setup_container():
    container = TestContainer()
    container.wire(modules=[...])

# tests/api/conftest.py — shared test client
@pytest.fixture
def client(setup_container) -> TestClient:
    return TestClient(app)

# Snapshot testing (API contracts)
def test_health(client, snapshot):
    response = client.get("/health")
    assert response.json() == snapshot  # syrupy
```

`uv run poe check-coverage` fails under 80%. The omit list in `pyproject.toml`
is `**/__main__.py`, `src/app/frontend/*`, `src/app/settings.py` — note
`api/__init__.py` is *not* omitted. `check-coverage` is not part of
`poe check`, so it has to be run deliberately.

## Dev Workflow

```bash
uv sync --all-groups          # install all deps

uv run poe serve              # API (:8000) + Streamlit (:10000)
uv run poe serve-api          # API only → /docs
uv run poe serve-ui           # Streamlit only

uv run poe check              # lint + typecheck + test — the pre-commit gate
uv run poe test               # pytest + coverage
uv run poe check-coverage     # fail if < 80% (not part of `check`)
uv run poe format             # pre-commit hooks

uv run poe ingest-data        # python -m app.data — refresh the panels
uv run poe probe-alpha-vantage  # coverage probe against Alpha Vantage

uv run poe docker-build       # build image
uv run poe docker-run         # run with .env file

uv run poe version-bump       # semantic-release (no tag)
```

## Adding a Data Source

The ingestion layer lives in `src/app/data/` and is not shaped like the API
layer — read **CLAUDE.md, "External source packages"** before adding one. It
carries the rules in full; they are deliberately not duplicated here, because
two copies of a convention drift.

```
src/app/data/
├── companies.py      # CompanyRegistry, loaded from config/companies.yaml
├── dates.py          # shared quarter/date helpers
├── splits.py         # shared split-adjustment helpers
├── xbrl.py           # shared XBRL fact handling
├── pipeline.py       # panel assembly
├── schema.py         # FINANCIAL_COLUMNS and panel shape
└── sources/          # one package per vendor
    ├── alpha_vantage/   # source.py + parsing.py
    ├── fred/            # source.py only — nothing pure to separate
    ├── sec_edgar/       # source.py + parsing.py + concepts.py
    └── yfinance_source/ # source.py + fetching.py
```

The three rules worth knowing before you open CLAUDE.md:

- **`source.py` imports from `parsing.py`, never the reverse.** Keep it acyclic.
- **Vendor field names stay inside their package.** `fiscalDateEnding`,
  `totalRevenue` and us-gaap tags must not appear outside — this is an
  Anti-Corruption Layer. Genuinely shared logic goes in `data/dates.py`,
  `splits.py` or `xbrl.py`.
- **Only `__init__.py` defines the public surface.** Import
  `from app.data.sources import SecEdgarSource`, never a submodule path.

Add a company by editing `config/companies.yaml` only — never read the
registry from module-level state; accept it as a constructor argument, the way
`Container.company_registry` (a `Singleton`) is injected into `YfinanceSource`
and `SecEdgarSource`.

## Settings Pattern

```python
# src/app/settings.py
class _Settings(BaseSettings):
    MY_CONFIG: str = "default"

    @property
    def DERIVED_PATH(self) -> Path:
        return self.ROOT_PATH / "some/path"

Settings = _Settings()
```

Import as `from app.settings import Settings` everywhere — the instance is
capitalised, so `from app.settings import settings` is an ImportError. Never
pass config as constructor args when `Settings` suffices.

## Naming Quick Reference

| Thing | Convention | Example |
|---|---|---|
| Classes | PascalCase | `TrainingService` |
| Functions | snake_case | `load_model` |
| Constants/registries | UPPER_CASE | `ROUTERS`, `EXCEPTION_HANDLERS` |
| Private | `_` prefix | `_Settings` |
| Test files | `test_<module>.py` | `test_training_service.py` |
| Exception files | `exceptions.py` per service | `services/training/exceptions.py` |

## Common Mistakes

| Mistake | Fix |
|---|---|
| Importing a service directly into a route without DI | Add to container + create `Annotated` alias in `dependencies.py` |
| Putting business logic in endpoints | Move to a service method |
| Raising `HTTPException` inside a service | Raise a domain exception; handle it in `error_handlers/` |
| Skipping `@inject` on endpoint using `Provide` | Every endpoint that uses `Depends(Provide[...])` needs `@inject` |
| Adding a new router without registering it | Add to the `ROUTERS` tuple in `api/routes/registry.py` |
| Hardcoding paths | Use a `Settings.SOME_PATH` property |
