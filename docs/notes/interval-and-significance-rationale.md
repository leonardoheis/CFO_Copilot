# Why leave-one-company-out, the jackknife and Diebold–Mariano

Rationale for the thesis methods section (NB02 plan, step 17). Agreed
2026-11-12 while building the Protocol B folds
(`src/app/services/evaluation/splits.py`), the Protocol B intervals
(`src/app/services/evaluation/conformal.py`) and the significance test
(`src/app/services/evaluation/metrics.py`). Spec: R3, R8 and R9 of
`docs/specs/nb02-evaluation-harness.md`.

## Decisions

- **Protocol B holds out one company at a time** (scikit-learn
  `LeaveOneGroupOut` on the ticker), not `KFold`, `StratifiedKFold`,
  `GroupKFold` or `StratifiedGroupKFold`.
- **Protocol B prediction intervals use the jackknife** (Barber et al., 2021).
  To score a held-out company J, the interval is centred on the prediction of
  the model fit without J. Its half-width is a conformal quantile of the other
  59 companies' held-out errors, divided by each company's own error scale,
  under Protocol A's time rule: only errors whose target date is on or before
  the origin, from the latest 12 origins, with ACI (γ = 0.2).
- **Not the jackknife+, not a bootstrap.** Bootstrap stays where it already
  is in the master plan: the confidence interval of the mean (§5.2) and
  inside the Model Confidence Set (NB08).
- **Each model is tested against the baseline to beat with the
  Diebold–Mariano test**, with the Harvey–Leybourne–Newbold correction, on
  one absolute-error loss difference per origin (statsmodels'
  `diebold_mariano_test`).
- **The Model Confidence Set (Hansen, Lunde & Nason, 2011) complements it in
  NB08; it does not replace it.**

## Argument: leave one company out, not KFold or GroupKFold

Protocol B asks how well a model forecasts a company it has never seen, so
the unit held out must be the **company**, never a row. Each scikit-learn
splitter was checked against the panel: 60 companies in 9 sectors of 9, 9, 9,
8, 8, 6, 5, 3 and 3. Versions 1.7.1 and 1.9.1 behave the same; the
percentages come from 200 seeds.

| Splitter | Unit held out | What happens on this panel |
|---|---|---|
| `KFold` | Rows (company-quarters) | A held-out AAPL quarter leaves AAPL's other quarters in training, so the company is not unseen. Shuffled folds also train on quarters after the test quarter (look-ahead) |
| `StratifiedKFold` on sector | Rows | Same two leaks as `KFold` |
| `GroupKFold(12, shuffle=True)` | Companies, 12 folds × 5 (the master plan's first design) | Ignores sectors. In 67 % of seeds a fold holds 2 or more companies of Materials, Utilities or Energy; in 35 % one of those sectors keeps at most one company in training |
| `StratifiedGroupKFold(12)` | Companies, spread by sector | Refuses: "n_splits=12 cannot be greater than the number of members in each class". Every sector has fewer than 12 companies |
| `StratifiedKFold(6)` on one row per company | Companies, 6 folds × 10 | Accepted, with a warning on every run. Small sectors are safe, but each model trains on 50 companies instead of 55 |
| **`LeaveOneGroupOut`** | **One company, 60 folds** | **Chosen.** Each model trains on 59 companies; every sector keeps all but the tested company |

1. **Why sector spread matters.** In production the model is trained on all
   60 companies, so a new utility is forecast by a model that learned from 3
   utilities. If a fold holds out 2 of the 3 utilities, the model scoring
   them learned from one, and the test measures "a sector the model barely
   knows" instead of "a company it has not seen". Whether that happens
   depends on the seed, and the spec reports every result per sector, so
   per-sector results would change with the seed.
2. **Why stratified group k-fold cannot work here.** It must place every
   sector in every fold, which needs at least 12 companies per sector for 12
   folds; the largest sector has 9. scikit-learn's allocation itself (sort by
   sector, deal round-robin into the folds) would spread the sectors; only
   that guard refuses. An own implementation of the same allocation was built
   and then dropped in favour of a library splitter.
