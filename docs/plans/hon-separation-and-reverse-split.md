# Plan — HON: 2026 separation and 1-for-2 reverse split

Spec: `docs/specs/hon-separation-and-reverse-split.md`.

Two independent items, H1 first because it is configuration only. Code and
tests here; the HON re-ingest and the notebook reruns are run by hand
afterwards, because they call live APIs and rewrite `data/processed/` and
`data/features/`.

## H1 — Withhold HON 2025-Q3

1. `config/companies.yaml`: under HON's `panel`, add `withheld_quarters` with
   `2025-09-30` and its reason (revenue restated to continuing operations,
   4,929, between whole-company quarters ≈9,300; review when the window passes
   2026-Q2), citing the spec, as ABT's entry does.
2. Test in `tests/data/test_companies.py` only if the registry test pins the
   withheld entries by company; otherwise the existing withheld-quarter tests
   in `test_pipeline.py` and `test_missing.py` already cover the mechanism.

Rerun: re-ingest HON.

Status: done (2026-10-30). The registry test pins HON's entry. HON
re-ingested on 2006-06-30 → 2026-06-30: exactly the 12 financial cells of
2025-09-30 became missing (revenue 4,929, operating income 866, EBITDA
1,114, …); no other cell changed. Market cap stays 66,063 there until H2.

A6 holds (author's NB00, NB01, NB01b runs of 2026-10-30, compared with
2026-10-28 in W&B). Every diagnostics change is HON's row (revenue `d_levels`
back to 1; forecastable counts unchanged at 52, 51, 54, 57). The register lost
12 HON entries and gained one (2025-06-30 EPS 4.90, the H2 basis, now next to
an empty quarter): 807 → 796. HON's 15 revenue target extremes are gone. NB01b
revenue rows changed for HON only, and every decision is unchanged.
Side effects:
- HON leaves NB01b for the three revenue-scaled targets (295 → 290 rows):
  the target's one-quarter gap is interpolated, but the revenue it is scaled
  by is not, so the scaled series breaks for a year and falls below the
  minimum length.
- The calendar group's best mutual information for revenue and EBITDA now
  reaches the 0.005 floor exactly, so C is no longer a drop candidate for
  them; it sits on the floor, and NB02's ablation decides it anyway.

## H2 — The filer's split ratio governs restated comparatives

The correction multiplies a per-share value by `filer ratio / market factor`
(and divides a share count by it) when the value comes from a filing made on
or after the event but describes a quarter ending before it. Filings made
before the event are already scaled by the market factor; quarters ending on
or after it are on the actual basis, which is the market basis there.

1. `data/sources/sec_edgar/concepts.py`: declare the split-ratio concept
   (`StockholdersEquityNoteStockSplitConversionRatio1`, unit `pure`).
2. `data/sources/sec_edgar/parsing.py`, pure functions:
   - pair each market split event with the filer ratios dated within 7 days;
     an event is corrected only when it has ratios, none agrees with the market
     factor within 1%, and they agree with each other; ratios that disagree
     with each other are logged and change nothing;
   - the correction multiplier for a set of records, from each record's quarter
     end (the records' index) and filing date: 1.0 except where a corrected
     event falls after the quarter end and on or before the filing date.
3. `data/sources/sec_edgar/chains.py`: in `quarterly_financials`, read the
   filer's ratios once through `facts_for` and pass the corrected events
   down; `_tag_chain_records` multiplies per-share values by the multiplier
   after the existing split scaling, `_shares_chain` divides share counts by
   it. Without ratios, or without market splits, the path is unchanged.
4. Tests in `tests/data/sources/test_sec_edgar_parsing.py` (pure functions)
   and `tests/data/sources/test_sec_edgar_shares.py` (through the chain):
   - HON's case: ratio 0.5 against factor 0.9535; a 2026-07-23 filing's
     2025-Q2 EPS 4.90 becomes 2.57 and its 317.5 m shares 605.5 m; its 2026-Q2
     values and a pre-event filing's values are unchanged;
   - an agreeing ratio (GE's 0.125) changes nothing;
   - DUK's case: 0.8708 and 0.333 near a 0.3333 event change nothing;
   - a ratio with no market event within 7 days changes nothing;
   - two disagreeing ratios near one event change nothing and log a warning.

Rerun: re-ingest HON. The other 59 are checked offline (step 5) rather than
re-ingested.

5. Offline check for A4: run the event pairing over the 60 companies' split
   ratios and Yahoo splits; only HON's 2026-06-29 event may be corrected.

Status: not started.

## Verification

- `uv run poe check` after each item.
- After the manual HON re-ingest (`uv run python -m app.data --ticker HON
  --start 2006-06-30 --end 2026-06-30`, after archiving HON's ledger entry if
  the batch path is used): A1–A3 against the copy in
  `data/backups/processed_2026-10-28/`; every other HON cell unchanged except
  the three per-share rows and the withheld row.
- After NB00, NB01 and NB01b: A6; NB00's ledger has no new `unexplained` row.
- Record the results here and in the spec, as in
  `docs/plans/output-sensitive-fixes.md`.
