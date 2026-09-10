# CFO Copilot — Code Quality Memory

A running log of code smells caught during development and the conventions
established to prevent them from recurring. Each entry records the smell,
where it was found, how it was fixed, and the rule that now applies.

Agents and contributors should consult this file alongside `AGENTS.md` /
`CLAUDE.md` before writing new code.

---

## [2026-09-09] Exceptions used as control flow in fallback loops

**Smell detected in:** `src/app/data/sources/yfinance_source.py`

**Pattern that triggered it (first form — silent):**
```python
except TickerNotFoundError:
    continue   # exception swallowed; nothing logged
```

**Pattern that triggered it (second form — logged but still wrong):**
```python
except TickerNotFoundError as error:
    logger.warning("Skipping %s: %s", market_ticker, error)
    continue   # exception still drives iteration — control flow via exceptions
```

**Why it is harmful:**
Both forms use exceptions as a signalling mechanism for ordinary loop flow.
Exceptions are for unexpected failures; using them to decide "try the next
item" couples iteration logic to error handling, obscures intent, and still
hides the "not found" case from callers (the exception is caught and
discarded). Adding a log message makes the skip visible, but does not fix the
underlying design: the exception should never have been raised there in the
first place.

**Fix applied:**
Split each public method into two layers:

- **Private `_try_*` helpers** return empty `Series` / `DataFrame` when no
  data is found (sentinel value). They only raise for genuine API failures
  (`DataSourceUnavailableError`).
- **Loop callers** check `.empty` (a plain value comparison), log a warning,
  and `continue` — no `try/except` anywhere in the loop.
- **Public methods** raise `TickerNotFoundError` once, after the loop, when
  every fallback is exhausted.

```python
# ✓ correct — no exception in the loop; sentinel value checked instead
result = self._try_fetch_splits(yf.Ticker(market_ticker), market_ticker)
if result.empty:
    logger.warning("No split data available for %s", market_ticker)
    continue
```

**Rule added to `AGENTS.md` / `CLAUDE.md`:** "Error-handling conventions"

---

## [2026-09-08] `# type: ignore[no-any-return]` masking untyped returns

**Smell detected in:** `src/app/data/sources/yfinance_source.py`

**Pattern that triggered it:**
```python
return result  # type: ignore[no-any-return]
```

**Why it is harmful:**
Silencing mypy with `no-any-return` hides the fact that a return type is
unresolved. It prevents mypy from catching genuine type errors in callers and
sets a precedent for ignoring type issues rather than fixing them.

**Fix applied:**
Removed the ignore comment. The underlying type issue was resolved by
guarding the `None` case explicitly and raising `TickerNotFoundError` before
the return, giving mypy a concrete, non-`Any` type at the return site.

**Rule added to `AGENTS.md` / `CLAUDE.md`:** "Typing conventions"

---

## [2026-09-08] Hardcoded company metadata in Python source

**Smell detected in:** `src/app/data/schema.py` (original `COMPANY_METADATA` dict)

**Pattern that triggered it:**
Company profiles (CIK numbers, sector, market tickers) were hardcoded as
Python dictionaries inside source files. Adding or changing a company required
a code change, a review, and a redeploy.

**Fix applied:**
Moved all company profiles to `config/companies.yaml`. Added
`src/app/data/companies.py` with:
- Pydantic-validated YAML loading (`load_company_registry`)
- Typed domain dataclasses (`ScrapedCompany`, `KnownCik`, `DualCikFiling`, etc.)
- Public resolver functions (`resolve_sec_ciks`, `resolve_market_history_tickers`, …)

Adding a new company now only requires editing the YAML file.

**Documented in:** `AGENTS.md` (planned extensions → data ingestion section)
