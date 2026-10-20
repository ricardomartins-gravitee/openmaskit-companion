"""Print scanner counts and advisory IDs, never source excerpts or secret values."""

import json
import os
import re
import sys
from pathlib import Path

MAX_REPORT_BYTES = 16 * 1024 * 1024


def read_report():
    # Only fixed scanner outputs inside the trusted runner temp directory are read.
    root = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    allowed = {
        "trivy-report.json": root / "trivy-report.json",
        "trivy-image.json": root / "trivy-image.json",
        "grype-report.json": root / "grype-report.json",
    }
    requested = Path(sys.argv[1])
    report_path = allowed[requested.name]
    if (
        requested != report_path
        or report_path.is_symlink()
        or not report_path.is_file()
    ):
        raise ValueError("Invalid scanner report")
    with report_path.open("rb") as report_file:
        raw = report_file.read(MAX_REPORT_BYTES + 1)
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError("Scanner report too large")
    return json.loads(raw)


def main():
    try:
        report = read_report()
        if Path(sys.argv[1]).name == "grype-report.json":
            matches = report["matches"]
            if not isinstance(matches, list):
                raise ValueError("Invalid Grype matches")
            results = [
                {
                    "Vulnerabilities": [
                        {"VulnerabilityID": match["vulnerability"]["id"]}
                        for match in matches
                    ]
                }
            ]
        else:
            results = report.get("Results") or []
        counts = {
            key: sum(len(result.get(key) or []) for result in results)
            for key in ("Vulnerabilities", "Misconfigurations", "Secrets")
        }
        advisory_ids = {
            item.get("VulnerabilityID", "")
            for result in results
            for item in (result.get("Vulnerabilities") or [])
        }
        safe_ids = sorted(
            item
            for item in advisory_ids
            if re.fullmatch(r"(?:CVE-\d{4}-\d{4,}|GHSA-[a-z0-9-]{14})", item)
        )
    except (OSError, ValueError, AttributeError, TypeError, IndexError, KeyError):
        print("Scanner report unavailable or invalid; contents withheld.")
        return 1
    print(
        f"Scanner findings: {counts['Vulnerabilities']} vulnerability, "
        f"{counts['Misconfigurations']} misconfiguration, {counts['Secrets']} secret."
    )
    print("Advisory IDs: " + (", ".join(safe_ids) if safe_ids else "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
