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
result = self._try_splits(yf.Ticker(market_ticker), market_ticker)
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
- A `CompanyRegistry` class exposing the resolvers as methods

Adding a new company now only requires editing the YAML file.

**Documented in:** `AGENTS.md` (planned extensions → data ingestion section)

---

## [2026-09-09] Registry loaded as an import-time global

**Smell detected in:** `src/app/data/companies.py`

**Pattern that triggered it:**
```python
SCRAPED_COMPANIES: Final[tuple[ScrapedCompany, ...]] = load_company_registry()
TICKER_INDEX: Final[dict[str, ScrapedCompany]] = _build_ticker_index(SCRAPED_COMPANIES)
```

**Why it is harmful:**
Global Data plus a Hidden Dependency. Every resolver silently reached for
module state instead of receiving it, so callers could not substitute a
different registry and a malformed YAML file failed at *import* time rather
than at a handleable call boundary. It was also inconsistent with the project's
`dependency-injector` convention, which the data layer had not yet adopted at
all.

**Fix applied:**
Replaced both globals with a `CompanyRegistry` class whose methods (
`company_metadata`, `market_history_tickers`, `sec_ciks`, `primary_sec_cik`)
supersede the former module-level resolvers. The registry is now constructed by
a `Singleton` provider in `injections/production.py` and injected into
`YfinanceSource`, `SecEdgarSource`, and `IngestionSources`. The YAML path moved
to `Settings.COMPANY_REGISTRY_PATH`, replacing a fragile
`Path(__file__).resolve().parents[3]` computation.

This also extended container coverage to the data layer for the first time; the
`ingest-data` and `probe-alpha-vantage` CLIs now resolve their sources from the
container instead of constructing them by hand.

---

## [2026-09-09] Duplicated Yahoo Finance history call

**Smell detected in:** `src/app/data/sources/yfinance_source.py`

**Pattern that triggered it:**
`fetch_stock_history` and `_try_stock_history` each contained their own copy of
the same `yf.Ticker(...).history(start=..., end=..., auto_adjust=False)` block
wrapped in an identical `try/except`. The duplication was introduced by the
previous refactor in this file.

**Why it is harmful:**
Duplicate Code of the same *rule*, not coincidental similarity. Any change to
the yfinance call (an extra argument, a different adjustment mode) had to be
made twice and could silently drift. It also carried a
`# type: ignore[no-any-return]` that the project's own typing convention
forbids.

**Fix applied:**
`fetch_stock_history` now delegates to `_try_stock_history` and adds only the
empty-check that raises `TickerNotFoundError`. The ignore comment disappeared
with the duplicate; the single remaining return uses
`cast("pd.DataFrame", history)`.

Two related fixes in the same file:
- Renamed `_fetch_splits` to `_try_splits` so both sentinel helpers share the
  `_try_*` prefix, and extended the `_YahooTicker` Protocol with `history(...)`
  so both accept an injected ticker object. `_try_stock_history` previously
  constructed `yf.Ticker` internally and was the only helper that could not be
  faked in a test.
- `_quarterly_dividend_yield` copies `dividends` before reassigning its index.
  It was mutating the yfinance-cached `.dividends` object in place, unlike the
  sibling price path which already copied.

---

## Inappropriate Static — helpers that never touch `self`

**Pattern that triggered it:**
Nine private helpers across `yfinance_source.py`, `sec_edgar.py` and
`alpha_vantage.py` were declared `@staticmethod` (or `@classmethod`) on their
source class: `_try_stock_history`, `_try_splits`, `_quarterly_dividend_yield`,
`_split_factors_for_filing_dates`, `_read_cache`, `_reports`, `_report_date`,
`_number`, `_millions`, `_row_for_date`.

**Why it is harmful:**
A `@staticmethod` on a class is neither one thing nor the other: it reads as
class API but cannot be overridden per-instance or injected, and it puts pure
functions inside a class that exists to hold state (`self._registry`,
`self._api_key`). It also inflates the class's surface for no benefit.

