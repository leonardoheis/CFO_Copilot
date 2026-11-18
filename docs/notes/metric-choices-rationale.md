# Why MASE is computed in the harness and R² is out of sample

Rationale for the thesis methods section (NB02 plan, step 17). Agreed
2026-11-04 while building the point metrics
(`src/app/services/evaluation/metrics.py`).

## Decision

- MAE, RMSE, MAPE and the mean squared errors come from scikit-learn
  (`sklearn.metrics`). No metric formula is written by hand.
- MASE is scikit-learn's `mean_absolute_error` on errors divided by each
  company's scale. The scale is computed by the harness: the company's
  seasonal-naive mean absolute error over the rows that train at the origin.
  No sktime or skforecast.
- R² is reported only out of sample, against the baseline to beat:
  1 − SSE(model) / SSE(baseline), on the same test rows. Plain R²
  (`r2_score`, against the mean of y) is not reported.

## MASE: why not sktime or skforecast

1. **The definition is the textbook one.** Hyndman & Koehler (2006) divide the
   forecast error by the in-sample mean absolute error of a naive forecast; for
   seasonal data the naive forecast is seasonal naive with period m (m = 4 for
   quarters). For h ≤ 4, a seasonal-naive forecast of quarter t is quarter
   t − 4 whatever the horizon, so its error on a training row is that row's
   year-over-year difference. The harness scale is therefore exactly their
   denominator.
2. **The libraries work one series at a time; the harness pools 60 companies
   and 16 origins.** sktime's `mean_absolute_scaled_error` takes one series'
   `y_train` and period `sp`. Here the training history differs at every
   origin (only target dates on or before it), and each company has its own
   scale. That is 60 × 16 calls per model, target and horizon, where the
   harness needs one groupby.
3. **They cannot express the signed-target scale.** Operating income, EBITDA
   and FCF are scored as level ÷ trailing four-quarter revenue at each row's
   own origin (spec R5). That denominator changes row by row, so the scaled
   history is not a plain series a library can difference.
4. **A heavy dependency for one formula.** Neither library is installed; the
   harness version would already compute the scale in one pandas line.

Two consequences to state in the thesis:

- Revenue's MASE is computed on log levels, not on raw levels. MASE is
  scale-free either way; the log scale is the harness's shared error scale
  (spec R5), so MASE and MAE are on the same footing.
- A MASE below 1 means the model beats seasonal naive's *in-sample* error, not
  its out-of-sample error. The out-of-sample comparison is the job of
  out-of-sample R² and Diebold–Mariano.

## R²: why only out of sample

Plain R² compares a model with the mean of y. On a cross-section of 60
companies of very different size, that mostly measures whether the forecast
knows each company's size. Seasonal naive at h = 1, last 16 labelled origins,
all 60 companies (from the spec's facts):

| Target | Plain R² on levels |
|---|---|
| Revenue | 0.981 |
| Operating income | 0.850 |
| FCF | 0.703 |

1. **It rewards size, not forecasting.** A rule with no model at all scores
   0.98 on revenue because large companies stay large.
2. **The error scale does not cure it.** Log revenue and revenue-scaled
   ratios still vary mostly between companies, so plain R² stays high.
3. **On the target itself it is about 0 by construction.** The targets are
   changes (year-over-year or quarter-over-quarter); their mean is near the
   forecast of any sensible model, so R² against it says nothing.
4. **Out-of-sample R² answers the thesis question.** Against the baseline to
   beat (Campbell & Thompson, 2008), 0 means no better than the baseline,
   positive means better, negative means worse. Each baseline scores exactly 0
   against itself (acceptance A8).

Suggested use in the thesis: show the table above once in the methods
section, to explain why plain R² is not used. It pre-empts the question "why
not R²?".

## Sources

| Claim | Source | Bib key |
|---|---|---|
| MASE: scale by the in-sample naive (seasonal naive for seasonal data) MAE | Hyndman & Koehler (2006), *International Journal of Forecasting* 22(4), 679–688, doi:10.1016/j.ijforecast.2006.03.001 | `hyndman2006another` |
| Seasonal MASE with period m | Hyndman & Athanasopoulos, *Forecasting: Principles and Practice*, 3rd ed., §5.8, <https://otexts.com/fpp3/accuracy.html> | `hyndman2021fpp` |
| Out-of-sample R² against a benchmark forecast | Campbell & Thompson (2008), "Predicting Excess Stock Returns Out of Sample: Can Anything Beat the Historical Average?", *Review of Financial Studies* 21(4), 1509–1531, doi:10.1093/rfs/hhm055 | `campbell2008predicting` |
| The plain R² values above | Spec `docs/specs/nb02-evaluation-harness.md`, "MAPE works for revenue only, and R² on levels measures size" | — |

Bib keys refer to the thesis repo's `references.bib`
(`cfo-copilot-thesis/references.bib`). Its `campbell2008distress` is a
different paper (Campbell, Hilscher & Szilagyi, distress risk); do not cite it
for out-of-sample R².

Points 2–4 on MASE are this project's own reasoning about the libraries' fit,
not a quoted source. sktime's signature is as recalled, not re-checked
against its current documentation.

## Paragraph for `main.tex`

> El MASE sigue la definición de \citet{hyndman2006another}: el error de
> pronóstico se divide por el error absoluto medio, dentro de la muestra, del
> pronóstico estacional ingenuo con período 4, calculado por empresa sobre los
> trimestres de entrenamiento de cada origen. Se calcula en el propio arnés y
> no con bibliotecas como sktime, que operan sobre una única serie: aquí cada
> una de las 60 empresas tiene su propia escala en cada uno de los 16 orígenes,
> y para los objetivos con signo la escala depende de los ingresos de los
> últimos cuatro trimestres en cada origen. El $R^2$ se informa solo fuera de
> la muestra, frente al \emph{baseline} a superar
> \citep{campbell2008predicting}: el $R^2$ habitual, que compara con la media,
> alcanza 0{,}98 en los ingresos para un pronóstico estacional ingenuo, porque
> mide la diferencia de tamaño entre empresas y no la calidad del pronóstico.
