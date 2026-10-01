from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from app.data import BlockedTargetError, IngestionDefects, load_ingestion_defects
from app.settings import Settings

SPEC = "docs/specs/ingestion-defects-cop-ge.md"


def _defects() -> IngestionDefects:
    return IngestionDefects(
        excluded_companies={"COP": SPEC}, blocked_targets={"opex_usd_m": SPEC}
    )


def test_a_blocked_target_is_refused_naming_its_spec() -> None:
    with pytest.raises(BlockedTargetError, match="ingestion-defects-cop-ge") as caught:
        _defects().require_selectable("opex_usd_m")

    assert caught.value.variable == "opex_usd_m"
    assert caught.value.spec == SPEC


def test_an_unblocked_target_passes() -> None:
    _defects().require_selectable("revenue_usd_m")


def test_excluded_companies_are_dropped_from_the_panels() -> None:
    panels = {"AAPL": pd.DataFrame(), "COP": pd.DataFrame()}

    assert set(_defects().without_excluded(panels)) == {"AAPL"}


def test_an_empty_registry_blocks_and_excludes_nothing() -> None:
    defects = IngestionDefects()
    panels = {"COP": pd.DataFrame()}

    defects.require_selectable("opex_usd_m")

    assert set(defects.without_excluded(panels)) == {"COP"}


def test_tickers_are_matched_in_upper_case() -> None:
    defects = IngestionDefects(excluded_companies={"cop": SPEC})

    assert defects.excluded_companies == {"COP": SPEC}


def test_unknown_keys_are_refused() -> None:
    with pytest.raises(ValidationError):
        IngestionDefects.model_validate({"blocked_companies": {}})


def test_registry_loads_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "defects.yaml"
    path.write_text(f"excluded_companies:\n  COP: {SPEC}\n", encoding="utf-8")

    assert load_ingestion_defects(path) == IngestionDefects(
        excluded_companies={"COP": SPEC}
    )


def test_the_project_registry_excludes_cop_and_blocks_opex() -> None:
    defects = load_ingestion_defects(Settings.INGESTION_DEFECTS_PATH)

    assert "COP" in defects.excluded_companies
    assert "opex_usd_m" in defects.blocked_targets


def test_an_empty_registry_file_blocks_nothing(tmp_path: Path) -> None:
    path = tmp_path / "defects.yaml"
    path.write_text("# nothing held back\n", encoding="utf-8")

    assert load_ingestion_defects(path) == IngestionDefects()


def test_a_registry_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "defects.yaml"
    path.write_text("- COP\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        load_ingestion_defects(path)
