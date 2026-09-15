---
name: pytest-testing
description: Writing Python tests with pytest — fixtures and their scopes, parametrize, marks, conftest.py placement, snapshot tests, and the real-vs-fake-vs-mock decision. Use when writing or restructuring tests, adding a fixture, covering many inputs at once, or deciding whether a dependency needs a mock at all. Triggers on "write a test", "add a test", "pytest", "fixture", "parametrize", "conftest", "how do I test this", "mock or not", "snapshot test".
---

# pytest Testing

## Overview

Always use pytest. Prefer real objects and fakes over mocks. Mock only at true system
boundaries (HTTP, filesystem, clock, external APIs). Tests that use real behavior catch
more bugs and survive refactoring better than tests full of `MagicMock`.

## Real vs mock

Not a true external boundary → use the real object.
A boundary you can substitute → use a fake (SQLite in-memory, `tmp_path`, a dict).
A boundary you cannot substitute → mock it (outbound HTTP, the clock, randomness).

**True boundaries (OK to mock):** outbound HTTP calls, system clock (`datetime.now`),
hardware (GPU, camera), third-party paid APIs, non-deterministic sources.

**Not boundaries (do NOT mock):** your own classes, database when SQLite works,
file I/O when `tmp_path` works, business logic you want to verify.

## Core Patterns

### Fixtures

Fixtures provide setup/teardown as injectable dependencies. Declare them as function parameters — pytest resolves them automatically.

```python
# tests/services/training/conftest.py  ← fixtures scoped to one feature
from collections.abc import Generator
from pathlib import Path

import pytest

@pytest.fixture
def model_path(tmp_path: Path) -> Generator[Path]:
    """A real file on disk, removed before and after — no mock needed.

    Yielding is what makes the teardown run even when the test fails.
    """
    path = tmp_path / "model_test.joblib"
    path.unlink(missing_ok=True)
    yield path
    path.unlink(missing_ok=True)

@pytest.fixture
def training_data_dimension_mismatch() -> tuple[list[list[float]], list[float]]:
    """Named for the scenario, not the shape — the test reads as a sentence."""
    X = [[25.0], [30.0], [35.0]]
    y = [5.0, 6.0]
    return X, y
```

**Fixture scopes** — choose the narrowest scope that avoids duplication:

| Scope | Lifetime | Use for |
|-------|----------|---------|
| `function` (default) | Each test | Mutable state, temp files |
| `module` | Each `.py` file | Read-only shared data |
| `session` | Entire run | Expensive setup (model load, DB schema) |

### parametrize — test many inputs without duplication

```python
import pytest

# Cover the boundary rather than a scatter of arbitrary values: one below,
# one at, one above. That is where off-by-one errors actually live.
@pytest.mark.parametrize("size,should_pass", [
    (0,                    False),  # empty
    (1,                    True),   # minimal valid
    (MAX_BYTES,            True),   # exactly at the limit
    (MAX_BYTES + 1,        False),  # one byte over
])
def test_size_gate(tmp_path, size, should_pass):
    f = tmp_path / "upload.bin"
    f.write_bytes(b"x" * size)
    assert accepts(f) is should_pass
```

### Marks — skip, xfail, categorize

```python
# pyproject.toml — register custom marks to suppress warnings
# [tool.pytest.ini_options]
# markers = ["slow: marks tests as slow", "integration: requires real services"]

@pytest.mark.slow
def test_embedding_similarity():
    ...

@pytest.mark.integration
def test_real_db_round_trip():
    ...

@pytest.mark.xfail(reason="GPU not available in CI", strict=False)
def test_llm_inference():
    ...
```

Run subsets: `pytest -m "not slow"` · `pytest -m integration`

### conftest.py placement

```
tests/
├── conftest.py            ← fixtures available to ALL tests
├── api/
│   ├── conftest.py        ← fixtures scoped to api/ only (e.g. the client)
│   └── routes/
│       └── test_health.py
└── services/
    └── training/
        ├── conftest.py    ← fixtures scoped to this feature
        └── test_training_service.py
```

Fixtures in a `conftest.py` are auto-discovered — no import needed.

### Snapshot tests — for wide, stable output

