# Output-sensitive catalog: triage and plan

Follows the "Output-sensitive catalog" section of
[code-smells-remediation.md](code-smells-remediation.md). The item numbers are
the same. That plan recorded seven items as "fixing this changes stored data or
notebook tables". This plan first checks that claim against today's data, and
then orders the work.

Evidence was gathered on 2026-10-26 from the stored panels in
`data/processed/` and the current code. All checks were read-only.

## Triage

| # | Smell | Changes stored data today? | Evidence | Proposed route |
|---|---|---|---|---|
| 26 | Invalid report dates: SEC logs and skips, Alpha Vantage raises | **No** | `nearest_quarter_end` with the 46-day tolerance placed every day from 1990 to 2039 (maximum distance 46 days). No valid date is unplaceable, so the SEC `except ValueError` branch in `xbrl._matches_quarter` never runs. | Ordinary refactor: remove the dead branch. No spec needed. |
| 8 | Yahoo fallback: prices and splits try `GOOGL → GOOG`, dividends do not | **No** | GOOGL is the only company with a second market ticker. Its own dividend history is present: 9 of 81 quarters carry a yield, from 2024-06-30. A first-non-empty fallback for dividends therefore never fires. The broad `except Exception` in `fetching.py` is the vendor boundary that wraps every yfinance failure in `DataSourceUnavailableError`, as `CLAUDE.md` requires. | Ordinary refactor: add the dividend fallback (first non-empty, never a union). A union would count the GOOGL and GOOG dividends twice. Keep the boundary `except`. |
| 17 | Two YoY revenue rules: flags turn non-positive revenue into missing, features raise | **No** | `panel_long.parquet` has 0 non-positive values in `revenue_usd_m` (4,860 rows), and none in `stock_price_usd` or `market_cap_usd_m`. | Ordinary refactor: unify on masking (decided). |
| 28 | Isolation Forest shares `flags.py` with the deterministic flags | **No** (if only moved) | The move is mechanical. The open question is whether the algorithm should stay at all. | Deferred until that question is decided. A move alone buys nothing in a 110-line module. |
| 9 | `MacroCorrelator` uses Pearson; the other diagnostics use Spearman | **Yes** | `panel.py` calls `growth.corr(...)` (Pearson). `correlation.py`, `feature_audit.py` and `transform_comparison.py` use Spearman. | Spec, then fix, then rerun NB01. |
| 16b | Positive columns change by percent in the outlier register, by log difference in correlations; only the register maps infinities to missing | **Yes** | `audit._quarterly_change` uses `pct_change`, quarter over quarter. `correlation._yoy_change` uses a log difference, year over year. Robust z-scores (median and MAD) differ between percent and log changes, so register entries change. | Spec, then fix, then rerun NB01. |
| 25 | XBRL tolerance: `xbrl_facts._values_match` scales on one operand (`max(0.01, abs(right) * 0.001)`); `xbrl._agree` is symmetric (`tolerance * max(abs(left), abs(right), 1.0)`) | **Unknown** | `_values_match` decides the majority value and which accessions are rejected. The SEC cache is in memory only, so measuring needs a fresh companyfacts download for the 60 companies. | Deferred (decided). When picked up: measure first; if no fact changes, it becomes an ordinary refactor, otherwise spec, then re-ingest. |

## Order of work

### Wave A: output-neutral refactors (no rerun)

Each item follows the usual loop: search callers, add a characterization test,
change, run `uv run poe check`, record the status, wait for a go-ahead.

1. **#26:** delete the unreachable `except ValueError` in
   `xbrl._matches_quarter`. Test: a parametrized check that every day of a
   leap year and a non-leap year places on a quarter.
2. **#8:** give `fetch_market_panel` the same candidate loop for dividends as
   for prices, taking the first non-empty series. Test: a fake GOOGL with no
   dividends falls back to GOOG's, and a fake with its own dividends never
   reads GOOG's.
3. **#17 (decided 2026-10-26: unify, masking):** one YoY log-growth rule,
   used by the NB00 outlier flag (`flags.outlier_flag`), the NB01 features
   (`features.transforms.yoy_log_growth`) and the correlation change for
   positive columns (`correlation._yoy_change`). A zero or negative value
   becomes missing and logs a warning that names the count; nothing raises.
   - Scope: only the YoY growth rule. `log_level` keeps raising
     `NonPositiveValueError`, because the target arms invert it and the
     series diagnosis already guards it with `log_defined`.
   - The rule lives where both `app/data` and `app/services` may import it.
     `flags.py` is in the data layer, which must not import services.
   - Characterization first: on the stored panels, the outlier flag, the
     feature exports and the correlation changes are equal before and after
     (no stored revenue is non-positive, so nothing should move).
   - Tests: a non-positive value becomes missing with a warning in all three
     places. The `test_transforms.py` case expecting the error from
     `yoy_log_growth` changes to expect the missing value.

### Wave B: measure and specify only (#9, #16b; decided 2026-10-26)

4. Measure offline from the stored panels:
   - **#9:** the sector-sensitivity table under Pearson and under Spearman;
     the largest change per cell, and any sign flips.
   - **#16b:** the outlier register under percent change and under log
     change; entries added and removed at the 10.0 robust-z threshold.
5. Write `docs/specs/diagnostics-change-measures.md` covering both, with the
   measured numbers as evidence. One decision is shared: which change measure
   and which correlation method NB01 uses throughout.
6. Stop there. Whether to implement the fixes and rerun NB01 (and NB01b if
   its tables depend on the register) is decided after reading the numbers.
   No code changes in this wave.

### Deferred

- **#25 (decided 2026-10-26: defer):** measuring needs a fresh companyfacts
  download for the 60 companies. When picked up: hold the download in memory
  with the `.env` user agent and write nothing to disk; count the periods
  where `_majority_value` or `_rejected_accessions` differ under the two
  tolerances. If none differ, unify on the symmetric `_agree` form as an
  ordinary refactor. Otherwise write `docs/specs/xbrl-tolerance.md` and
  re-ingest after the fix.
- **#28:** decide whether the Isolation Forest `outlier_flag` stays before
  moving it. If it goes, NB00 onward is rerun, and the decision needs its own
  spec.
