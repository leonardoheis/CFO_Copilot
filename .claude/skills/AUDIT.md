# Skills Audit — `.claude/skills/`

Audited 17 skills against the official `skill-creator` rubric
(`plugins/marketplaces/claude-plugins-official/plugins/skill-creator/skills/skill-creator/SKILL.md`),
via 3 parallel subagents plus the rubric's own `quick_validate.py`.

Date: 2026-09-15. Branch: `feature/data-ingestion`.

---

## Verdict

| Verdict | Count | Skills |
|---|---|---|
| SOLID | 5 | `analyzing-time-series`, `dependency-injection-python`, `pep8-check`, `solid-principles`, `stop-using-none` |
| NEEDS WORK | 7 | `cfo-copilot-structure`, `code-smells`, `design-patterns`, `optimal-scaffold`, `pydantic`, `pytest-testing`, `refactoring-techniques` |
| REWRITE / DELETE | 5 | `code-structure`, `ddd-python`, `find-skills`, `python-backend`, `python-oop` |

**Root cause, stated once:** most of these skills were transplanted from other
projects and never re-grounded. Fingerprints of at least four foreign
codebases are present — `classiflow` (decree classification, FAISS, PDFs,
`phi4-mini`), a Wine Reviews ML project, an Ollama/Spanish-document project,
and a TypeScript/Next.js server-actions project. A skill that is merely
generic makes an agent look around. A skill that confidently asserts false
repo facts makes it hunt for symbols that do not exist, or write code that
fails your lint gate.

---

## P0 — fix before trusting these skills

All verified against the working tree, not taken on the subagents' word.

| # | Skill | Problem | Fix |
|---|---|---|---|
| 1 | `python-oop` | Illegal `version: 1.0.0` frontmatter key (line 4). Only `name, description, license, allowed-tools, metadata, compatibility` permitted. | Delete line 4, or move under `metadata:`. |
| 2 | `python-oop` | Line 26 recommends `@staticmethod`. CLAUDE.md forbids it; `pylint.extensions.no_self_use` is enabled (`pyproject.toml:241`); **0** occurrences in `src/app/`. **Following this skill fails `poe lint`.** | Replace with: a helper reading neither `self` nor `cls` goes at module level as a private function. Same fix for the line 68 table row. |
| 3 | `python-backend` | Documents an `api → services → infrastructure → domain` architecture. **`src/app/infrastructure/` does not exist.** Also mandates per-client fakes, contradicting the `TestContainer` convention. | Delete the skill (see Consolidation below). |
| 4 | `optimal-scaffold` | Says `ROUTERS` is a **list** in `api/routes/__init__.py`. It is a **tuple** in `api/routes/registry.py:9`. Same drift for `EXCEPTION_HANDLERS` (`error_handlers/registry.py:11`). Edits land in the wrong file. | Point at `registry.py` for both; correct tuple syntax. |
| 5 | `optimal-scaffold` | Says `settings = _Settings()`, import `from app.settings import settings`. Real export is `Settings = _Settings()` (`settings.py:91`). **That import is an ImportError.** | `Settings = _Settings()` / `from app.settings import Settings`. |
| 6 | `code-smells` | Cites `ConfidenceTier`/`OodEvidence` (line 96) and "this project's `Settings.OOD_COSINE_THRESHOLD`" (line 124). None exist here. | Delete both parentheticals; generalize line 124. |
| 7 | `code-structure` | Entirely TypeScript (`export async function`, server actions, `previewUrl`) in a Python-only repo. Pushes an `actions/` layer that does not exist. | Port to Python/FastAPI or delete. |
| 8 | `ddd-python` | 636 lines (rubric: <500) and contains broken code: `rename()` assigns a `model_fields` annotation then `del`s it; `DomainEvent` uses `field(...)` unimported with non-default fields after a defaulted one → `TypeError` at import. | Move dataclass variants to `references/dataclasses.md` (−200 lines); fix both snippets. |
| 9 | `find-skills` | Premise is dead: instructs `npx skills find` against `skills.sh`, but discovery is built into this harness (~120 skills surfaced by name, first-party `Skill` tool). Worse, it triggers on "how do I do X" — hijacking ordinary questions. | Delete the directory. |
| 10 | `refactoring-techniques` | Line 105 references `.claude/learnings.md`. **File does not exist.** | Point at CLAUDE.md's error-handling conventions. |

---

## P1 — degrades triggering or accuracy

**Triggering collisions.** Ten Python skills share tokens: `refactor`,
`extract`, `decouple`, `avoid duplication`, `schema`, `domain`. A bare
"refactor this function" is a 4-way coin flip between `design-patterns`,
`refactoring-techniques`, `code-smells`, and `solid-principles` — and
`design-patterns` is the worst to win, since it proposes a GoF pattern for
what is usually an extract-method.