**Fix applied:**
They are now module-level private functions. This is the resolution that
satisfies both goals — no `@staticmethod`, and no ruff `no-self-use` (PLR6301)
violation, which fires on any method that ignores `self`.

**Convention going forward:**
- A helper that does not read `self` belongs at **module level**, not on the
  class as a `@staticmethod`.
- Converting a helper to module level can cascade: `_merge_income` and its three
  siblings only used `self` to reach the extracted helpers, so they moved out
  too. Re-run lint after each extraction.
- The one exception is **public** API on the source class (e.g.
  `YfinanceSource.fetch_stock_history`), which must stay a method even when it
  ignores `self`. Mark those `# noqa: PLR6301` with a reason.
- Prefer testing through the public API over calling privates: the four tests
  that reached into `YfinanceSource._try_*` were rewritten to drive
  `fetch_splits` / `fetch_stock_history` with a monkeypatched `yf.Ticker`,
  removing every private-access `noqa` from the suite.

---

## Dataclass where a Pydantic model belongs

**Pattern that triggered it:**
`ConceptSpec` (`sec_edgar.py`) and `FieldCoverage` / `CoverageReport`
(`coverage.py`) were frozen dataclasses. `CoverageReport` was then serialized by
hand with `dataclasses.asdict`.

**Why it is harmful:**
`ConceptSpec` accepted an empty tag tuple, which silently produces a concept
that can never resolve a value — a typo in `TAG_CHAINS` would surface as missing
data much later. `asdict` on `CoverageReport` gives no control over JSON
rendering and duplicates what Pydantic already does.

**Fix applied:**
All three became `BaseModel` with `ConfigDict(frozen=True, extra="forbid")`.
`ConceptSpec` gained a `reject_empty_tags` validator, and `report_as_dict` is
now `report.model_dump(mode="json")`. Two `# type: ignore[no-any-return]`
comments in `coverage.py` (`_oldest_date`, `_newest_date`) were removed in the
same pass by wrapping the value in `str(...)`.

**Convention going forward — when *not* to reach for Pydantic:**
- **Protocol-typed fields**: `IngestionSources` keeps `@dataclass` because
  Pydantic cannot validate `Protocol` fields without `@runtime_checkable` plus
  `arbitrary_types_allowed`, which gives a weaker guarantee than mypy already
  provides. Same for `ProbeContext`, which holds live source objects.
- **Exceptions**: `NoTrainedModelError` and `DimensionalityMismatchError` stay
  dataclasses; `BaseModel` does not subclass `Exception` cleanly.
- **`companies.py` stays split**: the `_*Config` Pydantic models validate the
  YAML shape and the dataclass domain types (`ScrapedCompany`, `KnownCik`, ...)
  model the business meaning, bridged by `_to_domain_company`. Collapsing them
  into one discriminated-union hierarchy would delete ~80 lines but leak the
  YAML `type:` discriminator into the domain. Keep the split.
- Pydantic models take **keyword arguments only**. Converting a dataclass that
  was constructed positionally (as `TAG_CHAINS` was) requires updating every
  call site.

---

## Source modules promoted to Anti-Corruption Layer packages

**Pattern that triggered it:**
After the `@staticmethod` removal, each source module was a class followed by a
run of loose module-level functions — `alpha_vantage.py` had ten, `sec_edgar.py`
was 354 lines mixing an HTTP client, us-gaap tag declarations, and panel
derivation. The grouping was real but implicit: you had to read the file to see
which parts touched the network and which were pure.

**Why it is harmful:**
Nothing signalled the boundary between the stateful adapter and the pure
translation of a vendor's payload, so there was no structural pressure keeping
vendor field names from spreading. It also made the wrong thing easy: the
obvious home for a "shared-looking" helper was a shared module, which would have
leaked one vendor's JSON keys into the common data layer.

**Fix applied:**
Every source is now a package with the same shape:

```
sources/<vendor>/
    __init__.py   # the only public surface
    source.py     # the *Source class: HTTP, cache, credentials
    parsing.py    # pure payload -> panel translation
```

