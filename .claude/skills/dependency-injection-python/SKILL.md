---
name: dependency-injection-python
description: Wiring dependencies in Python — constructor injection, Protocol-typed seams, and the dependency-injector Container with Factory/Singleton providers and FastAPI Depends aliases. Use when wiring services, clients, or repositories into classes or route handlers, when a class instantiates its own dependencies in __init__, or when overriding the container in tests. Triggers on "dependency injection", "DI container", "wiring", "provider", "inject", "hard to test because of", "swap implementations", "dependency-injector", "Provide", "Factory provider", "Singleton provider", "override the container".
---

# Dependency Injection — Python

## Overview

**"Give me what I need, don't make me create it yourself."**

A class that instantiates its own dependencies is tightly coupled to them — hard to test,
hard to swap, hard to reason about. DI moves object construction out of the class and into
a dedicated layer (the container), so the class only declares what it needs.

## The Problem

```python
# ❌ Tightly coupled — the forecaster picks its own model and path, so a test
#    cannot swap in a stub and every run reads the same binary from disk.
class ForecastService:
    def __init__(self) -> None:
        self.model = load_model(Path("binaries/model.joblib"))   # hardwired

# ✅ Loosely coupled — the caller decides which model implementation is used.
#    MLModel is a Protocol, so an ARIMA, an LSTM or a test stub all satisfy it.
class ForecastService:
    def __init__(self, model: MLModel) -> None:
        self.model = model
```

---

## Step 1 — Constructor Injection (pure Python)

The simplest form. No library needed. Sufficient for small scripts and single-file modules.

```python
# Construct dependencies outside the class, pass them in
model = load_model(Settings.MODEL_PATH)
service = ForecastService(model=model)

# Swapping the model implementation never touches ForecastService:
service = ForecastService(model=SarimaModel(order=(1, 1, 1), seasonal_period=4))
```

---

## Step 2 — Add Abstractions (Protocol)

Define the interface the class depends on, not the concrete type.
This makes swapping implementations (real → fake → mock) a one-line change.

```python
from typing import Protocol, Self, runtime_checkable

@runtime_checkable
class MLModel(Protocol):
    """Anything that fits and predicts — sklearn pipeline, ARIMA, LSTM, stub."""

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> Self: ...
    def predict(self, X: Sequence[Sequence[float]]) -> Sequence[float]: ...
```

---

## Step 3 — `dependency-injector` Container (for FastAPI / larger apps)

For applications with many services, use `dependency-injector` to manage construction
in one place.

### Install

```bash
uv add dependency-injector
```

### Directory layout

```
src/<package>/
├── injections/
│   ├── __init__.py      # configure_container() — wired once, cached
│   ├── production.py    # Container with real providers
│   └── test.py          # TestContainer for overrides
├── api/
│   ├── dependencies.py  # Annotated type aliases for FastAPI Depends()
│   └── routes/
│       └── predict/
│           └── endpoints.py  # @inject handlers
└── settings.py          # Pydantic BaseSettings singleton
```

### `injections/production.py` — declare providers

```python
from dependency_injector import containers, providers

from myapp.services import ForecastService, TrainingService
from myapp.settings import Settings

class Container(containers.DeclarativeContainer):
    # Factory → new instance per injection (stateless services)
    forecast_service = providers.Factory(ForecastService)
    training_service = providers.Factory(TrainingService)

    # Singleton → built once, shared for the whole process
    config_registry = providers.Singleton(
        ConfigRegistry.from_path,
        Settings.CONFIG_PATH,
    )

    # A provider can depend on another provider — pass the provider itself,
    # not a call to it, and the container resolves the order for you.
    data_source = providers.Factory(RemoteSource, registry=config_registry)
```

| Provider | When to use |
|----------|-------------|
| `providers.Factory` | Stateless services — fresh instance per call |
| `providers.Singleton` | Expensive shared resources — a parsed registry, a DB pool, a loaded model |
| `providers.Configuration` | Config values from env/file injected into providers |

### `injections/__init__.py` — wire once, cache

```python
from functools import cache
from .production import Container
from .test import TestContainer

@cache
def configure_container() -> Container:
    container = Container()
    container.wire(packages=["myapp"])   # scans all modules for @inject
    return container

__all__ = ["Container", "TestContainer", "configure_container"]
```

Call `configure_container()` at app startup:

```python
# myapp/__init__.py
from myapp.injections import configure_container
configure_container()
```

### `api/dependencies.py` — Annotated aliases for FastAPI

```python
from typing import Annotated
from dependency_injector.wiring import Provide
from fastapi import Depends
from myapp.services import ForecastService, TrainingService

ForecastServiceDependency = Annotated[
    ForecastService,
    Depends(Provide["forecast_service"]),
]
TrainingServiceDependency = Annotated[
    TrainingService,
    Depends(Provide["training_service"]),
]
```

### Route handler — `@inject` + typed parameter

```python
from dependency_injector.wiring import inject
from fastapi import APIRouter
from myapp.api.dependencies import ForecastServiceDependency

router = APIRouter(prefix="/forecast", tags=["Forecast"])

@router.post("/")
@inject                                        # ← required for dependency-injector wiring
def forecast(
    request: ForecastRequest,
    service: ForecastServiceDependency,        # ← resolved by the container
) -> ForecastResponse:
    output = service.forecast(request.to_entity())
    return ForecastResponse.from_entity(output)
```

### `settings.py` — Pydantic BaseSettings singleton

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class _Settings(BaseSettings):
    API_KEY: str = ""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def MODEL_PATH(self) -> Path:
        return Path(__file__).parent / "binaries" / "model.joblib"

Settings = _Settings()   # import this singleton everywhere — never re-instantiate
```

---

## Testing — Override the Container

```python
# injections/test.py
from dependency_injector.containers import DeclarativeContainer


class TestContainer(DeclarativeContainer):
    """This container overwrites the Production container for testing purposes."""

    # Declare only what a test needs to replace. Anything left out falls
    # through to the production container, so the real wiring is still
    # exercised — an empty TestContainer is a valid starting point.
    #
    # data_source = providers.Factory(StubSource)
```

```python
# tests/conftest.py
import pytest
from myapp.injections import configure_container
from myapp.injections.test import TestContainer

@pytest.fixture(autouse=True, scope="session")
def injector_override() -> None:
    container = configure_container()
    container.override(TestContainer)
    container.wire(packages=["tests"])
```

`container.override()` replaces only the providers defined in `TestContainer`.
Everything else resolves to production providers — so you only fake what matters.

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Instantiating a client inside `__init__` | Pass it as a parameter; let the container build it |
| Using `providers.Singleton` for stateful per-request data | Use `providers.Factory`; singletons share state across requests |
| Calling `configure_container()` more than once without `@cache` | Always wrap with `@cache` or `lru_cache(maxsize=1)` |
| Forgetting `@inject` on a route handler | Container wiring silently skips non-decorated functions |
| `container.wire(packages=["app"])` not including `"tests"` | Add `container.wire(packages=["tests"])` in `conftest.py` |
| Depending on a concrete class instead of a Protocol | Define a `Protocol`; inject the concrete implementation |

---

## Decision — Which approach?

- Single file or script → constructor injection, nothing else needed.
- FastAPI or several services sharing dependencies → `dependency-injector`
  with a `Container`.
- In between → constructor injection typed against a `Protocol`.
