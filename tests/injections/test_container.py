import pandas as pd

from app.data import FeatureStore, IngestionDefects
from app.injections import Container
from app.services.diagnostics import (
    DecisionTableBuilder,
    DiagnosticsService,
    FeatureAuditor,
)
from app.services.features import (
    FeatureGroup,
    FeatureService,
    FeatureSpec,
    TargetArm,
)
from app.settings import Settings
from tests.conftest import PanelFactory

KEYS = ["ticker", "origin_date", "target_date"]
TARGET_COLUMNS = ["target_level", "y"]


def test_services_resolve_to_their_types() -> None:
    container = Container()

    assert isinstance(container.diagnostics_service(), DiagnosticsService)
    assert isinstance(container.feature_service(), FeatureService)
    assert isinstance(container.feature_store(), FeatureStore)
    assert isinstance(container.feature_auditor(), FeatureAuditor)
    assert isinstance(container.decision_table_builder(), DecisionTableBuilder)


def test_feature_store_lives_under_the_data_directory() -> None:
    store = Container().feature_store()

    assert (
        store.path_for("revenue_usd_m", 1)
        == Settings.DATA_DIRECTORY / "features" / "features_revenue_usd_m_h1.parquet"
    )


def test_a_spec_override_builds_only_the_requested_groups(
    make_panel: PanelFactory,
) -> None:
    lags_only = FeatureSpec(groups=frozenset({FeatureGroup.LAGS}))
    service = Container().feature_service(builder__spec=lags_only)

    dataset = service.assemble(
        {"AAA": make_panel(ticker="AAA")}, horizon=1, arm=TargetArm.LOG_DIFF1
    )

    lag_columns = [
        column for column in dataset.columns if column not in KEYS + TARGET_COLUMNS
    ]
    assert lag_columns
    assert all(column.startswith("growth_yoy_lag") for column in lag_columns)


def test_the_default_feature_service_builds_every_group(
    make_panel: PanelFactory,
) -> None:
    panel = make_panel(ticker="AAA").assign(covid=False, structural_break=False)

    dataset = (
        Container()
        .feature_service()
        .assemble(
            {"AAA": panel},
            horizon=1,
            arm=TargetArm.LOG_DIFF1,
            regimes=pd.Series({"AAA": 0}),
        )
    )

    assert {"growth_yoy_lag1", "real_rate", "sector", "covid"} <= set(dataset.columns)


def test_ingestion_defects_load_from_the_project_registry() -> None:
    defects = Container().ingestion_defects()

    assert isinstance(defects, IngestionDefects)
    assert "COP" in defects.excluded_companies
