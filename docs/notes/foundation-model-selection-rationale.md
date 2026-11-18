# Why these foundation models, and why not TimeGPT

Rationale for the thesis methods section (NB02 plan, step 17) and for NB06.
Agreed 2026-11-17 while revising the master plan's D16, D20, D26 and NB06
section (`docs/CFO_COPILOT_MASTER_PLAN.md`). Every fact about a model was
checked that day on its official page; the sources are at the end.

## Decisions

- **Foundation models are core, not optional** (D26). NB06 runs TabPFN-TS,
  Chronos-2 and TimesFM-2.5, scored through the NB02 harness like every model.
- **TabPFN-TS is required and the primary cold-start model** (D20), with the
  TabPFN-3.5 weights, which are pretrained on synthetic data only.
- **Every model runs locally on the author's GPU and offline.** Nothing is sent
  to a provider at run time.
- **Excluded:** TimeGPT (D16), Moirai-2, and the fine-tuned TabPFN-TS-3
  checkpoint. Each fails at least one entry rule below.
- **A tabular foundation model joins NB06**, pooled across the 60 companies on
  NB01's features: **TabICLv2 is core; Kumo Tabular is secondary** until its
  score appears on TabArena's official leaderboard (see "Tabular models").

## The four entry rules

A model enters NB06 only if it passes all four. Each protects one claim the
thesis makes.

| Rule | Why it matters here |
|---|---|
| **Open weights** | An examiner must be able to rerun the model. A service can only be called, not inspected. |
| **Published pretraining corpus** | Quarterly revenue and cash flow of large US companies are among the most republished numbers online. A model trained on an undisclosed corpus may have seen the answers, so a good zero-shot score proves nothing (Appendix F, finding 4). Synthetic-only pretraining rules this out by construction. |
| **Pinnable version** | A result must name the exact weights that produced it, as every NB02 record names its commit and data freeze. A hosted model can change under the same name. |
| **No third-party data egress** | The panel stays on the author's machine. It is also the author's requirement since 2026-11-17: models are consumed locally, without internet. |

## Local and offline

- Weights are downloaded once into a cache outside git, then loaded with
  `HF_HUB_OFFLINE=1`. "Offline" therefore means offline at run time; the first
  download, and for TabPFN-3.5 a one-time licence acceptance, need internet.
- TabPFN-TS runs in its local mode. Its default is Prior Labs' cloud client,
  which would send the panel to their servers.
- `TABPFN_DISABLE_TELEMETRY=1`. Telemetry is on by default; it sends usage
  metadata, not data, but nothing should leave the machine.
- Hardware: an RTX A4000 with 8 GB. The largest core model is 200M parameters
  (under 1 GB of weights), NB06 only runs inference, and the panel is 60
  series of about 80 quarters.

## Time-series models

| Model | Weights | Corpus | Licence | Verdict |
|---|---|---|---|---|
| **TabPFN-TS** with TabPFN-3.5 (`tabpfn-time-series` 1.4.0) | Open; local mode | Synthetic only | Non-commercial (research and internal evaluation) | **Core, primary** |
| **Chronos-2** (120M) | Open | Real (Chronos datasets, GIFT-Eval pretrain) and synthetic, published | Apache-2.0 | **Core** |
| **TimesFM-2.5** (200M) | Open | GIFT-Eval pretrain, Wikimedia, Google Trends, synthetic, published | Apache-2.0 | **Core** |
| TimeGPT (Nixtla) | **Closed**: a paid API only | **Undisclosed** | Commercial service | **Excluded (D16)**: fails rules 1–4 |
| Moirai-2.0-R | Open | Includes **internal Salesforce data** | CC-BY-NC-4.0, research only | **Excluded**: fails rule 2 |
| TabPFN-TS-3 (fine-tuned checkpoint) | Open | Fine-tuning data **not stated** | Non-commercial | **Excluded**: fails rule 2, though it ranks 2nd on fev-bench |

TabPFN-2 weights (Prior Labs License: Apache 2.0 plus attribution) are the
fallback if the app is ever used commercially; TabPFN-3.5's licence forbids it.

## Tabular models (TabArena)

TabArena ranks models on ordinary tables, not time series. None of the
leaders below has a time-series version; TabPFN is the only family that does
(`tabpfn-time-series`). That does not disqualify them: NB01 already turned the
panel into a table (lags, rolling statistics, the macro block), which is what
TabPFN-TS builds internally. A tabular model on NB01's features, **pooled
across all 60 companies**, adds what TabPFN-TS lacks: it learns across
companies, where TabPFN-TS forecasts each series alone. It also gives a clean
comparison with NB04's LightGBM on identical features.

| Model | Weights and licence | Corpus | TabArena score | Verdict |
|---|---|---|---|---|
| **TabICLv2** (INRIA; `tabicl` 2.2.0; regressor `tabicl-regressor-v2-20260212`) | Open; BSD-3-Clause (package and Hugging Face card) | Synthetic only; pretraining code open (v1; v2 announced) | Among the top four single models on TabArena v0.1.4 (third-party snapshot, June 2026) | **Core**: passes all four rules, permissive licence, independent placement |
| **Kumo Tabular** (NVIDIA; `structured-data-models`; 28M–215M) | Open; OpenMDW 1.1, commercial use allowed | Synthetic only | 1950 Elo, first overall: **self-reported** (blog, 2026-09-29) | **Secondary**: passes all four rules; younger and unconfirmed (below) |
| LimiX-2 (400M) | Open; **StableAI LimiX Non-Commercial** | Synthetic (SCM) | 1935 Elo: **self-reported** | Not proposed: non-commercial like TabPFN-3.5, so it adds no licence advantage, and its score is unconfirmed |
| TabPFN-3, TabPFN-2.6, RealTabPFN-2.5 | Open; non-commercial | Synthetic | Top four (same snapshot) | Not added: the same family as TabPFN-TS, so they add little diversity |

