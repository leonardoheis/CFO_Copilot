import pytest

from app.services.features import (
    FeatureError,
    InvalidHorizonError,
    LeakageError,
    MissingFlagsError,
    MissingRegimeError,
    MixedTickerPanelError,
    NonPositiveValueError,
)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (NonPositiveValueError(count=2), "log is undefined for 2 non-positive values"),
        (
            InvalidHorizonError(horizon=5, max_horizon=4),
            "horizon must be 1 to 4, got 5",
        ),
        (
            MissingFlagsError(columns=("covid", "structural_break")),
            "group F needs the NB00 flag columns: covid, structural_break",
        ),
        (
            MissingRegimeError(ticker="AAA"),
            "no seasonality regime for AAA; run the EDA regimes first",
        ),
        (
            MixedTickerPanelError(tickers=("AAA", "BBB")),
            "features take one company's panel at a time, got: AAA, BBB",
        ),
        (
            LeakageError(origin=8, columns=("peek",)),
            "features at origin row 8 changed with later quarters: peek",
        ),
    ],
)
def test_message_is_built_from_the_fields(error: FeatureError, message: str) -> None:
    assert str(error) == message


def test_every_error_is_a_feature_error() -> None:
    with pytest.raises(FeatureError):
        raise InvalidHorizonError(horizon=0, max_horizon=4)


def test_fields_are_readable_by_the_caller() -> None:
    origin = 3
    error = LeakageError(origin=origin, columns=("a", "b"))

    assert error.origin == origin
    assert error.columns == ("a", "b")
