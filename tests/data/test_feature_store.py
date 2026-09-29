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


def test_path_is_one_file_per_horizon(tmp_path: Path) -> None:
    store = FeatureStore(directory=tmp_path / "features")

    assert store.path_for(3) == tmp_path / "features" / "features_h3.parquet"


def test_construction_creates_no_directory(tmp_path: Path) -> None:
    FeatureStore(directory=tmp_path / "features")

    assert not (tmp_path / "features").exists()


def test_written_dataset_reads_back_equal(tmp_path: Path) -> None:
    store = FeatureStore(directory=tmp_path / "features")
    dataset = _dataset()

    path = store.write(dataset, 2)

    assert path == store.path_for(2)
    pd.testing.assert_frame_equal(store.read(2), dataset)
