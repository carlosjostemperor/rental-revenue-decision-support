import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from rm_analytics import export_run, run_analysis
from rm_analytics.charts import build_figures
from rm_analytics.errors import DataValidationError

from conftest import ROOT, make_cfg, read_calendar_raw, read_raw


def statuses(result):
    a = result.audit.to_frame()
    return dict(zip(a.check, a.status))


def test_end_to_end_synthetic_run_is_consistent(dataset):
    r = run_analysis(dataset["cfg"], dataset["root"])
    st = statuses(r)
    assert not r.audit.has_failures
    for period in ("historical", "forward"):
        assert st[f"Bookings vs Report Builder booked nights ({period})"] == "PASS"
        assert st[f"Bookings vs Report Builder rental revenue ({period})"] == "PASS"
        assert st[f"Report Builder ADR = revenue / nights ({period})"] == "PASS"
    p = r.position_summary
    # Synthetic subject is priced at 75% of the base rate; comps at 0.85-1.20x -> gap around -25%
    assert -32 < p["median_daily_gap_pct"] < -18
    assert p["median_daily_gap_ci95_low_pct"] <= p["median_daily_gap_pct"] <= p["median_daily_gap_ci95_high_pct"]
    assert p["eligible_comparison_days"] <= p["subject_available_days"]
    truth = dataset["truth"]
    rec = r.reconciliation.set_index("period")
    assert rec.loc["forward", "bookings_stay_nights"] == truth["forward"]["nights"]
    assert rec.loc["historical", "bookings_stay_revenue"] == pytest.approx(truth["historical"]["revenue"])


def test_export_writes_manifest_with_hashes_and_no_guest_columns(dataset):
    r = run_analysis(dataset["cfg"], dataset["root"])
    out = export_run(r, build_figures(r))
    assert out.parent == dataset["root"] / "output" and not out.name.endswith("_FAILED")
    m = json.loads((out / "run_manifest.json").read_text())
    assert m["status"] == "REVIEW_REQUIRED"
    assert out.name.endswith("_REVIEW_REQUIRED")
    assert m["approved_for_automated_price_changes"] is False
    assert m["outstanding_review_items"]
    assert (out / "REVIEW_SUMMARY.md").is_file()
    assert (out / "minimum_stay_sensitivity.csv").is_file()
    assert set(m["inputs"]) == {"calendar", "bookings", "historical", "forward"}
    for name, digest in m["outputs_sha256"].items():
        import hashlib

        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    assert m["environment"]["pandas"] == pd.__version__
    cols = pd.read_csv(out / "booking_window_reservations.csv").columns
    assert "Listing Name" not in cols and "Reservation ID" not in cols
    # A second export never overwrites the first
    out2 = export_run(r)
    assert out2 != out and out.exists()


def test_failed_audit_is_exported_as_failed_and_flagged(dataset):
    path = dataset["data_dir"] / "bookings.csv"
    df = read_raw(path)
    r0 = run_analysis(dataset["cfg"], dataset["root"])
    rid = r0.window_bookings["Reservation ID"].iloc[0]
    df.loc[df["Reservation ID"] == rid, "Length of Stay (Days)"] = "40"
    df.to_csv(path, index=False)
    r = run_analysis(dataset["cfg"], dataset["root"])
    assert statuses(r)["Length of stay reconciles with check-in/check-out"] == "FAIL"
    out = export_run(r)
    assert out.name.endswith("_FAILED")
    assert json.loads((out / "run_manifest.json").read_text())["decision_use"].startswith("NOT FOR DECISIONS")


def test_input_modified_during_run_is_detected(dataset):
    r = run_analysis(dataset["cfg"], dataset["root"])
    with open(dataset["data_dir"] / "bookings.csv", "a") as fh:
        fh.write("\n")
    out = export_run(r)
    assert out.name.endswith("_FAILED")
    assert statuses(r)["Input unchanged during run (bookings)"] == "FAIL"


def test_wrong_report_builder_period_is_caught_by_reconciliation(dataset):
    """Audit finding #6: a Report Builder export for the wrong stay range used to pass silently."""
    path = dataset["data_dir"] / "report_builder_historical.csv"
    df = read_raw(path)
    df.loc[1, "Booked Nights"] = "30"
    df.loc[1, "Rental Revenue"] = "$9,000.00"
    df.loc[1, "Rental ADR"] = "$300.00"
    df.to_csv(path, index=False)
    st = statuses(run_analysis(dataset["cfg"], dataset["root"]))
    assert st["Bookings vs Report Builder booked nights (historical)"] == "WARN"
    assert st["Bookings vs Report Builder rental revenue (historical)"] == "WARN"
    r = run_analysis(dataset["cfg"], dataset["root"])
    out = export_run(r)
    manifest = json.loads((out / "run_manifest.json").read_text())
    assert manifest["status"] == "REVIEW_REQUIRED"
    assert "REVIEW REQUIRED" in manifest["decision_use"]
    assert any("Report Builder booked nights" in entry["check"] for entry in manifest["outstanding_review_items"])