3. **Why not fewer, larger folds.** `StratifiedKFold(6)` keeps the small
   sectors but trains each model on 50 companies, further from production's
   60. It also weakens model comparison: with the Nadeau–Bengio correction the
   variance factor grows from 1/12 + 5/55 ≈ 0.17 (12 × 5) to
   1/6 + 10/50 ≈ 0.37 (6 × 10), about twice the variance.
4. **Why leave-one-company-out.** It is the leave-one-out cross-validation of
   Müller & Guido (2016, ch. 5) with the company, not the row, as the unit.
   The sector problem disappears, because only the tested company leaves
   training, and each model trains on 59 of 60 companies, the closest
   possible to production. It is the method the book recommends for small
   datasets ("time-consuming… but sometimes provides better estimates on
   small datasets"), and 60 companies is a small dataset.
5. **The price.** 60 fits per origin instead of 12, about 5×, for models
   trained on the panel. Zero-shot foundation models are not trained on it,
   so holding a company out costs them nothing.
6. **The time axis is handled separately.** Within each held-out company,
   Protocol A's rolling origin still applies: a row trains at origin t only if
   its target date is on or before t (the idea of the `gap` parameter in
   scikit-learn's `TimeSeriesSplit`, applied by date across 60 companies).

## Argument: the jackknife

1. **It answers Protocol B's question.** Protocol B asks how well a model
   forecasts a company it has never seen. Leave-one-company-out (scikit-learn
   `LeaveOneGroupOut`; Müller & Guido, 2016) already fits one model without
   each company to make the point forecasts. The jackknife calibrates the
   interval with those same held-out errors, so every error used is the error
   of an unseen company.
2. **It costs no extra fits.** The 60 fits per origin exist for the point
   forecasts; the interval reuses their errors. Any bootstrap adds B fits per
   origin on top: 110 instead of 60 at B = 50.
3. **The jackknife+ would break the protocol.** It centres company J's
   interval on the predictions of every other leave-one-out model. Each of
   those was trained on J, so J would no longer be unseen. A clean jackknife+
   needs a model fit without both i and J: 60 × 59 ≈ 3,500 fits per origin.
4. **The jackknife+-after-bootstrap has the same problem** (Kim, Xu &
   Barber, 2020). Keeping J unseen restricts it to bootstrap models that left
   out both J and the calibrating company, about 0.36² ≈ 13 % of them, so it
   needs a large B.
5. **A plain bootstrap interval has no coverage guarantee.** Conformal
   methods are the master plan's design for prediction intervals (D9) because
   they control coverage without assuming a distribution (Vovk et al., 2005;
   Lei et al., 2018).
6. **The price, stated honestly.** The jackknife has no worst-case coverage
   guarantee; the jackknife+ guarantees 1 − 2α. The jackknife covers well when
   the model is stable, that is, when leaving one company out barely moves it
   (Barber et al., 2021). So coverage is measured, not assumed: per level, per
   sector and per H, and Checkpoint 3 requires seasonal naive to cover within
   ±5 points at every H.
7. **A production app could use the jackknife+.** A genuinely new company is
   in none of the 60 leave-one-out models, so the restriction in point 3 does
   not apply there.

### Where bootstrap does belong

| Use | Question | Where |
|---|---|---|
| Confidence interval of the mean (inner band) | How uncertain is the model itself? | LightGBM / CatBoost, 50-resample bootstrap (master plan §5.2) |
| Model Confidence Set | Which models are tied for best? | Block bootstrap of the loss differences, NB08 |
| Prediction interval (outer band) | Where will the actual value land? | Conformal: rolling split conformal with ACI (Protocol A), jackknife (Protocol B) |

## Argument: Diebold–Mariano

1. **It answers the harness's question.** For every model the harness asks
   one pairwise question: does it beat the baseline to beat? The DM test
   compares exactly two forecasts on the same rows (Diebold & Mariano, 1995).
2. **It is a test of forecasts, which is what we have.** Diebold (2015)
   argues the test stays valid for comparing forecasts, as opposed to
   comparing the models that produced them.
3. **The correction suits a small sample.** With 16 origins the test has 16
   observations. Uncorrected DM over-rejects in small samples; the
   Harvey–Leybourne–Newbold correction scales the statistic and uses
   Student's t with 15 degrees of freedom (Harvey et al., 1997).
4. **One observation per origin, not per row.** The 60 companies at one
   origin share the same macro shocks, so the ~960 test rows are not
   independent. The loss difference is averaged over companies at each
   origin, and the variance allows autocorrelation up to lag h − 1 because
   forecasts from consecutive origins overlap.
5. **A library computes it.** statsmodels' `diebold_mariano_test` does the
   test; the harness only averages per origin. Its Newey–West variance weights
   the lags with a declining kernel where Harvey et al. weight them equally;
   at h = 1 the two coincide, and the result equals a one-sample t-test
   (checked against SciPy in the tests).

### Why the Model Confidence Set complements it

| | Diebold–Mariano (HLN) | Model Confidence Set |
|---|---|---|
| Question | Does **this model** beat **the baseline**? | Which of **all models** are tied for best? |
| Compares | 2 forecasts | Many models, family-wise error control |
| Where | Harness, every model, NB02 onward | NB08, once every family exists |
| Library | statsmodels `diebold_mariano_test` | `arch.bootstrap.MCS` (to add with `uv add arch` in NB08) |

With 16 origins the MCS's block bootstrap resamples only 16 time points, so
the set will likely be wide, with many models tied. That is an honest
small-sample result, to be reported as such.

Giacomini & White (2006) test conditional rather than unconditional
predictive ability. It is a valid alternative, but nothing in this design
needs the conditional version, and there is no maintained Python
implementation to use under the project's library-first rule.

## Libraries checked for the jackknife (2026-11-12)

None fits; every reason is about the design, not the library's quality.

| Library | Version checked | Why it does not fit |
|---|---|---|
| scikit-learn | 1.7.1, 1.9.1 | No conformal prediction at all |
| MAPIE | 1.6.0 (2026-10-19) | `CrossConformalRegressor` refits a scikit-learn estimator on its own folds; no time axis; treats the scored company as new data (≈ 3,600 fits per origin); cannot wrap the baselines or foundation models; residuals in target space, not the R5 scale |
| puncc | 0.9.3 (2026-06-23) | `CVPlus` refits its own models; requires `numpy<2.0` (project: 2.3.2) |
| crepes | 0.9.1 (2026-06-12) | Accepts given residuals, but would replace only the five-line conformal quantile; ACI's out-of-range levels still need our guard |
| Fortuna (AWS) | 0.2.0 (2024-12-08) | Requires `numpy<2.0`; JAX/Flax/TensorFlow stack; one release in two years |
| coverforest | 0.0.3 (2025-01-21) | Random forests only; no release since |
| sktime, darts, statsforecast conformal wrappers | maintained | Calibrate each series on its own past errors, not on other companies' |

`jackknife_half_widths` is therefore the project's own rules (exclude the
scored company, no target after the origin, the window, ACI) around one
conformal quantile. Its tests check it against reference behaviour:
exchangeable synthetic errors reach nominal coverage at 80, 90 and 95 %
(± 2 points); a company is never calibrated on its own errors; an error whose
target is after the origin never calibrates.

## Sources

| Claim | Source | Bib key |
|---|---|---|
| The jackknife and the jackknife+; jackknife+ coverage ≥ 1 − 2α; the jackknife needs a stable algorithm | Barber, Candès, Ramdas & Tibshirani (2021), *Annals of Statistics* 49(1), 486–507 | `barber2021jackknife` |
| Jackknife+-after-bootstrap | Kim, Xu & Barber (2020), *Predictive inference is free with the jackknife+-after-bootstrap*, NeurIPS 33 | **not yet in `references.bib`** |
| Conformal prediction, distribution-free coverage | Vovk, Gammerman & Shafer (2005); Lei, G'Sell, Rinaldo, Tibshirani & Wasserman (2018), *JASA* 113(523) | `vovk2005algorithmic`, `lei2018distribution` |
| Conformal prediction without exchangeability, the licence for the company axis | Barber, Candès, Ramdas & Tibshirani (2023) | `barber2023beyond` |
| Adaptive conformal inference | Gibbs & Candès (2021), NeurIPS | `gibbs2021aci` |
| Leave-one-out cross-validation; k-fold, stratified k-fold and group cross-validation | Müller & Guido (2016), ch. 5 | `muller2016introduction` |
| The splitters' behaviour (`KFold`, `GroupKFold`, `StratifiedGroupKFold`, `LeaveOneGroupOut`) | scikit-learn User Guide §3.1, <https://scikit-learn.org/stable/modules/cross_validation.html>; the refusal checked in `sklearn/model_selection/_split.py` | `pedregosa2011scikit` |
| Corrected variance for comparing models over cross-validation folds | Nadeau & Bengio (2003), *Machine Learning* 52(3) | `nadeau2003inference` |
| The Diebold–Mariano test | Diebold & Mariano (1995), *JBES* 13(3) | `diebold1995comparing` |
| Small-sample correction | Harvey, Leybourne & Newbold (1997), *IJF* 13(2) | `harvey1997testing` |
| DM tests compare forecasts, not models | Diebold (2015), *Comparing predictive accuracy, twenty years later*, *JBES* 33(1) | **not yet in `references.bib`** |
| Model Confidence Set | Hansen, Lunde & Nason (2011), *Econometrica* 79(2) | `hansen2011mcs` |
| Conditional predictive ability | Giacomini & White (2006), *Econometrica* 74(6), 1545–1578 | **not yet in `references.bib`** |

Bib keys refer to the thesis repo's `references.bib`
(`cfo-copilot-thesis/references.bib`). The fit counts (60, 110, ≈ 3,500) and
the 13 %, the fold percentages over 200 seeds and the Nadeau–Bengio factors
are computed for this panel and design, not quoted; present them as the
author's argument.

## Paragraph for `main.tex`

> Bajo el Protocolo B, cada empresa se pronostica con un modelo entrenado sin
> ella (validación cruzada dejando una empresa fuera,
> \cite{muller2016introduction}). Se descartaron \textit{KFold} y
> \textit{StratifiedKFold} sobre filas, porque dejarían en el entrenamiento
> otros trimestres de la misma empresa, y \textit{GroupKFold} con 12 grupos
> de 5 empresas, porque al ignorar el sector deja en algunos pliegues a un
> sector pequeño (Materiales, Servicios Públicos) con una sola empresa de
> entrenamiento; su versión estratificada no es aplicable, ya que ningún
> sector reúne las 12 empresas que exigiría. Su intervalo de predicción se calibra con
> los errores de las demás empresas excluidas: el \textit{jackknife}
> \cite{barber2021jackknife}, con la regla temporal y la corrección adaptativa
> del Protocolo A \cite{gibbs2021aci}. Se descartó el \textit{jackknife+}
> porque centra el intervalo en modelos que sí vieron a la empresa evaluada,
> y un \textit{bootstrap} porque añade ajustes sin aportar garantía de
> cobertura; el \textit{bootstrap} se reserva para el intervalo de confianza
> de la media y para el conjunto de confianza de modelos. Como el
> \textit{jackknife} no garantiza la cobertura en el peor caso, la cobertura
> se mide por nivel, sector e historia disponible. Cada modelo se compara con
> el mejor \textit{baseline} mediante la prueba de Diebold--Mariano con la
> corrección de Harvey, Leybourne y Newbold
> \cite{diebold1995comparing,harvey1997testing}, sobre una diferencia de
> pérdida por origen, ya que las empresas de un mismo origen comparten los
> mismos choques macroeconómicos. El conjunto de confianza de modelos
> \cite{hansen2011mcs} complementa esta prueba al comparar todas las familias
> a la vez.
