from collections.abc import Mapping
from pathlib import Path

import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, field_validator

from app.data.exceptions import BlockedTargetError


class IngestionDefects(BaseModel):
    """Companies and targets held back until their ingestion fix lands.

    Each entry names the spec of its fix; deleting the entry lifts it.

    Usage::

        defects = container.ingestion_defects()
        defects.require_selectable(TargetVariable.OPEX)
        panels = defects.without_excluded(panels)
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    excluded_companies: dict[str, str] = {}
    blocked_targets: dict[str, str] = {}

    @field_validator("excluded_companies")
    @classmethod
    def _upper_case_tickers(cls, excluded: dict[str, str]) -> dict[str, str]:
        return {ticker.upper(): spec for ticker, spec in excluded.items()}

    def require_selectable(self, variable: str) -> None:
        """Refuse a target variable an open ingestion defect blocks.

        Raises:
            BlockedTargetError: The variable is blocked, naming the fix's spec.
        """
        spec = self.blocked_targets.get(variable)
        if spec is not None:
            raise BlockedTargetError(variable=variable, spec=spec)

    def without_excluded(
        self, panels: Mapping[str, pd.DataFrame]
    ) -> dict[str, pd.DataFrame]:
        """Drop the companies an open ingestion defect excludes.

        Returns:
            The remaining panels, keyed as given.
        """
        return {
            ticker: panel
            for ticker, panel in panels.items()
            if ticker.upper() not in self.excluded_companies
        }


def load_ingestion_defects(path: Path) -> IngestionDefects:
    """Load the ingestion-defect registry.

    Returns:
        The registry; an empty file excludes and blocks nothing.
    """
    # An empty file parses to None, which means nothing is held back.
    return IngestionDefects.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    )
