from pathlib import Path

import pandas as pd


class FeatureStore:
    """Read and write one pooled feature parquet per forecast horizon.

    Usage::

        store = container.feature_store()
        path = store.write(dataset, horizon)
        dataset = store.read(horizon)
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def path_for(self, horizon: int) -> Path:
        return self._directory / f"features_h{horizon}.parquet"

    def write(self, dataset: pd.DataFrame, horizon: int) -> Path:
        """Write one horizon's dataset, creating the directory on first write.

        Returns:
            The written file.
        """
        path = self.path_for(horizon)
        path.parent.mkdir(parents=True, exist_ok=True)
        dataset.to_parquet(path, index=False)
        return path

    def read(self, horizon: int) -> pd.DataFrame:
        return pd.read_parquet(self.path_for(horizon))
