import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    return yaml.load(
        (ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader
    )


CONNECTOR_REPOSITORY = "ricardomartins-gravitee/openmaskit-connector"
CONNECTOR_PIN = "0ee39a0e177ce3e169c919d6b4da9e84052202e8"


def test_quality_and_security_gate_all_companion_checks_and_packaging():
    jobs = workflow("validate.yml")["jobs"]
    for name in ("quality", "security"):
        assert jobs[name]["uses"] == f"./.github/workflows/{name}.yml"
        assert "workflow_call" in workflow(f"{name}.yml")["on"]
    assert set(jobs["intel-wheel"]["needs"]) == {"quality", "security"}
    assert set(jobs["integration"]["needs"]) == {"quality", "security"}
    assert set(jobs["test"]["needs"]) == {"intel-wheel", "integration"}
    assert set(jobs["release-metadata"]["needs"]) == {
        "test",
        "integration",
        "quality",
        "security",
    }
    assert set(jobs["package"]["needs"]) == {
        "test",
        "intel-wheel",
        "release-metadata",
    }
    assert (
        "publish" not in jobs and "image" not in jobs and "native-release" not in jobs
    )


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
    assert re.fullmatch("[0-9a-f]{40}", CONNECTOR_PIN)
    quality_workflow = workflow("quality.yml")
    quality_commands = "\n".join(
        step.get("run", "")
        for job in quality_workflow["jobs"].values()
        for step in job.get("steps", [])
    )
    assert "shellcheck scripts/build_intel_dependencies.sh" not in quality_commands


def test_coverage_gate_includes_all_companion_code_and_branches():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["coverage"]
    assert config["run"]["branch"] is True
    assert config["run"]["source"] == ["src/openmaskit_companion"]
    assert config["report"]["fail_under"] >= 80
    assert "omit" not in config["run"]


def test_ci_uses_locked_dependencies_without_implicit_resynchronization():
    for name in ("validate.yml", "quality.yml"):
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
                    if command.startswith("uv sync"):
                        assert "--no-install-package openmaskit-connector" in command


def test_connector_source_and_intel_wheel_are_pinned_to_the_same_commit():
    pin = json.loads((ROOT / "dependencies/connector.json").read_text())
    commit = pin["commit"]
    assert commit == CONNECTOR_PIN
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert "openmaskit-connector==0.1.0a2" in pyproject["project"]["dependencies"]
    source = pyproject["tool"]["uv"]["sources"]["openmaskit-connector"]
    assert source["rev"] == commit
    jobs = workflow("validate.yml")["jobs"]
    assert jobs["intel-wheel"]["uses"] == (
        f"{CONNECTOR_REPOSITORY}/.github/workflows/intel-wheel.yml@{commit}"
    )
    assert jobs["intel-wheel"]["with"]["source-ref"] == commit
    assert jobs["intel-wheel"]["permissions"] == {
        "contents": "read",
        "attestations": "read",
        "actions": "read",
    }
    jobs_to_check = {
        "quality": workflow("quality.yml")["jobs"]["python"],
        **{name: jobs[name] for name in ("integration", "test", "package")},
    }
    for job in jobs_to_check.values():
        checkouts = [
            step
            for step in job["steps"]
            if step.get("uses", "").startswith("actions/checkout@")
            and step.get("with", {}).get("repository") == CONNECTOR_REPOSITORY
        ]
        assert len(checkouts) == 1
        assert checkouts[0]["with"]["ref"] == commit
        assert checkouts[0]["with"]["path"] == ".runtime/connector-source"
        commands = [step.get("run", "") for step in job["steps"]]
        installer = next(
            index
            for index, command in enumerate(commands)
            if "scripts/install_connector.py" in command
        )
        checkout = next(
            index for index, step in enumerate(job["steps"]) if step in checkouts
        )
        assert checkout < installer

    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    locked_connector = next(
        package
        for package in lock["package"]
        if package["name"] == "openmaskit-connector"
    )
    assert locked_connector["version"] == "0.1.0a2"
    locked_git = locked_connector["source"]["git"]
    parsed_git = urlsplit(locked_git)
    assert parsed_git.scheme == "https"
    assert parsed_git.netloc == "github.com"
    assert parsed_git.path == "/ricardomartins-gravitee/openmaskit-connector.git"
    assert dict(parse_qsl(parsed_git.query)) == {"rev": commit}
    assert parsed_git.fragment == commit
    assert locked_git.startswith(source["git"] + "?")


def test_dependency_audit_excludes_only_connector_source_and_keeps_its_libraries():
    quality = workflow("quality.yml")
    export = next(
        step
        for job in quality["jobs"].values()
        for step in job.get("steps", [])
        if step.get("name") == "Export all locked dependencies for auditing"
    )
    omitted = re.findall(r"--no-emit-package(?:=|\s+)(\S+)", export["run"])
    assert omitted == ["openmaskit-connector"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    package = next(
        item for item in lock["package"] if item["name"] == "openmaskit-connector"
    )
    transitive = {dependency["name"] for dependency in package.get("dependencies", [])}
    assert transitive
    assert transitive.isdisjoint(omitted)


def test_connector_wheel_is_verified_before_installing_on_intel():
    jobs = workflow("validate.yml")["jobs"]
    test = jobs["test"]
    assert set(test["strategy"]["matrix"]["os"]) == {"macos-26", "macos-15-intel"}
    steps = test["steps"]
    downloads = [step for step in steps if "download-artifact@" in step.get("uses", "")]
    assert len(downloads) == 1
    assert downloads[0]["if"] == "matrix.os == 'macos-15-intel'"
    assert downloads[0]["with"]["name"] == "intel-cryptography-wheel"
    commands = "\n".join(step.get("run", "") for step in steps)
    assert "--group intel-build" not in commands
    assert "--no-install-package cryptography" in commands
    assert ".runtime/connector-source/scripts/intel_wheel.py prepare" in commands
    assert ".runtime/connector-source/scripts/test_crypto.py" in commands
    for step in steps:
        for command in re.findall(r"\buv pip install\b[^\n]*", step.get("run", "")):
            assert "--no-build" in command
            assert "--no-deps" in command
            assert "--require-hashes" in command


def test_companion_app_is_built_and_exercised_on_both_macos_architectures():
    jobs = workflow("validate.yml")["jobs"]
    steps = jobs["test"]["steps"]
    commands = "\n".join(step.get("run", "") for step in steps)
    assert "swift format lint --strict" in commands
    assert "swift test --package-path desktop/macos" in commands
    assert "scripts/bundle.py" in commands
    assert "scripts/test_bundle.py" in commands
    assert "connector-source/scripts/test_crypto.py" in commands
    assert "scripts/manager_acceptance.py" not in commands
    assert "--image" not in commands
    assert not any("archive.py" in step.get("run", "") for step in steps)
    bundle_test = (ROOT / "scripts/test_bundle.py").read_text()
    assert (
        "Contents/Resources/backend/openmaskit-companion/openmaskit-companion"
        in bundle_test
    )
    assert "tests/test_app_contract.py" in bundle_test
    assert '"COMPANION_BINARY"' in bundle_test


def test_local_candidate_relay_acceptance_is_isolated_and_does_not_publish_an_image():
    jobs = workflow("validate.yml")["jobs"]
    integration = jobs["integration"]
    assert integration["runs-on"] == "ubuntu-24.04"
    commands = "\n".join(step.get("run", "") for step in integration["steps"])
    assert ".runtime/connector-source" in commands
    assert "docker buildx build" in commands
    assert "openmaskit-connector:candidate" in commands
    assert "manager_acceptance.py --candidate-image" in commands
    assert "gh release" not in commands
    assert "docker push" not in commands


def test_mac_app_archives_are_main_only_attested_and_have_checksums():
    jobs = workflow("validate.yml")["jobs"]
    release = jobs["release-metadata"]
    assert "refs/heads/main" in release["if"]
    assert "event_name != 'pull_request'" in release["if"]
    assert (
        release["outputs"]["relay-image"] == "${{ steps.release.outputs.relay-image }}"
    )
    release_commands = "\n".join(step.get("run", "") for step in release["steps"])
    assert "scripts/connector_release.py" in release_commands
    assert "GH_TOKEN" in "\n".join(
        str(step.get("env", {})) for step in release["steps"]
    )
    package = jobs["package"]
    assert "refs/heads/main" in package["if"]
    assert "event_name != 'pull_request'" in package["if"]
    assert package["permissions"]["id-token"] == "write"
    assert package["permissions"]["attestations"] == "write"
    package_commands = "\n".join(step.get("run", "") for step in package["steps"])
    assert "scripts/bundle.py --image" in package_commands
    assert "scripts/test_bundle.py" in package_commands
    assert "scripts/archive.py" in package_commands
    assert (
        "${{ needs.release-metadata.outputs.relay-image }}"
        in package["env"]["RELAY_IMAGE"]
    )
    assert any(
        "attest-build-provenance@" in step.get("uses", "") for step in package["steps"]
    )
    assert any("upload-artifact@" in step.get("uses", "") for step in package["steps"])
    archive = (ROOT / "scripts/archive.py").read_text()
    assert "ditto" in archive
    assert "OpenMaskit Companion.app" in archive
    assert "SHA256SUMS.txt" in archive
    assert "openmaskit-companion-cli-" not in archive


def test_scanner_downloads_enforce_https_across_redirects():
    for name in ("quality.yml", "security.yml"):
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
