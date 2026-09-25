from datetime import date
from pathlib import Path
from typing import Annotated

import pandas as pd
import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict


def _require_quarter_ends(
    breaks: dict[str, tuple[date, ...]],
) -> dict[str, tuple[date, ...]]:
    off_calendar = [
        f"{ticker} {quarter}"
        for ticker, quarters in breaks.items()
        for quarter in quarters
        if not pd.Timestamp(quarter).is_quarter_end
    ]
    if off_calendar:
        message = f"not a calendar quarter end: {', '.join(off_calendar)}"
        raise ValueError(message)
    return breaks


_QuarterEndBreaks = Annotated[
    dict[str, tuple[date, ...]], AfterValidator(_require_quarter_ends)
]


class _BreaksConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    breaks: _QuarterEndBreaks


def load_structural_breaks(path: Path) -> dict[str, tuple[date, ...]]:
    """Load the hand-entered break quarters.

    Returns:
        Sorted break quarters keyed by upper-case ticker.
    """
    config = _BreaksConfig.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    return {
        ticker.upper(): tuple(sorted(quarters))
        for ticker, quarters in config.breaks.items()
    }
