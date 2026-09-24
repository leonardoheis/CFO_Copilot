# CFO Copilot — Master Plan

**Project:** Quarterly financial forecasting for public companies, conditioned on macroeconomic variables, with a natural-language layer for querying and explaining results.
**Repo:** `leonardoheis/CFO_Copilot` (ELC FastAPI production template)
**Deliverable:** FastAPI + Streamlit app on Render, serving per-series model selection with calibrated intervals, charts, and an NL-SQL chat.
**Thesis scope:** ML / time-series forecasting. The chat layer is a product feature, not a thesis contribution.
**Status:** per-company panels ingested for 60 of 60 companies; NB00 consolidation next (`docs/plans/nb00-ingest-and-consolidate.md`).
**Last updated:** 2026-09-16 — rev 4 (adds Appendix F literature grounding + references.bib)

---

## 0. Decisions

### 0.1 Locked

| # | Decision | Rationale |
|---|---|---|
| D1 | Frequency: **quarterly** | Finest granularity for 10-Q fundamentals |
| D2 | Window: **2006-Q2 → 2026-Q2** (81 quarters) | Covers GFC, COVID, 2022–24 rate cycle |
| D3 | Universe: **60 companies, 9 sectors**, no banks or insurers | Schema has gross_profit/EBITDA/FCF/margins — meaningless for financials |
| D4 | Default target transform: **`log(x)`, panel-wide**, with alternatives as measured arms | One rule keeps errors commensurable across companies; per-company Box-Cox (λ −0.46 to 2.33) would not |
| D5 | Horizons: **h ∈ {1,2,3,4}**, direct (one model per h) | Avoids recursive error compounding |
| D6 | Mandatory baseline: **seasonal naive**, reported even when it wins | Currently beats everything; hiding that would be dishonest |
| D7 | **Protocol A first, then Protocol B.** Both required. | A is the standard result; B is what the app needs |
| D8 | Both protocols emit **both** PI and CI | Their difference separates irreducible volatility from model ignorance |
| D9 | Intervals via **conformal prediction** | Model-agnostic, coverage guarantees, works in both protocols |
| D10 | Tracking + registry: **Weights & Biases** | Artifact lineage makes the notebook→API handoff auditable |
| D11 | Deployment: **Render Standard ($25/mo, 2 GB, 1 CPU)** | Free tier's 512 MB cannot host the app plus any model |
| D12 | Collection: **SEC EDGAR XBRL first**, yfinance for prices, FRED for macro, Alpha Vantage last resort | Alpha Vantage free tier ~25 req/day makes 60 tickers impossible; EDGAR is unlimited and is the filer's own tagged data |
| D13 | Macro: **final revised values + documented look-ahead limitation** | Vintages (ALFRED) are the optional upgrade; affects only gdp_yoy, unemployment_rate, cpi_yoy |
| D14 | Chat layer: **NL-SQL over six curated DuckDB views**, single-company scope | Natural language in, validated SQL out, no free-form table access |
| D15 | Charts on **both** paths — forecast results and SQL query results | Every numeric answer is also a visual |
| D16 | TimeGPT: **excluded entirely** | Closed weights, undisclosed corpus, not reproducible by an examiner |
| D17 | QLoRA NL-SQL fine-tuning: **phase 2** (Appendix E) | Views + few-shot first; measure before training |
| D18 | Distress / Altman Z: **deferred chapter, retained** | Option 1 (forecast a variable) is the thesis; Option 2 (distress class) follows if time allows |
| D19 | SLM-vs-API comparison: **config choice, not a thesis section** | Nice-to-have; thesis is ML/time-series |
| D20 | **TabPFN-TS is the primary cold-start baseline**, alongside Chronos-2 | Synthetic-only pretraining ⇒ contamination-free on these series; Hollmann et al. 2025 (*Nature*) is literally titled "Accurate predictions on small data" [`hollmann2025tabpfn`, `hoo2025tabpfnts`] |
| D21 | Pooling is **conditioned on series relatedness** (sector / size cluster), not assumed global | Global models are not more restrictive than local ones [`monteromanso2021global`], but mixing *unrelated* financial series measurably degrades accuracy [`das2026chronosfinance`]. Both must be reconciled. |
| D22 | Significance testing: **HLN-corrected Diebold-Mariano + Model Confidence Set** | 81 quarters is a small sample, so uncorrected DM over-rejects [`harvey1997testing`]; MCS gives family-wise error control across many model families [`hansen2011mcs`] |
| D23 | The residual-shrinkage design is framed as **forecast combination with a benchmark anchor** | Puts it in an established literature (FFORMA, M4 combination findings) rather than presenting it as ad hoc [`monteromanso2020fforma`, `makridakis2020m4`] |
| D24 | Macro block expanded to 10 variables: +yield_spread_10y2y, +mfg_confidence, +sp500_return_lag1 | Yield spread and mfg_confidence are FRED, same pipeline as the existing 7; S&P500 is yfinance and must be lagged to avoid reverse causality with the panel's own constituents |

### 0.2 Deferred — decide at the named point, not now

| # | Open question | Decide at | Notes |
|---|---|---|---|
| O1 | Transform beyond log — sqrt, Box-Cox, per-sector? | NB01 / NB04 | Log is the default; alternatives run as arms and the data decides |
| O2 | Which model sizes / how many prompts for the chat SLM | NB10 | 8 GB local fits one 8B; Render's 2 GB fits ~3B. Constraint is known, choice is not |
| O3 | Which models are actually deployable on 2 GB CPU | NB08 / NB10 | `torch-cpu` wheel is ~200 MB, so more is deployable than first assumed. Measure, don't guess. |
| O4 | Macro vintages upgrade | After M6 | Only if time allows and results look revision-sensitive |

### 0.3 Blocking task

**E1 — is the 2026-Q2 row reported or projected?** **Resolved 2026-09-23: reported.** Confirmed by the project owner; all 60 companies carry 2026-Q2 revenue and none repeats the prior quarter. 2026-Q3 is the forecast quarter (horizon 1 from the 2026-Q2 origin). Recorded in `docs/specs/nb00-ingest-and-consolidate.md`; `is_projected` is true only for quarters after `Settings.LAST_REPORTED_QUARTER`.

---

## 1. Objective

**Q1 (thesis, Protocol A).** For a company in the panel, forecast a chosen financial variable h quarters ahead with a calibrated interval. Does pooling across companies and adding macro covariates beat per-company univariate forecasting, and by how much, per sector?

**Q2 (thesis, Protocol B).** Does the answer hold for a company the model has never seen, as a function of how much history that company has?

**Q3 (product, not thesis).** Can a user query and understand those results in natural language, with charts?

---

## 2. Architecture

```
┌──────────────────┐   ┌───────────────────┐   ┌──────────────────────┐
│  Streamlit UI    │──▶│  FastAPI service  │──▶│  Artifacts (baked    │
│  forecast page   │   │  /forecast        │   │  into Docker image   │
│  chat page       │   │  /simulate        │   │  at build time from  │
│  comparison page │◀──│  /chat            │◀──│  W&B registry)       │
│  diagnostics     │   │  /diagnostics     │   └──────────────────────┘
└──────────────────┘   │  /health          │
                       └─────────┬─────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
      forecasting service   nl2sql service     chat service
      (artifact + conformal) (DuckDB, 6 views)  (router, explainer,
              │                  │               numeric validator)
              ▼                  ▼                  │
      panel_long.parquet ◀───────┘                  ▼
      macro_q.parquet                        LLMBackend protocol
      conformal_residuals.parquet            (llamacpp | ollama |
      policy_table.parquet                    anthropic | openai | vertex)
```

