# Backlog

Ideas parked for later. Not planned, not specced: each needs a spec before
any code (see `CLAUDE.md`, "Plans and specs").

## AT&T 2018 operating income repeats 2017's

*Parked 2026-11-13, found while building Protocol B.* In the frozen panel
(`data/backups/thesis_2026-10-30/`), T's operating income for 2018-Q1, Q2 and
Q3 equals 2017's exactly: 6,201, 6,466 and 7,269 (`T` panel,
`operating_income_usd_m`). Three identical quarters in a row is almost
certainly an ingestion defect, likely a filing's prior-year comparative column
read as the current quarter.

- **Scale.** A scan for values equal to the same quarter a year earlier (not
  missing, not zero) found 16 in 12 companies across the four targets: T
  operating income 3, TXN free cash flow 2, and one each for MDT and PG
  EBITDA, CL, CMCSA and UPS free cash flow, LMT operating income, and CL, F,
  KMB and LLY revenue. Values are whole millions, so isolated repeats are
  expected by chance; T's run of three is not.
- **Effect.** Small for Protocol A. Under Protocol B it gave T a zero own
  error scale at H = 8, which the sector-peer blend (spec R8) now absorbs.
- **Next.** Check T's 2018 10-Qs against the panel, fix the source rule, and
  re-ingest only after NB02 is tagged (plan, "Before starting"). Record the
  change in the NB00 spec's defect register, as for COP and GE.

## Trigger ingestion from the API

*Parked 2026-11-04.* Today ingestion runs only from the command line
(`uv run poe ingest-data`, `add-company`, `reingest-batch`,
`probe-alpha-vantage`); the API exposes only `/health`, `/prediction/train`
and `/prediction/predict`.

Idea: a route package (`api/routes/ingestion/`) that reports ingestion status
and, possibly, starts a run.

To settle in the spec:

- **Read-only first?** A status endpoint (last run, companies and quarters
  covered, data freeze in use) is cheap and harmless; firing a run is not.
- **Background work.** A full ingest takes minutes and hits rate limits
  (Alpha Vantage, SEC). The request must return at once and the run continue
  elsewhere (a job id to poll), not block a worker.
- **Who may fire it.** The API is public on Render; firing a run needs
  authentication, and at most one run at a time.
- **Where the data lands.** Render's disk is ephemeral; a run there loses its
  output on redeploy unless it writes to persistent storage.
- **Not while the thesis is frozen.** The harness works on
  `data/backups/thesis_2026-10-30/`; no re-ingest until NB02 is tagged.
