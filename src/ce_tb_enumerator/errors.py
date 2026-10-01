class ConfigurationError(ValueError):
    """Raised when a configuration is invalid or internally inconsistent."""


class OutputExistsError(FileExistsError):
    """Raised when an output target exists and overwrite was not requested."""
