import pytest
from pydantic import ValidationError

from app.services.tracking import InvalidRunNameError, RunConfig, run_name


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            {"notebook": "nb01", "model": "eda", "variable": "revenue_usd_m"},
            "nb01-eda-revenue",
        ),
        (
            {
                "notebook": "nb04",
                "model": "lgbm_resid",
                "variable": "revenue_usd_m",
                "protocol": "A",
            },
            "nb04-lgbm_resid-revenue-A",
        ),
        (
            {
                "notebook": "nb04",
                "model": "lgbm_resid",
                "variable": "revenue_usd_m",
                "protocol": "B",
                "history_len": 12,
            },
            "nb04-lgbm_resid-revenue-B-H12",
        ),
    ],
)
def test_run_name_follows_master_plan(kwargs: dict[str, str], expected: str) -> None:
    assert run_name(**kwargs) == expected  # type: ignore[arg-type]  # parametrized kwargs


def test_history_length_needs_protocol_b() -> None:
    with pytest.raises(InvalidRunNameError):
        run_name(
            notebook="nb04",
            model="m",
            variable="revenue_usd_m",
            protocol="A",
            history_len=8,
        )


def test_run_config_dumps_master_plan_keys() -> None:
    config = RunConfig(panel_size=60, n_rows=4860, target_variable="revenue_usd_m")

    assert config.model_dump(mode="json") == {
        "panel_size": 60,
        "n_rows": 4860,
        "target_variable": "revenue_usd_m",
        "target_transform": None,
        "feature_groups": [],
        "n_features": None,
        "protocol": None,
        "history_len": None,
        "horizon": None,
        "macro_source": "final_revised",
        "harness_version": None,
        "seed": 42,
    }


def test_run_config_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        RunConfig(panel_size=1, n_rows=1, target_variable="x", surprise=1)  # type: ignore[call-arg]  # the point of the test