**TabICLv2 or Kumo Tabular.** Both pass the rules. TabICLv2 is proposed
because it appears on TabArena's own leaderboard, not only in its authors'
claims (seen through a third-party snapshot; the live board could not be read
directly), it has a paper (arXiv 2602.11139) and open pretraining code, and
its licence is the most permissive. Kumo Tabular claims the higher score and outputs 999 quantiles
for regression, which would give intervals directly, but it was published
seven weeks before this decision, its score is the authors' own, and its model
card shows no regression example. Running both is cheap (inference only, about
5,000 pooled rows per horizon). Decided 2026-11-17: TabICLv2 core, Kumo
Tabular secondary until its score appears on the official leaderboard.

## How each model sees the macro block

Next quarter's macro values are unknown at the origin, so every model gets
them lagged by at least h quarters; otherwise it reads the future.

- **Chronos-2** takes them natively as past covariates.
- **TabPFN-TS** uses only known-future covariates and drops past-only and
  static ones, so the lagged values must enter as known-future columns.
- **TimesFM-2.5**: its model card documents no covariates.
- **The tabular models** read them as ordinary columns of NB01's features,
  which are already lagged.

## Sources

| Claim | Source | Bib key |
|---|---|---|
| TabPFN-v2: synthetic pretraining, small data | Hollmann et al. (2025), *Nature* 637 | `hollmann2025tabpfn` |
| TabPFN-TS | Hoo et al. (2025), arXiv | `hoo2025tabpfnts` |
| TabPFN-3 pretrained exclusively on synthetic data; TabPFN-TS-3 2nd on fev-bench; licence | Prior Labs, *TabPFN-3 technical report*, <https://priorlabs.ai/technical-reports/tabpfn-3> | **not yet in `references.bib`** |
| `tabpfn-time-series` 1.4.0: default TabPFN-3.5, cloud client by default, covariates, telemetry | <https://pypi.org/project/tabpfn-time-series/> | — |
| Weight licences, offline use, `TABPFN_TOKEN` | <https://github.com/PriorLabs/TabPFN> | — |
| Chronos-2 | Ansari et al. (2025); model card <https://huggingface.co/amazon/chronos-2> | `ansari2025chronos2` |
| TimesFM | Das et al. (2024), ICML; card <https://huggingface.co/google/timesfm-2.5-200m-pytorch> | `das2024timesfm` |
| Moirai-2 corpus and licence | <https://huggingface.co/Salesforce/moirai-2.0-R-small> | `woo2024moirai` (Moirai 1) |
| TimeGPT | Garza & Mergenthaler-Canseco (2023), arXiv | `garza2023timegpt` |
| GIFT-Eval, the corpus overlap risk | Aksu et al. (2024) | `aksu2024gifteval` |
| TabArena | Erickson et al. (2025), arXiv 2506.16791 | **not yet in `references.bib`** |
| TabICLv2 | arXiv 2602.11139; <https://github.com/soda-inria/tabicl>; <https://huggingface.co/jingang/TabICL> | **not yet in `references.bib`** |
| Kumo Tabular | NVIDIA, <https://huggingface.co/blog/nvidia/kumo-tabular>; <https://huggingface.co/nvidia/Kumo-Tabular> | — (blog) |
| LimiX-2 | <https://huggingface.co/stableai-org/LimiX-2> | — |

Verify the TabArena and TabICLv2 author lists against arXiv before adding the
bib entries; this note cites them by identifier only.

## Paragraph for `main.tex`

> Los modelos fundacionales se incorporan solo si cumplen cuatro condiciones:
> pesos abiertos, un corpus de preentrenamiento publicado, una versión fija y
> ninguna transferencia de datos a terceros. La segunda es la decisiva: los
> ingresos y flujos de caja trimestrales de las grandes empresas
> estadounidenses están entre las series numéricas más difundidas, de modo
> que un modelo entrenado con un corpus no publicado pudo haberlas visto, y un
> buen resultado sin entrenamiento previo no probaría nada. Por eso se
> excluyó TimeGPT \cite{garza2023timegpt}, cuyo modelo solo se ofrece como
> servicio y cuyo corpus no es público, y Moirai-2, cuyo corpus incluye datos
> internos no publicados. El modelo principal es TabPFN-TS
> \cite{hoo2025tabpfnts}, preentrenado exclusivamente con datos sintéticos
> \cite{hollmann2025tabpfn}, junto con Chronos-2 \cite{ansari2025chronos2} y
> TimesFM \cite{das2024timesfm}. Todos se ejecutan localmente, sin conexión a
> internet, sobre una GPU de 8 GB. Como TabPFN-TS pronostica cada empresa por
> separado, se añade un modelo fundacional tabular, entrenado sobre los
> atributos del NB01 de las 60 empresas a la vez, que se compara con LightGBM
> sobre los mismos atributos.
