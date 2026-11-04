"""Revenue Management Analytics: auditable pricing-position analysis of PriceLabs exports."""

from .config import AnalysisConfig
from .errors import ConfigError, DataValidationError
from .pipeline import AnalysisResult, run_analysis
from .export import export_run

__version__ = "2.1.0"

__all__ = [
    "AnalysisConfig",
    "AnalysisResult",
    "ConfigError",
    "DataValidationError",
    "export_run",
    "run_analysis",
    "__version__",
]
