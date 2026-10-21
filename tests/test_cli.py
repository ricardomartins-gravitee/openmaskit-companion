import json

import pytest
from openmaskit_connector.state import read_json

from openmaskit_companion import cli, manager


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
    manager.initialize(tmp_path, manager.IMAGE_PREFIX + "a" * 64)
    calls = []
    monkeypatch.setattr(manager, "compose", lambda _home, *args: calls.append(args))
    monkeypatch.setattr(
        manager, "status", lambda _home: {"initialized": True, "services": []}
    )
    invoke(tmp_path, action)
    assert calls == [tuple(expected)]
    assert json.loads(capsys.readouterr().out)["initialized"] is True
