import math
from pathlib import Path

import pandas as pd

from app.data import FeatureStore


def _dataset() -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": ["AAA", "BBB"],
        "sector": pd.Categorical(["Technology", "Energy"]),
        "y": [0.1, math.nan],
    })


def test_path_is_one_file_per_variable_and_horizon(tmp_path: Path) -> None:
    store = FeatureStore(directory=tmp_path / "features")

    assert (
        store.path_for("ebitda_usd_m", 3)
        == tmp_path / "features" / "features_ebitda_usd_m_h3.parquet"
    )


def test_construction_creates_no_directory(tmp_path: Path) -> None:
    FeatureStore(directory=tmp_path / "features")

    assert not (tmp_path / "features").exists()


def test_written_dataset_reads_back_equal(tmp_path: Path) -> None:
    store = FeatureStore(directory=tmp_path / "features")
    dataset = _dataset()

    path = store.write(dataset, "revenue_usd_m", 2)

    assert path == store.path_for("revenue_usd_m", 2)
    pd.testing.assert_frame_equal(store.read("revenue_usd_m", 2), dataset)


def test_two_variables_do_not_overwrite_each_other(tmp_path: Path) -> None:
    store = FeatureStore(directory=tmp_path / "features")
    revenue = _dataset()
    ebitda = _dataset().assign(y=[0.5, 0.25])

    store.write(revenue, "revenue_usd_m", 1)
    store.write(ebitda, "ebitda_usd_m", 1)

    pd.testing.assert_frame_equal(store.read("revenue_usd_m", 1), revenue)
    pd.testing.assert_frame_equal(store.read("ebitda_usd_m", 1), ebitda)
