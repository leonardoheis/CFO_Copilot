from enum import StrEnum
from typing import Annotated, Literal, NamedTuple, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.data.dates import QUARTERS_PER_YEAR
from app.settings import RANDOM_SEED

_STL_MINIMUM_CYCLES = 2


def _ordered_in_unit_interval(pair: tuple[float, float]) -> tuple[float, float]:
    lower, upper = pair
    if not 0.0 <= lower < upper <= 1.0:
        message = f"must satisfy 0 <= lower < upper <= 1, got {pair}"
        raise ValueError(message)
    return pair


QuantilePair = Annotated[tuple[float, float], AfterValidator(_ordered_in_unit_interval)]


class Direction(StrEnum):
    """Which way an outlier register entry departs from normal."""

    UP = "up"
    DOWN = "down"
    NON_POSITIVE = "non_positive"


class SeriesStatus(StrEnum):
    OK = "ok"
    INSUFFICIENT_DATA = "insufficient_data"
    CONSTANT = "constant"


class SeriesDiagnostics(BaseModel):
    """Everything NB01 records about one company's variable."""

    # Enum values, so the diagnostics frame and its parquet hold plain strings.
    model_config = ConfigDict(frozen=True, extra="forbid", use_enum_values=True)

    ticker: str
    variable: str
    n_obs: int
    status: SeriesStatus
    log_defined: bool
    d_levels: int | None = None
    d_log: int | None = None
    seasonal_strength: float | None = None
    trend_strength: float | None = None
    ljung_box_p: float | None = None
    box_cox_lambda: float | None = None
    coefficient_of_variation: float | None = None
    # Isolated interior quarters filled by linear interpolation before diagnosis.
    interpolated: int = 0


class MacroCorrelation(NamedTuple):
    """How closely one company's YoY growth tracks one macro series."""

    macro_column: str
    correlation: float


class CompanyMacroSensitivity(BaseModel):
    """One company's YoY growth correlation with every macro series."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    sector: str
    correlations: tuple[MacroCorrelation, ...]

    def as_table_row(self) -> dict[str, float | str]:
        """Flatten for a DataFrame: one column per macro series, then ``sector``.

        Returns:
            The correlations keyed by macro column, followed by the sector.
        """
        return {**dict(self.correlations), "sector": self.sector}


class DiagnosticsSettings(BaseModel):
    """Test levels and window sizes behind every series diagnosis."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    min_observations: int = 16
    significance: float = Field(default=0.05, gt=0.0, lt=1.0)
    seasonal_period: int = Field(default=QUARTERS_PER_YEAR, ge=2)
    ljung_box_lag: int = Field(default=8, ge=1)
    max_differencing_order: int = Field(default=2, ge=0)
    # Longest interior gap filled for diagnosis only; 0 fills nothing.
    max_interpolated_gap: int = Field(default=1, ge=0)
    # Window over which a transform's change size is compared with its level.
    variance_window: int = Field(default=8, ge=3)

    @model_validator(mode="after")
    def _floor_covers_two_seasonal_cycles(self) -> Self:
        if self.min_observations <= _STL_MINIMUM_CYCLES * self.seasonal_period:
            message = (
                f"min_observations {self.min_observations} must exceed two seasonal "
                f"cycles ({_STL_MINIMUM_CYCLES * self.seasonal_period}) for STL"
            )
            raise ValueError(message)
        return self


class RegimeSettings(BaseModel):
    """How companies are clustered into seasonality regimes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n_regimes: int = Field(default=3, ge=2)
    seed: int = RANDOM_SEED
    n_init: int = Field(default=10, ge=1)


class ProfileSettings(BaseModel):
    """How the automated profile is generated."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Pairwise scatter plots take the pooled-panel report from 2.9 MB to 40 MB.
    interactions: bool = False


class OutlierSettings(BaseModel):
    """How the outlier register judges a company's quarter-over-quarter changes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    z_threshold: float = Field(default=10.0, gt=0.0)
    hampel_window: int = Field(default=8, ge=3)
    # A calm window's MAD can be ~0; flooring it at this share of the company's
    # overall MAD keeps the Hampel score finite.
    hampel_mad_floor: float = Field(default=0.25, gt=0.0, le=1.0)
    # Fewer changes than two years give a median and MAD too unstable to judge by.
    min_changes: int = Field(default=8, ge=4)
    # P/E is stock price over EPS, and both are registered themselves; EPS near
    # zero (2 cents) makes it explode to five digits, repeating one event as noise.
    derived_columns: tuple[str, ...] = ("pe_ratio",)


class CorrelationSettings(BaseModel):
    """When a pair of columns counts as redundant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    redundancy_threshold: float = Field(default=0.85, gt=0.0, lt=1.0)


class FigureSettings(BaseModel):
    """How the EDA figures look and how much of each distribution they show."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    style: Literal["whitegrid", "white", "darkgrid", "ticks"] = "whitegrid"
    clip_quantiles: QuantilePair = (0.01, 0.99)
    top_series: int = Field(default=4, ge=1)


class SegmentSettings(BaseModel):
    """How the target's spread is summarised within a segment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spread_quantiles: QuantilePair = (0.25, 0.75)


class DecisionSettings(BaseModel):
    """The thresholds behind NB01's decision table (spec D3-D5)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Below 0.01 so the covid flag (0.009 for revenue) is not dropped: it
    # moves only three quarters, which an average over 81 quarters dilutes.
    mutual_information_floor: float = Field(default=0.005, ge=0.0)
    significance: float = Field(default=0.05, gt=0.0, lt=1.0)
    forecastable_share: float = Field(default=0.5, gt=0.0, le=1.0)
