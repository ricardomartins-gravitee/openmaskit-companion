"""CLI, persistence and failure boundaries using only disposable synthetic state."""

import asyncio
import json
import subprocess
from unittest.mock import Mock

import httpx
import pytest
import respx
from openmaskit_connector import connector
from openmaskit_connector.state import write_json

from openmaskit_companion import cli, installation, manager


@pytest.fixture
def home(tmp_path):
    manager.initialize(tmp_path, manager.IMAGE_PREFIX + "a" * 64)
    installation.save(tmp_path, "managed", manager.WEB)
    return tmp_path


def fingerprint(home):
    return {
        str(p.relative_to(home)): p.read_bytes() for p in home.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize(
    "configured,ready", [(False, False), (True, False), (True, True)]
)
def test_managed_dashboard_rechecks_readiness_and_preserves_selection(
    home, configured, ready, monkeypatch, capsys
):
    before = fingerprint(home)
    monkeypatch.setattr(
        manager,
        "status",
        lambda _: {"configured": configured, "ready": ready, "dashboard": manager.WEB},
    )
    if configured and ready:
        cli.main(["--home", str(home), "dashboard"])
        assert json.loads(capsys.readouterr().out)["ready"]
    else:
        with pytest.raises(SystemExit):
            cli.main(["--home", str(home), "dashboard"])
        assert json.loads(capsys.readouterr().err)["code"] == "unavailable"
    assert fingerprint(home) == before


@pytest.mark.parametrize("wait", [False, True])
def test_cli_refresh_waits_only_when_requested(home, wait, monkeypatch, capsys):
    events = []
    monkeypatch.setattr(manager, "wait_dashboard", lambda _: events.append("wait"))
    monkeypatch.setattr(
        manager,
        "refresh_connections",
        lambda _: events.append("refresh") or {"connected": True},
    )
    cli.main(
        [
            "--home",
            str(home),
            "refresh-connections",
            *(["--wait-ready"] if wait else []),
        ]
    )
    assert json.loads(capsys.readouterr().out)["connected"]
    assert events == (["wait", "refresh"] if wait else ["refresh"])


def test_cli_preparation_uses_the_explicit_state_home(home, monkeypatch, capsys):
    prepare = Mock(return_value={"initialized": True})
    monkeypatch.setattr(manager, "prepare_managed", prepare)
    image = manager.IMAGE_PREFIX + "a" * 64
    cli.main(["--home", str(home), "prepare-managed", "--image", image])
    prepare.assert_called_once_with(home, image)
    assert json.loads(capsys.readouterr().out)["initialized"]


@pytest.mark.parametrize("approved", [False, True])
def test_cli_registration_requires_local_approval(home, approved, monkeypatch, capsys):
    monkeypatch.setattr(
        connector, "profiles", lambda _: {"fixture": {}} if approved else {}
    )
    register = Mock(return_value={"id": "fixture", "connected": True})
    monkeypatch.setattr(manager, "register_target", register)
    args = ["--home", str(home), "register", "fixture", "--name", "Synthetic MCP"]
    if approved:
        cli.main(args)
        register.assert_called_once_with(home, "fixture", "Synthetic MCP")
        assert json.loads(capsys.readouterr().out)["connected"]
    else:
        with pytest.raises(SystemExit):
            cli.main(args)
        register.assert_not_called()
        assert "error" in json.loads(capsys.readouterr().err)


def test_cli_revocation_uses_only_the_scoped_admin_endpoint(home, monkeypatch, capsys):
    admin = Mock(return_value={"revoked": True})
    monkeypatch.setattr(manager, "admin", admin)
    cli.main(["--home", str(home), "revoke", "computer-fixture"])
    admin.assert_called_once_with(
        home, "POST", "/admin/revoke", {"id": "computer-fixture"}
    )
    assert json.loads(capsys.readouterr().out)["revoked"]


@pytest.mark.parametrize("failure", [KeyboardInterrupt(), asyncio.CancelledError()])
def test_cli_interruption_does_not_emit_partial_or_private_output(
    home, failure, monkeypatch, capsys
):
    monkeypatch.setattr(manager, "status", Mock(side_effect=failure))
    cli.main(["--home", str(home), "status"])
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        "private",
        {"schema": 2},
        {"schema": 1, "mode": "existing", "configured": 1},
        {
            "schema": 1,
            "mode": "managed",
            "configured": True,
            "dashboard": "http://127.0.0.1:9473",
        },
        {"schema": 1, "mode": "managed", "configured": True, "dashboard": manager.WEB},
    ],
)
def test_corrupt_selection_is_rejected_without_rewriting_any_file(tmp_path, data):
    path = tmp_path / "installation.json"
    original = json.dumps(data).encode()
    path.write_bytes(original)
    with pytest.raises(installation.InstallationError) as error:
        installation.selection(tmp_path)
    assert error.value.code == "invalid_selection"
    assert path.read_bytes() == original
    assert not (tmp_path / "stack").exists()


