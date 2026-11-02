from dataclasses import dataclass


class FeatureError(Exception):
    """Base error for feature engineering."""


@dataclass
class NonPositiveValueError(FeatureError):
    """Raised when a log transform meets zero or negative values."""

    count: int

    def __str__(self) -> str:
        return f"log is undefined for {self.count} non-positive values"


@dataclass
class InvalidHorizonError(FeatureError):
    """Raised for a horizon outside 1 to ``max_horizon``."""

    horizon: int
    max_horizon: int

    def __str__(self) -> str:
        return f"horizon must be 1 to {self.max_horizon}, got {self.horizon}"


@dataclass
class MissingFlagsError(FeatureError):
    """Raised when group F is requested without the NB00 flag columns."""

    columns: tuple[str, ...]

    def __str__(self) -> str:
        return f"group F needs the NB00 flag columns: {', '.join(self.columns)}"


@dataclass
class MissingRegimeError(FeatureError):
    """Raised when group S is requested without a seasonality regime."""

    ticker: str

    def __str__(self) -> str:
        return f"no seasonality regime for {self.ticker}; run the EDA regimes first"


@dataclass
class MixedTickerPanelError(FeatureError):
    """Raised when a panel holds more than one company, or none."""

    tickers: tuple[str, ...]

    def __str__(self) -> str:
        return (
            "features take one company's panel at a time, got: "
            f"{', '.join(self.tickers)}"
        )


@dataclass
class LeakageError(FeatureError):
    """Raised when a feature changes after only later quarters changed."""

    origin: int
    columns: tuple[str, ...]

    def __str__(self) -> str:
        return (
            f"features at origin row {self.origin} changed with later quarters: "
            f"{', '.join(self.columns)}"
        )


@dataclass
class MissingRevenueError(FeatureError):
    """Raised when a revenue-scaled arm is used without the revenue series."""

    arm: str

    def __str__(self) -> str:
        return f"the {self.arm} arm divides by trailing revenue; pass revenue="


@dataclass
class UnsupportedArmError(FeatureError):
    """Raised when a target arm is used on a variable it does not belong to."""

    variable: str
    arm: str
    supported: tuple[str, ...]

    def __str__(self) -> str:
        return (
            f"{self.variable} cannot use the {self.arm} arm; "
            f"use one of: {', '.join(self.supported)}"
        )
