from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.services.tracking.exceptions import InvalidRunNameError

Protocol = Literal["A", "B"]


def run_name(
    *,
    notebook: str,
    model: str,
    variable: str,
    protocol: Protocol | None = None,
    history_len: int | None = None,
) -> str:
    """Build the W&B run name of master plan §2.3.

    Returns:
        ``{notebook}-{model}-{variable}[-{protocol}[-H{history_len}]]``.

    Raises:
        InvalidRunNameError: ``history_len`` is given without protocol B.
    """
    if history_len is not None and protocol != "B":
        message = "history_len only applies to protocol B"
        raise InvalidRunNameError(message)
    parts = [notebook, model, variable.removesuffix("_usd_m")]
    if protocol is not None:
        parts.append(protocol)
    if history_len is not None:
        parts.append(f"H{history_len}")
    return "-".join(parts)


class RunConfig(BaseModel):
    """The config logged on every run so results stay comparable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    panel_size: int
    n_rows: int
    target_variable: str | None = None
    target_transform: str | None = None
    feature_groups: tuple[str, ...] = ()
    n_features: int | None = None
    protocol: Protocol | None = None
    history_len: int | None = None
    horizon: int | None = None
    macro_source: Literal["final_revised", "point_in_time"] = "final_revised"
    harness_version: str | None = None
    seed: int = 42


class WandbSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project: str
    entity: str | None
    mode: Literal["online", "offline", "disabled"]
    api_key: str
    run_directory: Path
