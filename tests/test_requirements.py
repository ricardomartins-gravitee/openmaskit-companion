"""Missing prerequisites are simulated; never uninstall or stop the user's Docker."""

import json
import subprocess
from unittest.mock import Mock

import pytest

from openmaskit_companion import cli, installation, manager, requirements


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setattr(requirements.sys, "platform", "darwin")
    monkeypatch.setattr(requirements, "desktop_installed", lambda: True)
    monkeypatch.setattr(manager, "docker_binary", lambda: "/synthetic/docker")
    context = Mock()
    monkeypatch.setattr(manager, "local_docker", context)
    command = Mock(
        return_value=subprocess.CompletedProcess(
            [], 0, "--wait --wait-timeout --pull", ""
        )
    )
    monkeypatch.setattr(requirements.subprocess, "run", command)
    return context, command


def checks(report):
    return {row["id"]: row for row in report["checks"]}


def test_ready_prerequisites_use_only_bounded_read_only_local_commands(runtime):
    context, command = runtime
    report = manager.prerequisites()
    assert report["ready"]
    assert len(report["checks"]) == 5
    assert all(row["state"] == "ready" for row in report["checks"])
    context.assert_called_once()
    assert [call.args[0] for call in command.call_args_list] == [
        ["/synthetic/docker", "compose", "up", "--help"],
        ["/synthetic/docker", "info", "--format", "{{.ServerVersion}}"],
    ]
    assert all(call.kwargs["timeout"] == 5 for call in command.call_args_list)


def test_uninstalled_desktop_blocks_even_a_leftover_cli(runtime, monkeypatch):
    context, command = runtime
    monkeypatch.setattr(requirements, "desktop_installed", lambda: False)
    report = manager.prerequisites()
    assert not report["ready"]
    assert checks(report)["desktop"]["state"] == "needs_attention"
    assert checks(report)["context"]["state"] == "blocked"
    context.assert_not_called()
    command.assert_not_called()


def test_missing_cli_blocks_dependent_checks_without_running_commands(
    runtime, monkeypatch
):
    context, command = runtime

    def absent():
        raise ValueError("synthetic private diagnostic")

    monkeypatch.setattr(manager, "docker_binary", absent)
    report = manager.prerequisites()
    assert not report["ready"]
    assert checks(report)["cli"]["state"] == "needs_attention"
    assert "synthetic private diagnostic" not in json.dumps(report)
    context.assert_not_called()
    command.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        ValueError("remote private context"),
        OSError("private path"),
        subprocess.TimeoutExpired("docker", 5),
    ],
)
def test_invalid_or_remote_context_never_probes_daemon_or_compose(runtime, error):
    context, command = runtime
    context.side_effect = error
    report = manager.prerequisites()
    assert not report["ready"]
    assert checks(report)["context"]["state"] == "needs_attention"
    assert "private" not in json.dumps(report)
    command.assert_not_called()


@pytest.mark.parametrize("failure", [1, "timeout", "missing", "old_compose"])
def test_compose_failure_is_clear_and_does_not_hide_daemon_state(runtime, failure):
    _, command = runtime

    def run(arguments, **kwargs):
        if "compose" in arguments:
            if failure == "timeout":
                raise subprocess.TimeoutExpired("docker", 5)
            if failure == "missing":
                raise FileNotFoundError("private executable")
            return subprocess.CompletedProcess(
                [], 1 if failure == 1 else 0, "old unsupported help", "private error"
            )
        return subprocess.CompletedProcess([], 0, "private version", "")

    command.side_effect = run
    report = manager.prerequisites()
    assert not report["ready"]
    assert checks(report)["compose"]["state"] == "needs_attention"
    assert checks(report)["daemon"]["state"] == "ready"
    assert "private" not in json.dumps(report)


def test_stopped_engine_and_recovery_are_detected_on_each_check(runtime):
    _, command = runtime
    command.side_effect = [
        subprocess.CompletedProcess([], 0, "--wait --wait-timeout --pull", ""),
        subprocess.CompletedProcess([], 1, "", "private engine error"),
        subprocess.CompletedProcess([], 0, "--wait --wait-timeout --pull", ""),
        subprocess.CompletedProcess([], 0, "private version", ""),
    ]
    first = manager.prerequisites()
    assert not first["ready"]
    assert checks(first)["daemon"]["state"] == "needs_attention"
    assert manager.prerequisites()["ready"]
    assert "private" not in json.dumps(first)


def test_fresh_cli_check_never_creates_configuration(runtime, tmp_path, capsys):
    cli.main(["--home", str(tmp_path), "prerequisites"])
    assert json.loads(capsys.readouterr().out)["ready"]
    assert not list(tmp_path.iterdir())


def test_prepare_rechecks_requirements_before_writing_or_switching_state(
    runtime, tmp_path, monkeypatch
):
    monkeypatch.setattr(requirements, "desktop_installed", lambda: False)
    installation.save(tmp_path, "existing", "http://127.0.0.1:9473")
    before = (tmp_path / "installation.json").read_bytes()
    with pytest.raises(installation.InstallationError):
        manager.prepare_managed(tmp_path, manager.IMAGE_PREFIX + "a" * 64)
    assert (tmp_path / "installation.json").read_bytes() == before
    assert not (tmp_path / "stack").exists()


def test_removed_docker_keeps_configured_managed_selection(
    runtime, tmp_path, monkeypatch
):
    manager.initialize(tmp_path, manager.IMAGE_PREFIX + "a" * 64)
    installation.save(tmp_path, "managed", manager.WEB)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    monkeypatch.setattr(requirements, "desktop_installed", lambda: False)
    monkeypatch.setattr(
        manager, "compose", Mock(side_effect=FileNotFoundError("private path"))
    )
    monkeypatch.setattr(manager, "admin", Mock(side_effect=ValueError("private token")))
    report = manager.prerequisites()
    state = manager.status(tmp_path)
    assert not report["ready"] and not state["ready"]
    assert state["configured"] and state["mode"] == "managed"
    assert {p: p.read_bytes() for p in before} == before
    assert "private" not in json.dumps(state)
