import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    return yaml.load(
        (ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader
    )


def test_security_and_quality_are_required_before_publishing():
    jobs = workflow("validate.yml")["jobs"]
    assert set(jobs["image"]["needs"]) == {"quality", "security"}
    assert set(jobs["publish"]["needs"]) == {"test", "image", "quality", "security"}
    for name in ("quality", "security"):
        assert jobs[name]["uses"] == f"./.github/workflows/{name}.yml"
        assert "workflow_call" in workflow(f"{name}.yml")["on"]


def test_workflows_pin_external_actions_and_do_not_ignore_failures():
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        data = workflow(path.name)
        assert "pull_request_target" not in data["on"]
        for job in data["jobs"].values():
            assert job.get("continue-on-error", "false") == "false"
            for step in job.get("steps", []):
                assert step.get("continue-on-error", "false") == "false"
                if "uses" in step:
                    assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", step["uses"])


def test_coverage_gate_includes_all_production_code_and_branches():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["coverage"]
    assert config["run"]["branch"] is True
    assert config["run"]["source"] == ["src/openmaskit_companion"]
    assert config["report"]["fail_under"] >= 80
    assert "omit" not in config["run"]


def report_summary(path):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/security_report.py"), str(path)],
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_security_summary_withholds_secrets_source_and_untrusted_identifiers(tmp_path):
    private = "synthetic-private-value-must-not-be-printed"
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "Results": [
                    {
                        "Target": private,
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-2026-12345",
                                "Description": private,
                            },
                            {"VulnerabilityID": private},
                        ],
                        "Misconfigurations": [{"ID": private, "Message": private}],
                        "Secrets": [{"Match": private, "Code": {"Lines": [private]}}],
                    }
                ]
            }
        )
    )
    result = report_summary(report)
    assert result.returncode == 0
    assert "2 vulnerability, 1 misconfiguration, 1 secret" in result.stdout
    assert "CVE-2026-12345" in result.stdout
    assert private not in result.stdout + result.stderr


@pytest.mark.parametrize("content", ["not-json", "[]", '{"Results":[null]}'])
def test_security_summary_fails_closed_without_dumping_malformed_reports(
    tmp_path, content
):
    report = tmp_path / "report.json"
    report.write_text(content)
    result = report_summary(report)
    assert result.returncode == 1
    assert (
        result.stdout == "Scanner report unavailable or invalid; contents withheld.\n"
    )
    assert result.stderr == ""


def test_security_summary_missing_report_is_not_success(tmp_path):
    result = report_summary(tmp_path / "missing.json")
    assert result.returncode == 1
    assert result.stderr == ""
