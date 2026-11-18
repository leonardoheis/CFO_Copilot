from typing import Final

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib.figure import Figure

_STYLE: Final = "whitegrid"


def mae_by_sector_figure(by_sector: pd.DataFrame, *, title: str) -> Figure:
    """One heatmap per baseline: MAE by sector and horizon, on one colour scale.

    ``by_sector`` holds ``baseline, sector, horizon, mae`` for one target.

    Returns:
        The figure, one panel per baseline in the order they appear.
    """
    baselines = list(dict.fromkeys(by_sector["baseline"]))
    with sns.axes_style(_STYLE):
        figure, axes = plt.subplots(
            1,
            len(baselines),
            figsize=(4 * len(baselines), 5),
            sharey=True,
            squeeze=False,
        )
        for panel, baseline in zip(axes[0], baselines, strict=True):
            table = by_sector[by_sector["baseline"] == baseline].pivot_table(
                index="sector", columns="horizon", values="mae"
            )
            sns.heatmap(
                table,
                annot=True,
                fmt=".3f",
                cmap="viridis",
                vmin=by_sector["mae"].min(),
                vmax=by_sector["mae"].max(),
                cbar=False,
                ax=panel,
            )
            panel.set(title=baseline, xlabel="horizon", ylabel="")
        figure.suptitle(title)
        figure.set_layout_engine("tight")
    return figure


def coverage_reliability_figure(pooled: pd.DataFrame, *, title: str) -> Figure:
    """Empirical coverage at each nominal level, one point per run of a baseline.

    ``pooled`` holds ``baseline, level, coverage``; a dashed line marks each
    nominal level, so a point above it over-covers.

    Returns:
        The figure.
    """
    levels = sorted(pooled["level"].unique())
    with sns.axes_style(_STYLE):
        figure, axes = plt.subplots(figsize=(7, 5))
        sns.stripplot(
            pooled, x="level", y="coverage", hue="baseline", dodge=True, ax=axes
        )
        for position, level in enumerate(levels):
            axes.hlines(
                level, position - 0.4, position + 0.4, colors="grey", linestyles="--"
            )
        axes.set(title=title, xlabel="nominal level", ylabel="empirical coverage")
        figure.set_layout_engine("tight")
    return figure


def error_by_history_figure(pooled: pd.DataFrame, *, title: str) -> Figure:
    """Protocol B MAE against the quarters of history, one panel per horizon.

    ``pooled`` holds ``baseline, horizon, history, mae``, with the histories
    in the order they should read, shortest first.

    Returns:
        The figure.
    """
    horizons = sorted(pooled["horizon"].unique())
    with sns.axes_style(_STYLE):
        figure, axes = plt.subplots(
            1, len(horizons), figsize=(4 * len(horizons), 4), sharey=True, squeeze=False
        )
        for panel, horizon in zip(axes[0], horizons, strict=True):
            sns.lineplot(
                pooled[pooled["horizon"] == horizon],
                x="history",
                y="mae",
                hue="baseline",
                marker="o",
                sort=False,
                legend=horizon == horizons[-1],
                ax=panel,
            )
            panel.set(
                title=f"h = {horizon}", xlabel="quarters of history", ylabel="MAE"
            )
        figure.suptitle(title)
        figure.set_layout_engine("tight")
    return figure
