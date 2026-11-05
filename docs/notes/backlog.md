# Backlog

Ideas parked for later. Not planned, not specced: each needs a spec before
any code (see `CLAUDE.md`, "Plans and specs").

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
