# Template scaffold replacement (deferred)

Deferred to the next development wave. These items come from the
[code-smells remediation plan](code-smells-remediation.md) (its "Dormant
scaffold" section), and the item numbers are the same. All of them sit in
template code from the FastAPI scaffold that the forecasting work does not use.
Fixing them before their trigger fires would mean redesigning code that is
about to be replaced.

Last checked 2026-10-26: no trigger has fired. There is no NB09, no `Forecast`
or `Forecaster` type, and no real Streamlit page or API route.

None of these changes stored parquets or notebook outputs, so none needs a
notebook rerun.

## Do first if the API is deployed before NB09

`.github/workflows/deploy.yml` deploys from `master` to Render, and
`train_router` is still registered in `api/routes/registry.py`. A public
deployment exposes `POST /prediction/train`, which overwrites the model file
on the server. Before any deployment is used, unregister `train_router` from
`ROUTERS` and delete its route test. That change can ship on its own, ahead
of the rest of this plan.

## Items

| # | Smell | Where | Trigger |
|---|---|---|---|
| 1 | Template product vertical: machine age and time-to-failure types, and the "FastAPI Production Template" title | `api/app.py` (`create_app`), `api/routes/prediction/`, `api/routes/train/`, `domain/prediction_*.py`, `services/prediction/`, `services/training/` | NB09, when real `Forecast` and `Forecaster` types exist |
| 4 | Model loaded from disk twice per prediction | `services/prediction/service.py` (`load_model` call) | Disappears with #1 |
| 29 | Train schema raises a service exception | `api/routes/train/schemas.py` | Disappears with #1 |
| 30 | Services modelled as Pydantic `BaseModel` | `services/prediction/service.py`, `services/training/service.py` | Disappears with #1; write the NB09 service as a plain class from the start |
| 3 (part) | `MODEL_DIRECTORY` creates its directory whenever it is read | `settings.py` (`MODEL_DIRECTORY`) | With #1: move the `mkdir` into the writer when the template `save_model` is replaced |
| 11 | One container for the API and the research providers | `injections/production.py` (`Container`) | The first real API service (NB09); only the research and ingestion halves are real today |
| 33 | Template dead code: `create_examples` (`utils/exampler.py`), `ExamplerMixIn` on `BaseEntity`, the empty `TestContainer` (`injections/test.py`) and its override in `tests/conftest.py`, the Streamlit test page and its registry entry, the health page's "Prediction:" label and hardcoded URL, unused `UI_HOST`, `API_HOST` and `SOCKET_URL` in `settings.py` | as listed | The first real Streamlit page or API route |

## Steps when the trigger fires

1. Write the NB09 forecasting spec in `docs/specs/` first: the `Forecast` and
   `Forecaster` contract and the API request and response.
2. Replace the #1 vertical in one slice: new domain types, service, routes and
   tests, then delete the template files. #4, #29, #30 and #3 (part) go with
   it.
3. Split the container (#11) once there is a real API service to put on the
   API side.
4. Delete the #33 dead code that the new routes and pages leave unused.
5. Update `CLAUDE.md` and `AGENTS.md` (directory tree and endpoint table),
   then run `uv run poe check`.