def test_report_builder_internal_adr_inconsistency_warns(dataset):
    path = dataset["data_dir"] / "report_builder_forward.csv"
    df = read_raw(path)
    df.loc[1, "Rental ADR"] = "$999.00"
    df.to_csv(path, index=False)
    st = statuses(run_analysis(dataset["cfg"], dataset["root"]))
    assert st["Report Builder ADR = revenue / nights (forward)"] == "WARN"


def test_overlapping_reservations_fail(dataset):
    path = dataset["data_dir"] / "bookings.csv"
    df = read_raw(path)
    dup = df.iloc[[0]].copy()
    dup["Reservation ID"] = "SYN-OVERLAP"
    pd.concat([df, dup]).to_csv(path, index=False)
    r = run_analysis(dataset["cfg"], dataset["root"])
    assert r.audit.has_failures
    assert "FAIL" in {statuses(r)["No overlapping reservations (historical)"], statuses(r)["No overlapping reservations (forward)"]}


def test_subject_home_inside_comp_set_fails(dataset):
    path = dataset["data_dir"] / "competitor_calendar.csv"
    raw = read_calendar_raw(path)
    copy = raw.iloc[:, 1:4].copy()
    copy.iloc[0, 0] = "Subject home listed on another channel"
    raw = pd.concat([raw, copy], axis=1, ignore_index=True)
    raw.to_csv(path, index=False, header=False)  # same prices and availability as the subject
    r = run_analysis(dataset["cfg"], dataset["root"])
    assert statuses(r)["Comp set contains the subject home"] == "FAIL"
    cfg_drop = make_cfg(dataset["data_dir"], duplicate_policy="drop")
    r2 = run_analysis(cfg_drop, dataset["root"])
    assert r2.dropped_comps == ["Subject home listed on another channel"] and not r2.audit.has_failures


def test_too_few_comps_fail(dataset):
    r = run_analysis(make_cfg(dataset["data_dir"], min_active_comps=11), dataset["root"])
    assert statuses(r)["Comp set size >= min_active_comps"] == "FAIL"


def test_attestations_change_governance_status(dataset):
    cfg = make_cfg(dataset["data_dir"], analyst="Analyst A", attest_report_periods_verified=True,
                   attest_comp_set_reviewed=True, attest_storage_approved=True)
    gov = run_analysis(cfg, dataset["root"]).audit.to_frame().query("category == 'governance'")
    assert (gov.status == "PASS").all()


def test_missing_input_file_raises(dataset):
    (dataset["data_dir"] / "bookings.csv").unlink()
    with pytest.raises(DataValidationError, match="Missing input"):
        run_analysis(dataset["cfg"], dataset["root"])


def test_semicolon_delimited_exports_supported(dataset):
    for name in ("bookings.csv", "report_builder_historical.csv", "report_builder_forward.csv"):
        p = dataset["data_dir"] / name
        read_raw(p).to_csv(p, index=False, sep=";")
    p = dataset["data_dir"] / "competitor_calendar.csv"
    read_calendar_raw(p).to_csv(p, index=False, header=False, sep=";")
    assert not run_analysis(dataset["cfg"], dataset["root"]).audit.has_failures


# ---- Notebook executes top to bottom (local Jupyter kernel) ---------------------------------
def test_notebook_runs_end_to_end(tmp_path):
    nbclient = pytest.importorskip("nbclient")
    nbformat = pytest.importorskip("nbformat")
    import shutil

    proj = tmp_path / "proj"
    shutil.copytree(ROOT / "rm_analytics", proj / "rm_analytics")
    shutil.copy(ROOT / "Revenue_Management_EDA.ipynb", proj)
    from rm_analytics.synthetic import SYNTHETIC_TARGET, generate_synthetic_dataset

    generate_synthetic_dataset(proj / "data" / "example_synthetic")
    nb = nbformat.read(proj / "Revenue_Management_EDA.ipynb", as_version=4)
    env = {"RMA_DATA_DIR": "data/example_synthetic", "RMA_PROPERTY": SYNTHETIC_TARGET, "MPLBACKEND": "Agg"}
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        client = nbclient.NotebookClient(nb, timeout=300, kernel_name="python3", resources={"metadata": {"path": str(proj)}})
        client.execute()
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    runs = list((proj / "output").iterdir())
    assert len(runs) == 1 and not runs[0].name.endswith("_FAILED")
    assert (runs[0] / "pricing_timeseries.png").is_file()


