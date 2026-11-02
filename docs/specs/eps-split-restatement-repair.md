# Spec — EPS split-restatement repair runs on every panel

Wave 2, item O1 (`docs/plans/code-smells-wave-2.md`).

## Problem

A quarter cannot report positive net income and non-positive EPS: both
describe the same common earnings. SEC produces that pair when a split-restated
annual EPS is combined with a nine-month comparator that was never restated
(GIS fiscal 2009, 2-for-1 split in 2010), giving a false negative fourth
quarter. Ingestion repairs it by taking the vendor's positive EPS for exactly
those quarters.

The repair sits inside the vendor fallback, and the fallback is skipped when
SEC left no gaps. A panel with complete SEC financials therefore keeps the
inconsistent EPS, and the P/E built from it is undefined for that quarter.

## Evidence

Measured 2026-10-27 from `data/processed/`, offline.

- Stored panels with positive net income and EPS at or below zero:
  **0 of 4,860** rows in `panel_long.parquet`, and 0 in the 60 per-ticker
  panels.
- Every one of the 60 panels called the fallback: each has at least one
  `alpha_vantage` row. Each window starts at **2006-06-30** (20 years before
  2026-06-30), and SEC XBRL starts at **2008-04-01**, so every SEC frame has at
  least seven empty quarters and the gap test never passes.
- The repair did fire where it was built for: GIS's quarter filed under
  2009-06-30 holds **0.43**, the Alpha Vantage value, with provenance
  `ytd_derived`.

So the defect is **latent**: it does not affect any stored panel, and fires
only for a window starting after March 2008: a `--start` given by hand, or the
default 20-year window once its end reaches 2028-06-30 (start 2008-06-30),
provided SEC has no other gap.

**Counter-example, not in scope.** The reverse pair, a loss with positive EPS,
occurs in **18** rows (TSLA 2013–2014 ×5, LLY 2008 ×2, BMY ×2, M ×2, and one
each for ABT, F, MCD, MDT, MRK, NEE, UPS). Ten come from Alpha Vantage, and
several have plausible causes (EPS from continuing operations, non-controlling
interests). It is not the split defect and this repair must not touch it.

## Required behaviour

1. The inconsistent-EPS repair applies to every panel, whether or not SEC left
   gaps.
2. The vendor is still consulted only when it can change something: when SEC
   left gaps, or when at least one quarter has the inconsistent pair. A
   gap-free, consistent panel makes no vendor request (the Alpha Vantage free
   tier allows 25 a day).
3. Only quarters with positive net income and non-positive EPS change, and only
   when the vendor's EPS for that quarter is positive. Otherwise the SEC value
   stays and a warning names the ticker and quarter.

## Acceptance criteria

- A test: SEC financials with no gaps and one inconsistent quarter come out
  with the vendor's positive EPS in that quarter and no other change.
- A test: a gap-free, consistent panel makes no fallback call.
- A test: an inconsistent quarter whose vendor EPS is missing or non-positive
  keeps the SEC value and logs a warning.
- Re-ingesting any one stored company gives a panel identical to the stored
  one (expected, from the evidence above).

## Reruns

None for the stored data: no stored row changes. Re-ingestion is needed only to
confirm the last acceptance criterion; NB00 onward stays as it is.

## Out of scope

- The reverse pair (loss with positive EPS).
- The restatement-versus-comparator defect itself (IBM revenue in
  `docs/data-coverage.md`); this repairs only its EPS symptom.
