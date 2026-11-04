"""Exception types. Every validation failure raises one of these instead of silently coercing data."""


class ConfigError(ValueError):
    """The run configuration is invalid or internally inconsistent."""


class DataValidationError(ValueError):
    """An input file does not satisfy the input contract; results would be wrong or incomplete."""
