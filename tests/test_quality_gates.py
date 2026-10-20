import json
import os
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
    assert set(jobs["publish"]["needs"]) == {
        "test",
        "image",
        "quality",
        "security",
        "intel-wheel",
    }
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


def test_ci_disallows_dependency_source_builds_and_implicit_resynchronization():
    for name in ("validate.yml", "quality.yml", "intel-wheel.yml"):
        for job in workflow(name)["jobs"].values():
            for step in job.get("steps", []):
                for command in re.findall(
                    r"\buv (?:sync|run)\b[^\n]*", step.get("run", "")
                ):
                    assert "--frozen" in command
                    assert "--no-build" in command
                    if command.startswith("uv run"):
                        assert "--no-sync" in command
                        assert "--no-build" in command
    assert "uv sync --frozen --no-build" in (ROOT / "Dockerfile").read_text()


def test_intel_compilation_is_explicit_isolated_scanned_and_reused_in_same_run():
    jobs = workflow("validate.yml")["jobs"]
    assert set(jobs["intel-wheel"]["needs"]) == {"quality", "security"}
    assert jobs["intel-wheel"]["uses"] == "./.github/workflows/intel-wheel.yml"
    assert jobs["test"]["needs"] == "intel-wheel"
    test_commands = "\n".join(s.get("run", "") for s in jobs["test"]["steps"])
    assert "scripts/bundle.py" in test_commands
    assert "scripts/test_bundle.py" in test_commands
    builder = workflow("intel-wheel.yml")["jobs"]["wheel"]
    assert builder["runs-on"] == "macos-15-intel"
    assert builder["env"]["OPENSSL_STATIC"] == "1"
    steps = builder["steps"]
    commands = "\n".join(step.get("run", "") for step in steps)
    assert "--only-group intel-build" in commands
    assert "uv build" in commands and "--no-build-isolation" in commands
    assert "scripts/intel_wheel.py fetch" in commands
    assert "scripts/intel_wheel.py seal" in commands
    assert "scripts/test_crypto.py" in commands
    assert "scripts/intel_wheel.py sbom" in commands
    assert "--fail-on high" in commands
    assert "grype-report.json" in commands
    scans = [step["with"] for step in steps if "trivy-action@" in step.get("uses", "")]
    assert {scan["scan-type"] for scan in scans} == {"fs", "sbom"}
    for scan in scans:
        assert scan["exit-code"] == "1"
        assert scan["ignore-unfixed"] == "false"
        assert scan["severity"] == "HIGH,CRITICAL"
    for name in ("test", "package"):
        steps = jobs[name]["steps"]
        downloads = [s for s in steps if "download-artifact@" in s.get("uses", "")]
        assert len(downloads) == 1
        assert downloads[0]["if"] == "matrix.os == 'macos-15-intel'"
        assert downloads[0]["with"]["name"] == "intel-cryptography-wheel"
        assert "run-id" not in downloads[0]["with"]
        commands = "\n".join(step.get("run", "") for step in steps)
        assert "--no-install-package cryptography" in commands
        assert "scripts/intel_wheel.py prepare" in commands
        assert "scripts/test_crypto.py" in commands
    for job in [builder, jobs["test"], jobs["package"]]:
        for step in job["steps"]:
            for command in re.findall(r"\buv pip install\b[^\n]*", step.get("run", "")):
                assert "--no-build" in command
                assert "--no-deps" in command
                assert "--require-hashes" in command


def test_scanner_downloads_enforce_https_across_redirects():
    for name in ("quality.yml", "security.yml", "intel-wheel.yml"):
        for job in workflow(name)["jobs"].values():
            for step in job.get("steps", []):
                command = step.get("run", "")
                if "curl " in command:
                    assert "--proto '=https'" in command
                    assert "--proto-redir '=https'" in command
                    assert "--insecure" not in command


def report_summary(path, *, root=None, remove_root=False):
    environment = {**os.environ, "RUNNER_TEMP": str(root or path.parent)}
    if remove_root:
        environment.pop("RUNNER_TEMP")
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/security_report.py"), str(path)],
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
    )


def test_security_summary_withholds_secrets_source_and_untrusted_identifiers(tmp_path):
    private = "synthetic-private-value-must-not-be-printed"
    report = tmp_path / "trivy-report.json"
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
    report = tmp_path / "trivy-report.json"
    report.write_text(content)
    result = report_summary(report)
    assert result.returncode == 1
    assert (
        result.stdout == "Scanner report unavailable or invalid; contents withheld.\n"
    )
    assert result.stderr == ""


def test_security_summary_missing_report_is_not_success(tmp_path):
    result = report_summary(tmp_path / "trivy-image.json")
    assert result.returncode == 1
    assert result.stderr == ""


def test_grype_summary_withholds_component_details(tmp_path):
    private = "synthetic-private-component-details"
    path = tmp_path / "grype-report.json"
    path.write_text(
        json.dumps(
            {
                "matches": [
                    {
                        "vulnerability": {
                            "id": "CVE-2026-12345",
                            "description": private,
                        },
                        "artifact": {"locations": [private]},
                    },
                    {"vulnerability": {"id": private}},
                ]
            }
        )
    )
    result = report_summary(path)
    assert result.returncode == 0
    assert "2 vulnerability" in result.stdout
    assert "CVE-2026-12345" in result.stdout
    assert private not in result.stdout + result.stderr


@pytest.mark.parametrize("report", [{}, {"matches": None}, {"matches": [None]}])
def test_grype_summary_fails_closed(tmp_path, report):
    path = tmp_path / "grype-report.json"
    path.write_text(json.dumps(report))
    assert report_summary(path).returncode == 1


def test_security_summary_rejects_paths_outside_runner_temp(tmp_path):
    root = tmp_path / "runner"
    root.mkdir()
    outside = tmp_path / "trivy-report.json"
    outside.write_text('{"Results":[]}')
    assert report_summary(outside, root=root).returncode == 1


def test_security_summary_rejects_unapproved_report_names(tmp_path):
    path = tmp_path / "other.json"
    path.write_text('{"Results":[]}')
    assert report_summary(path).returncode == 1


def test_security_summary_requires_runner_temp(tmp_path):
    path = tmp_path / "trivy-report.json"
    path.write_text('{"Results":[]}')
    assert report_summary(path, remove_root=True).returncode == 1


def test_security_summary_rejects_symbolic_links(tmp_path):
    target = tmp_path / "target.json"
    target.write_text('{"Results":[]}')
    path = tmp_path / "trivy-report.json"
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("Symbolic links are unavailable for this Windows account")
    assert report_summary(path).returncode == 1


def test_security_summary_rejects_oversized_reports(tmp_path):
    path = tmp_path / "trivy-report.json"
    with path.open("wb") as report:
        report.truncate(16 * 1024 * 1024 + 1)
    assert report_summary(path).returncode == 1
