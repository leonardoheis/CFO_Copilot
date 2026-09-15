# Skills Audit — status

Audited 17 skills against the official `skill-creator` rubric (3 parallel
subagents), then remediated. This file records what was wrong and where it was
fixed, so the current wording is traceable to a reason.

Audited and remediated 2026-09-15 on `feature/data-ingestion`.

**Guard:** `uv run poe check-skills` ([scripts/check_skills.py](../../scripts/check_skills.py))
now fails on foreign markers, dead paths, missing symbols, and global/project
drift. Run it before editing a skill.

---

## The shadowing mechanic (read this first)

A personal skill at `~/.claude/skills/<name>/` **silently shadows** a project
skill of the same name. Precedence is Enterprise > Personal > Project, with no
warning. Twelve names collide here, and the project copies were byte-identical
forks (CRLF vs LF), so **editing only the project copy changes nothing**.

Both copies are now fixed and kept identical; `check-skills` fails if they
drift apart.

`~/.claude/skills/` was made a git repo before any edit (it is not otherwise
version-controlled and `backups/` was empty). A pre-remediation snapshot also
exists at `~/.claude/skills.bak-20260915`.

---

## P0 — fixed

| Skill | Defect | Fix |
|---|---|---|
| `python-oop` | Illegal `version: 1.0.0` frontmatter key (global copy) | Removed |
| `python-oop` | Recommended `@staticmethod`; CLAUDE.md forbids it, `no_self_use` is on (`pyproject.toml:241`), 0 uses in `src/app/`. **Code following it failed `poe lint`.** | Replaced with the module-level-function rule plus the reason |
| `optimal-scaffold` | `from app.settings import settings` — real export is `Settings` (`settings.py:91`). **An ImportError.** | Corrected, with a note naming the trap |
| `optimal-scaffold` | `ROUTERS` described as a list in `api/routes/__init__.py`; it is a tuple in `registry.py:9`. Same for `EXCEPTION_HANDLERS`. **Edits landed in the wrong file.** | Corrected both paths and types |
| `python-backend` | Documented an `api → services → infrastructure → domain` architecture; `src/app/infrastructure/` does not exist. Also mandated per-client fakes, contradicting `TestContainer` | Regrounded on the real layering; fakes replaced with the container-override seam |
| `code-structure` | Entirely TypeScript (server actions, `previewUrl`) in a Python repo, pushing an `actions/` layer that exists nowhere | Rewritten in Python with handler/service vocabulary |
| `ddd-python` | Two snippets raised at import: `rename()` assigned a `model_fields` annotation then `del`'d it; `DomainEvent` put non-default subclass fields after a defaulted base field (`TypeError`) | Both fixed **and executed** to confirm |
| `ddd-python` | 636 lines against a <500 rubric; every concept shown twice | 462 lines; dataclass variants moved to `references/dataclasses.md` |
| `code-smells` | Cited `ConfidenceTier`/`OodEvidence`/`OOD_COSINE_THRESHOLD` — none exist | Replaced with generic guidance |
| `refactoring-techniques` | Referenced `.claude/learnings.md` — file does not exist | Replaced |
| `find-skills` | Triggered on "how do I do X", hijacking ordinary questions into an `npx skills` search, in a harness with built-in discovery | Narrowed to explicit install intent only |

## P1 — fixed

**Foreign-project contamination.** `pytest-testing`, `pydantic`,
`solid-principles` and `dependency-injection-python` were built on examples
from other codebases — `classiflow` (decree classification, FAISS, PDFs), Wine
Reviews, Ollama/`phi4-mini` — while claiming CFO_Copilot provenance. All
examples are now domain-neutral, so these skills stay correct in any repo.

Two real defects surfaced during the purge: `pydantic` imported
`DimensionalityMismatchError` from `app.exceptions` (real path
`app.services.training.exceptions`), and `dependency-injection-python`
referenced `Settings.MODELS_PATH` (real name `MODEL_PATH`).

**Trigger collisions.** Ten Python skills shared `refactor`, `extract`,
`decouple`, `schema`. Each skill now owns a disjoint *stage of the work*:

| Skill | Stage |
|---|---|
| `code-smells` | Diagnose — name what is wrong. **Owns bare "refactor this"** |
| `refactoring-techniques` | Apply — the named mechanical fix |
| `design-patterns` | Propose — a GoF pattern, gated on approval |
| `solid-principles` | Judge — class-design principles |
| `dependency-injection-python` | Wire — providers and container |
| `code-structure` | Place — which layer |
| `optimal-scaffold` | Place, CFO_Copilot-specific |

`design-patterns` narrowed hardest, dropping all five overloaded tokens — a
GoF pattern proposed for what is usually an extract-method was the most
expensive wrong answer available.

**Coverage gaps.** `src/app/data/` was invisible to every skill; a section in
`optimal-scaffold` now points at CLAUDE.md rather than duplicating its rules.
`pytest-testing` gained the snapshot-test and container-override sections it
lacked. The `ingest-data`, `probe-alpha-vantage` and `check` poe tasks are
documented.

## P2 — fixed

All-caps `## MANDATORY RULE:` headings, Obsidian `[[wikilinks]]`, graphviz
`dot` blocks nothing renders, `ExamplerMixin` → `ExamplerMixIn`, and the
committed `__pycache__`. Worked examples added to `python-backend`,
`refactoring-techniques` and `design-patterns`, which had none.

---

## Decisions worth remembering

- **Generic skills use generic examples.** The global skills load in every
  repo, so CFO_Copilot symbols do not belong in them. Only
  `optimal-scaffold`, `cfo-copilot-structure` and `analyzing-time-series` are
  project-specific.
- **The global `optimal-scaffold` was deleted**, not fixed. It was
  CFO_Copilot-specific but triggered on generic phrases, so it fired in
  unrelated repos while shadowing the project copy. Nothing was lost — the two
  differed in 5 lines out of 241.
- **Nothing else was deleted.** Overlap is solved by narrowing descriptions.

## Not a defect — do not "fix"

`quick_validate.py` reports `UnicodeDecodeError` on
`dependency-injection-python`, `pytest-testing` and `solid-principles`. All
three are valid UTF-8; the script opens files without `encoding=`, so Python
defaults to cp1252 on Windows and chokes on `❌`/`✅`/`—`. Validator bug.

It also rejects `disable-model-invocation` and `argument-hint` in ~24
third-party global skills. Those are real Claude Code fields the validator
does not know about. Not ours, not broken.
