---
name: python-backend
description: Layer boundaries and import direction for a layered Python backend — what may import what, where interfaces live, and which rules each layer enforces. Use when adding a service, an external client, or a new layer, or when reviewing whether code sits in the right one. Triggers on "backend", "service layer", "API layer", "which layer imports which", "layering", "external client". For the DI container itself use dependency-injection-python; for modelling the domain use ddd-python.
---

# Python Backend

## Overview

Four layers — api → services → data → domain — plus a cross-cutting utils
layer. Each has a strict import direction and a single responsibility. Fail
fast, type strictly, and prefer named models over loose `Any`/`dict`/`tuple`.

The "data" layer is whatever holds concrete implementations that talk to the
outside world: HTTP clients, vendor SDK adapters, persistence. Some codebases
call it `infrastructure/` or `adapters/`; use whatever name the project
already uses rather than introducing a new one.

## Linting

```bash
uv run poe lint
```

Run after every change.

## Typing Rules

- Prefer a named model over `Any`, a bare `dict`, or a positional `tuple`. A
  `dict` signature hides what the caller must supply and gives the type checker
  nothing to verify; a named model documents and checks it in one move.
  (Payload-shaped data at a boundary — a parsed JSON body, a DataFrame — is a
  legitimate exception; translate it into a model as soon as it crosses.)
- `| None` only when absent is genuinely a valid state. If you are returning
  `None` for several different reasons, return distinct result types instead.
- Fail fast and close to the root cause, so the traceback points at the bug
  rather than at the first place the bad value was used.
- Add `from __future__ import annotations` only when a forward reference
  cannot be resolved with a quoted string literal or by reordering
  definitions — it changes annotations to strings at runtime, which breaks
  libraries that introspect them.

## Layer Architecture

```
api  →  services  →  data  →  domain
                             ↑
                    utils (cross-cutting)
```

### Domain Layer

- Imports: itself + utils only
- Contains: domain entities, validation rules/invariants, business logic, **interfaces** for external communication
- Interfaces defined here (a `Protocol` is usually enough — no ABC needed) are
  satisfied by Data-layer implementations and injected wherever they are used

### Data Layer

- Imports: itself + domain + utils
- Contains: concrete implementations of the Domain's interfaces — HTTP clients,
  vendor adapters, persistence — plus the entities they return
- Clients are never manually instantiated; they are wired through the DI
  container so tests can swap them at one seam
- Keep vendor field names inside their own package. A vendor's JSON keys
  leaking upward is how a third-party schema change becomes a refactor of your
  whole codebase

**Testing seam**: override the DI container in tests (e.g. a `TestContainer`
that rebinds providers) rather than maintaining a parallel fake for every real
client. One override point is less code to keep in sync, and it tests the
wiring as well as the logic. Write a fake only for a client whose behaviour a
test needs to steer.

### Services Layer

- Imports: itself + data + domain + utils
- Contains: Service classes that orchestrate Data and Domain code
- May contain Pydantic models for method signatures and validation
- No interfaces or abstract classes here — an interface with one
  implementation is indirection without a payoff. Interfaces belong in Domain,
  where something else actually implements them.
- Output to the API layer must use Service or Domain models — never return a
  Data-layer entity directly, or the vendor's shape becomes your API contract

### API Layer

- Imports: itself + services + utils
- Contains: API/server code and payload validation only
- **No business logic** beyond API validation
- **No try/except**

### Utils Layer

- Contains: custom exceptions, logging, profiling, environment variable settings, other cross-cutting concerns

## Quick Reference

| Rule | Layer |
|------|-------|
| No `try/except` | API |
| No interfaces/abstract classes | Services |
| Clients never manually instantiated | Data |
| Swap dependencies by overriding the container | Data (in tests) |
| Never return Data-layer models to API | Services |
| All interfaces live here | Domain |
| Env vars, logging, exceptions | Utils |

## Example: keeping the vendor out of the Service

The rule "never return a Data-layer entity to the API" is easiest to see as a
diff. Before — the vendor's field names have escaped into the response, so
renaming them upstream breaks the API contract:

```python
# services/quotes.py
def latest_quote(self, ticker: str) -> dict:
    return self._client.fetch(ticker)   # {"01. symbol": ..., "05. price": ...}
```

After — the adapter translates at the boundary, and the Service returns a type
the API owns:

```python
# data/sources/vendor/parsing.py
def to_quote(payload: dict) -> Quote:
    return Quote(symbol=payload["01. symbol"], price=Decimal(payload["05. price"]))

# services/quotes.py
def latest_quote(self, ticker: str) -> Quote:
    return to_quote(self._client.fetch(ticker))
```

The vendor's `"05. price"` now appears in exactly one file.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Returning a Data-layer entity from a Service | Map to a Service/Domain model first |
| Adding business logic in an API route handler | Move to a Service |
| Manually instantiating a client | Wire it through the DI container |
| Typing a parameter as `dict` | Define a Pydantic model or TypedDict |
| Services importing from API | Invert the dependency |
| Vendor field names appearing outside the Data layer | Translate at the boundary |
