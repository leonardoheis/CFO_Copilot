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


class PanelStoreError(Exception):
    """Base error for reading stored panels."""


class PanelNotFoundError(PanelStoreError):
    """Raised when no panel file exists for a ticker."""


class MalformedPanelError(PanelStoreError):
    """Raised when a stored panel breaks the schema or the quarterly calendar."""


class ConsolidationError(Exception):
    """Base error for building the consolidated panel and its flags."""


class MacroMismatchError(ConsolidationError):
    """Raised when companies disagree on the shared macro block."""
