"""Collector-specific exception hierarchy."""


class CollectorError(Exception):
    """Base class for collector failures."""


class ConfigurationError(CollectorError):
    """Raised when collector configuration is invalid."""


class LoginWallDetected(CollectorError):
    """Raised when X/Twitter requires login before public content is visible."""


class RateLimited(CollectorError):
    """Raised when throttling signals persist after retry policy is exhausted."""


class ExtractionError(CollectorError):
    """Raised when tweet extraction fails unexpectedly."""
