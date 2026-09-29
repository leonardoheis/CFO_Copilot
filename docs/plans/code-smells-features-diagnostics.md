# Code smells in the features and diagnostics services — Implementation Plan

> **No commit steps.** CLAUDE.md forbids `git commit`/`push`/PR without explicit
> permission for that action. Each task ends at green checks and stages nothing.

**Source:** code-smell review of 2026-09-29 over `services/features/`,
`services/diagnostics/`, `data/panel_store.py`, `data/feature_store.py` and
`playground/01_eda_feature_engineering.ipynb`. Nine smells found; nothing is a
bug (308 tests green before this plan).

**No spec.** Every task is a behaviour-preserving refactor, which CLAUDE.md
lets go without one. The single contract change, the export column rename in
Task 4, is called out there; nothing reads the export yet.

**Goal:** remove the smells that mislead or hide a tunable now; record the
design-level ones with the trigger that would make them worth fixing.

## Global Constraints

- mypy strict; `uv run poe check` green at the end of every task.
- No `# noqa`, `# ruff: ignore`, `# type: ignore`, `# pyright: ignore`.
- Name the refactoring technique before editing (`refactoring-techniques`).
- Existing tests are the safety net: a task may rename what they call, never
  change what they expect. Test count may only grow.
- Superseded plan sections (EDA plan Tasks 2–7) are history: leave their code
  blocks as written. Update only live docs: the services spec and plan, and
  EDA plan Task 8.

## Findings and disposition

| # | Smell | Where | Disposition |
|---|---|---|---|
| 1 | Fallacious Comment + Uncommunicative Name | `features/builder.py:21-29` | **Task 1** |
| 4 | Magic Number / Oddball Solution | `diagnostics/panel.py:68` `n_init=10` | **Task 2** |
| 6 | Duplicate Code (one rule, two places) | `diagnostics/series.py:140`, `:209` | **Task 3** |
| 5 | Fallacious Name | `features/service.py:35` `target_level_usd_m` | **Task 4** |
| 9 | Magic Number | notebook cell 1 `60 - len(EXCLUDED)` | **Task 5** |
| 7 | Message Chain | `features/service.py:30,60` `self._builder.spec.…` | **Task 6** |
| 2 | Switch Statements across methods | `features/transforms.py:70-74`, `87-94` | Deferred — see below |
| 3 | Tramp Data | `regimes` through `service.py` → `builder.py` | Deferred — see below |
| 8 | Middle Man | `diagnostics/service.py:44-52` | Accepted — spec D1 |

Order: 1 → 2 → 3 → 4 → 5 → 6. Each is independent; the order puts the
misleading ones first.

---

### Task 1: Name the feature groups (smell 1)

**Technique:** Rename (enum members), then delete the comments the new names
make redundant.

The comments are wrong for two members: `XD` builds `real_rate`
(`fed_funds − cpi_yoy`, a *derived macro* column), not "cross-sectional";
`C` builds `target_quarter`, a *calendar* feature, not "categorical".

| Member now | Renamed | Value (unchanged) |
|---|---|---|
| `L` | `LAGS` | `"L"` |
| `R` | `ROLLING` | `"R"` |
| `M` | `MARGINS` | `"M"` |
| `X` | `MACRO` | `"X"` |
| `XD` | `MACRO_DERIVED` | `"XD"` |
| `C` | `CALENDAR` | `"C"` |
| `S` | `STATIC` | `"S"` |
| `F` | `FLAGS` | `"F"` |

Values stay the single letters: they are what `RunConfig.feature_groups` logs
to W&B and what the EDA spec's R6 table names, so runs stay comparable.

**Files** (occurrences of `FeatureGroup.<letter>`):
`src/app/services/features/builder.py` (8), `service.py` (1),
`tests/services/features/test_builder.py` (19), `test_service.py` (3),
`test_leakage.py` (1), `tests/injections/test_container.py` (1),
`docs/plans/feature-diagnostics-services.md` (1).

- [x] Step 1: add a test that pins the values: `[g.value for g in FeatureGroup] == ["L", "R", "M", "X", "XD", "C", "S", "F"]`. It passes before and after; it guards the W&B contract.
- [x] Step 2: rename members and every `FeatureGroup.<letter>` reference; delete the eight comments.
- [x] Step 3: `grep -rnE "FeatureGroup\.(L|R|M|X|XD|C|S|F)\b" src tests` finds nothing; `uv run poe check`.

### Task 2: `n_init` joins the regime settings (smell 4)

**Technique:** Replace Magic Number with Symbolic Constant — here a settings
field, since it is tunable like its neighbours `n_regimes` and `seed`.

