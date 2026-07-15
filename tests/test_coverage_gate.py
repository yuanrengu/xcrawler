"""Tests for the critical-module coverage gate."""

from scripts.check_critical_coverage import coverage_failures


def _report(entries):
    return {
        "files": {
            path: {"summary": {"percent_covered": percent}}
            for path, percent in entries.items()
        }
    }


def test_coverage_gate_accepts_every_file_at_its_floor():
    floors = {"main.py": 72.0, "fetch_more_history.py": 90.0}

    assert coverage_failures(_report(floors), floors) == []


def test_coverage_gate_reports_missing_and_below_floor_files():
    floors = {"main.py": 72.0, "fetch_more_history.py": 90.0}

    assert coverage_failures(_report({"main.py": 71.99}), floors) == [
        "main.py: 71.99% is below required 72.00%",
        "fetch_more_history.py: missing from coverage report",
    ]