Render instance: 2 GB RAM, 1 CPU. Everything above runs in one container; `__main__.py` already starts API (:8000) and Streamlit (:10000) in parallel processes.

### 2.1 FastAPI endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/companies` | Tickers + available history length |
| `GET` | `/variables` | Forecastable variables + diagnostics |
| `POST` | `/forecast` | ticker, variable, horizon, level → point, PI, CI, drivers, model, backtest stats |
| `POST` | `/forecast/cold-start` | Raw quarterly history for an unknown company (min 8 quarters, else 422) |
| `POST` | `/simulate` | Forecast with macro overrides + OOD flag |
| `POST` | `/chat` | NL question → routed answer + chart spec + citations |
| `GET` | `/diagnostics/{ticker}/{variable}` | NB01 output |
| `GET` | `/health` | Resolved artifact versions |

**Design rule: the API never trains.** It loads fitted artifacts at startup. Training happens offline in notebooks and writes versioned W&B artifacts.

### 2.2 Streamlit pages

1. **Forecast** — company + variable + horizon; fan chart (PI outer band, CI inner band); model name and its backtest MAE inline
2. **New company** — CSV upload, schema validation, cold-start forecast, explicit "history is H quarters, so model M is used"
3. **Chat** — NL question, answer, generated SQL shown, chart rendered
4. **Model comparison** — NB08 leaderboard, filterable by protocol / sector / horizon
5. **Diagnostics** — per-series output from the diagnostics skill
6. **Distress** — deferred (D18)

### 2.3 Weights & Biases

Project `cfo-copilot`. One run per `(notebook, model, variable, protocol)`:

```
{nb}-{model}-{variable}-{protocol}[-H{history_len}]
e.g.  nb04-lgbm_resid-revenue-A   /   nb04-lgbm_resid-revenue-B-H12
```

**Config logged on every run** — this is what makes results comparable:

```yaml
panel_size: 60
n_rows: 4800
target_variable: revenue_usd_m
target_transform: log_diff1 | log_diff4 | seasnaive_residual
shrinkage_lambda: 0.5
feature_groups: [L, R, M, X, XD, C, S, F]
n_features: 25
protocol: A | B
history_len: null | 8 | 12 | 20 | 40
horizon: 1
harness_version: nb02-v1.0.0        # must match the frozen harness tag
macro_source: final_revised          # or point_in_time
git_sha: ...
seed: 42
```

**Metrics** logged per run and per company (so the sector breakdown is queryable): MAE, RMSE, MASE, CRPS, coverage@{80,90,95}, mean interval width, Winkler, DM statistic vs seasonal naive.

**Artifacts with lineage:**

| Artifact | Type | Producer | Consumer |
|---|---|---|---|
| `panel_long`, `macro_q` | dataset | NB00 | all |
| `features_h{1..4}` | dataset | NB02 | NB03–NB07 |
| `harness` | code | NB02 | NB03–NB08 |
| `model_{family}_{variable}_h{h}` | model | NB03–NB07 | NB08, API |
| `conformal_residuals` | dataset | NB03–NB07 | API |
| `policy_table` | dataset | NB08 | API |
| `views.sql`, `nl2sql_fewshot.json` | code | NB10 | API |

**Registry.** Two aliases: `staging` (NB08 winner) and `production` (integration test green). Pull artifacts during the **GitHub Actions build** and `COPY` into the image — never at runtime. Render's filesystem is ephemeral and cold starts are already slow; a startup W&B call would make both worse. Record resolved versions in `/health`.

**Offline fallback.** `WANDB_MODE=offline` + `wandb sync` so a tracking outage never blocks a training run.

### 2.4 Deployment and dependency split

Render Standard: 2 GB RAM, 1 CPU, always on, no GPU (Render offers no GPU tiers at any price). Two uv groups keep the image inside 2 GB:

```toml
[dependency-groups]
serve = ["fastapi", "streamlit", "duckdb", "lightgbm", "statsmodels",
         "pandas", "pyarrow", "sqlglot", "llama-cpp-python",
         "torch"]          # CPU-only index, ~200 MB not ~2.5 GB
research = ["torch",        # CUDA build, local only
            "neuralforecast", "transformers", "autogluon.timeseries",
            "shap", "wandb", "unsloth"]
```

`serve` goes in the Docker image. `research` is local-only and never built. Configure the CPU torch index in `pyproject.toml` so the deployed build can't accidentally pull CUDA wheels.

**GPU is for training, not serving.** Inference for LightGBM, SARIMAX, small LSTM/NHITS and small foundation models runs on CPU. Whether the specific NB08 winner fits in 2 GB is O3, measured at NB10.

**LLM backends**, one protocol, chosen by env var:

| Environment | `LLM_BACKEND` | Notes |
|---|---|---|
| Local dev / experiments | `llamacpp` | 8B Q4_K_M on the A4000 (8 GB) |
| Render — router + NL-SQL | `llamacpp` | ~3B GGUF on CPU; short outputs (20–80 tokens) make this viable |
| Render — explainer | `anthropic` / `openai` / `vertex` | ~300-token outputs are too slow on 1 CPU |
| Thesis demo (optional) | tunnel to the A4000 | Free, self-hosted, laptop is in the room |

---

## 3. Data layer

### 3.1 Schema (per company-quarter)

```
keys      : ticker, company, sector, date
financial : revenue_usd_m, gross_profit_usd_m, opex_usd_m,
            operating_income_usd_m, ebitda_usd_m, net_income_usd_m,
            free_cash_flow_usd_m
ratios    : gross_margin, operating_margin, net_margin, eps, pe_ratio
market    : stock_price_usd, dividend_yield, market_cap_usd_m
macro     : gdp_yoy, fed_funds, unemployment_rate, cpi_yoy, dxy, vix, wti_oil,
            yield_spread_10y2y, mfg_confidence, sp500_return_lag1
flags     : covid, structural_break, outlier_flag, is_projected
```

Macro is identical across companies (verified byte-for-byte on the first 7 files), so it lives once in `macro_q.parquet` joined on `date` — not 60 duplicate copies.

### 3.2 Source priority (D12)

| Data | Source | Limit | Repo location |
|---|---|---|---|
| Fundamentals | **SEC EDGAR XBRL Company Facts** | none | `data/sources/sec/`, `data/xbrl.py` |
| Prices, market cap, dividends | **yfinance** | generous | `data/sources/yahoo/` |
| Macro (9 FRED series) | **FRED** | 120 req/min, free key | `data/sources/fred/` |
| S&P 500 return (lagged) | **yfinance** | generous | `data/sources/yahoo/` — new `index.py`, mirrors per-company price puller but pulls `^GSPC` once |
| Gap-filling only | Alpha Vantage | ~25 req/day | `data/sources/alpha_vantage/` |

