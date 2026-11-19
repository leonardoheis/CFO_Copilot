# Implement NB02 frozen inputs

Spec: [NB02 frozen inputs](../specs/nb02-frozen-inputs.md).
Finding: [Hidden dependency in the data freeze](../reviews/evaluation-code-smells.md).

1. Extend the provenance fingerprint in `src/app/data/provenance.py`. Use
   `PanelStore` for the two consolidated paths and include each file's relative
   name and content digest.
2. Add focused cases to `tests/data/test_provenance.py` for each required
   input, a feature rename, and an unrelated file.
3. Point the NB02 panel and feature stores at the thesis freeze in the setup
   cell. Check the fingerprint again before appending results. Preserve
   existing notebook outputs and the original Git tag.
4. Compare the archived inputs with the published baseline files and run
   `uv run poe check`. Leave the full NB02 rerun for separate approval.

The 18 archived Parquets match `nb02-v1.0.0` byte for byte. The NB02 setup cell
loaded 60 company panels and read the 16 feature datasets from the archive,
each with 4,844 rows. The revised identifier is
`thesis_2026-10-30-7e803506d994`.
