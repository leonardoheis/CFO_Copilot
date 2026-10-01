from collections.abc import Generator, Mapping
from contextlib import contextmanager

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib.figure import Figure

from app.services.diagnostics.audit import OutlierRegister
from app.services.diagnostics.models import FigureSettings


class EdaFigures:
    """Build the EDA's figures; the notebook only calls, shows and logs them.

    Each method returns a matplotlib ``Figure`` and styles it locally, so no
    global plotting state changes behind the caller.

    Usage::

        figures = container.eda_figures()
        run.log_figure("register_counts", figures.register_counts(register))
    """

    def __init__(
        self, settings: FigureSettings, outlier_register: OutlierRegister
    ) -> None:
        self._settings = settings
        self._outlier_register = outlier_register

    @contextmanager
    def _styled(self) -> Generator[None]:
        with sns.axes_style(self._settings.style):
            yield

    def _clipped_long(self, changes: pd.DataFrame) -> pd.DataFrame:
        # Clipped per column so one extreme quarter cannot flatten a panel.
        lower, upper = self._settings.clip_quantiles
        clipped = changes.clip(changes.quantile(lower), changes.quantile(upper), axis=1)
        return clipped.melt(var_name="column", value_name="yoy_change").dropna()

    def register_counts(self, register: pd.DataFrame) -> Figure:
        with self._styled():
            figure, axes = plt.subplots(figsize=(10, 5))
            sns.countplot(
                register,
                y="column",
                hue="direction",
                order=register["column"].value_counts().index,
                ax=axes,
            )
            axes.set(
                title="Outlier register: entries per column and direction",
                xlabel="entries",
                ylabel="",
            )
            figure.tight_layout()
        return figure

    def top_series_scores(
        self, register: pd.DataFrame, panels: Mapping[str, pd.DataFrame]
    ) -> Figure:
        """Plot the most extreme company-columns: level, and distance from normal.

        Returns:
            One row per series; a spike above the threshold put it in the register.
        """
        top = register.drop_duplicates(["ticker", "column"]).head(
            self._settings.top_series
        )
        pairs = zip(top["ticker"].astype(str), top["column"].astype(str), strict=True)
        with self._styled():
            figure, grid = plt.subplots(
                max(len(top), 1), 2, figsize=(13, 3.2 * max(len(top), 1)), squeeze=False
            )
            for row, (ticker, column) in enumerate(pairs):
                scores = self._outlier_register.scores_for(panels[ticker], column)
                level_axes, score_axes = grid[row]
                level_axes.plot(scores["date"], scores["value"], color="steelblue")
                level_axes.set_title(f"{ticker} {column}: level")
                score_axes.plot(
                    scores["date"],
                    scores["robust_z"].abs(),
                    color="green",
                    label="robust z (whole history)",
                )
                score_axes.plot(
                    scores["date"],
                    scores["hampel_z"].abs(),
                    color="purple",
                    alpha=0.8,
                    label="Hampel z (8-quarter window)",
                )
                score_axes.axhline(
                    self._outlier_register.z_threshold,
                    color="red",
                    linestyle="--",
                    label="threshold",
                )
                score_axes.set_yscale("symlog", linthresh=1)
                score_axes.set_ylim(bottom=0)
                score_axes.set_title(f"{ticker} {column}: distance from normal")
            grid[0, 1].legend(fontsize=7, loc="upper right")
            figure.tight_layout()
        return figure

    def target_distribution(self, target_frame: pd.DataFrame, *, title: str) -> Figure:
        lower, upper = target_frame["y"].quantile(list(self._settings.clip_quantiles))
        with self._styled():
            grid = sns.displot(
                target_frame[target_frame["y"].between(lower, upper)],
                x="y",
                row="arm",
                col="horizon",
                kde=True,
                bins=50,
                height=2.2,
                aspect=1.4,
                facet_kws={"sharex": False, "sharey": False},
            )
            grid.figure.suptitle(
                f"{title}: target per arm and horizon (1st-99th percentile)", y=1.02
            )
        return grid.figure

    def change_distributions(self, changes: pd.DataFrame) -> Figure:
        with self._styled():
            grid = sns.displot(
                self._clipped_long(changes),
                x="yoy_change",
                col="column",
                col_wrap=4,
                kde=True,
                bins=40,
                height=2.2,
                aspect=1.4,
                facet_kws={"sharex": False, "sharey": False},
            )
            grid.figure.suptitle(
                "Year-over-year change per column (1st-99th percentile)", y=1.02
            )
        return grid.figure

    def change_boxplots(self, changes: pd.DataFrame) -> Figure:
        clipped = self._clipped_long(changes)
        columns = list(dict.fromkeys(clipped["column"]))
        with self._styled():
            # One panel per column: the columns' units differ (EPS in dollars,
            # the rest as shares of revenue), so a shared axis would hide most.
            figure, panels = plt.subplots(
                len(columns), 1, figsize=(10, 0.6 * len(columns) + 0.8), squeeze=False
            )
            for axes, column in zip(panels[:, 0], columns, strict=True):
                # Drawn with matplotlib directly: seaborn 0.13's boxplot still
                # passes matplotlib 3.10 the deprecated ``vert`` argument.
                axes.boxplot(
                    clipped.loc[clipped["column"] == column, "yoy_change"],
                    orientation="horizontal",
                    tick_labels=[column],
                    patch_artist=True,
                    boxprops={"facecolor": "lightcoral"},
                    widths=0.6,
                )
            panels[0, 0].set_title("Spread and outliers of each column's change")
            figure.tight_layout()
        return figure

    def categories(self, company_sectors: pd.Series, regimes: pd.Series) -> Figure:
        with self._styled():
            figure, (sector_axes, regime_axes) = plt.subplots(1, 2, figsize=(13, 4))
            sns.countplot(
                y=company_sectors,
                order=company_sectors.value_counts().index,
                color="steelblue",
                ax=sector_axes,
            )
            sector_axes.set(title="Companies per sector", xlabel="companies", ylabel="")
            sns.countplot(x=regimes, color="seagreen", ax=regime_axes)
            regime_axes.set(
                title="Companies per seasonality regime (0 = least seasonal)",
                xlabel="regime",
                ylabel="companies",
            )
            figure.tight_layout()
        return figure

    def _heatmap(self, table: pd.DataFrame, *, title: str, size: float) -> Figure:
        with self._styled():
            figure, axes = plt.subplots(figsize=(size, size * 0.85))
            sns.heatmap(
                table,
                annot=True,
                fmt=".2f",
                cmap="coolwarm",
                center=0,
                vmin=-1,
                vmax=1,
                linewidths=0.5,
                annot_kws={"size": 6},
                ax=axes,
            )
            axes.set_title(title)
            figure.tight_layout()
        return figure

    def correlation_heatmap(self, matrix: pd.DataFrame) -> Figure:
        return self._heatmap(
            matrix, title="Spearman correlation of year-over-year changes", size=14
        )

    def sector_sensitivity(self, table: pd.DataFrame) -> Figure:
        return self._heatmap(
            table, title="YoY growth vs macro: mean correlation by sector", size=11
        )

    def seasonal_strength(self, diagnostics: pd.DataFrame) -> Figure:
        with self._styled():
            figure, axes = plt.subplots(figsize=(8, 4))
            sns.histplot(diagnostics, x="seasonal_strength", bins=20, ax=axes)
            axes.set(
                title="Seasonal strength (STL, period 4)",
                xlabel="seasonal strength",
                ylabel="companies",
            )
            figure.tight_layout()
        return figure

    def segment_boxplots(self, frame: pd.DataFrame, segments: list[str]) -> Figure:
        lower, upper = frame["y"].quantile(list(self._settings.clip_quantiles))
        clipped = frame[frame["y"].between(lower, upper)]
        with self._styled():
            figure, panels = plt.subplots(
                1, len(segments), figsize=(5 * len(segments), 5), squeeze=False
            )
            for axes, segment in zip(panels[0], segments, strict=True):
                values = sorted(clipped[segment].dropna().unique(), key=str)
                # matplotlib directly: seaborn 0.13 passes a deprecated ``vert``.
                axes.boxplot(
                    [clipped.loc[clipped[segment] == value, "y"] for value in values],
                    orientation="horizontal",
                    tick_labels=[str(value) for value in values],
                    patch_artist=True,
                    boxprops={"facecolor": "lightsteelblue"},
                )
                axes.set(title=f"Target by {segment}", xlabel="target")
            figure.tight_layout()
        return figure

    def seasonal_profile(self, profile: pd.DataFrame) -> Figure:
        with self._styled():
            figure, axes = plt.subplots(figsize=(8, 4))
            sns.lineplot(
                profile,
                x="target_quarter",
                y="mean_y",
                hue="regime",
                marker="o",
                ax=axes,
            )
            axes.set(
                title="Mean target by forecast quarter, per regime",
                xlabel="calendar quarter forecast",
                ylabel="mean target",
                xticks=[1, 2, 3, 4],
            )
            figure.tight_layout()
        return figure

    def median_timeline(self, timeline: pd.DataFrame) -> Figure:
        with self._styled():
            figure, axes = plt.subplots(figsize=(12, 4))
            axes.plot(timeline["date"], timeline["median_y"], color="steelblue")
            for date in timeline.loc[timeline["covid"], "date"]:
                axes.axvspan(
                    date - pd.offsets.QuarterEnd(1), date, color="orange", alpha=0.25
                )
            for date in timeline.loc[timeline["breaks"] > 0, "date"]:
                axes.axvline(date, color="grey", linestyle=":", linewidth=1)
            axes.axhline(0, color="black", linewidth=0.5)
            axes.set(
                title="Panel-median target (covid shaded, breaks marked)",
                ylabel="median target",
            )
            figure.tight_layout()
        return figure

    def feature_ranking(self, features: pd.DataFrame) -> Figure:
        scored = features.dropna(subset=["mutual_information"])
        with self._styled():
            figure, axes = plt.subplots(figsize=(10, 0.25 * len(scored) + 1.5))
            sns.barplot(
                scored,
                x="mutual_information",
                y="feature",
                hue="group",
                dodge=False,
                ax=axes,
            )
            axes.set(
                title="Mutual information with the target, per feature",
                xlabel="mutual information (nats)",
                ylabel="",
            )
            figure.tight_layout()
        return figure