When the code under test returns a large structure (an API response body, a
rendered document, a serialized model), asserting field by field is noisy and
under-checks. A snapshot library such as `syrupy` stores the accepted output
beside the test and diffs against it:

```python
def test_health_endpoint(client, snapshot):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == snapshot   # compared against the stored snapshot
```

The first run writes the snapshot; later runs fail on any difference. Review
the diff before accepting an update (`--snapshot-update`) — a snapshot blindly
re-recorded proves nothing.

Use snapshots for output whose *whole shape* matters and changes rarely. Avoid
them for a single value, or for anything containing timestamps or random ids
unless you normalize those first.

## Fakes over Mocks

A **fake** is a real, lightweight implementation that behaves like the real thing:

```python
# Instead of mocking the store, use a plain dict — it has the same behaviour
# and, unlike a MagicMock, it will actually fail if the logic is wrong.
def test_exact_duplicate_detected(tmp_path):
    seen: dict[str, str] = {}                # real dict, not MagicMock

    payload = tmp_path / "doc.bin"
    payload.write_bytes(b"contents")
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    seen[digest] = "job-original"

    result = check_duplicate(job_id="job-duplicate", digest=digest, seen=seen)

    assert result.is_duplicate is True
    assert result.duplicate_of == "job-original"
```

**In-memory substitutes:**

| Real dependency | Fake substitute |
|----------------|-----------------|
| PostgreSQL / SQLite | SQLite in-memory: `"sqlite:///:memory:"` |
| File system | `tmp_path` (pytest built-in) |
| Redis / hash store | `dict` |
| Vector index | The real index class with a small dimension |
| Model inference | A small stub class returning a fixed result |

### Swapping dependencies wholesale

If the app wires its dependencies through a DI container, override the
container once in the root `conftest.py` rather than patching each collaborator
in every test. One seam replaces many `patch` calls, and the real wiring still
gets exercised for everything you did not override:

```python
@pytest.fixture(autouse=True, scope="session")
def injector_override() -> None:
    container = configure_container()
    container.override(TestContainer)   # only the providers it declares
    container.wire(packages=["tests"])
```

## Assertions

Just use `assert`. pytest rewrites assertions to show rich diffs on failure — no need
for `assertEqual`, `assertTrue`, or `assertIsNone`:

```python
assert result.passed is True
assert result.digest == expected_digest
assert "Empty file" in result.reason
assert result.size_bytes == 0
```

## File & Naming Conventions

```
tests/
├── conftest.py
├── fixtures/                 ← real fixture files (CSVs, sample payloads)
│   └── sample_panel.csv
└── services/
    └── training/
        └── test_training_service.py   ← test_<module>.py
```

- File: `test_<module>.py`
- Function: `test_<what_it_does>_<expected_outcome>`
- One behavior per test function — short tests are easier to debug

## Running Tests

```bash
uv run pytest tests/                        # all tests
uv run pytest tests/services/training/      # one directory
uv run pytest -k "duplicate"               # by name pattern
uv run pytest -m "not slow"                # by mark
uv run pytest -x                           # stop on first failure
uv run pytest -v                           # verbose output
uv run poe test                            # project alias (see pyproject.toml)
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Mocking your own classes | Pass the real object; redesign if it's too hard to construct |
| `scope="session"` on mutable fixtures | Mutations leak between tests — use `function` scope |
| Patching the wrong namespace | Patch where the name is **used**, not where it's defined: `patch("mymodule.os.path")` not `patch("os.path")` |
| Two test files sharing a basename | Add `__init__.py` to the packages, or rename — without one, pytest cannot import both |
| Giant test functions testing many things | Split into one assertion per function; parametrize instead |
| Not registering custom marks | Add to `[tool.pytest.ini_options] markers` in `pyproject.toml` |

## When Mocking Is Correct

```python
from unittest.mock import patch
import pytest

def test_skips_remote_check_when_rules_already_decide(tmp_path):
    # patch is correct here: the remote call is a true external boundary, and
    # the point of the test is that it must NOT happen on the fast path.
    with patch("myapp.validation._remote_check") as remote:
        result = validate(path=tmp_path / "in.bin", strict=False)
        remote.assert_not_called()     # the rule-based path must not call out
        assert result.accepted is True
```

Mock to **verify behavior at a boundary** — not to make a dependency easier to construct.
