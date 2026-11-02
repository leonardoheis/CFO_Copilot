# Plan — NB01's five pending items

Spec: [`docs/specs/nb01-pending-items.md`](../specs/nb01-pending-items.md).

The thesis ("Decisiones para la etapa de modelado → Pendientes") and NB01's
open question 6 list five items. Decided 2026-10-19: fix items 1–3; accept
item 4 (GOOGL 2012-Q4); keep EBITDA as a target, reported next to operating
income (item 5); OXY 2025-Q4 stays missing until its restated figures are filed.

## Status

| # | Item | Outcome | Spec |
|---|---|---|---|
| 1 | D&A filed as parts | Fix: sum depreciation + intangible amortization where no total is filed (≈15 companies, not only ABT) | E1, P1 |
| 2a | ABT 2012-Q4, BMY 2008-Q4, OXY 2025-Q4 revenue | Fix: withhold the three quarters; the accession vote stays | E2, P2 |
| 2b | EPS jumps 2026-Q2 (GOOGL, HON, AMZN) | Resolved, no change: real non-operating gains | E3 |
| 3 | Structural breaks | Fix: 7 new breaks, ABT moved to 2012-Q1 | E4, P3 |
| 4 | GOOGL 2012-Q4 | Accepted as a limitation | P4 |
| 5 | Operating income vs EBITDA | Decided: keep both, report together | P4 |

## Steps

1. **P1 — D&A from parts** (TDD).
   - `sec_edgar/concepts.py`: add `depreciation` (`Depreciation`) and
     `intangible_amortization` (`AmortizationOfIntangibleAssets`) chains; drop
     `Depreciation` from the `dep_amort` total chain.
   - `sec_edgar/source.py` / `parsing.py`: D&A = total where filed, else
     depreciation + non-negative amortization, else depreciation, as
     `cost_of_revenue` combines its parts.
   - Tests in `tests/data/sources/`: parts only → sum; total present → total;
     negative amortization → depreciation alone.
2. **P2 — withheld quarters** (TDD).
   - `data/companies.py`: `withheld_quarters: dict[date, str]` on the panel
     config and `CompanyPanelMetadata`.
   - `data/pipeline.py`: blank `FINANCIAL_COLUMNS` for those dates next to the
     `has_reliable_opex` blanking, after the Alpha Vantage fallback.
   - `data/missing.py`: ledger reason `withheld_quarter` for those cells.
   - `config/companies.yaml`: ABT 2012-12-31, BMY 2008-12-31, OXY 2025-12-31,
     each with its reason; OXY's says to delete it after the Q3 2026 10-Q.
   - Tests: blanked even where Alpha Vantage has values; other quarters
     untouched; ledger reason.
3. **P3 — breaks.** `config/structural_breaks.yaml`: PFE 2009-12-31, MRK
   2009-12-31, CMCSA 2011-03-31, ECL 2012-03-31, DUK 2012-09-30, MDT 2015-03-31,
   OXY 2025-03-31; ABT 2013-03-31 → 2012-03-31. Update the master plan's §3.4.
4. **Verify:** `uv run poe check`.
5. **Re-run (user), once:** NB00 (re-ingest; SEC is fetched over the network),
   then NB01, then NB01b. Check C2–C5 on the new panel.
6. **Record:** NB01's open question 6, the thesis's "Pendientes" and results
   (with permission for existing text), the spec's status.

## Verification

Acceptance criteria C1–C5 of the spec.
