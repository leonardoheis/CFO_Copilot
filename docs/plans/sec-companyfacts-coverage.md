# Plan — read SEC companyfacts, widen the revenue chain, derive gated EPS

Implements [`docs/specs/sec-companyfacts-coverage.md`](../specs/sec-companyfacts-coverage.md).

Four steps, one per cause in the spec. Each lands with its tests and a green
`uv run poe check`. Re-ingestion and the NB00/NB01 reruns come last, once,
after all four.

## Step 1 — fetch a company's facts once, from `companyfacts` (Cause A; R1, R2)

**Files:** `src/app/data/sources/sec_edgar/source.py`,
`src/app/data/sources/sec_edgar/parsing.py`, `src/app/data/sources/sec_edgar/__init__.py` (no
change expected), tests in `tests/data/sources/test_sec_edgar.py`.

- Replace `SEC_CONCEPT_URL` with
  `SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"`.
- `SecEdgarSource` keeps a per-instance cache `dict[str, JsonObject]` keyed by
  CIK; `_company_facts(cik)` fetches on first use. A `404` means the CIK has
  no XBRL filings and caches an empty payload; any other HTTP error raises
  `DataSourceUnavailableError`, as today.
- `fetch_concept(cik, tag, unit)` keeps its public signature — every chain
  call site and every test that monkeypatches it stays as is — and becomes a
  lookup into the cached payload.
- The lookup itself is pure, so it goes in `parsing.py` as
  `concept_facts(payload, tag, unit) -> list[XbrlFact]`: absent tag or unit →
  `[]`; a unit that is present but not a list → `MalformedPayloadError`
  (the shape `companyconcept` returned in Cause A must never again read as
  "no facts").
- The instance is a `Factory` in the container, so the cache lives for one
  ingestion and is not shared across tickers.

**Tests (TDD, write first):**
- `concept_facts` returns the list for a present tag/unit, `[]` for an absent
  tag, `[]` for an absent unit, and raises `MalformedPayloadError` for
  `{"USD": {}}`.
- Two `fetch_concept` calls for different tags of the same CIK make one HTTP
  request (patch `requests.get` in `app.data.sources.sec_edgar.source`).
- A `404` from `companyfacts` yields `[]` for every tag.

**Cassettes.** The five recorded SEC cassettes hit `companyconcept` URLs and
must be re-recorded. A `companyfacts` payload is ~5 MB per CIK; add a
`before_record_response` hook to `vcr_config` in `tests/data/conftest.py`
that keeps only the us-gaap tags named in `TAG_CHAINS` and
`DILUTED_SHARES_FALLBACK`, so cassettes stay near today's size. Re-record
`test_pipeline`'s cassette for the same reason.

## Step 2 — one revenue tag (Cause B; R3)

**File:** `src/app/data/sources/sec_edgar/concepts.py`.

Append `RegulatedAndUnregulatedOperatingRevenue` to the `revenue` chain,
after `Revenues`. `prefer_largest` stays on. Do **not** add
`RevenueFromContractWithCustomerIncludingAssessedTax` — the spec's
counter-example (SO, GE) shows it inflating revenue above the total.

**Tests:**
- A filer reporting only `RegulatedAndUnregulatedOperatingRevenue` resolves
  revenue from it (NEE's shape).
- A filer reporting `RevenueFromContractWithCustomerExcludingAssessedTax` and
  the larger `RegulatedAndUnregulatedOperatingRevenue` for the same quarter
  resolves the larger (DUK 2018 Q1: 5,928 → 6,135).

**Verification:** the only revenue changes in already-SEC quarters are the
four listed in spec criterion 6.

## Step 3 — legacy CIKs (Cause C; R4)

**File:** `config/companies.yaml` only.

- DIS: `known_cik 0001744489` → `dual_cik`, `legacy_cik: "0001001039"`,
  `current_cik: "0001744489"`.
- MDT: `sec_ticker_lookup` → `dual_cik`, `legacy_cik: "0000064670"`,
  `current_cik: "0001613103"`.

**Tests:** extend the registry test that pins dual-CIK companies, if one
pins them; `CompanyRegistry.sec_ciks("DIS")` returns both, oldest first.

## Step 4 — gated EPS derivation in the vendor fallback (Cause D; R5, R6)

**Files:** `src/app/data/sources/alpha_vantage/parsing.py`,
`src/app/data/sources/alpha_vantage/source.py`,
`tests/data/sources/test_alpha_vantage_parsing.py`.

- New pure function in `parsing.py`:
  `fill_eps_from_net_income(values_by_date) -> None`. It computes the median
  of `|net_income / shares − eps| / |eps|` over quarters reporting all three
  (excluding `|eps| ≤ 0.05`, where a relative error is meaningless). If the
  median is ≤ `EPS_DERIVATION_TOLERANCE = 0.02`, every quarter with net income
  and shares but no EPS gets `net_income / shares`, and a `logger.warning`
  names the quarter as derived (R6). Otherwise it logs once that the filer
  failed the gate and changes nothing.
- Units: `net_income_usd_m` is in millions, shares are a raw count — the
  quotient multiplies by `MILLIONS_DIVISOR`.
- `source.py` calls it after `merge_earnings`.

**Tests:**
- A filer whose reported EPS matches net income ÷ shares fills a missing
  quarter with the quotient.
- A filer whose reported EPS is ~30% off (MRK's shape) fills nothing.
- A quarter missing shares stays empty.
- A filer with no quarter reporting all three fills nothing (no evidence for
  the gate).

## Step 5 — re-ingest and rerun (after all four steps, once)

Not code; run on approval.

1. `uv run poe ingest-data --ticker <T>` for NEE, DUK, ABT, KO, F, COST, BBY,
   SO, DIS, MDT (XOM is out of scope; re-ingest it too, since Step 1 changes
   how every SEC fact is read).
2. Then every other ticker: Step 1 changes the read path for all of them.
   `reingest-batch` skips tickers in `data/processed/reingest_ledger.json`, so
   either clear that ledger or loop over `ingest-data`.
3. Diff each panel against its previous version: changed cells in
   already-SEC-sourced quarters are reviewed against the filer's figure
   (spec criterion 6); no non-null cell may become null (criterion 7).
4. Rerun NB00, then NB01.

## Verification

- `uv run poe check` green after each step.
- Acceptance criteria 1–8 of the spec, checked on the re-ingested panels with
  the same scripts that produced the spec's tables.