# ---- v2.1: quality gates and comparable-stay sensitivity ----------------------------------
def test_review_gate_requires_zero_warns():
    from rm_analytics.audit import AuditLog, PASS, WARN, FAIL

    log = AuditLog()
    assert log.decision_status == "VALIDATED"
    log.add("test", "ok", PASS, "valid")
    assert log.decision_status == "VALIDATED"
    log.add("test", "needs human review", WARN, "reason")
    assert log.decision_status == "REVIEW_REQUIRED"
    assert log.review_items() == [{"category": "test", "check": "needs human review", "status": WARN, "detail": "reason"}]
    log.add("test", "invalid", FAIL, "reason")
    assert log.decision_status == "FAILED"


def test_minimum_stay_sensitivity_groups_partition_eligible_days(dataset):
    r = run_analysis(dataset["cfg"], dataset["root"])
    p = r.position_summary
    assert p["days_min_stay_matched"] + p["days_min_stay_differs"] + p["days_min_stay_unknown"] == p["eligible_comparison_days"]
    assert p["days_min_stay_matched"] > 0
    assert p["days_min_stay_differs"] > 0
    out = export_run(r)
    df = pd.read_csv(out / "minimum_stay_sensitivity.csv")
    assert df["comparison_dates"].sum() == p["eligible_comparison_days"]
    assert set(df["minimum_stay_group"]) == {"matched", "different", "unknown"}
    assert df.loc[df.minimum_stay_group == "matched", "median_gap_vs_comp_median_pct"].notna().all()


def test_warning_outputs_are_hashed_and_report_lists_warnings(dataset):
    import hashlib
    r = run_analysis(dataset["cfg"], dataset["root"])
    out = export_run(r)
    m = json.loads((out / "run_manifest.json").read_text())
    assert "REVIEW_SUMMARY.md" in m["outputs_sha256"]
    assert hashlib.sha256((out / "REVIEW_SUMMARY.md").read_bytes()).hexdigest() == m["outputs_sha256"]["REVIEW_SUMMARY.md"]
    review = (out / "REVIEW_SUMMARY.md").read_text()
    assert "REVIEW_REQUIRED" in review
    assert "Minimum stay comparable" in review
    assert "Report Builder stay-date ranges verified" in review


def test_strong_duplicate_flag_retains_basis(dataset):
    path = dataset["data_dir"] / "competitor_calendar.csv"
    raw = read_calendar_raw(path)
    copy = raw.iloc[:, 1:4].copy()
    copy.iloc[0, 0] = "Cross-channel copy of target"
    pd.concat([raw, copy], axis=1, ignore_index=True).to_csv(path, index=False, header=False)
    r = run_analysis(dataset["cfg"], dataset["root"])
    d = r.duplicates
    assert (d.match_basis == "price_and_availability").any()
    assert r.audit.has_failures


def test_shared_blocked_days_with_different_prices_only_warns_and_is_not_auto_dropped(dataset):
    import numpy as np
    from rm_analytics.duplicates import detect_duplicate_listings, apply_duplicate_policy

    cfg = make_cfg(dataset["data_dir"], duplicate_policy="drop")
    dates = pd.date_range("2026-11-03", periods=30)
    records = []
    for name, factor in [("Home A", 1.0), ("Home B", 1.35), ("Subject Home", 1.75)]:
        for i, date in enumerate(dates):
            unavailable = i in {2, 5, 8, 12, 18, 24}
            records.append({"listing": name, "date": date, "advertised_price": (300 + i * 3) * factor,
                            "available": 0 if (unavailable and name != "Subject Home") else 1,
                            "minimum_stay": 3})
    frame = pd.DataFrame(records)
    dups = detect_duplicate_listings(frame, "Subject Home", cfg)
    row = dups[((dups.listing_a == "Home A") & (dups.listing_b == "Home B")) |
               ((dups.listing_a == "Home B") & (dups.listing_b == "Home A"))]
    assert len(row) == 1 and row.iloc[0].match_basis == "shared_unavailability_review"
    assert row.iloc[0].shared_blocked_days == 6
    _, comps, dropped = apply_duplicate_policy(frame, ["Home A", "Home B"], "Subject Home", dups, cfg)
    assert set(comps) == {"Home A", "Home B"} and dropped == []


def test_all_available_calendars_do_not_trigger_shared_unavailability(dataset):
    from rm_analytics.duplicates import detect_duplicate_listings
    dates = pd.date_range("2026-11-03", periods=30)
    records = []
    for name, factor in [("A", 1.0), ("B", 1.3)]:
        for i, date in enumerate(dates):
            records.append({"listing": name, "date": date, "advertised_price": (300 + i) * factor,
                            "available": 1, "minimum_stay": 3})
    frame = pd.DataFrame(records)
    assert detect_duplicate_listings(frame, "C", dataset["cfg"]).empty
