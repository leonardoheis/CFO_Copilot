from typing import Final

import pandas as pd

from app.services.evaluation.exceptions import EvaluationLeakageError

# Known only once the target date has passed, so a model never predicts from them.
LABEL_COLUMNS: Final = ("y", "target_level")


def check_no_look_ahead(
    train: pd.DataFrame, test: pd.DataFrame, origin: pd.Timestamp
) -> None:
    """Refuse to hand a model rows that reach past the origin.

    ``train`` and ``test`` are the frames a model's ``fit`` and ``predict``
    receive. The rules are requirement R12 of
    ``docs/specs/nb02-evaluation-harness.md``: every training target is known
    by the origin, the test rows carry no label, and no test row forecasts from
    before a training target.

    Raises:
        EvaluationLeakageError: A rule is broken; the message names which.
    """
    late = int((train["target_date"] > origin).sum())
    if late:
        raise EvaluationLeakageError(
            origin=origin,
            reason=f"{late} training rows have a target date after the origin",
        )
    labels = ", ".join(column for column in LABEL_COLUMNS if column in test.columns)
    if labels:
        raise EvaluationLeakageError(
            origin=origin, reason=f"the test rows carry labels: {labels}"
        )
    early = int((test["origin_date"] < train["target_date"].max()).sum())
    if early:
        raise EvaluationLeakageError(
            origin=origin,
            reason=f"{early} test rows forecast from before a training target date",
        )