**Files:** `services/diagnostics/models.py`, `panel.py`,
`tests/services/diagnostics/test_models.py`.

- [x] Step 1: extend `test_defaults_are_todays_values` to expect `{"n_regimes": 3, "seed": 42, "n_init": 10}`; add "`n_init=0` is refused". Run: fails.
- [x] Step 2: `RegimeSettings.n_init: int = Field(default=10, ge=1)`; `assign` passes `n_init=self._settings.n_init`.
- [x] Step 3: `uv run poe check`. Regime tests unchanged and green proves the clustering did not move.

### Task 3: One rule for "logs are defined" (smell 6)

**Technique:** Extract Method.

Two places decide whether every analysed value is positive, one with an
empty-series guard and one without. They agree today only because the second
runs after the length check.

**Files:** `services/diagnostics/series.py`.

- [x] Step 1: `def _log_defined(observed: pd.Series) -> bool: return bool(len(observed) and (observed > 0).all())`.
- [x] Step 2: use it in `_unanalysed` and in `diagnose`.
- [x] Step 3: existing cases cover all three paths (short, constant zero/positive, non-positive, positive); `uv run poe check`.

### Task 4: `target_level_usd_m` → `target_level` (smell 5)

**Technique:** Rename (column).

The name asserts a unit the service cannot know: `FeatureSpec.target_variable`
may be `eps`. **Contract change:** the column name in
`features_h{h}.parquet` changes. Nothing reads those files yet (NB01 has not
been run, NB02 is not written), so there is no migration.

**Files:** `services/features/service.py`, `tests/services/features/test_service.py`,
`tests/injections/test_container.py`, notebook cell 4 (`NON_FEATURE_COLUMNS`),
`docs/plans/eda-feature-engineering.md` Task 8 text (live section only).

- [x] Step 1: rename in the tests first; run: fails on the missing column.
- [x] Step 2: rename in the service and the notebook.
- [x] Step 3: `grep -rn "target_level_usd_m" src tests` finds nothing; `uv run poe check`.

### Task 5: Name the expected company count (smell 9)

**Technique:** Replace Magic Number with Symbolic Constant.

**Files:** notebook cell 1.

- [x] Step 1: `NB00_COMPANIES = 60` beside `QUARTERS = 81`; `assert len(panels) == NB00_COMPANIES - len(EXCLUDED)  # A1`.
- [x] Step 2: `uv run poe check` (nbqa linters run on the notebook).

### Task 6: Stop reaching through the builder's spec (smell 7)

**Technique:** Hide Delegate.

`FeatureService` reads `self._builder.spec.target_variable` and
`self._builder.spec.groups` to decide its own behaviour: it knows the builder's
configuration shape.

**Files:** `services/features/builder.py`, `service.py`,
`tests/services/features/test_builder.py`.

- [x] Step 1: tests on the builder: `target_variable` returns the spec's; `includes(FeatureGroup.STATIC)` is true for the default spec and false for a lags-only spec.
- [x] Step 2: `FeatureBuilder.target_variable` (property) and `FeatureBuilder.includes(group) -> bool`; the service calls those. Drop the public `spec` property if nothing else reads it (grep first).
- [x] Step 3: `uv run poe check`.

---

## Deferred, with the trigger that reopens each

**Smell 2 — Switch Statements across `make` and `reconstruct`.** Both branch
on `self.arm` in parallel; each arm's inverse lives in a different method from
its forward. With three stable arms the round-trip test (all arms × horizons)
catches drift, and polymorphism would add three classes. **Reopen when** a
fourth arm is added: then apply Replace Conditional with Polymorphism, one
small class per arm holding `make` and `reconstruct` together.

**Smell 3 — Tramp Data (`regimes`).** Only group S uses it, yet it crosses
`assemble` → `_company_rows` → `build` → `_static_features`, and
`check_lookahead`. **Reopen when** regimes need versioning or a second static
input appears; then inject them into the builder
(`container.feature_service(builder__regimes=...)`) so only the builder
carries them. Doing it now would move a runtime value into construction for
one caller.

**Smell 8 — Middle Man in `DiagnosticsService`.** Two of three methods
forward. Accepted by the services spec, decision D1 (one facade per package).
**Reopen when** forwarding methods outnumber ones with their own logic.

## Verification

- [x] `uv run poe check` green; test count ≥ 308 + the new cases (Tasks 1, 2, 6).
- [x] `grep -rnE "FeatureGroup\.(L|R|M|X|XD|C|S|F)\b|target_level_usd_m" src tests` finds nothing.
- [x] Summarize changes per task; propose a commit. Stage nothing.
