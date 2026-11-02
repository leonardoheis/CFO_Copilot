class TrackingError(Exception):
    """Base error for experiment tracking."""


class TrackingUnavailableError(TrackingError):
    """Raised when the tracking backend is not installed."""


class MissingApiKeyError(TrackingError):
    """Raised when online tracking is requested without an API key."""


class InvalidRunNameError(TrackingError):
    """Raised when run-name parts contradict each other."""
