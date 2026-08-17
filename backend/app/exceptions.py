class WatermonitorError(Exception):
    """Base exception for expected application failures."""


class ExternalServiceError(WatermonitorError):
    """Raised when an upstream service cannot be used."""


class ExternalDataError(WatermonitorError):
    """Raised when upstream data is malformed or missing required fields."""


class StationNotFound(WatermonitorError):
    """Raised when a requested station is not available in the current feed."""

