from typing import Literal, NamedTuple, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

_STL_MINIMUM_CYCLES = 2


class SeriesDiagnostics(BaseModel):
    """Everything NB01 records about one company's variable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    variable: str
    n_obs: int
    status: Literal["ok", "insufficient_data", "constant"]
    log_defined: bool
    d_levels: int | None = None
    d_log: int | None = None
    seasonal_strength: float | None = None
    trend_strength: float | None = None
    ljung_box_p: float | None = None
    box_cox_lambda: float | None = None
    coefficient_of_variation: float | None = None


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
    seasonal_period: int = Field(default=4, ge=2)
    ljung_box_lag: int = Field(default=8, ge=1)
    max_differencing_order: int = Field(default=2, ge=0)

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
    seed: int = 42
    n_init: int = Field(default=10, ge=1)
