import json
import subprocess
from unittest.mock import patch

import pytest
import respx
from openmaskit_connector.state import write_json

from openmaskit_companion import cli, installation, manager


@pytest.fixture
def host(tmp_path):
    manager.initialize(tmp_path, manager.IMAGE_PREFIX + "a" * 64)
    installation.save(tmp_path, "managed", manager.WEB)
    write_json(
        tmp_path / "connection.json", {"id": "computer-test", "token": "synthetic"}
    )
    write_json(
        tmp_path / "profiles.json",
        {"fixture": {"name": "Fixture", "command": "/synthetic/mcp"}},
    )
    return tmp_path


@pytest.mark.parametrize(
    "action",
    [
        "start-dependencies",
        "start-installed",
        "wait-services",
        "docker-status",
        "connector-status",
        "refresh-connections",
    ],
)
def test_automatic_start_never_initializes_a_fresh_installation(
    tmp_path, action, capsys
):
    with (
        patch.object(manager, "compose") as compose,
        patch.object(manager, "docker_binary") as binary,
    ):
        with pytest.raises(SystemExit):
            cli.main(["--home", str(tmp_path), action])
    assert json.loads(capsys.readouterr().err)["code"] == "not_configured"
    compose.assert_not_called()
    binary.assert_not_called()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "action",
    [
        "start-dependencies",
        "start-installed",
        "docker-status",
        "connector-status",
        "refresh-connections",
    ],
)
def test_existing_installation_is_never_started_or_reconnected(
    tmp_path, action, capsys
):
    installation.save(tmp_path, "existing", "http://127.0.0.1:9473")
    with (
        patch.object(manager, "compose") as compose,
        patch.object(manager, "admin") as admin,
    ):
        with pytest.raises(SystemExit):
            cli.main(["--home", str(tmp_path), action])
    assert json.loads(capsys.readouterr().err)["code"] == "external_installation"
    compose.assert_not_called()
    admin.assert_not_called()


@pytest.mark.parametrize(
    "action", ["start-dependencies", "start-installed", "wait-services"]
)
def test_start_uses_existing_project_without_pulling_or_replacing_state(
    host, action, capsys
):
    before = {p: p.read_bytes() for p in host.rglob("*") if p.is_file()}
    with (
        patch.object(manager, "compose", return_value="") as compose,
        patch.object(manager, "finish_start", return_value={"ready": True}),
    ):
        cli.main(["--home", str(host), action])
    assert json.loads(capsys.readouterr().out)["ready"]
    args = compose.call_args.args
    assert args[:4] == (host, "up", "--detach", "--pull") and args[4] == "never"
    if action == "start-dependencies":
        assert args[-2:] == ("presidio-analyzer", "connector-relay")
    if action == "start-installed":
        assert "--wait" not in args
    assert {p: p.read_bytes() for p in before} == before


@pytest.mark.parametrize("outcome", [0, 1, "timeout"])
def test_docker_probe_is_read_only_local_and_bounded(host, outcome):
    with (
        patch.object(manager, "docker_binary", return_value="/synthetic/docker"),
        patch.object(manager, "local_docker") as local,
        patch.object(subprocess, "run") as run,
    ):
        if outcome == "timeout":
            run.side_effect = subprocess.TimeoutExpired("docker", 5)
        else:
            run.return_value = subprocess.CompletedProcess(
                [], outcome, "sensitive daemon detail", ""
            )
        result = manager.docker_ready(host)
    assert result == {"ready": outcome == 0}
    local.assert_called_once()
    assert run.call_args.args[0] == [
        "/synthetic/docker",
        "info",
        "--format",
        "{{.ServerVersion}}",
    ]
    assert run.call_args.kwargs["timeout"] == 5
    assert "sensitive" not in json.dumps(result)


def test_remote_context_failure_prevents_daemon_probe(host):
    with (
        patch.object(manager, "docker_binary", return_value="/synthetic/docker"),
        patch.object(manager, "local_docker", side_effect=ValueError("remote")),
        patch.object(subprocess, "run") as run,
    ):
        with pytest.raises(ValueError):
            manager.docker_ready(host)
    run.assert_not_called()


def test_dashboard_wait_is_bounded_and_does_not_leak_probe_errors(host):
    with (
        patch.object(
            manager.installation,
            "probe",
            side_effect=installation.InstallationError("unavailable"),
        ),
        patch.object(manager.time, "monotonic", side_effect=[0, 0, 31]),
        patch.object(manager.time, "sleep") as pause,
    ):
        with pytest.raises(installation.InstallationError):
            manager.wait_dashboard(host)
    pause.assert_called_once_with(0.25)


def test_dashboard_wait_accepts_ready_database_before_mcp_repair(host):
    with (
        patch.object(manager.installation, "probe") as probe,
        patch.object(manager.time, "sleep") as pause,
    ):
        manager.wait_dashboard(host)
    probe.assert_called_once_with(manager.WEB)
    pause.assert_not_called()


