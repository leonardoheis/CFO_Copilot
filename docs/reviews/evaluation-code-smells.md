# Evaluation code smells

Reviewed GitHub's `master` at `ebcad0d` on 2026-11-18 with the repository's
`code-smells` checklist. The findings below concern the NB02 evaluation
harness and the results it produces for subsequent model notebooks.

## P2 - Hidden dependency in the data freeze

[`data_freeze_id`](../../src/app/data/provenance.py#L13) hashes only the feature
Parquets. [NB02](../../src/app/playground/02_evaluation_harness.ipynb#L75) loads
the consolidated panels separately, and the
[harness](../../src/app/services/evaluation/harness.py#L113) uses them to
reconstruct actuals and compute baselines. A probe changed a panel file while
keeping the features fixed and got the same freeze ID. A revised panel can
therefore affect the scores attributed to an existing freeze.

Load the panels and features from the same freeze and fingerprint both sets of
inputs. Verify that changing either input changes the identifier or is rejected
before results are written.

## P2 - Learned state can cross held-out folds

[`_held_out_predictions`](../../src/app/services/evaluation/harness.py#L267)
calls `fit` on the same forecaster for every fold. The row checks verify each
fit's inputs, while a forecaster that retains state can remember a company from
a previous fold. With two companies and an accumulating forecaster, a probe
showed company B present in memory when B was held out.

Create a fresh model for each fold, then reuse that fitted model across the
history lengths for that fold. Cover isolation with a deliberately stateful
forecaster.

## P3 - Results have no run identity

[`ResultsStore.append`](../../src/app/data/results_store.py#L23) appends new
files on every call, and [NB02's summary](../../src/app/playground/02_evaluation_harness.ipynb#L4212)
filters the combined records by Git commit. Appending the same one-row result
twice yielded two matching rows. Rerunning a notebook at the same commit
inflates that summary's counts and makes distinct runs hard to select.

Persist a run identifier and have consumers select a single run explicitly.
Verify the selection with two runs from the same commit.

## P3 - Feature history requirements repeat the feature definitions

The [feature builder](../../src/app/services/features/builder.py#L16) derives
lag and rolling column names from their configuration, while
[`QUARTERS_READ_BY_FEATURE`](../../src/app/services/features/builder.py#L31)
lists the names and history lengths by hand. Protocol B
[`truncate_history`](../../src/app/services/evaluation/splits.py#L88) leaves
unlisted columns in place. The [existing test](../../tests/services/features/test_builder.py#L101)
checks the entries already in the lookup, so a new lag omitted from it can pass
the test and expose more history than the fold allows.

Generate the history lengths from the same feature definitions and have the
test check that every generated history-dependent column is covered.

## Verification

`uv run poe check` passed on the reviewed commit in an isolated checkout
with 727 tests passed and 1 expected failure. The first three findings were
reproduced with synthetic inputs. The feature-history finding follows from
the lookup and the coverage of its existing test.