`sec_edgar` adds `concepts.py` (`ConceptSpec`, `TAG_CHAINS`, unit constants) and
`yfinance_source` uses `fetching.py` (helpers over an injected `YahooTicker`)
instead of `parsing.py`. `fred/` has only `source.py` — it has nothing pure to
separate, and an empty `parsing.py` for symmetry would be worse than none.

**Why this is the right home, in DDD terms:**
These functions are an **Anti-Corruption Layer**, not a crosscutting concern.
Crosscutting means orthogonal to every domain (logging, auth, transactions);
this is translation of one external system's model into ours, and the ACL
pattern puts that translation at the boundary with that specific system. The
genuinely shared logic — `dates.py`, `splits.py`, `xbrl.py` — was already
extracted; what remained was vendor-specific and could not be shared, because
nothing else speaks `fiscalDateEnding` or `quarterlyReports`.

**Conventions this established:**
- One-way imports: `source.py` -> `parsing.py`, never the reverse.
- Names crossing a module boundary lose the leading underscore. Ruff's
  `import-private-name` rejects importing `_foo` from a sibling, so
  package-internal helpers are public within the package and stay off the public
  API by not appearing in `__init__.py`.
- Tests patch the submodule that owns the import:
  `app.data.sources.yfinance_source.source.yf.Ticker`, not the package root.
  Eleven monkeypatch targets moved down one level in this refactor.
- `ConceptSpec` gained a named `DILUTED_SHARES_FALLBACK` constant instead of
  being constructed inline inside `_fetch_shares_chain`.

**Verified, not assumed:**
The `# noqa: PLR6301` on `fetch_stock_history` is rewritten by the toolchain to
`# ruff: ignore[no-self-use]`. Because `# ruff:` is normally a *file-level*
directive prefix, this was checked rather than trusted: stripping the comment
makes `no-self-use` fire again, and an injected unused import is still reported,
so it suppresses exactly one rule on one line and does not disable the file.

---

## Falsy `or` swallowing a legitimately reported zero

**Pattern that triggered it:**

```python
values["eps"] = number(report, "dilutedEPS") or number(report, "basicEPS")
```

**Why it is harmful:**
This is a real data-corruption bug, not a style issue. `or` tests falsiness, not
`None`. A breakeven quarter reports a diluted EPS of `0.00`, which is falsy, so
the expression silently discards the correct value and substitutes `basicEPS`.
Amazon — the primary company in this project — has genuine near-zero EPS
quarters, so this path was reachable with real data. The same shape appeared in
`row_for_date` as `values = values or empty_financial_quarter_values()`, where an
empty dict is also falsy.

**Fix applied:**
Explicit `is None` checks, and two regression tests: a reported `0.00` diluted
EPS must stay `0.0` even when `basicEPS` is `1.50`, and an *absent* `dilutedEPS`
must still fall back to `basicEPS`. Both behaviours matter and only the second
was previously covered.

**Convention going forward:**
Never use `or` to supply a fallback for a value that can legitimately be `0`,
`0.0`, `""`, or an empty collection. Write `x if x is not None else fallback`.
The one place a falsy test is correct is a division guard (`_margin`), where
`None` and `0.0` are exactly the set of undividable denominators — and that is
documented in the function's docstring.

---

## Stringly-typed value bags at the ACL boundary

**Pattern that triggered it:**
`FinancialQuarterValues = dict[str, float | None]` accumulated values by string
key (`values["revenue_usd_m"] = ...`), and `row_for_date` returned
`dict[str, date | float | None]` that was handed to `pandas.DataFrame`.

**Why it is harmful:**
A mistyped key silently created a new entry, leaving the real field `None`
forever with no error at any layer. Nothing tied the emitted keys to
`FINANCIAL_COLUMNS`, so the panel contract lived only in the `.loc[...]` reorder
at the call site.

**Fix applied:**
Both became Pydantic models in `schema.py`: `FinancialQuarterValues` (mutable
accumulator, `extra="forbid"`) and `FinancialsRow` (the emitted row). Writes are
now attribute assignments that mypy checks. `FINANCIAL_ACCUMULATOR_FIELDS` and
`empty_financial_quarter_values()` were deleted — field defaults replace them.
`tests/data/test_schema.py` locks `list(FinancialsRow.model_fields)` to
`["date", *FINANCIAL_COLUMNS, "shares_outstanding"]`, since `model_dump()` order
is what pandas consumes.

