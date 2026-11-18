# Local models

Every model file the project runs or trains, kept on this machine only: git
ignores everything here but this README, and the Docker image leaves the folder
out. Deployment takes its models from the W&B registry, not from here.

`Settings.LOCAL_MODELS_DIRECTORY` points here; set `LOCAL_MODELS_DIRECTORY` in
`.env` to keep the weights on another disk. Plan:
`docs/plans/local-models.md`.

| Folder | Holds | Used by |
|---|---|---|
| `gguf/` | Chat model weights for llama.cpp | NB10 |
| `hf/` | Hugging Face cache (`HF_HOME`): Chronos-2, TimesFM-2.5, TabICLv2 | NB06 |
| `tabpfn/` | TabPFN weights (`TABPFN_MODEL_CACHE_DIR`) | NB06, NB10 |
| `trained/<notebook>/` | `model_{family}_{variable}_h{h}.joblib`, also logged to W&B | NB03–NB07 |

## Pinned files

A result cites the file it ran with by this SHA-256. A file whose hash differs
is a different model.

| File | Bytes | SHA-256 | Source |
|---|---|---|---|
| `gguf/gemma-4-E4B-it-Q4_K_M.gguf` | 4,977,171,584 | `85a896a047553e842f25297ee5b031d64ff30147d9c4af17b1e4b394cd1fab87` | Copied from `Trabajo-Integrador/models/` |
