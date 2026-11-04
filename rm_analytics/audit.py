"""PASS / WARN / FAIL audit log.

Rules followed by every check:
* A check must be able to fail on real data (no checks that re-test a filter just applied).
* Human verifications are explicit attestations recorded in the configuration, not hard-coded WARNs.
* FAIL means results must not be used for decisions; the export marks the run as FAILED.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


@dataclass
class AuditLog:
    entries: list = field(default_factory=list)

    def add(self, category: str, check: str, status: str, detail: str) -> None:
        if status not in (PASS, WARN, FAIL):
            raise ValueError(f"invalid status {status}")
        self.entries.append({"category": category, "check": check, "status": status, "detail": str(detail)})

    def require(self, category: str, check: str, passed: bool, detail: str, severity: str = FAIL) -> None:
        self.add(category, check, PASS if passed else severity, detail)

    @property
    def has_failures(self) -> bool:
        return any(e["status"] == FAIL for e in self.entries)

    @property
    def has_warnings(self) -> bool:
        return any(e["status"] == WARN for e in self.entries)

    @property
    def decision_status(self) -> str:
        """Governance gate: no warning-containing run is represented as validated."""
        if self.has_failures:
            return "FAILED"
        if self.has_warnings:
            return "REVIEW_REQUIRED"
        return "VALIDATED"

    def review_items(self) -> list[dict]:
        """Unresolved issues, including failures. All require documented resolution."""
        return [dict(e) for e in self.entries if e["status"] != PASS]

    def counts(self) -> dict:
        frame = self.to_frame()
        return {s: int((frame.status == s).sum()) if len(frame) else 0 for s in (PASS, WARN, FAIL)}

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.entries, columns=["category", "check", "status", "detail"])


def pct_diff(a: float, b: float) -> float:
    """Absolute % difference of a versus b (b is the reference)."""
    if b == 0 or pd.isna(a) or pd.isna(b):
        return float("nan")
    return abs(a / b - 1) * 100