---

## Where `X | None` was deliberately kept

Reviewing `alpha_vantage/parsing.py` against the "stop using None" guidance, most
of its `None`s were the legitimate kind and were left alone:

- `report_date() -> date | None` and `number()/millions() -> float | None` stay.
  The test is whether a caller does something *different* per reason, and none
  do: a missing field, a wrong type, and an unparsable value all mean "this
  quarter did not report it", and every caller either skips or propagates.
  Adding a result type with a `reason` nobody branches on would be the same
  overload problem in a fancier box.
- These are also a **system boundary** (external API JSON), which is the one
  place `X | None` is the right tool rather than a smell.
- `reports()` already returns `[]` rather than `None` for "nothing here", which
  is the pattern to copy: callers iterate with no guard at all.

The lesson: the guidance is about *ambiguous* absence. Applying it mechanically
to every `| None` would have added ceremony and removed nothing.

---

## One `except ValueError` hiding two different failures

**Pattern that triggered it:**

```python
try:
    return nearest_quarter_end(date.fromisoformat(raw_date), 46)
except ValueError:
    return None
```

**Why it is harmful:**
The single handler covered two unrelated conditions with opposite correct
responses. `date.fromisoformat` failing means `fiscalDateEnding` is **malformed**
— the API changed shape or the payload is corrupt — and swallowing it turned a
format change into silent gaps in the panel. `nearest_quarter_end` failing would
mean the date parsed but could not be placed on a quarter, a different situation
entirely. Neither was distinguishable by the caller.

**Verified before acting, and it changed the fix:**
The second branch is **unreachable at the shipped tolerance**. Brute-forcing
every date from 2003 to 2027 showed the maximum distance to a nearest quarter end
is exactly 46 days — the longest quarter is 92 days, so half of it is 46, and the
guard tests `> 46`. The 46 was evidently chosen to accept every date. The
"off-cycle fiscal filing" case that seemed to justify returning `None` does not
exist, and a test written for it failed, which is what exposed this.

**Fix applied:**
`report_date` is now **total**: it returns `date`, never `date | None`. Absent,
non-string, and unparsable `fiscalDateEnding` all raise the new
`MalformedPayloadError(DataSourceError)`. The unreachable tolerance branch also
raises rather than returning a sentinel, so a future tightening of
`QUARTER_END_TOLERANCE_DAYS` fails loudly instead of silently dropping quarters.
Removing the optional return deleted four `if quarter_date is None: continue`
guards from the merge functions.

**Convention going forward:**
- One `try` per failure mode. If a block can raise the same exception type for
  reasons that deserve different handling, split it.
- Prefer making a function **total** over returning `X | None`: if every non-value
  outcome is an error, raise, and the callers' `None` checks disappear.
- Check whether a defensive branch is reachable before designing around it. Here
  a five-line brute force replaced a plausible-sounding assumption that was wrong
  and would have added a warning path, a sentinel, and a test for a case that
  cannot occur.

---

## Error severity and code-smell review

External payload parsing now follows a loss-based rule: warn and return `None`
when one field is unusable, raise `MalformedPayloadError` when a record cannot
be placed or a payload is structurally invalid, and wrap all bare conversion
errors before they leave the data layer.

The reviewed Alpha Vantage merge functions shared the same report iteration and
quarter accumulator setup. That scaffolding was extracted, but the extraction
intentionally creates an accumulator before field-level validation; panel rows
are driven by the requested quarter dates, so this does not add output rows.
The two unused public XBRL wrappers were removed because production already
uses the dataframe-producing entry point. The shared 46-day fiscal tolerance
was moved to `dates.py` so Alpha Vantage and SEC cannot drift.

`OutOfBoundsDatetime` is a `ValueError` subclass raised by pandas for dates such
as `9999-12-31`; the report-date error message therefore describes both
malformed and unplaceable dates instead of falsely claiming only a tolerance
failure.
