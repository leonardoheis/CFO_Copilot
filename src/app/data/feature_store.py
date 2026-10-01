from pathlib import Path

import pandas as pd


class FeatureStore:
    """Read and write one pooled feature parquet per target variable and horizon.

    ``variable`` is the target's panel column name, e.g. ``"ebitda_usd_m"``.

    Usage::

        store = container.feature_store()
        path = store.write(dataset, "revenue_usd_m", horizon)
        dataset = store.read("revenue_usd_m", horizon)
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def path_for(self, variable: str, horizon: int) -> Path:
        return self._directory / f"features_{variable}_h{horizon}.parquet"

    def write(self, dataset: pd.DataFrame, variable: str, horizon: int) -> Path:
        """Write one variable's dataset for one horizon, creating the directory.

        Returns:
            The written file.
        """
        path = self.path_for(variable, horizon)
        path.parent.mkdir(parents=True, exist_ok=True)
        dataset.to_parquet(path, index=False)
        return path

    def read(self, variable: str, horizon: int) -> pd.DataFrame:
        return pd.read_parquet(self.path_for(variable, horizon))
