import hashlib

from rm_analytics.synthetic import generate_synthetic_dataset

from conftest import ROOT


def _digests(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.glob("*.csv"))}


def test_generator_is_deterministic(tmp_path):
    generate_synthetic_dataset(tmp_path / "a")
    generate_synthetic_dataset(tmp_path / "b")
    assert _digests(tmp_path / "a") == _digests(tmp_path / "b")


def test_committed_example_matches_generator(tmp_path):
    generate_synthetic_dataset(tmp_path)
    assert _digests(tmp_path) == _digests(ROOT / "data" / "example_synthetic")
