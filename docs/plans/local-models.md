# Local models directory

One place in this repository for every model file the project runs or trains:
the pretrained models used locally (Gemma 4 for NB10, TabPFN-TS and the other
NB06 foundation models) and each model NB03–NB07 trains. Nothing in it enters
git; each file is named so a result can say exactly which weights produced it.

Decisions behind it: the master plan's NB06 "Local and offline" rules, O2 (the
chat model), and the NB10 section (Gemma 4 E4B and TabPFN-TS, local MCP
server). Rationale for the model choices:
`docs/notes/foundation-model-selection-rationale.md`.

**When:** before NB03, the first notebook that trains a model. Steps 1 and 3
are done (2026-11-18). Steps 2 and 4 go together at NB06: the variables in
step 2 are read when the Hugging Face and TabPFN libraries are imported, and
nothing imports them before NB06.

## Layout

```
models/                          # gitignored, except README.md
├── README.md                    # what each folder holds and where it came from
├── gguf/
│   └── gemma-4-E4B-it-Q4_K_M.gguf
├── hf/                          # HF_HOME: Chronos-2, TimesFM-2.5, TabICLv2 weights
├── tabpfn/                      # TABPFN_MODEL_CACHE_DIR: TabPFN-3.5 (and TabPFN-2) weights
└── trained/
    └── <notebook>/model_{family}_{variable}_h{h}.joblib
```

`src/app/ml_binaries/` stays as it is: it holds the template's
`/prediction` model and is not part of the forecasting work.

## Steps

1. **Directory and setting.** *(Done.)* Create `models/` with a short
   `README.md`, which also keeps the folder in git. Add
   `Settings.LOCAL_MODELS_DIRECTORY` (default `ROOT_PATH / "models"`,
   overridable from `.env` so the Mac can point elsewhere). Ignore `models/*`
   in `.gitignore` except `README.md`, and add `models` to `.dockerignore`:
   deployment pulls its
   artifacts from the W&B registry in CI, never from this folder (master plan,
   Registry).
   - *Test:* the setting resolves under the repository root by default and
     follows an `.env` override.
2. **Offline environment.** *(At NB06, with step 4.)* Set, for every process
   that loads a model:
   `HF_HOME=models/hf`, `HF_HUB_OFFLINE=1` (after step 3–4's downloads),
   `TABPFN_MODEL_CACHE_DIR=models/tabpfn`, `TABPFN_DISABLE_TELEMETRY=1`. Put
   them in `.env.example` and load them in the settings, so notebooks and the
   MCP server share one source.
3. **Gemma 4 E4B (NB10).** *(Done; hash in `models/README.md`.)* Copy
   `Trabajo-Integrador/models/gemma-4-E4B-it-Q4_K_M.gguf` (4,977,171,584
   bytes) into `models/gguf/` rather than downloading it again, and check the
   copy's SHA-256 against the source. The chat setting (O2) points at it.
4. **TabPFN-TS and the other NB06 weights.** The author accepts the TabPFN-3.5
   licence once at ux.priorlabs.ai (an account step only the author can take),
   then one run with network on downloads TabPFN-3.5 into `models/tabpfn/` and
   Chronos-2, TimesFM-2.5 and TabICLv2 into `models/hf/`. Record each file's
   name and SHA-256 in `models/README.md`; that is the pinned version NB06
   cites. From then on `HF_HUB_OFFLINE=1`.
5. **Trained models (NB03–NB07).** Each notebook saves what it trains to
   `models/trained/<notebook>/model_{family}_{variable}_h{h}.joblib`, the
   master plan's artifact name, and logs the same file to W&B. The W&B
   artifact stays the source of truth for deployment; the local file is the
   working copy.
   - *Test:* a save-and-load round trip under a temporary
     `LOCAL_MODELS_DIRECTORY`.

## Verification

- `uv run poe check` green.
- `git status` shows nothing under `models/` but `README.md`.
- With the network off, NB06's setup cell loads every model from `models/`.
