# Ingestion: tag precedence, progress output, and an add-company command

Implements [`docs/specs/sec-tag-precedence.md`](../specs/sec-tag-precedence.md)
(part 1). Parts 2 and 3 are tooling and have no separate spec.

## Context

Three things, discovered while registering ORCL and IBM.

**1. A superseded us-gaap tag silently wins over the real value.** The tag
chain takes the first tag that reports a quarter. When a filer migrates
between tags, the old tag often keeps reporting a *partial* figure rather than
stopping. For Oracle:

| quarter | `SalesRevenueNet` | `Revenues` (truth) | ratio |
|---|---|---|---|
| 2009-03-31 … 2009-12-31 | **0** | 5453 … 5858 | 0.00 |
| 2010-03-31 | **458** | 6404 | 0.07 |
| 2010-06-30 | **1832** | 9505 | 0.19 |
| 2011-06-30 | **1829** | 10775 | 0.17 |

The zeros were fixed by treating 0 as not-reported. The 2010–2011 values are
not zero, so they still win and the panel carries revenue ~5× too low. IBM has
tag transitions too, so it is exposed to the same failure.

**2. The scraper is silent.** `python -m app.data --ticker IBM` prints one
line at the start and one at the end, with 12 SEC concept chains, prices,
macros and an Alpha Vantage fallback in between. A slow run is
indistinguishable from a hung one.

**3. Registering a company is a manual two-file edit.** `config/companies.yaml`
plus the pinned set in `test_scraped_companies_lists_each_profile_once`. Easy
to get the CIK wrong, and nothing warns about the traps we just hit.

---

## 1. Tag precedence — opt in per concept

**Do not apply "prefer the larger value" globally.** Verified counter-example:
`eps` chains `EarningsPerShareDiluted` → `EarningsPerShareBasic`, and Basic is
*always ≥* Diluted (MSFT 2023: 2.46 vs 2.45 every quarter). A blanket rule
would silently switch every EPS to Basic — a regression worse than the bug.

Add a field to `ConceptSpec` in
`src/app/data/sources/sec_edgar/concepts.py`:

```python
class ConceptSpec(BaseModel):
    tags: tuple[str, ...]
    unit: str = USD_UNIT
    prefer_largest: bool = False  # for totals whose narrower tag is a subtotal
```

Set `prefer_largest=True` on **`revenue`, `cogs`, `dep_amort`,
`operating_cash_flow`, `capex`** — the multi-tag concepts that never report a
negative in any panel written so far, where a value under a narrower tag is a
component of the same period's total.

Leave `eps` false: it chains Diluted → Basic, and Basic is always ≥ Diluted,
so the flag would silently replace a correct value with a wrong one. See
[`docs/specs/sec-tag-precedence.md`](../specs/sec-tag-precedence.md) for the
verified numbers and the full concept table. `costs_and_expenses`,
`operating_income` and `net_income` have a single tag each, so precedence
cannot arise for them.

In `_fetch_tag_chain` (`sources/sec_edgar/source.py`), when `prefer_largest`
is set, keep reading the whole chain and take the element-wise maximum instead
of stopping at the first non-null. This subsumes the existing zero-filter:
0 loses to any real value. Keep `_without_placeholder_zeros` for the
`False` path.

Cost: one extra HTTP call per affected concept for filers that resolve on the
first tag. Four concepts, so at most four more calls per ingest — acceptable
against silently wrong revenue.

**Tests** (`tests/data/sources/test_sec_edgar.py`, monkeypatching
`fetch_concept` as the existing tests do):

- a superseded tag reporting 458 does not beat a later tag reporting 6404
- `prefer_largest=False` still stops at the first tag (EPS keeps Diluted over
  a larger Basic) — this is the regression guard for the counter-example above
- the existing zero case still passes through the new path
- negative values are not mangled: a `net_income` chain (`prefer_largest`
  False) with -100 in the first tag keeps -100

---

## 2. Progress output — per-step lines with timing

Plain `click.echo`, no new dependency, assertable in tests, readable in CI.
Shape:

```
ORCL  resolving CIK                                      0000341439   0.4s
ORCL  SEC concepts          12/12                                    8.1s
ORCL  prices and splits                                              1.2s
ORCL  macro series                                                   0.9s
ORCL  Alpha Vantage fallback   filling 43 gaps                       4.6s
ORCL  wrote 81 rows -> data/processed/ORCL_panel.parquet            15.4s
```

Emit from `runner.py` around the pipeline stages rather than from inside the
sources, so the data layer stays free of presentation concerns. Add a
`--quiet` flag that suppresses everything except the final line.

The Alpha Vantage line should state how many gaps it is filling — that number
is the signal that a filer's SEC data is thin, and it is invisible today.

**Tests** (`tests/data/test_runner.py`, click's `CliRunner`):
- a normal run prints a line per stage and the final destination
- `--quiet` prints only the final line
- the fallback line reports the gap count

---

## 3. `add-company` command

New click command, registered next to `ingest-data`:

```bash
uv run python -m app.data.add_company --ticker IBM
uv run python -m app.data.add_company --ticker IBM --ingest
```

Steps:

1. Look up the CIK in SEC's `company_tickers.json` — the same source
   `SecEdgarSource._lookup_ticker_cik` already uses. Refuse unknown tickers
   (this is what caught `IBME`).
2. Refuse a ticker already in the registry.
3. Take `--company` and `--sector`, defaulting the company name to SEC's
   `title`, title-cased. Sector has no authoritative free source, so prompt
   for it rather than guessing.
4. Append the entry to `config/companies.yaml`, preserving the existing block
   style (round-trip the file as text, not via a YAML dump that would reformat
   the whole file).
5. **Run the traps check and print warnings** — the part that earns the
   command:
   - probe `revenue` across its tag chain; if two tags report the same quarter
     with a ratio outside ~0.9–1.1, warn that a tag transition is present
   - detect a non-calendar fiscal year from the fact `end` dates and say so
     explicitly (Oracle's May year-end is why its 2009 broke)
6. With `--ingest`, run the ingestion afterwards.

The pinned company set in `test_scraped_companies_lists_each_profile_once`
still needs a manual edit — the command must not rewrite tests. Print a
reminder naming the file and the string to add.

**Tests** (`tests/data/test_add_company.py`): unknown ticker rejected;
duplicate rejected; YAML entry appended with the right CIK and the file's
other entries untouched; trap warnings fire on a stubbed transition.

---

## Verification

1. `uv run poe check` green at each step.
2. Re-ingest **ORCL** and confirm 2010–2011 revenue reads 6404 / 9505 / 7502 /
   8582 instead of 458 / 1832 / 1698 / 1753, and that no revenue is 0.
3. Re-ingest **MSFT** and **AAPL** and diff against the current panels — must
   be 0 cells changed, the same check used for the zero fix.
4. Confirm EPS is unchanged for MSFT across the whole panel (the Basic/Diluted
   regression guard, verified against real data rather than only the unit test).
5. Run `add-company --ticker IBM` on a copy of the registry and confirm the
   trap check reports IBM's tag transitions, if any.

## Order

1 → 2 → 3. The tag fix is the only one that changes stored data, so it lands
first and its re-ingest verification is the baseline for everything after.

## Not doing

- **Per-company tag overrides in the YAML.** Considered and rejected: it needs
  manual curation per ticker *and* per transition, so the work grows with the
  registry. Revisit only if a filer defeats the largest-value rule.
- **A rich progress bar.** `rich` is installed and would look better
  interactively, but it is noisy in CI logs and harder to assert on.
