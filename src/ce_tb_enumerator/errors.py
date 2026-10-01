class ConfigurationError(ValueError):
    """Raised when a configuration is invalid or internally inconsistent."""


class OutputExistsError(FileExistsError):
    """Raised when an output target exists and overwrite was not requested."""


class OutputTransactionError(OSError):
    """Raised when output publication fails but prior outputs remain recoverable."""


class OutputRecoveryError(OutputTransactionError):
    """Raised when automatic rollback is incomplete and recovery material is retained."""
