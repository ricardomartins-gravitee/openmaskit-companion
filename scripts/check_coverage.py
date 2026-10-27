"""Require statements and branches in every backend module, not only the average."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def percentage(covered, total):
    if type(covered) is not int or type(total) is not int or not 0 <= covered <= total:
        raise ValueError("Invalid coverage counters")
    return 100 * covered / total if total else 100.0


def check(report, required):
    failures, rows = [], []
    for name in sorted(required):
        if name not in report["files"]:
            failures.append(name + ": missing report")
            continue
        summary = report["files"][name]["summary"]
        lines = percentage(summary["covered_lines"], summary["num_statements"])
        branches = percentage(summary["covered_branches"], summary["num_branches"])
        rows.append((name, lines, branches))
        if lines < 95 or branches < 90:
            failures.append(name + ": requires 95% statements and 90% branches")
    total = report["totals"]
    combined = percentage(
        total["covered_lines"] + total["covered_branches"],
        total["num_statements"] + total["num_branches"],
    )
    if combined < 95:
        failures.append("Backend total: requires 95% combined coverage")
    return rows, failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    required = {
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in (ROOT / "src/openmaskit_companion").glob("*.py")
    }
    try:
        rows, failures = check(json.loads(args.report.read_text()), required)
    except (ValueError, KeyError, TypeError, OSError):
        raise SystemExit("Backend coverage report is missing or invalid") from None
    for name, lines, branches in rows:
        print(f"{name}: {lines:.2f}% statements, {branches:.2f}% branches")
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
