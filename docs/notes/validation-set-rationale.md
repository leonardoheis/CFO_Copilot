# Why the harness has no validation set

Rationale for the thesis methods section (NB02 plan, step 17). Agreed
2026-11-02 while building the Protocol A splits
(`src/app/services/evaluation/splits.py`).

## Decision

- The harness gives every model the same two row sets per origin: `train`
  (target date on or before the origin) and `test` (the origin's rows). There
  is no third, validation split.
- Models with nothing to tune (seasonal naive, naive, drift, ARIMA, linear
  regression) train on all of `train`.
- Models that tune (LightGBM, LSTM; AutoGluon internally) carve a validation
  set out of `train` themselves: the latest *v* quarters, cut on
  `target_date`, never at random. After choosing their settings they refit on
  all of `train`.

## Argument

1. **A validation set exists to make a choice.** It selects what training
   cannot: hyperparameters, the number of boosting rounds, a variant. The
   baselines have no parameters; ARIMA and linear regression *estimate* theirs
   from the training rows, which is training, not tuning. With nothing to
   choose, a validation set has no job.
2. **The test set is already out of sample.** In a single train/test split,
   validation protects the test set from being tuned on. Here every model is
   refit at each of the 16 origins and scored only on quarters after that
   origin (rolling origin). As long as nothing is selected on those scores,
   the test results are honest without a validation set.
3. **In a time series it costs the most informative quarters.** A
   time-series validation set cannot be random; it must be the latest
   training quarters, or it leaks the future. Those are the quarters closest
   to the forecast. At the first test origin (2022-Q2, h = 1), a four-quarter
   validation set would hold back the targets 2021-Q3 to 2022-Q2, which is the
   2021–22 inflation surge: the regime the model is about to forecast. That is
   about 4 of the 64 quarters of history before the origin (≈ 6 %), but the
   most relevant 6 %. Under Protocol B with H = 8 it would be half of a new
   company's history.
4. **When a model must tune, nothing is lost.** It selects on the held-back
   quarters, then refits on all of `train` with the chosen settings, so the
   validation quarters inform the choice and still reach the final model.

Every model sees the same inputs (`train`) and is scored on the same rows
(`test`), so the comparison stays fair; how a model uses its training rows is
part of the model, as ARIMA's estimation is.

## A related caveat: selection on the test origins

Picking the best model on the same 16 test origins and then reporting its
score there is optimistic: the test set has served as a validation set. NB08
must either rely on the Diebold–Mariano test and the Model Confidence Set
against the baseline (master plan D22), or hold back a final set of origins
used for no choice. To decide in NB08's spec.

## Sources

| Claim | Source | Bib key |
|---|---|---|
| Rolling origin: each test point is forecast only from earlier data | Hyndman & Athanasopoulos, *Forecasting: Principles and Practice*, 3rd ed., §5.10, <https://otexts.com/fpp3/tscv.html> (checked 2026-11-02) | `hyndman2021fpp` |
| Training data estimates the parameters; test data is not used in fitting | Same book, §5.8, <https://otexts.com/fpp3/accuracy.html> (checked 2026-11-02) | `hyndman2021fpp` |
| Rolling origin as the reference design for out-of-sample evaluation | Tashman (2000), *International Journal of Forecasting* 16(4), 437–450 | `tashman2000outofsample` |
| Cross-validation and validation sets for time series | Bergmeir & Benítez (2012), *Information Sciences* 191, 192–213; Bergmeir, Hyndman & Koo (2018), *CSDA* 120, 70–83 | `bergmeir2012cv`, `bergmeir2018note` |
| Time series cannot be split at random | scikit-learn User Guide §3.1.2.6, <https://scikit-learn.org/stable/modules/cross_validation.html> (checked 2026-11-02) | `pedregosa2011scikit` |
| A validation set costs training data: three sets "drastically reduce the number of samples which can be used for learning the model" | scikit-learn User Guide §3.1 (same page) | `pedregosa2011scikit` |
| After tuning, the best settings build the final estimator "on the whole dataset" | scikit-learn User Guide §3.2, <https://scikit-learn.org/stable/modules/grid_search.html> (checked 2026-11-02) | `pedregosa2011scikit` |
| Selecting a model on the evaluation data inflates its score | Cawley & Talbot (2010), *JMLR* 11, 2079–2107; Varma & Simon (2006), *BMC Bioinformatics* 7:91 | `cawley2010overfitting`, `varma2006bias` |

Bib keys refer to the thesis repo's `references.bib`
(`cfo-copilot-thesis/references.bib`). The scikit-learn rows cite the
software paper; quote the User Guide by URL in a footnote.

Point 3 is this project's own inference from two sourced facts (a
time-series validation set must be the latest data; a validation set removes
training data). The 2022-Q2 example and the ≈ 6 % are computed from our panel
(2006-Q2 → 2026-Q2), not quoted. Present them as the author's argument.

## Paragraph for `main.tex`

> Los modelos sin hiperparámetros (los *baselines*, ARIMA y la regresión
> lineal) se entrenan con todas las filas disponibles en cada origen, sin
> conjunto de validación: no tienen nada que seleccionar, y el diseño de
> origen móvil ya mantiene fuera de la muestra los trimestres de prueba
> \cite{hyndman2021fpp,tashman2000outofsample}. En una serie temporal, la
> validación debe estar formada por los trimestres de entrenamiento más
> recientes, de modo que reservarla retiraría justamente las observaciones
> más cercanas al pronóstico: en el primer origen de prueba (2022-T2), una
> validación de cuatro trimestres ocultaría al modelo el alza inflacionaria
> de 2021--22, el régimen que está por pronosticar. Los modelos que sí se
> ajustan (LightGBM, LSTM) eligen su configuración sobre los últimos
> trimestres de entrenamiento y luego se reentrenan con todas las filas de
> entrenamiento, de manera que los datos de validación informan la elección
> sin perderse para el modelo final.
