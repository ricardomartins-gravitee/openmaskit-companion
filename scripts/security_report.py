"""Print scanner counts and advisory IDs, never source excerpts or secret values."""

import json
import re
import sys
from pathlib import Path


def main():
    try:
        report = json.loads(Path(sys.argv[1]).read_text())
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
    except (OSError, ValueError, AttributeError, TypeError, IndexError):
        print("Scanner report unavailable or invalid; contents withheld.")
        return 1
    print(
        f"Trivy findings: {counts['Vulnerabilities']} vulnerability, "
        f"{counts['Misconfigurations']} misconfiguration, {counts['Secrets']} secret."
    )
    print("Advisory IDs: " + (", ".join(safe_ids) if safe_ids else "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
