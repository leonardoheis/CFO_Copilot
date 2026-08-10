class DataSourceError(Exception):
    """Base error for data ingestion failures."""


class DataSourceUnavailableError(DataSourceError):
    """Raised when an external data provider cannot be reached or returns an error."""


class TickerNotFoundError(DataSourceError):
    """Raised when a ticker is unknown to a data source."""
