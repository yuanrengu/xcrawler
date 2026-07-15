"""Enforce per-file coverage floors for fetch transaction code."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

CRITICAL_COVERAGE_FLOORS = {
    "xcrawler/clients/x_api.py": 88.0,
    "fetch_more_history.py": 90.0,
    "main.py": 72.0,
}


def coverage_failures(report: dict, floors: dict[str, float] | None = None) -> list[str]:
    failures = []
    files = report.get("files", {})
    for path, minimum in (floors or CRITICAL_COVERAGE_FLOORS).items():
        file_report = files.get(path)
        if file_report is None:
            failures.append(f"{path}: missing from coverage report")
            continue
        actual = float(file_report.get("summary", {}).get("percent_covered", 0.0))
        if actual < minimum:
            failures.append(f"{path}: {actual:.2f}% is below required {minimum:.2f}%")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="coverage.py JSON report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    failures = coverage_failures(report)
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1

    for path, minimum in CRITICAL_COVERAGE_FLOORS.items():
        actual = report["files"][path]["summary"]["percent_covered"]
        print(f"PASS: {path} {actual:.2f}% (required {minimum:.2f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
