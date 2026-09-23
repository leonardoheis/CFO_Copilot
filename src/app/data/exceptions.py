class DataSourceError(Exception):
    """Base error for data ingestion failures."""


class DataSourceUnavailableError(DataSourceError):
    """Raised when an external data provider cannot be reached or returns an error."""


class TickerNotFoundError(DataSourceError):
    """Raised when a ticker is unknown to a data source."""


class MalformedPayloadError(DataSourceError):
    """Raised when a provider's response is not the shape the parser expects.

    Distinct from a value simply being absent: this means the data that *is*
    present cannot be interpreted, so silently treating it as missing would hide
    a provider format change behind gaps in the panel.
    """
