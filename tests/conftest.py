import sys
from pathlib import Path

import matplotlib
import pandas as pd
import pytest

matplotlib.use("Agg")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rm_analytics import AnalysisConfig  # noqa: E402
from rm_analytics.synthetic import DEFAULT_WINDOWS, SYNTHETIC_TARGET, generate_synthetic_dataset  # noqa: E402


def make_cfg(data_dir, **overrides) -> AnalysisConfig:
    params = dict(DEFAULT_WINDOWS)
    params.update(property_name=SYNTHETIC_TARGET, data_dir=str(data_dir), output_dir="output", bootstrap_iterations=300)
    params.update(overrides)
    return AnalysisConfig(**params)


@pytest.fixture
def dataset(tmp_path):
    """Fresh synthetic dataset per test, so tests can mutate files safely."""
    data_dir = tmp_path / "data"
    truth = generate_synthetic_dataset(data_dir)
    return {"root": tmp_path, "data_dir": data_dir, "truth": truth, "cfg": make_cfg(data_dir)}


def read_raw(path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def read_calendar_raw(path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, header=None, keep_default_na=False)