@pytest.mark.parametrize("candidate", ["path", "user", "desktop", "absent"])
def test_docker_discovery_checks_executable_permissions_and_standard_locations(
    candidate, monkeypatch, tmp_path
):
    monkeypatch.setattr(manager.shutil, "which", lambda _: "/synthetic/docker")
    monkeypatch.setattr(manager.Path, "home", lambda: tmp_path)
    expected = {
        "path": "/synthetic/docker",
        "user": str(tmp_path / ".docker/bin/docker"),
        "desktop": "/Applications/Docker.app/Contents/Resources/bin/docker",
    }.get(candidate)
    monkeypatch.setattr(manager.Path, "is_file", lambda path: str(path) == expected)
    monkeypatch.setattr(manager.os, "access", lambda path, _: str(path) == expected)
    if expected:
        assert manager.docker_binary() == expected
    else:
        with pytest.raises(ValueError, match="Docker Desktop"):
            manager.docker_binary()


def test_nonempty_stack_is_not_adopted_or_overwritten(tmp_path):
    stack = tmp_path / "stack"
    stack.mkdir()
    private = stack / "synthetic-settings"
    private.write_bytes(b"preserve")
    with pytest.raises(ValueError, match="empty"):
        manager.initialize(tmp_path, manager.IMAGE_PREFIX + "a" * 64)
    assert private.read_bytes() == b"preserve"
    assert not (stack / "managed.json").exists()


@pytest.mark.parametrize("name", ["compose.yaml", ".env", "stack"])
def test_scoped_compose_rejects_redirected_managed_files_before_docker(
    home, name, monkeypatch
):
    if name == "stack":
        outside = home / "moved-stack"
        (home / "stack").rename(outside)
        (home / "stack").symlink_to(outside, target_is_directory=True)
    else:
        path = home / "stack" / name
        outside = home / ("moved-" + name)
        path.rename(outside)
        path.symlink_to(outside)
    before = fingerprint(outside) if outside.is_dir() else outside.read_bytes()
    binary = Mock()
    monkeypatch.setattr(manager, "docker_binary", binary)
    with pytest.raises(ValueError):
        manager.compose(home, "stop")
    binary.assert_not_called()
    assert (
        fingerprint(outside) if outside.is_dir() else outside.read_bytes()
    ) == before


@pytest.mark.parametrize("name", ["stack", "managed.json"])
def test_prepare_rejects_symlinked_state_before_prerequisite_checks(
    home, name, monkeypatch
):
    path = home / "stack" if name == "stack" else home / "stack/managed.json"
    moved = home / "moved"
    path.rename(moved)
    path.symlink_to(moved, target_is_directory=moved.is_dir())
    requirements = Mock()
    monkeypatch.setattr(manager, "prerequisites", requirements)
    with pytest.raises(installation.InstallationError):
        manager.prepare_managed(home, manager.IMAGE_PREFIX + "a" * 64)
    requirements.assert_not_called()


def test_prepare_rejects_a_foreign_project_marker_without_reinitializing(
    home, monkeypatch
):
    marker = home / "stack/managed.json"
    write_json(marker, {"schema": 1, "project": "unrelated-project"})
    before = fingerprint(home)
    monkeypatch.setattr(manager, "prerequisites", lambda: {"ready": True})
    with pytest.raises(ValueError, match="marker"):
        manager.prepare_managed(home, manager.IMAGE_PREFIX + "a" * 64)
    assert fingerprint(home) == before


@pytest.mark.parametrize(
    "raw",
    [
        "null",
        "3",
        '"synthetic-private-value"',
        "{}",
        "[{}]",
        '[{"Service": "openmaskit"}]',
        "bad-json",
    ],
)
def test_malformed_docker_status_is_a_safe_json_failure(home, raw, monkeypatch, capsys):
    before = fingerprint(home)
    monkeypatch.setattr(manager, "compose", lambda *_a, **_k: raw)
    monkeypatch.setattr(manager, "admin", lambda *_a, **_k: {"connectors": []})
    try:
        cli.main(["--home", str(home), "status"])
    except SystemExit as error:
        assert error.code == 1
    output = capsys.readouterr()
    reply = json.loads(output.out or output.err)
    assert reply.get("ready") is not True
    assert "synthetic-private-value" not in json.dumps(reply)
    assert fingerprint(home) == before


def test_status_reports_dashboard_failure_without_losing_saved_selection(
    home, monkeypatch
):
    monkeypatch.setattr(
        manager,
        "compose",
        lambda *_a, **_k: json.dumps([{"Service": "openmaskit", "State": "running"}]),
    )
    monkeypatch.setattr(manager, "admin", lambda *_a, **_k: {"connectors": []})
    monkeypatch.setattr(
        installation,
        "probe",
        Mock(side_effect=installation.InstallationError("unavailable")),
    )
    before = fingerprint(home)
    status = manager.status(home)
    assert status["configured"] and not status["ready"]
    assert status["connection_error"] == installation.MESSAGES["unavailable"]
    assert fingerprint(home) == before


