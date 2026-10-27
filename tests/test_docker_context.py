"""Companion's Docker Desktop default must not change terminal configuration."""

import os
import subprocess
from unittest.mock import Mock

import pytest

from openmaskit_companion import installation, manager, requirements


@pytest.mark.parametrize("system", ["darwin", "linux", "win32"])
@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"DOCKER_HOST": "unix:///synthetic/explicit.sock"},
        {"DOCKER_CONTEXT": "synthetic-explicit"},
        {
            "DOCKER_CONTEXT": "synthetic-explicit",
            "DOCKER_HOST": "tcp://remote.invalid:2375",
        },
    ],
)
def test_desktop_default_is_scoped_and_explicit_overrides_are_preserved(
    monkeypatch, system, overrides
):
    monkeypatch.setattr(manager.sys, "platform", system)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    before = dict(os.environ)
    result = manager.docker_environment()
    expected = dict(before)
    if system == "darwin" and not overrides:
        expected["DOCKER_CONTEXT"] = "desktop-linux"
    assert result == expected
    assert dict(os.environ) == before


@pytest.mark.parametrize("action", ["compose", "ready", "prerequisites"])
def test_validation_and_operations_use_the_same_desktop_context(
    monkeypatch, tmp_path, action
):
    manager.initialize(tmp_path, manager.IMAGE_PREFIX + "a" * 64)
    installation.save(tmp_path, "managed", manager.WEB)
    monkeypatch.setattr(manager.sys, "platform", "darwin")
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.setattr(requirements, "desktop_installed", lambda: True)
    monkeypatch.setattr(manager, "docker_binary", lambda: "/synthetic/docker")
    calls = []

    def run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        if arguments[1:3] == ["context", "inspect"]:
            assert arguments[3] == "desktop-linux"
            value = '"unix:///synthetic/desktop.sock"'
        elif "--help" in arguments:
            value = "--wait --wait-timeout --pull"
        else:
            value = "[]"
        return subprocess.CompletedProcess(arguments, 0, value, "")

    monkeypatch.setattr(manager.subprocess, "run", run)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    if action == "compose":
        manager.compose(tmp_path, "ps", "--all", "--format", "json")
    elif action == "ready":
        assert manager.docker_ready(tmp_path)["ready"]
    else:
        assert manager.prerequisites()["ready"]
    assert len(calls) >= 2
    assert all(
        kwargs["env"]["DOCKER_CONTEXT"] == "desktop-linux" for _, kwargs in calls
    )
    assert all("use" not in arguments for arguments, _ in calls)
    assert os.environ.get("DOCKER_CONTEXT") is None
    assert {p: p.read_bytes() for p in before} == before


def test_explicit_remote_host_remains_rejected_before_contacting_any_daemon(
    monkeypatch, tmp_path
):
    manager.initialize(tmp_path, manager.IMAGE_PREFIX + "a" * 64)
    monkeypatch.setattr(manager.sys, "platform", "darwin")
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setenv("DOCKER_HOST", "tcp://remote.invalid:2375")
    monkeypatch.setattr(manager, "docker_binary", lambda: "/synthetic/docker")
    run = Mock()
    monkeypatch.setattr(manager.subprocess, "run", run)
    with pytest.raises(ValueError, match="local Docker"):
        manager.compose(tmp_path, "stop")
    run.assert_not_called()


def test_requirement_checks_without_an_explicit_environment_preserve_the_callers_context(
    monkeypatch,
):
    monkeypatch.setattr(requirements.sys, "platform", "linux")
    monkeypatch.setenv("DOCKER_CONTEXT", "synthetic-explicit")
    validate = Mock()
    run = Mock(
        return_value=subprocess.CompletedProcess(
            [], 0, "--wait --wait-timeout --pull", ""
        )
    )
    monkeypatch.setattr(requirements.subprocess, "run", run)
    assert requirements.check(lambda: "/synthetic/docker", validate)["ready"]
    assert validate.call_args.args[1]["DOCKER_CONTEXT"] == "synthetic-explicit"
    assert all(
        call.kwargs["env"]["DOCKER_CONTEXT"] == "synthetic-explicit"
        for call in run.call_args_list
    )