def test_connector_status_only_observes_this_paired_computer(host):
    rows = {
        "connectors": [
            {"id": "unrelated", "connected": True},
            {"id": "computer-test", "connected": False},
        ]
    }
    with patch.object(manager, "admin", return_value=rows):
        assert manager.connector_status(host) == {"connected": False}
    (host / "connection.json").unlink()
    with patch.object(manager, "admin") as admin:
        assert manager.connector_status(host) == {"connected": False}
    admin.assert_not_called()


def online():
    return {
        "connectors": [
            {
                "id": "computer-test",
                "connected": True,
                "profiles": {"fixture": "Fixture"},
            }
        ]
    }


def target(name="fixture", url=None, source="custom"):
    return {
        "name": name,
        "source": source,
        "config": {
            "transport": "http",
            "url": url or "http://connector-relay:9495/mcp/computer-test/fixture",
        },
    }


@respx.mock
def test_reconnect_refreshes_only_owned_active_approved_targets(host):
    rows = [
        target(),
        target("other", "http://connector-relay:9495/mcp/other-computer/fixture"),
        target(
            "unapproved", "http://connector-relay:9495/mcp/computer-test/unapproved"
        ),
        target("inactive"),
        target("remote", "https://example.invalid/mcp"),
        target("catalog", source="marketplace"),
    ]
    respx.get(manager.WEB + "/api/targets").respond(200, json={"targets": rows})
    respx.get(manager.WEB + "/api/targets/custom/fixture").respond(
        200, json={"active": True, "config": target()["config"]}
    )
    respx.get(manager.WEB + "/api/targets/custom/inactive").respond(
        200, json={"active": False, "config": target()["config"]}
    )
    respx.get(manager.WEB + "/api/csrf").respond(200, json={"token": "synthetic-csrf"})
    down = respx.post(manager.WEB + "/api/targets/custom/fixture/deactivate").respond(
        200, json={"ok": True}
    )
    up = respx.post(manager.WEB + "/api/targets/custom/fixture/activate").respond(
        200, json={"connected": True}
    )
    before = {p: p.read_bytes() for p in host.rglob("*") if p.is_file()}
    with patch.object(manager, "admin", return_value=online()):
        assert manager.refresh_connections(host) == {"connected": True, "refreshed": 1}
    assert down.called and up.called
    assert down.calls[0].request.headers["X-CSRF-Token"] == "synthetic-csrf"
    assert {p: p.read_bytes() for p in before} == before
    assert all(
        call.request.method == "GET"
        or call.request.url.path.endswith(("/deactivate", "/activate"))
        for call in respx.calls
    )


@respx.mock
def test_offline_connector_does_not_change_targets(host):
    with patch.object(manager, "admin", return_value={"connectors": []}):
        assert manager.refresh_connections(host) == {"connected": False, "refreshed": 0}
    assert not respx.calls


@respx.mock
def test_no_matching_targets_does_not_register_new_servers(host):
    respx.get(manager.WEB + "/api/targets").respond(
        200, json={"targets": [target("remote", "https://example.invalid/mcp")]}
    )
    with patch.object(manager, "admin", return_value=online()):
        assert manager.refresh_connections(host) == {"connected": True, "refreshed": 0}
    assert len(respx.calls) == 1


@respx.mock
def test_reconnect_failure_reports_error_without_rewriting_config(host):
    respx.get(manager.WEB + "/api/targets").respond(200, json={"targets": [target()]})
    respx.get(manager.WEB + "/api/targets/custom/fixture").respond(
        200, json={"active": True, "config": target()["config"]}
    )
    respx.get(manager.WEB + "/api/csrf").respond(200, json={"token": "synthetic"})
    respx.post(manager.WEB + "/api/targets/custom/fixture/deactivate").respond(200)
    respx.post(manager.WEB + "/api/targets/custom/fixture/activate").respond(
        200, json={"connected": False}
    )
    with (
        patch.object(manager, "admin", return_value=online()),
        pytest.raises(ValueError),
    ):
        manager.refresh_connections(host)
    assert not any(call.request.method in {"PUT", "DELETE"} for call in respx.calls)


@respx.mock
def test_reconnect_is_bounded_before_changing_any_connection(host):
    rows = [target("fixture" + str(i)) for i in range(33)]
    respx.get(manager.WEB + "/api/targets").respond(200, json={"targets": rows})
    for row in rows:
        respx.get(manager.WEB + "/api/targets/custom/" + row["name"]).respond(
            200, json={"active": True, "config": row["config"]}
        )
    with (
        patch.object(manager, "admin", return_value=online()),
        pytest.raises(ValueError),
    ):
        manager.refresh_connections(host)
    assert all(call.request.method == "GET" for call in respx.calls)