- `design-patterns` — drop `refactor`/`extract`/`avoid duplication`; keep `which design pattern`, `Strategy/Observer/Factory/Adapter`, `swap implementations at runtime`.
- `pydantic` — replace bare `schema` with `request schema`/`response schema`/`pydantic schema`.
- `python-oop` — drop `separate concerns` (that is SRP, owned by `solid-principles`) and `refactor to classes`.
- `cfo-copilot-structure` vs `optimal-scaffold` — same repo, same job, already divergent facts. Narrow the former to *navigation*, let the latter own *creation*. Or merge (recommended below).

**Descriptions are keyword lists, not capability statements.** Five of six in
group B open with "Use when…" and never say what the skill *contains*. The
rubric wants both, and wants them pushy, because Claude under-triggers.
Weakest: `analyzing-time-series` (won't fire on "should I difference this
before ARIMA?"), `design-patterns` (opens with a governance rule), `pydantic`.

**"When to use" stranded in the body** — invisible at trigger time, so it does
nothing: `ddd-python` (`## When to Activate`), `code-structure`
(`## When to Use`), `stop-using-none` (11 lines), `find-skills` (22 lines).

**Foreign examples claiming local provenance** — `pytest-testing` and
`pydantic` are built on `classiflow` (FAISS, PDFs, `decreto.pdf`) while
`pydantic:13` claims *"Project convention (from CFO_Copilot)"*.
`dependency-injection-python:65` claims `ClassificationService` is "the pattern
used in this project". `solid-principles` uses `OllamaClient`/`decreto`.

**Coverage gaps against the live repo:**
- `src/app/data/` — the largest, most active subtree, with its own CLAUDE.md conventions (Anti-Corruption Layer, one-way `source.py → parsing.py`, `config/companies.yaml`) — is **invisible to every skill audited**.
- `pytest-testing` never mentions **syrupy snapshots** or **`TestContainer`** — the repo's two defining test mechanics — despite being the skill that fires on "write a test".
- Missing poe tasks: `ingest-data`, `probe-alpha-vantage`, and `check` (the documented pre-commit gate).

---

## P2 — polish

- All-caps `## MANDATORY RULE:` headings in `code-smells`, `refactoring-techniques`, `design-patterns`. The rubric flags this; the reasoning underneath is already good enough to carry it.
- Zero worked examples in `python-backend`, `refactoring-techniques`, `design-patterns`, `pep8-check`. The two skills that pass cleanest (`solid-principles`, `stop-using-none`) are the two with paired before/after code.
- Unresolvable Obsidian wikilinks `[[code-smells]]`, `[[refactoring-techniques]]`.
- Graphviz `dot` blocks in `dependency-injection-python` and `pytest-testing` — nothing renders them; prose is shorter.
- `ExamplerMixin` vs real `ExamplerMixIn` (`utils/exampler.py:11`) — `optimal-scaffold` and `pydantic` disagree with each other.
- Committed `scripts/__pycache__/*.pyc` in `analyzing-time-series`.
- `pydantic` raises `DimensionalityMismatchError` from `app.exceptions` — real path is `app.services.training.exceptions`; also, raising a non-`ValueError` in a validator bypasses Pydantic's error collection.

---

## Consolidation recommendation

17 skills is too many for one repo; the overlap is why triggering is unreliable.

- **Delete `python-backend`** — broadest triggers, worst accuracy. It beats correct siblings on generic prompts while serving an architecture this repo doesn't have. `cfo-copilot-structure` + `optimal-scaffold` + `dependency-injection-python` already cover its correct intent.
- **Delete `find-skills`** — superseded by the harness.
- **Delete or port `code-structure`** — wrong language entirely.
- **Merge `python-oop` into `solid-principles`** — its "one class = one responsibility" *is* SRP. Extract the sklearn fit/transform material as a separate narrow skill if it's still wanted.
- **Merge `optimal-scaffold` into `cfo-copilot-structure`** — keep the latter's name (it tracks CLAUDE.md), fold in the former's step-by-step checklist, fix the registry/settings drift once.

Net: 17 → 12, with the surviving set grounded in the real tree.

**Keep as-is:** the `code-smells` → `refactoring-techniques` handoff is
deliberate and well-managed (the latter's description explicitly says it fires
*after* a code-smells finding). That is the pattern the other overlaps should
imitate.

---

## Not a defect — do not "fix"

`quick_validate.py` reports `UnicodeDecodeError` on
`dependency-injection-python`, `pytest-testing`, and `solid-principles`. All
three are **valid UTF-8**. The script calls `open()` without `encoding=`, so
Python defaults to cp1252 on Windows and chokes on `❌`/`✅`/`—`. The bug is in
the validator, not your files. Fix upstream with `open(path, encoding="utf-8")`.

---

## Suggested order

1. **P0 #1–5** — one-line edits, each prevents a concrete failure (lint break, ImportError, wrong-file edit).
2. **Deletions** — `find-skills`, `python-backend`, `code-structure`. Removes the worst mis-triggering in one move.
3. **P0 #6–8, #10** — dead references and `ddd-python`'s broken snippets.
4. **Merges** — `python-oop` → `solid-principles`, `optimal-scaffold` → `cfo-copilot-structure`.
5. **P1 descriptions** — narrow collided trigger tokens, add capability statements.
6. **Add `src/app/data/` coverage** to whichever structure skill survives.