def test_compose_failure_does_not_expose_stderr_or_change_configuration(
    home, monkeypatch
):
    monkeypatch.setattr(manager, "docker_binary", lambda: "/synthetic/docker")
    monkeypatch.setattr(manager, "local_docker", lambda *_: None)
    monkeypatch.setattr(
        manager.subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            [], 1, "", "synthetic-private-command"
        ),
    )
    before = fingerprint(home)
    with pytest.raises(ValueError) as error:
        manager.compose(home, "stop")
    assert "synthetic-private-command" not in str(error.value)
    assert fingerprint(home) == before


def test_unavailable_context_prevents_daemon_and_compose_commands(monkeypatch):
    run = Mock(
        return_value=subprocess.CompletedProcess(
            [], 1, "private-context", "private-token"
        )
    )
    monkeypatch.setattr(manager.subprocess, "run", run)
    with pytest.raises(ValueError, match="context"):
        manager.local_docker("/synthetic/docker", {})
    assert run.call_count == 1


def test_dashboard_wait_retries_bounded_probes_and_stops_on_recovery(home, monkeypatch):
    probe = Mock(
        side_effect=[installation.InstallationError("unavailable"), {"ready": True}]
    )
    monkeypatch.setattr(installation, "probe", probe)
    monkeypatch.setattr(manager.time, "monotonic", lambda: 0)
    pause = Mock()
    monkeypatch.setattr(manager.time, "sleep", pause)
    before = fingerprint(home)
    manager.wait_dashboard(home)
    assert probe.call_count == 2
    pause.assert_called_once_with(0.25)
    assert fingerprint(home) == before


@respx.mock
@pytest.mark.parametrize("name,connected", [("✨", True), ("Fixture", False)])
def test_registration_rejects_unusable_names_and_unconnected_results(
    home, name, connected, monkeypatch
):
    write_json(home / "connection.json", {"id": "computer-fixture"})
    monkeypatch.setattr(
        manager,
        "admin",
        lambda *_a, **_k: {
            "connectors": [
                {
                    "id": "computer-fixture",
                    "connected": True,
                    "profiles": {"fixture": "Fixture"},
                }
            ]
        },
    )
    respx.get(manager.WEB + "/api/csrf").respond(200, json={"token": "synthetic"})
    create = respx.post(manager.WEB + "/api/targets/custom").respond(
        201, json={"connected": connected}
    )
    with pytest.raises(ValueError):
        manager.register_target(home, "fixture", name)
    assert create.call_count == (0 if name == "✨" else 1)


@respx.mock
def test_registration_recovers_an_inactive_owned_target_without_deleting_it(
    home, monkeypatch
):
    write_json(home / "connection.json", {"id": "computer-fixture"})
    monkeypatch.setattr(
        manager,
        "admin",
        lambda *_a, **_k: {
            "connectors": [
                {
                    "id": "computer-fixture",
                    "connected": True,
                    "profiles": {"fixture": "Fixture"},
                }
            ]
        },
    )
    url = "http://connector-relay:9495/mcp/computer-fixture/fixture"
    respx.get(manager.WEB + "/api/csrf").respond(200, json={"token": "synthetic"})
    respx.post(manager.WEB + "/api/targets/custom").respond(409)
    respx.get(manager.WEB + "/api/targets/custom/fixture").respond(
        200, json={"config": {"url": url}}
    )
    respx.get(manager.WEB + "/health").respond(200, json={"targets": []})
    activate = respx.post(manager.WEB + "/api/targets/custom/fixture/activate").respond(
        200, json={"connected": True}
    )
    before = fingerprint(home)
    assert manager.register_target(home, "fixture", "Fixture")["connected"]
    assert activate.call_count == 1
    assert fingerprint(home) == before
    assert all(call.request.method not in {"DELETE", "PUT"} for call in respx.calls)


@respx.mock
@pytest.mark.parametrize("status", [200, 401, 503])
def test_admin_uses_private_admin_credential_and_preserves_state(home, status):
    before = fingerprint(home)
    settings = json.loads((home / "stack/relay/relay.json").read_text())
    route = respx.get(manager.RELAY + "/admin/connectors").respond(
        status, json={"connectors": []}
    )
    if status == 200:
        assert manager.admin(home, "GET", "/admin/connectors") == {"connectors": []}
    else:
        with pytest.raises(httpx.HTTPStatusError):
            manager.admin(home, "GET", "/admin/connectors")
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer " + settings["admin_token"]
    assert settings["proxy_token"] not in str(request.headers)
    assert fingerprint(home) == before
