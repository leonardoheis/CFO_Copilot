---
name: cfo-copilot-structure
description: >-
  Describes CFO Copilot repository layout, layer boundaries, API conventions,
  and where to add new code. Use when navigating the codebase, adding features,
  endpoints, services, data pipelines, or when the user mentions AGENTS.md,
  project structure, or architecture.
---

# CFO Copilot Project Structure

Read [AGENTS.md](../../AGENTS.md) at the repository root for the full guide.

## Quick reference

**Layers** (outside → in): `api/routes` → `domain` → `services` → `ml_binaries/`

**Entry points**:
- `python -m app` — API + Streamlit
- `python -m app.api` — API only
- `python -m app.frontend` — UI only

**Add a feature**:
1. `api/routes/<feature>/` (endpoints, schemas)
2. `domain/` + `services/<feature>/`
3. Wire in `injections/production.py` and `api/dependencies.py`
4. Register router in `api/routes/__init__.py`
5. Tests in `tests/`

**Conventions**: API schemas use camelCase JSON; domain uses business names. Services raise exceptions mapped in `api/error_handlers/`.

**Before every commit**: `uv run poe check` (lint + typecheck + test).

For directory tree, endpoints table, commands, and planned extensions, see [AGENTS.md](../../AGENTS.md).
