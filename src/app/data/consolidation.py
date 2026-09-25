from collections.abc import Mapping
from typing import Final, NamedTuple

import pandas as pd

from app.data.exceptions import ConsolidationError, MacroMismatchError
from app.data.schema import MACRO_COLUMNS

DROPPED_CONSTANT_COLUMNS: Final = ("is_public",)
_MACRO_FRAME_COLUMNS: Final = ["date", *MACRO_COLUMNS]


class ConsolidatedPanels(NamedTuple):
    panel_long: pd.DataFrame
    macro_q: pd.DataFrame


def _shared_macro(panels: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    reference_ticker, reference = next(iter(panels.items()))
    reference_macro = reference[_MACRO_FRAME_COLUMNS].reset_index(drop=True)
    differing = [
        ticker
        for ticker, panel in panels.items()
        if not panel[_MACRO_FRAME_COLUMNS]
        .reset_index(drop=True)
        .equals(reference_macro)
    ]
    if differing:
        differing_list = ", ".join(differing)
        message = f"macro block differs from {reference_ticker} for: {differing_list}"
        raise MacroMismatchError(message)
    return reference_macro


def _require_constant(panel: pd.DataFrame, columns: tuple[str, ...]) -> None:
    varying = [
        column for column in columns if panel[column].ne(panel[column].iloc[0]).any()
    ]
    if varying:
        varying_list = ", ".join(varying)
        message = f"refusing to drop columns that vary: {varying_list}"
        raise ConsolidationError(message)


def consolidate_panels(panels: Mapping[str, pd.DataFrame]) -> ConsolidatedPanels:
    """Stack the per-company panels and split the shared macro block out.

    Returns:
        ``panel_long`` sorted by ticker and date without macro or constant
        columns, and ``macro_q`` with one row per quarter.

    Raises:
        ConsolidationError: There are no panels.
    """
    if not panels:
        message = "no panels to consolidate"
        raise ConsolidationError(message)
    macro_q = _shared_macro(panels)
    stacked = pd.concat(panels.values(), ignore_index=True)
    _require_constant(stacked, DROPPED_CONSTANT_COLUMNS)
    panel_long = stacked.drop(columns=[*MACRO_COLUMNS, *DROPPED_CONSTANT_COLUMNS])
    return ConsolidatedPanels(
        panel_long=panel_long.sort_values(["ticker", "date"], ignore_index=True),
        macro_q=macro_q,
    )
