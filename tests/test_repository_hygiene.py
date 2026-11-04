"""Guards for public-repository hygiene: no confidential identifiers, no notebook outputs."""

import json
from pathlib import Path

from conftest import ROOT

# Stored reversed so this file does not itself contain the tokens it searches for.
FORBIDDEN_REVERSED = ["5035", "ht721", "sretnerrorepme", "slatner rorepme", "ecarret elpmet", "solrac"]
FORBIDDEN = [t[::-1] for t in FORBIDDEN_REVERSED]
TEXT_SUFFIXES = {".py", ".md", ".txt", ".ipynb", ".csv", ".toml", ".cfg", ".json", ".gitignore", ""}
SKIP_DIRS = {".git", "output", "__pycache__", ".pytest_cache", "input"}


def _files():
    for p in ROOT.rglob("*"):
        if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS) and p.suffix in TEXT_SUFFIXES:
            yield p


def test_no_confidential_identifiers_in_tracked_files():
    hits = []
    for p in _files():
        text = p.read_text(encoding="utf-8", errors="ignore").casefold()
        hits += [(str(p.relative_to(ROOT)), t) for t in FORBIDDEN if t in text]
    assert not hits, hits


def test_notebook_has_no_saved_outputs():
    nb = json.loads((ROOT / "Revenue_Management_EDA.ipynb").read_text())
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            assert not cell.get("outputs") and cell.get("execution_count") is None


def test_gitignore_protects_real_data():
    text = (ROOT / ".gitignore").read_text()
    assert "data/input/*" in text and "output/" in text


def test_example_data_is_synthetic_only():
    for p in (ROOT / "data" / "example_synthetic").glob("*.csv"):
        content = p.read_text()
        assert "SYNTHETIC" in content or "Synthetic" in content, p
