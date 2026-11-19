# NB02 frozen inputs

NB02 evaluates four targets at four horizons. The thesis freeze contains 16
feature Parquets and two consolidated panel Parquets. The saved evaluation
uses the features to supply model inputs and the consolidated panels to
reconstruct actuals and compute reference forecasts. The original freeze
identifier covered the 16 feature files only, so a change to a panel file
could change scores without changing the recorded identifier.

## Requirements

- NB02 reads the features and both consolidated panel files from the same
  named freeze. Updating the working data directory has no effect on the
  inputs loaded from that freeze.
- The identifier is stable for the same named freeze and covers the relative
  filenames and contents of the feature Parquets, `processed/panel_long.parquet`,
  and `processed/macro_q.parquet`. Changing any of these inputs changes the
  identifier. Per-company panel exports and reports are outside the
  fingerprint because NB02 does not read them.
- A freeze without feature Parquets or either consolidated panel file is
  rejected. If the fingerprint changes after NB02 loads its inputs, the
  notebook refuses to append the run.
- The original records and notebook outputs remain historical evidence. The
  new identifier does not retroactively relabel existing runs.

## Acceptance

- A fixture returns a stable identifier. Modifying either panel file or a
  feature file, or renaming a feature file with its contents intact, changes it.
- Omitting either consolidated panel or all feature files fails with a data
  error that identifies the missing input.
- The archived thesis files used by NB02 match the files at the published
  baseline commit byte for byte. This verifies input equivalence; rerunning
  scoring or publishing new results is outside this change.
