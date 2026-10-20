import json
import sys
from io import StringIO

import pytest

from openmaskit_companion import cli, manager
from openmaskit_companion.state import read_json, write_json


def invoke(home, *args):
    cli.main(["--home", str(home), *args])


def test_status_outputs_safe_json_without_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        manager,
        "status",
        lambda _home: {
            "initialized": True,
            "services": [],
            "connectors": [],
            "automatic_updates": False,
        },
    )
    invoke(tmp_path, "status")
    output = capsys.readouterr().out
    assert json.loads(output)["initialized"] is True
    assert "token" not in output


def test_approve_requires_explicit_confirmation_and_saves_profile(
    tmp_path, monkeypatch, capsys
):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({"command": sys.executable, "args": ["synthetic"]})
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "approve")
    invoke(
        tmp_path / "home",
        "approve",
        "fixture",
        "--name",
        "Synthetic",
        "--profile",
        str(profile_path),
    )
    assert json.loads(capsys.readouterr().out) == {
        "approved": "fixture",
        "restart_connector": True,
    }
    saved = read_json(tmp_path / "home/profiles.json")["fixture"]
    assert saved["command"] == sys.executable
    assert saved["args"] == ["synthetic"]
    assert saved["name"] == "Synthetic"


def test_approve_cancel_does_not_write_profile(tmp_path, monkeypatch, capsys):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({"command": "/usr/bin/env"}))
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")
    with pytest.raises(SystemExit) as error:
        invoke(
            tmp_path / "home",
            "approve",
            "fixture",
            "--name",
            "Synthetic",
            "--profile",
            str(profile_path),
        )
    assert error.value.code == 1
    assert not (tmp_path / "home/profiles.json").exists()
    captured = capsys.readouterr()
    error_line = captured.err.strip().splitlines()[-1]
    assert json.loads(error_line)["error"]
    assert "synthetic" not in captured.err


def test_approve_rejects_invalid_profile_without_saving(tmp_path, capsys):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({"command": "relative-command"}))
    with pytest.raises(SystemExit) as error:
        invoke(
            tmp_path / "home",
            "approve",
            "fixture",
            "--yes",
            "--name",
            "Synthetic",
            "--profile",
            str(profile_path),
        )
    assert error.value.code == 1
    assert not (tmp_path / "home/profiles.json").exists()
    assert json.loads(capsys.readouterr().err)["error"]


@pytest.mark.parametrize("profile_id", ["../escape", "UPPER", "bad id", "a" * 49])
def test_cli_validates_profile_identifiers_before_dispatch(profile_id):
    with pytest.raises(SystemExit) as error:
        cli.parser().parse_args(["forget", profile_id])
    assert error.value.code == 2


def test_forget_and_profiles_operate_on_private_approved_state(tmp_path, capsys):
    write_json(
        tmp_path / "profiles.json",
        {
            "keep": {
                "name": "Keep",
                "command": sys.executable,
                "args": [],
                "env": {},
                "cwd": None,
            },
            "remove": {
                "name": "Remove",
                "command": sys.executable,
                "args": [],
                "env": {},
                "cwd": None,
            },
        },
    )
    invoke(tmp_path, "profiles")
    assert json.loads(capsys.readouterr().out) == {
        "profiles": [{"id": "keep", "name": "Keep"}, {"id": "remove", "name": "Remove"}]
    }
    invoke(tmp_path, "forget", "remove")
    assert json.loads(capsys.readouterr().out) == {
        "removed": "remove",
        "restart_connector": True,
    }
    assert list(read_json(tmp_path / "profiles.json")) == ["keep"]


def test_pair_reads_code_from_stdin_without_echoing_it(tmp_path, monkeypatch, capsys):
    code = "synthetic-pairing-code"
    monkeypatch.setattr("sys.stdin", StringIO(code + "\n"))
    monkeypatch.setattr(
        manager,
        "pair",
        lambda _home, endpoint, supplied: {
            "paired": supplied == code,
            "id": "computer-test",
            "endpoint": endpoint,
        },
    )
    invoke(tmp_path, "pair", "--endpoint", "http://127.0.0.1:9495", "--code-stdin")
    output = capsys.readouterr().out
    assert json.loads(output)["paired"] is True
    assert code not in output


def test_setup_accepts_only_digest_and_returns_safe_json(tmp_path, capsys):
    digest = manager.IMAGE_PREFIX + "a" * 64
    invoke(tmp_path, "setup", "--image", digest)
    output = capsys.readouterr().out
    assert json.loads(output) == {"dashboard": manager.WEB, "initialized": True}
    assert digest not in output
    project = read_json(tmp_path / "stack/managed.json")["project"]
    assert project.startswith(manager.PROJECT + "-")
    assert len(project) == len(manager.PROJECT) + 13


def test_setup_rejects_unpinned_image_with_safe_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        invoke(tmp_path, "setup", "--image", "example/companion:latest")
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().err)["error"]


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("start", ["up", "--detach", "--wait", "--wait-timeout", "300"]),
        ("stop", ["stop", "--timeout", "45"]),
    ],
)
def test_lifecycle_forwards_only_scoped_compose_arguments(
    tmp_path, monkeypatch, capsys, action, expected
):
    calls = []
    monkeypatch.setattr(manager, "compose", lambda _home, *args: calls.append(args))
    monkeypatch.setattr(
        manager, "status", lambda _home: {"initialized": True, "services": []}
    )
    invoke(tmp_path, action)
    assert calls == [tuple(expected)]
    assert json.loads(capsys.readouterr().out)["initialized"] is True