**New in rev 5 (D24):** yield_spread_10y2y (FRED `T10Y2Y`, already spread-computed
by FRED) and mfg_confidence (FRED `BSCICP02USM460S` — OECD Business Confidence
Indicator, manufacturing, seasonally adjusted; a survey-sentiment index, not the
ISM PMI diffusion index — verify the series' start date covers 2006) join the
macro block. sp500_return_lag1 is **lagged by one quarter, always** — the S&P 500
partially reflects the panel's own largest constituents (AAPL, MSFT...), so using
it contemporaneously risks reverse causality; the lag makes the causal direction
(financial conditions → future fundamentals) explicit. Use return, not level —
the level is nonstationary and correlates with revenue trend for reasons
unrelated to any macro link.

Tickers come from `config/companies.yaml` via `CompanyRegistry` — adding 53 companies is a config change, not new code. Cache raw responses to disk before parsing; make per-ticker failures non-fatal and logged.

### 3.3 Target variables

1. `revenue_usd_m` — primary, most forecastable, strongest seasonality
2. `operating_income_usd_m` — noisier, more macro-sensitive
3. `ebitda_usd_m`
4. `free_cash_flow_usd_m` — hardest, crosses zero (so MAPE is unusable)

### 3.4 Known hazards

| Hazard | Where | Handling |
|---|---|---|
| **Projected last row** | 2026-Q2, all files | **E1 — verify. Set `is_projected`; exclude from train and test** |
| Fiscal-calendar misalignment | AAPL Sep, MSFT/PG Jun, NKE May, COST Aug, DE Oct, WMT/HD/M/BBY Jan | Audit whether `date` is calendar or fiscal period-end; standardise, record offset |
| COVID break | 2020-Q2 → 2020-Q4 | Intervention dummy, not noise to fit |
| Spinoffs / M&A | ABT 2013-Q1, PFE 2020-Q4, MRK 2021-Q2, T 2022-Q2, GE 2023–24, BMY 2019-Q4 | `structural_break` dummy, hand-entered |
| Pre-IPO gaps | TSLA (6 revenue, 16 price/EPS, 44 P/E) | Leave NaN; never impute a pre-existence value |
| One-off items | AMZN 2026-Q2: 31% net margin, EPS 1.95→5.75, FCF −8,821 | Isolation Forest flag, retained not deleted |
| Macro revision look-ahead | gdp_yoy, unemployment_rate, cpi_yoy | **D13: documented limitation.** fed_funds/dxy/vix/wti_oil are market data, never revised |

---

## 4. Evaluation protocols

Both run through **one shared function** in NB02. No model notebook defines its own split.

```python
evaluate(
    predict_fn,                   # (train, test_row, horizon) -> (point, pi_lo, pi_hi, ci_lo, ci_hi)
    protocol: "A" | "B",
    horizons=[1,2,3,4],
    history_len=None,             # protocol B only
    variable="revenue_usd_m",
    levels=[0.80, 0.90, 0.95],
) -> pd.DataFrame
```

One row per `(model, ticker, origin_date, horizon, level)` with point, actual, bounds, fold id. All notebooks append to `results.parquet`.

### Protocol A — temporal (known company) — FIRST

- Expanding window, origin sweeps the last 16 quarters
- Train on all companies, all dates `< origin`; test the held-out quarter
- Reported per company and per sector

### Protocol B — cold start (new company) — SECOND

- GroupKFold on ticker, 12 folds × 5 companies. Held-out companies appear in zero training rows.
- Truncate each held-out company's own history to H ∈ {8, 12, 20, 40, all} and forecast from there
- Produces the accuracy-vs-history-length surface that becomes the app's routing policy

---

## 5. Uncertainty quantification

### 5.1 The two intervals

| | Question | Contains | UI |
|---|---|---|---|
| **PI** | Where will the actual value land? | Parameter uncertainty + irreducible noise | Outer band |
| **CI** | Where is the conditional mean? | Model uncertainty only | Inner band |

`PI − CI` ≈ aleatoric (business volatility). `CI` ≈ epistemic (shrinks with data).

### 5.2 Per-family mechanisms

| Family | PI | CI |
|---|---|---|
| SARIMAX | Analytic state-space | `se_mean` |
| LightGBM / CatBoost | Quantile regression | 50-resample bootstrap spread |
| LSTM / NHITS / TFT | Quantile head / DistributionLoss | 10-seed ensemble |
| Foundation models | Sample paths / native quantiles | Context-length jitter ensemble |
| AutoGluon-TS | Native quantile_levels | Bagged-fold variance |

### 5.3 Conformal layer

- **Protocol A → EnbPI / ACI.** Time series violate exchangeability; rolling calibration window with adaptive level adjustment.
- **Protocol B → cross-conformal on the company axis.** Whole companies are held out, so the company is the exchangeable unit and split conformal is valid. Calibrate on held-out companies' residuals, apply to the new company.

Store as `conformal_residuals.parquet` keyed by `(model, variable, horizon, H_bin, level)`. The API reads; never recomputes.

### 5.4 Protocol × interval matrix

| | Protocol A | Protocol B |
|---|---|---|
| PI method | EnbPI / ACI on own history | Cross-conformal across held-out companies |
| PI validity | Approximate, adaptively corrected | **Exact marginal coverage** |
| PI meaning | "Given your 20 years of filings…" | "Given companies like you…" |
| CI method | Analytic or ensemble | Spread across the 12 group folds |
| CI meaning | Parameter uncertainty — narrow | "We don't know you yet" — **wide, must narrow as H grows** |

The Protocol B CI narrowing with H is a **test, not an assumption**. If it doesn't narrow, the calibration is wrong and the dashboard number is decorative.

### 5.5 Interval metrics

Empirical coverage @ 80/90/95 (never nominal), mean interval width, **Winkler / MIS** (catches wide-but-covering intervals), CRPS, reliability diagram per model.

---

## 6. Notebook sequence

Every notebook has an exit criterion. Do not advance until met.

### NB00 — Ingest & consolidate
- EDGAR XBRL → 60 companies; yfinance prices; FRED macro; concatenate → `panel_long.parquet` (~4,800 rows) + `macro_q.parquet`
- **Resolve E1** (projected vs reported final row)
- Fiscal-calendar audit; `date` → datetime; drop constant columns (`is_public`)
- `covid`, `structural_break` dummies; Isolation Forest → `outlier_flag`
- **Exit:** row count = Σ per-company rows; macro table exactly 81 rows; zero unexplained NaNs; E1 answered in writing

### NB01 — EDA
Per-series (diagnostics skill, 60 × 4 variables): ADF + KPSS, required `d` on levels **and** logs, seasonality strength/period, STL, Ljung-Box, Box-Cox λ, ACF/PACF.

Panel-level (the chapter's best figures):
- Seasonal-strength distribution across 60 → cluster into 3–4 regimes, use cluster id as a feature
- `d` on levels vs logs, all 60 → tests D4 at scale
- **Macro sensitivity heatmap: company growth × macro variable, by sector.** The plot that justifies the macro block; impossible with 7 companies
- Cross-company growth correlation; growth distribution by sector; CV ranking
- Transform comparison (O1): log vs sqrt vs Box-Cox vs per-sector, on variance stability and residual normality
- **Exit:** every (company, variable) has a diagnostics record; macro heatmap shows clear sector differentiation

### NB02 — Harness & feature store  ← KEYSTONE, build first
- `evaluate()` per §4, both protocols
- Feature builder: lags 1–5 + 8, rolling mean/std 4 and 8q, momentum, lag-1 margins, lag-1 macro, quarter dummy, ticker/sector/regime categoricals, covid/break/outlier flags
- Transform + inverse with round-trip test
- **Leakage assertions:** no feature references date ≥ origin; `is_projected` rows excluded; macro source recorded
- **Metric computation lives here, not in model notebooks.** All errors converted to log-level of the variable at t+h before comparison — MAE on a QoQ target and MAE on a YoY target are different quantities
- Baselines: seasonal naive, naive, drift
- Conformal wrappers (EnbPI for A, cross-conformal for B)
- **Exit:** `evaluate()` reproduces the seasonal-naive baseline bit-for-bit twice; all leakage assertions pass; **then freeze and tag `nb02-v1.0.0`**

### NB03 — Statistical
Seasonal naive, drift, ETS, Theta, AutoARIMA, **SARIMAX + macro exog**, per company via `statsforecast`. Record each model's minimum viable H for Protocol B.
- **Exit:** SARIMAX beats seasonal naive on Protocol A at h=1, or a documented reason why not

### NB04 — Gradient boosting & linear
Pooled LightGBM, CatBoost, RidgeCV, ElasticNet. Quantile regression for PI, bootstrap for CI.

**Three target arms** (measured at 7 companies, Appendix D; ranking changes with feature count so nothing is locked):

| Arm | Target | Reconstruction |
|---|---|---|
| `log_diff1` | `log(x).diff()` | `log(x_t) + ŷ` |
| `log_diff4` | `log(x).diff(4)` | `log(x_{t-3}) + ŷ` |
| **`seasnaive_residual`** | `log(x).diff(4) − log(x).diff(4).shift(1)` | `log(x_{t-3}) + y_yoy_{t-1} + λ·ŷ` |

The residual arm exists because the winning baseline *is* a lag-1 of YoY growth with coefficient pinned to 1, and an unconstrained LightGBM given that lag loses to it. Making the baseline's error the target means predicting zero reproduces the baseline. Shrinkage λ ∈ {0.25, 0.5, 0.75, 1.0}, tuned on the harness, **logged against `panel_size`** — λ should drift toward 1.0 as rows increase, and that plot is a thesis figure.

**Feature groups:**
```
L   lags 1,2,3,4,5,8 of the differenced target      ← dominant signal
R   rolling mean/std 4 and 8q; momentum (lag1 − lag2)
M   lag-1 YoY growth of ebitda, opex, fcf; lag-1 margins; op-income ratio
X   lag-1 levels of all 10 macro variables            ← best non-lag group
    (includes yield_spread_10y2y, mfg_confidence, sp500_return_lag1 — see D24)
XD  real rate (fed_funds − cpi_yoy) only — mechanical d1/d4 measured useless
C   quarter dummy
S   ticker, sector, seasonality-regime id
F   covid, structural_break, outlier flags
```
- Full group ablation, each a separate W&B run; local vs pooled on identical features; SHAP by sector
- **Relatedness-conditioned pooling test (D21).** Run pooling three ways: all 60, within-sector only, within size/volatility cluster only. The literature supports global models in general but also documents accuracy *loss* from mixing unrelated financial series, so this is a measurement, not an assumption.
- **Exit:** pooled beats local (confirmed at 7 companies: −10.5% MAE, −17% RMSE) **and** the macro group's marginal contribution is re-measured at 60. At 7 companies macro improved MAE 10.7% with zero cross-sectional variation, so it may be a time/regime proxy. If the gain survives with sector-varying sensitivity, the macro block is a genuine contribution; if it vanishes, say so. **Fallback rule:** if all-60 pooling fails to beat per-cluster pooling inside the Model Confidence Set at the 10% level, adopt clustered-global models as the production configuration.

**D24 — three new macro variables (yield spread, mfg_confidence, S&P 500 lagged
return), run through the same ablation as the original 7, not assumed useful.**
The panel's own group ablation already found mechanical macro deltas added
nothing (Appendix D, finding 3); these three get identical treatment —
with-vs-without in the group ablation, not appended on faith. Additionally, per
D21, check whether S&P500 sensitivity varies by sector as expected (cyclical
names loading harder than utilities/staples) — if it doesn't show that pattern,
that's a sign of residual endogeneity rather than genuine macro signal, and the
variable should be dropped or the lag lengthened.

### NB05 — Deep global
LSTM (committed in TP5 — **performed regardless of outcome**), NHITS, N-BEATS, TFT, PatchTST via `neuralforecast`. Static covariates = ticker, sector, regime. 10-seed ensembles for CI. TFT variable importances → explainability artifact.
- **Exit:** reported honestly even if LSTM loses to NHITS and to LightGBM. A documented negative result on deep learning under small-sample financial data is a legitimate finding.

### NB06 — Foundation models
**Inclusion criteria** — all four required: open weights, published pretraining corpus, version pinnable, no third-party data egress. Your series are the most redistributed numeric series on the internet, so an undisclosed corpus makes zero-shot claims unfalsifiable.

Primary arms: **TabPFN-TS** (D20 — the primary cold-start baseline: 11M parameters, pretrained on synthetic tabular data only, so contamination-free on these series, and explicitly built for small data), **Chronos-2** (group attention gives zero-shot *covariate-informed* forecasting — directly relevant to the 7-variable macro block), **TimesFM-2.5**, **Moirai-2 / Moirai-MoE** (Any-Variate Attention takes the macro block as covariates).
Secondary if time: Toto, Sundial, FlowState, VisionTS, TiRex.
**Excluded: TimeGPT (D16).**
Check the GIFT-Eval leaderboard before finalising; it moves monthly.
- **Exit:** at least one foundation model beats pooled LightGBM at H=8 in Protocol B, or the cold-start hypothesis is falsified and documented. **Plot accuracy vs available history length and report the crossover point explicitly** — that curve is the most publishable single result in the thesis, and no published work gives it for firm-level quarterly fundamentals.

### NB07 — AutoML
**AutoGluon-TimeSeries** (not PyCaret — its TS module is local-model-only and cannot do the global panel). Two configs to avoid circularity: `best_quality` (includes and ensembles Chronos — the *practitioner benchmark*) and foundation-models-excluded (the clean scientific arm).
- **Exit:** both configs logged with preset recorded

### NB08 — Synthesis
- Leaderboard: MAE / RMSE / MASE / CRPS / coverage / Winkler per model × variable × horizon × protocol × H-bin × sector
- **Diebold-Mariano** vs seasonal naive for every model; corrected resampled t-test across companies
- Calibration curves; conformal coverage verification
- **`policy_table.parquet`** with two winners per cell: `best_model` (thesis result) and `best_deployable_model` (fits 2 GB CPU — O3). **Report the accuracy gap between them** — the cost of deployment constraints is a finding, not something to hide
- Model card per selected model
- **Exit:** policy table covers every routable combination; no cell falls back to an unvalidated model

### NB09 — Deployment integration
- `Forecaster` protocol (extends `MLModel` with intervals and drivers) in `domain/`
- `forecasting` + `simulation` services with DI registration, domain exceptions, error handlers
- Artifacts pulled in CI and baked into the image
- Fan chart, driver waterfall, backtest track record, coverage plot, macro sensitivity
- Cold-start integration test on a company held out of every fold
- **Exit:** `/forecast/cold-start` on a genuinely unseen company returns an interval whose width matches NB08's prediction for that H-bin; 80% coverage gate passes

### NB10 — Conversational layer (§11)
Gated on M6. Exit criteria in §11.

### NB11 — Distress chapter (deferred, D18)
Altman Z / Z″ per company-quarter; ordinal target (distress <1.81 / grey / safe >2.99); reuse NB02 harness; ordinal logit + LightGBM + Markov-switching. Metrics: QWK, macro-F1, Brier, transition matrix. Secondary target: Merton distance-to-default.
- **Exit:** ≥10% of company-quarters outside the safe zone, or the label is too degenerate and that is documented

---

## 7. Metrics reference

| Metric | Use | Note |
|---|---|---|
| MAE, RMSE | Point accuracy | Primary |
| **MASE** | Scale-free | **Use instead of MAPE** — MAPE is undefined on negative, explodes near zero; FCF, net income, operating income all cross zero |
| CRPS | Predictive distribution | Primary probabilistic metric |
| Pinball loss | Per-quantile | |
| Coverage @ 80/90/95 | Interval validity | Empirical only |
| Winkler / MIS | Interval sharpness | |
| Diebold-Mariano | Pairwise significance | vs seasonal naive, always. **Use the Harvey-Leybourne-Newbold small-sample correction** — 81 quarters makes uncorrected DM over-reject [`harvey1997testing`] |
| **Model Confidence Set** | Family-wise model selection | Returns the set of statistically indistinguishable best models across all families, with error control [`hansen2011mcs`] |
| Nadeau-Bengio corrected t | Resampled CV comparison | Accounts for overlapping folds in Protocol B [`nadeau2003inference`] |
| R² | Reported but flagged | Near zero on differenced series even for useful models |
| QWK, macro-F1, Brier | NB11 distress | Ordinal-aware |

**Never report only the cross-company mean.** TSLA (CV 124%) and PG (CV 10%) are not comparable. Every table breaks out by sector.

---

## 8. Repository layout (aligned to the existing template)

```
CFO_Copilot/
├── .github/workflows/          # lint_and_test, publish, deploy (Render)
├── config/companies.yaml       # 60 tickers  ← D12 entry point
├── notebooks/                  # NB00 … NB11 (orchestration only)
├── src/app/
│   ├── settings.py             # Pydantic settings; add LLM_BACKEND, WANDB_*
│   ├── domain/
│   │   ├── ml_model.py         # existing MLModel protocol
│   │   ├── forecaster.py       # NEW: Forecaster → point, PI, CI, drivers
│   │   └── forecast.py         # NEW: Forecast entity
│   ├── services/
│   │   ├── forecasting/        # artifact load, features, conformal lookup
│   │   ├── simulation/         # macro overrides + OOD detection
│   │   ├── nl2sql/             # DuckDB views, sqlglot validation, execution
│   │   ├── chat/               # router, explainer, numeric validator
│   │   ├── llm/                # LLMBackend protocol + implementations
│   │   └── tracking/           # W&B run/config/artifact helpers
│   ├── injections/production.py
│   ├── api/
│   │   ├── routes/             # forecast/ simulate/ chat/ diagnostics/
│   │   └── error_handlers/     # OODScenarioError, UnsafeSQLError, …
│   ├── frontend/pages/         # forecast, cold_start, chat, comparison, diagnostics
│   └── data/sources/           # sec, yahoo, fred, alpha_vantage (existing)
├── sql/views.sql               # the six curated views
├── results/                    # local mirror; W&B artifacts are canonical
├── artifacts/                  # pulled in CI, COPYed into image
├── tests/                      # leakage tests non-negotiable; cassette LLM calls
└── pyproject.toml              # serve / research dependency groups
```

**Conventions from the existing repo (D-C18):** business logic in services, never in routes; raise domain exceptions and map them in `error_handlers/`; register services in the DI container with an `Annotated` alias in `dependencies.py`; `@inject` on every endpoint using `Provide`; paths via `settings.*`; **80% coverage gate** — use `pytest-recording` cassettes for LLM calls so CI never hits an API.

Notebooks orchestrate and visualise. Reusable code lives in `src/app/`. A notebook that defines a model class is a notebook whose results the API cannot reproduce.

---

## 9. Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| **2026-Q2 row is projected** | **Critical** | E1 — resolve before NB00 exits |
| Pooling unrelated series degrades accuracy | High | D21 relatedness-conditioned pooling test in NB04; documented in the literature for cross-market financial series |
| Foundation-model results contaminated by pretraining | High | D20 — TabPFN-TS (synthetic-only pretraining) as primary arm; closed-corpus models excluded (D16); reported as a validity threat |
| Uncorrected DM over-rejects at 81 quarters | Medium | D22 — HLN correction + Model Confidence Set |
| Macro revision look-ahead | High | D13 documented; vintages as O4 upgrade. Published evidence shows predictive-content conclusions can *reverse* under vintage data, so this is a real limitation, not a technicality |
| Four notebooks, four splits | Critical | NB02 keystone, frozen and tagged |
| Errors compared across target definitions | High | Harness converts everything to log-level before comparison. This mistake produced a 33% phantom improvement in early testing. |
| Macro is a time/regime proxy, not a macro effect | High | NB04 exit re-measures at 60 with sector-varying sensitivity |
| Seasonal naive never beaten | High | Acceptable if documented; scaling to 60 is the mitigation |
| Fiscal-calendar misalignment | High | NB00 audit first |
| NB08 winner doesn't fit 2 GB CPU | Medium | Two-winner policy table; O3 measured at NB10 |
| Generated SQL is unsafe | Medium | Read-only connection, sqlglot AST check, view allowlist (§11) |
| LLM fabricates a number | Medium | Numeric validator, §11 |
| Sweep leaks test origins | Medium | Sweeps inside the training fold only |
| Render cold start / cost | Low | Standard tier is always-on; verify whether a workspace fee applies on top |
| Alpha Vantage rate limit | Low | D12 — EDGAR-first makes it non-blocking |

---

## 10. Milestones

| M | Deliverable | Gate |
|---|---|---|
| M0 | E1 resolved | Blocking |
| M1 | 60 companies collected, `panel_long.parquet` | NB00 exit |
| M2 | EDA complete, macro heatmap produced | NB01 exit |
| M3 | **Harness frozen and tagged** | NB02 exit — hard gate |
| M4 | Statistical + boosting arms | NB03, NB04 exit |
| M5 | Deep + foundation + AutoML arms | NB05–NB07 exit |
| M6 | Policy table, DM tests | NB08 exit |
| M7 | App deployed on Render, cold-start test green | NB09 exit |
| M8 | Chat layer | NB10 exit — **after M6** |
| M9 | Distress chapter | NB11 exit — if time (D18) |

---

## 11. Conversational layer (NB10, gated on M6)

Product feature, not a thesis contribution (D19). Built only after M6.

### 11.1 Router

4-way classification, `temperature=0`, GBNF-constrained JSON:

| Intent | Handler |
|---|---|
| forecast / confidence / drivers / track record | `get_forecast()` — fixed tool |
| "what if …" | `simulate()` — fixed tool |
| exploratory data question | `nl2sql()` → DuckDB |
| out of scope | refuse |

Ambiguous → ask a clarifying question rather than guess.

### 11.2 The six views (D14)

Never let the model write SQL against raw columns for derived concepts. Each view gets a natural-language description and 3 example queries; that block goes in the prompt.

```sql
v_panel      -- clean base: ticker, sector, date, all financial/market columns
v_growth     -- precomputed qoq_growth, yoy_growth per variable
v_forecasts  -- stored forecast history: point, pi_lo, pi_hi, ci_lo, ci_hi, model
v_backtest   -- actual, predicted, error, abs_pct_error per origin
v_peer_stats -- sector medians and percentiles by quarter
v_macro      -- 81 rows, one per quarter
```

Scope is single-company at query time (D14): the selected ticker is injected as a bound filter, not left to the model.

### 11.3 SQL hardening — non-negotiable

- Read-only DuckDB connection, parquet baked into the image
- `sqlglot` AST parse; reject anything that is not a single `SELECT`
- Table allowlist = exactly the six views
- Injected `LIMIT 1000`; 5-second timeout
- Generated SQL shown in the UI so the user can see what ran

### 11.4 Explainer + numeric validator

**The LLM never emits a number.** Every figure is a template slot filled from the tool payload. Post-generation, extract all numerals from the answer and assert each appears in the payload; reject and regenerate on mismatch. Report the result: *"0 fabricated figures across N responses"* is a measurable safety property.

### 11.5 Charts on both paths (D15)

**Deterministic, always rendered**, no LLM involved: fan chart (history + point + PI + CI), driver waterfall from SHAP, backtest track record, coverage plot, macro sensitivity.

**LLM-selected** via `get_chart_spec()`, returning a spec from a fixed enum — the model picks *which* chart, never *how* to draw it:

```json
{"chart": "fan", "variable": "revenue_usd_m", "horizons": [1,2,3,4],
 "annotate": ["covid_break"]}
```

**SQL-result charts** get their own spec types (line by quarter, bar by company, scatter vs macro), inferred from the result-set shape. Never let the model emit plotting code — that is an arbitrary-code-execution surface and it breaks reproducibility.

### 11.6 Scenario tool

```python
def simulate(ticker, variable, horizon, macro_overrides: dict):
    feats = build_features(ticker, as_of=latest)
    for k, v in macro_overrides.items():
        feats[f"X_{k}"] = v
    return model.predict(feats), conformal_interval(...)
```

If an override falls outside the training range, conformal intervals are no longer calibrated and tree models cannot extrapolate. **Detect OOD overrides and label the output an unvalidated scenario, not a forecast.** That caveat is worth a paragraph in the thesis.

### 11.7 Exit criteria

- ~120 question evaluation set across five intents: forecast, confidence/drivers, scenario, exploratory-SQL, out-of-scope
- Router accuracy; **SQL execution accuracy** (does it return the right rows — not string-matching the SQL); numeric fidelity (target 100%); refusal precision/recall on the out-of-scope slice
- Tool interface built so a fourth tool can be added without touching the loop

---

## Appendix A — Company universe

| Sector | Tickers | n |
|---|---|---|
| Technology | AAPL (Apple), MSFT (Microsoft), ORCL (Oracle), CSCO (Cisco), IBM (IBM), INTC (Intel), TXN (Texas Instruments), ADBE (Adobe), QCOM (Qualcomm) | 9 |
| Consumer Cyclical | AMZN (Amazon), TSLA (Tesla), HD (Home Depot), MCD (McDonald's), NKE (Nike), F (Ford), M (Macy's), BBY (Best Buy), SBUX (Starbucks) | 9 |
| Consumer Defensive | PEP (PepsiCo), PG (Procter & Gamble), KO (Coca-Cola), WMT (Walmart), COST (Costco), CL (Colgate-Palmolive), GIS (General Mills), KMB (Kimberly-Clark) | 8 |
| Communication Services | GOOGL (Alphabet), T (AT&T), VZ (Verizon), CMCSA (Comcast), DIS (Disney), NFLX (Netflix) | 6 |
| Healthcare | JNJ (Johnson & Johnson), PFE (Pfizer), MRK (Merck), ABT (Abbott), UNH (UnitedHealth), LLY (Eli Lilly), BMY (Bristol-Myers Squibb), AMGN (Amgen), MDT (Medtronic) | 9 |
| Energy | XOM (Exxon Mobil), CVX (Chevron), COP (ConocoPhillips), SLB (Schlumberger), OXY (Occidental Petroleum) | 5 |
| Industrials | CAT (Caterpillar), DE (Deere), GE (General Electric), BA (Boeing), HON (Honeywell), UNP (Union Pacific), UPS (United Parcel Service), LMT (Lockheed Martin) | 8 |
| Utilities | NEE (NextEra Energy), DUK (Duke Energy), SO (Southern Company) | 3 |
| Materials | APD (Air Products), SHW (Sherwin-Williams), ECL (Ecolab) | 3 |

**60 of 60 named.** Same profile throughout: listed pre-2006, non-financial, full quarterly history. Distressed names included deliberately (F, GE, BA, OXY, M, BBY, INTC) so NB11's Altman Z target is not degenerate. Materials is a new sector, added to broaden macro sensitivity — APD/ECL are exposed to industrial-production and energy-cost swings distinct from Energy-sector names, and SHW/ECL carry housing/construction cyclicality not otherwise represented.

## Appendix B — Baseline results at 7 companies

Rolling origin, h=1, last 16 quarters × 7 companies, n=112, target = QoQ log growth of revenue:

| Model | MAE | RMSE | vs seasonal naive |
|---|---|---|---|
| Seasonal naive | **0.0400** | 0.0622 | — |
| SARIMA (per company) | 0.0441 | 0.0761 | +10.4% |
| LightGBM pooled | 0.0442 | **0.0650** | +10.5% |
| LightGBM local | 0.0494 | 0.0784 | +23.5% |
| Ridge local | 0.0585 | 0.0869 | +46.3% |
| Ridge pooled | 0.0669 | 0.0913 | +67.4% |

Pooling improves LightGBM by 10.5% MAE / 17% RMSE at only 516 rows. Nothing beats seasonal naive — the empirical justification for scaling to 60.

## Appendix C — Diagnostics at 7 companies (revenue)

| Ticker | n | d (levels) | d (log) | Seasonal | Seas. str | Trend str | Box-Cox λ | CV |
|---|---|---|---|---|---|---|---|---|
| AAPL | 81 | 1 | 0 | yes (p=4) | 0.933 | 0.992 | 0.60 | 63% |
| AMZN | 81 | 2 | 2 | yes (p=4) | 0.908 | 0.999 | 0.14 | 99% |
| GOOGL | 81 | 2 | 1 | yes (p=4) | 0.279 | 0.996 | 0.10 | 91% |
| MSFT | 81 | 2 | 1 | yes (p=4) | 0.770 | 0.999 | −0.46 | 62% |
| PEP | 81 | 1 | 2 | yes (p=4) | 0.961 | 0.984 | 0.48 | 30% |
| PG | 81 | 2 | 2 | yes (p=4) | 0.577 | 0.926 | 2.33 | 10% |
| TSLA | 75 | 2 | 1 | **no** | 0.000 | 0.975 | 0.16 | 124% |

All forecastable (Ljung-Box p ≈ 0). Seasonal strength spans 0.00–0.96, so seasonality must be company-specific. Box-Cox λ spans −0.46 to 2.33, so no shared variance-stabilising transform exists — hence D4, with O1 open for alternatives.

## Appendix D — LightGBM feature & target ablation at 7 companies

All errors as **MAE of log-level of revenue at t+1**, so target definitions are comparable. 476 rows, rolling origin over 16 quarters, n=112.

| Method | Target | nfeat | MAE | ≈% err | vs best baseline |
|---|---|---|---|---|---|
| **Seasonal naive (repeat YoY growth)** | — | — | **0.0400** | 4.0% | — |
| Seasonal naive (level 4q ago) | — | — | 0.0934 | 9.3% | +134% |
| Naive (last quarter level) | — | — | 0.1132 | 11.3% | +183% |
| LGBM lags only | qoq | 6 | 0.0583 | 5.8% | +46% |
| LGBM lags only | yoy | 6 | 0.0517 | 5.2% | +29% |
| LGBM + rolling | yoy | 8 | 0.0502 | 5.0% | +26% |
| LGBM + calendar + static | yoy | 11 | 0.0501 | 5.0% | +25% |
| LGBM + other financial lines | yoy | 18 | 0.0488 | 4.9% | +22% |
| **LGBM + macro (no financial lines)** | yoy | 18 | **0.0457** | 4.6% | **+14%** |
| LGBM + financials + macro | yoy | 25 | 0.0468 | 4.7% | +17% |
| LGBM + all + macro deltas | qoq | 34 | 0.0448 | 4.5% | +12% |

### Residual-boosted arm (target = seasonal-naive error)

| Features | λ | nfeat | MAE | RMSE | vs baseline |
|---|---|---|---|---|---|
| L+R | 1.00 | 8 | 0.0523 | 0.0789 | +31% |
| L+R | 0.50 | 8 | 0.0440 | 0.0662 | +10% |
| L+R+C+S+X | 0.50 | 18 | 0.0438 | 0.0659 | +10% |
| **L+R+C+S+M+X** | **0.50** | 25 | **0.0430** | **0.0664** | **+7.5%** |

**Conclusions carried into NB04:**
1. **Lags dominate.** Naive 11.3% → lags-only 5.2%. Nothing else comes close.
2. **Macro is the strongest non-lag group** (+10.7% relative), more than rolling, calendar, static and financials combined. Caveat: zero cross-sectional variation at 7 companies; re-measure at 60.
3. **Mechanical macro deltas are useless.** Keep only economically meaningful composites (real rate).
4. **Financials + macro is worse than macro alone** at 476 rows. Feature count is binding; should reverse at ~4,800.
5. **Calendar and static are near-free but currently inert** — 7 ticker levels over 476 rows memorises.
6. **Shrinking toward the baseline is the biggest LightGBM win.** λ=0.5 moved the residual arm from +31% to +7.5%.
7. **Nothing beats seasonal naive yet.**

## Appendix E — Phase 2 (deferred, D17)

Not in this plan. Recorded so the design isn't lost.

**E.1 QLoRA for NL-SQL.** Run only if views + few-shot execution accuracy comes in below ~85%. LoRA, not full fine-tuning: `r=16, alpha=32`, target q/k/v/o/gate/up/down, 4-bit NF4 + double quant, `bf16` compute, `flash_attention_2`, gradient checkpointing, batch 1 × grad-accum 16, seq 1024, `paged_adamw_8bit`, Unsloth. Staged 4B → 8B on the A4000 (8 GB, sm_86). Dataset: ~600 question/SQL pairs generated from templates over the six views, paraphrased, **verified by execution not by reading**, held out by template family. Deliverable: views vs views+QLoRA vs API execution-accuracy comparison. Expect 1–2 h for 3 epochs. Close other apps — the display driver can hold ~1 GB of VRAM. If OOM at 8B, cut `max_seq_length` to 768 before touching LoRA rank.

**E.2 Document layer.** Historical EDGAR filing corpus (MD&A, risk factors) for the 60 known companies, section-aware chunking, `(ticker, period, section, filing_date)` metadata, retrieval for business-narrative questions. Upload path for non-public documents (board decks, internal budgets) with CIK/period binding validation and three-way reconciliation (panel vs document vs forecast). Text features as feature group `T` in the NB04 ablation, **lagged by filing date not period end** (a 10-Q for the quarter ending June is filed in late July — using it dated June leaks six weeks of hindsight).

**E.3 Macro vintages (O4).** ALFRED point-in-time series for gdp_yoy, unemployment_rate, cpi_yoy; rerun Protocol A and report the accuracy delta as a measure of revision look-ahead bias.

**E.4 Cloud Run GPU experiment.** Skipped (D-C17/D2). If revisited: deploy the merged adapter to Cloud Run GPU (L4, scales to zero, ~$0.70/hr while warm), measure cold start and p50/p95 latency, then tear down. Never a 24/7 GPU VM (~$500/mo).

## Appendix F — Literature grounding

Every design decision in this plan now has a citation. Full BibTeX in `references.bib`; keys below.

### F.1 Citation map by plan section

| Plan section | Decision it defends | Key references |
|---|---|---|
| §4 pooling / global models | D21, NB04 | `monteromanso2021global` (global models are **not** more restrictive than local; complexity constant in the number of series), `makridakis2022m5acc` (first M competition won by global ML), `das2026chronosfinance` (mixing unrelated markets *hurts*) |
| §6 NB02 tabularization | Reduction to supervised regression | `elsayed2021gbrt` (windowed GBRT matches/beats SOTA deep models on 9 datasets), `bentaieb2012multistep` (direct vs recursive), `ke2017lightgbm`, `chen2016xgboost` |
| §3 target variables, §6 NB04 | Firm-level financial forecasting | `cao2024fundamental` (ML earnings forecasts beat cross-sectional models *and* analyst consensus), `vanbinsbergen2023man`, `bradshaw2012reexam`, `gerakos2013regression` |
| §3 macro block | D12, macro covariates | `ghysels2006predicting`, `ghysels2004midas` (MIDAS for the mixed-frequency problem), `stock2002diffusion` (factor alternative to 7 raw covariates) |
| §3.4 macro revisions | D13, O4 | `croushore2001realtime`, `croushore2011frontiers` (predictive content can **vanish** in real time), `stark2002forecasting` (inflation forecasts most revision-sensitive — so CPI is the covariate to worry about) |
| §7 metrics | MASE over MAPE | `hyndman2006another` (MASE; MAPE degenerate near zero — FCF and operating income cross zero), `gneiting2007proper` (CRPS, MSIS), `gneiting2014probabilistic` |
| §7 significance | D22 | `diebold1995comparing`, `harvey1997testing`, `hansen2011mcs`, `nadeau2003inference` |
| §4 protocols | Rolling origin, group CV | `tashman2000outofsample`, `bergmeir2012cv` (blocked CV is safe and more robust than single hold-out), `bergmeir2018note`, `deprado2018advances` (purging/embargo) |
| §5.3–5.4 conformal | D9, the Protocol B design | **`barber2023beyond`** (conformal beyond exchangeability — the theoretical licence for cross-conformal on the company axis), `gibbs2021aci`, `xu2021enbpi`, `romano2019cqr`, `barber2021jackknife`, `vovk2005algorithmic` |
| §5.1 PI vs CI | D8 | `kendall2017uncertainties`, `lakshminarayanan2017ensembles`, `gal2016dropout`, `huellermeier2021aleatoric` |
| §6 NB05 | Deep arms, and the expected negative result | `salinas2020deepar`, `oreshkin2020nbeats`, `challu2023nhits`, `lim2021tft`, `nie2023patchtst`, `zeng2023transformers` (DLinear beats many transformers) |
| §6 NB06 | D16, D20 | `hoo2025tabpfnts`, `hollmann2025tabpfn` (*Nature*), `ansari2025chronos2`, `ansari2024chronos`, `das2024timesfm`, `woo2024moirai`, `liu2025moiraimoe`, `rasul2023lagllama`, `aksu2024gifteval`, `garza2023timegpt` (cite to justify its exclusion) |
| §6 NB07 | AutoML arm | `shchur2023autogluon`, `monteromanso2020fforma` |
| §4 Protocol B | The cold-start requirement | **`oreshkin2021metalearning`** (zero-shot transfer to unseen series without retraining, at state-of-practice accuracy), `hewamalage2021rnn` (how accuracy degrades with limited history) |
| §6 NB11 distress | D18 | `altman1968zscore`, `altman1977zeta`, `altman2005emerging` (Z″), `ohlson1980oscore`, `zmijewski1984methodological`, `merton1974pricing`, `shumway2001hazard`, `campbell2008distress`, `dasilas2024ml`, `chawla2002smote` |
| §3.4 breaks | COVID, spinoffs | `hamilton1989regime`, `bai1998estimating`, `bai2003multiple`, `hyndman2021fpp` |
| §0 D4, §6 NB01 | One transform panel-wide | `box1964transformations`, `wang2006characteristic` (seasonal/trend strength features), `lubba2019catch22`, `hyndman2021fpp` |
| §6 NB00 outliers | Isolation Forest gate | `liu2008isolation`, `ester1996dbscan` |
| §6 NB04 explainability | SHAP by sector | `lundberg2017shap`, `lundberg2020treeshap` |
| §11.2–11.3 NL-SQL | D14, the views design | `yu2018spider`, **`li2023bird`** (GPT-4 reaches only 54.89% execution accuracy vs 92.96% human; external knowledge grounding lifts it ~20 points — the case for a curated semantic layer), `pourreza2023dinsql`, `gao2024dailsql`, `talaei2024chess` |
| Appendix E.1 QLoRA | D17 | `hu2022lora`, `dettmers2023qlora`, `pourreza2024dtssql` (fine-tuned 7B for text-to-SQL) |
| §11.4 numeric validator | The safety property | `ji2023hallucination`, `es2024ragas`, `willard2023guided` (grammar-constrained decoding) |
| Appendix E.2 documents | Deferred text layer | `loughran2011liability`, `cohen2020lazy` (10-K text *changes* predict outcomes — motivates the filing-date lag), `araci2019finbert`, `yang2020finbert`, `wu2023bloomberggpt` |
| §2.3, §8 governance | W&B, model cards | `sculley2015debt`, `mitchell2019modelcards`, `gebru2021datasheets` |
| §7, §9 benchmark evidence | D6 | `makridakis2020m4` (combination won; pure ML underperformed), `makridakis2022m5acc`, `makridakis2022m5unc`, `makridakis2024m6` |
| §4 panel structure | 60 × 81 panel | `baltagi2021panel`, `arellano1991tests` |
| §3 macro block (D24) | Yield spread, mfg_confidence, S&P500 lagged | `stock2002diffusion` (factor rationale for adding correlated macro signals); yield-curve and business-confidence indices are standard covariates already covered by the macro/MIDAS references in §4 |

### F.2 The five plan claims, tested against the literature

| Claim | Verdict | Action |
|---|---|---|
| (a) Seasonal naive is hard to beat on quarterly financial series | **Supported** — at a one-year horizon the random walk performs as well as methods using far larger predictor sets, and the HVZ fundamentals model does *worse* than a naive random walk | Keep as the primary skill baseline; report MASE against it |
| (b) Pooling across companies improves accuracy | **Supported, with a documented failure mode** — mixing series across equity and interest-rate markets *reduces* accuracy, because noisy context degrades the model | D21 relatedness-conditioned pooling test |
| (c) Deep learning underperforms on ~80-observation series | **Supported for bespoke deep architectures only** — but tabular/foundation models are the modern exception, and one of them is titled "Accurate predictions on small data" | **Restate the claim** as "*bespoke* deep architectures underperform"; benchmark TabPFN-TS and Chronos-2 as the small-data champions |
| (d) Shrinking a correction toward a strong baseline helps at small n | **Supported** | D23 — frame it as forecast combination with a benchmark anchor, cite FFORMA and the M4 combination findings |
| (e) Foundation models win at short history, trained models at long | **Supported** | Plot accuracy vs history length and report the crossover explicitly (NB06 exit) |

### F.3 Contradictions to pre-empt

The thesis should address these rather than be caught out in a defence.

1. **Global models do not require homogeneous series.** Don't over-justify homogeneity as a precondition for pooling — the theory says global methods are no more restrictive than local ones.
2. **But mixing *unrelated* series can hurt.** Reconcile 1 and 2 via relatedness-conditioned pooling (D21). This is the sharpest open question in the plan.
3. **"Transformers beat everything" is contested.** DLinear and windowed GBRT results caution against defaulting to deep models at this sample size — which is also why NB05's negative result is defensible rather than embarrassing.
4. **Contamination inflates foundation-model benchmarks.** Large-cap US fundamentals are among the most redistributed numeric series in existence. This is why D16 excludes closed-corpus models and D20 promotes the synthetic-pretrained one.
5. **Real-time vs revised macro data can reverse conclusions.** D13's limitation is substantive, not cosmetic. If time allows, O4's ALFRED robustness appendix for CPI and GDP is the cheapest way to defuse it.

### F.4 Fallback thresholds derived from the literature

| If… | Then… |
|---|---|
| All-60 pooling doesn't beat per-cluster pooling inside the MCS at 10% | Adopt clustered-global models as the production config |
| TabPFN-TS / Chronos-2 don't beat seasonal naive on cold-start companies at short history | Fall back to the shrinkage-to-benchmark rule (D23) |
| Accuracy-vs-history crossover occurs below ~20 quarters | Make foundation models the default for young companies in the policy table |

### F.5 Bibliographic cautions

- Several 2024–2026 entries are still arXiv preprints (Chronos-2, TabPFN-TS, TimesFM, Moirai/Moirai-MoE, GIFT-Eval, CHESS, DTS-SQL, M6). Verify final venues, volumes and pages before submission. TabPFN-v2 **is** peer-reviewed (*Nature* 637), and Moirai-MoE is in ICML 2025 proceedings.
- **Altman et al. 1977 (ZETA) pages are 29–54** per Elsevier, not the widely-copied 29–51. **Shumway 2001 pages are 101–124**, not the erroneous 5–32 found in some secondary sources.
- Four entries were reasoned from domain knowledge rather than retrieved directly and need field-checking: Efron & Morris (1975) on shrinkage, the SHAP-critique papers (Kumar et al. 2020; Aas et al. 2021), Bandara et al. on COVID anomaly handling, and the M6 volume/pages.
