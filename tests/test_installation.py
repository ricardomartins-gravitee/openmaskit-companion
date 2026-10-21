"""Connection selection is additive; OpenMaskit stores and other stacks stay untouched."""

import copy
import json
import sqlite3
from unittest.mock import patch

import httpx
import pytest
import respx
from openmaskit_connector.state import write_json

from openmaskit_companion import cli, installation, manager

URL = installation.DEFAULT_EXISTING_URL
HEALTH = {
    "status": "healthy",
    "database": {"connected": True, "status": "healthy"},
    "targets": [],
}
IMAGE = manager.IMAGE_PREFIX + "a" * 64


def fingerprint(root):
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (URL + "/", URL),
        ("http://localhost:9473", URL),
        ("https://127.0.0.1", "https://127.0.0.1:443"),
        ("http://[::1]:9473", "http://[::1]:9473"),
        ("http://127.0.0.2:9473", "http://127.0.0.2:9473"),
    ],
)
def test_loopback_address_normalization(value, expected):
    assert installation.local_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        None,
        "http://example.com:9473",
        "http://127.0.0.1.evil.invalid:9473",
        "http://192.168.1.2:9473",
        "file:///etc/passwd",
        "ftp://127.0.0.1:9473",
        "http://user:secret@127.0.0.1:9473",
        URL + "/api/targets",
        URL + "?token=secret",
        URL + "#secret",
        URL + "\n",
        " " + URL,
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "http://127.0.0.1:bad",
        "http://[::1",
    ],
)
def test_invalid_address_fails_before_network_or_state_changes(value, tmp_path):
    with patch.object(httpx.Client, "stream") as request:
        with pytest.raises(installation.InstallationError, match="local OpenMaskit"):
            installation.connect_existing(tmp_path, value)
    request.assert_not_called()
    assert not list(tmp_path.iterdir())


@respx.mock
def test_connection_only_checks_health_and_preserves_all_existing_data(tmp_path):
    existing = tmp_path / "existing-openmaskit"
    existing.mkdir()
    database = sqlite3.connect(existing / "store.db")
    database.executescript("""CREATE TABLE rules (path TEXT, prefix TEXT); INSERT INTO rules VALUES ('messages.author','header');
        CREATE TABLE settings (name TEXT, value TEXT); INSERT INTO settings VALUES ('analyzer','synthetic-presidio');""")
    database.close()
    (existing / "encryption.key").write_bytes(b"synthetic-encryption-key")
    (existing / "openmaskit.yaml").write_text("synthetic: retained\n")
    home = tmp_path / "companion"
    manager.initialize(home, IMAGE)
    write_json(home / "profiles.json", {"fixture": {"command": "/synthetic/mcp"}})
    write_json(home / "connection.json", {"id": "fixture", "token": "synthetic-token"})
    before = fingerprint(tmp_path)
    request = respx.get(URL + "/health").respond(200, json=HEALTH)
    with (
        patch.object(manager, "compose") as docker,
        patch.object(manager, "initialize") as create,
    ):
        result = installation.connect_existing(home, URL)
        state = manager.status(home)
    docker.assert_not_called()
    create.assert_not_called()
    assert result["configured"] and state["mode"] == "existing" and state["ready"]
    assert not state["can_manage_services"] and not state["paired"]
    after = fingerprint(tmp_path)
    for name, snapshot in before.items():
        assert after[name] == snapshot, name
    assert set(after) - set(before) == {"companion/installation.json"}
    assert request.call_count == 2
    assert all(
        call.request.method == "GET" and call.request.url.path == "/health"
        for call in respx.calls
    )
    assert "synthetic-token" not in json.dumps(state)


@respx.mock
def test_connection_survives_restart_and_offline_server_without_falling_back(tmp_path):
    installation.save(tmp_path, "existing", URL)
    before = (tmp_path / "installation.json").read_bytes()
    respx.get(URL + "/health").mock(side_effect=httpx.ConnectError("synthetic secret"))
    with patch.object(manager, "compose") as docker:
        state = manager.status(tmp_path)
    docker.assert_not_called()
    assert state["configured"] and not state["ready"]
    assert state["dashboard"] == URL
    assert state["mode"] == "existing"
    assert "synthetic secret" not in state["error"]
    assert (tmp_path / "installation.json").read_bytes() == before


@respx.mock
def test_failed_replacement_preserves_previous_connection(tmp_path):
    installation.save(tmp_path, "existing", URL)
    before = (tmp_path / "installation.json").read_bytes()
    respx.get("http://127.0.0.1:9478/health").respond(
        200, json={"password": "synthetic-private"}
    )
    with pytest.raises(installation.InstallationError):
        installation.connect_existing(tmp_path, "http://127.0.0.1:9478")
    assert (tmp_path / "installation.json").read_bytes() == before


@pytest.mark.parametrize(
    "operation",
    [
        "compose",
        "admin",
        "register",
        "setup",
        "start",
        "stop",
        "pairing-code",
        "revoke",
        "pair",
        "connect",
    ],
)
def test_existing_mode_cannot_manage_or_mutate_an_installation(
    tmp_path, operation, capsys
):
    installation.save(tmp_path, "existing", URL)
    with (
        patch.object(manager, "docker_binary") as docker,
        patch.object(httpx.Client, "request") as request,
    ):
        if operation in {"compose", "admin", "register"}:
            with pytest.raises(
                installation.InstallationError, match="outside Companion"
            ):
                if operation == "compose":
                    manager.compose(tmp_path, "up", "--detach")
                if operation == "admin":
                    manager.admin(tmp_path, "POST", "/admin/pairings")
                if operation == "register":
                    manager.register_target(tmp_path, "test", "Test")
        else:
            arguments = {"setup": ["--image", IMAGE], "revoke": ["synthetic"]}.get(
                operation, []
            )
            with pytest.raises(SystemExit):
                cli.main(["--home", str(tmp_path), operation, *arguments])
            assert (
                json.loads(capsys.readouterr().err)["code"] == "external_installation"
            )
    docker.assert_not_called()
    request.assert_not_called()


@respx.mock
@pytest.mark.parametrize(
    "body",
    [
        [],
        {},
        {"status": "ok"},
        {**HEALTH, "database": []},
        {**HEALTH, "database": {"connected": 1}},
        {**HEALTH, "targets": [{}]},
        {**HEALTH, "targets": None},
    ],
)
def test_unrecognized_health_schema_is_rejected_without_saving(body, tmp_path):
    respx.get(URL + "/health").respond(200, json=body)
    with pytest.raises(installation.InstallationError, match="supported OpenMaskit"):
        installation.connect_existing(tmp_path, URL)
    assert not (tmp_path / "installation.json").exists()


@respx.mock
@pytest.mark.parametrize("status", [200, 503])
def test_unavailable_database_is_not_reported_as_ready(status, tmp_path):
    respx.get(URL + "/health").respond(
        status, json={**HEALTH, "database": {"connected": False}}
    )
    with pytest.raises(installation.InstallationError, match="database is unavailable"):
        installation.connect_existing(tmp_path, URL)
    assert not (tmp_path / "installation.json").exists()


@respx.mock
@pytest.mark.parametrize("status", [200, 503])
def test_unhealthy_mcp_does_not_prevent_opening_dashboard_to_fix_it(status, tmp_path):
    respx.get(URL + "/health").respond(
        status,
        json={
            **HEALTH,
            "status": "unhealthy",
            "targets": [{"initialized": False, "name": "synthetic-private-name"}],
        },
    )
    installation.connect_existing(tmp_path, URL)
    state = manager.status(tmp_path)
    assert (
        state["ready"] and state["server_count"] == 1 and state["health"] == "unhealthy"
    )
    assert "synthetic-private-name" not in json.dumps(state)


@respx.mock
def test_redirects_and_oversized_or_non_json_responses_are_rejected(tmp_path):
    route = respx.get(URL + "/health")
    for response in [
        httpx.Response(302, headers={"Location": "https://external.invalid/"}),
        httpx.Response(200, text="private-not-json"),
        httpx.Response(200, content=b"x" * 1_048_577),
    ]:
        route.return_value = response
        with pytest.raises(installation.InstallationError):
            installation.connect_existing(tmp_path, URL)
    assert len(respx.calls) == 3
    assert not (tmp_path / "installation.json").exists()


@respx.mock
def test_health_request_deadline_is_bounded(tmp_path, monkeypatch):
    respx.get(URL + "/health").respond(200, json=HEALTH)
    clock = iter([0, 6])
    monkeypatch.setattr(installation.time, "monotonic", lambda: next(clock))
    with pytest.raises(installation.InstallationError, match="could not be reached"):
        installation.connect_existing(tmp_path, URL)


@pytest.mark.parametrize(
    "data",
    [
        [],
        None,
        {},
        {"schema": 1, "mode": "other", "configured": True, "dashboard": URL},
        {"schema": 1, "mode": "existing", "configured": "yes", "dashboard": URL},
        {"schema": 1, "mode": "managed", "configured": True, "dashboard": URL},
    ],
)
def test_invalid_saved_connection_fails_closed(data, tmp_path):
    (tmp_path / "installation.json").write_text(json.dumps(data))
    with pytest.raises(installation.InstallationError, match="saved installation"):
        installation.selection(tmp_path)


def test_selection_cannot_be_a_symlink(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("unchanged")
    (tmp_path / "installation.json").symlink_to(outside)
    with pytest.raises(installation.InstallationError):
        installation.selection(tmp_path)
    with pytest.raises(installation.InstallationError):
        installation.save(tmp_path, "existing", URL)
    assert outside.read_text() == "unchanged"


def test_new_installations_require_completion_but_legacy_installations_keep_state(
    tmp_path, monkeypatch
):
    assert installation.selection(tmp_path)["mode"] == "unconfigured"
    manager.initialize(tmp_path, IMAGE)
    before = fingerprint(tmp_path)
    assert installation.selection(tmp_path)["configured"]
    assert fingerprint(tmp_path) == before
    monkeypatch.setattr(manager, "docker_binary", lambda: "/synthetic/docker")
    monkeypatch.setattr(manager, "local_docker", lambda *_: None)
    manager.prepare_managed(tmp_path, IMAGE)
    assert not installation.selection(tmp_path)["configured"]
    for name, value in before.items():
        assert fingerprint(tmp_path)[name] == value
    manager.prepare_managed(tmp_path, IMAGE)
    for name, value in before.items():
        assert fingerprint(tmp_path)[name] == value


def test_prepare_checks_docker_before_creating_any_state(tmp_path, monkeypatch):
    def absent():
        raise ValueError("synthetic-private-docker-error")

    monkeypatch.setattr(manager, "docker_binary", absent)
    with pytest.raises(installation.InstallationError, match="Open Docker Desktop"):
        manager.prepare_managed(tmp_path, IMAGE)
    assert not list(tmp_path.iterdir())


def test_prepare_reuses_existing_stack_and_preserves_rules_on_switch(
    tmp_path, monkeypatch
):
    manager.initialize(tmp_path, IMAGE)
    write_json(
        tmp_path / "installation.json",
        {"schema": 1, "mode": "existing", "configured": True, "dashboard": URL},
    )
    (tmp_path / "stack/synthetic-rules.db").write_bytes(b"synthetic-saved-rules")
    before = fingerprint(tmp_path / "stack")
    monkeypatch.setattr(manager, "docker_binary", lambda: "/synthetic/docker")
    monkeypatch.setattr(manager, "local_docker", lambda *_: None)
    with patch.object(manager, "initialize") as create:
        manager.prepare_managed(tmp_path, IMAGE)
    create.assert_not_called()
    assert fingerprint(tmp_path / "stack") == before
    assert installation.selection(tmp_path)["mode"] == "managed"


def test_finish_requires_health_for_all_owned_services(tmp_path, monkeypatch):
    manager.initialize(tmp_path, IMAGE)
    installation.save(tmp_path, "managed", manager.WEB, configured=False)
    good = {
        "ready": True,
        "configured": False,
        "services": [
            {"name": name, "state": "running", "health": "healthy"}
            for name in ["openmaskit", "presidio-analyzer", "connector-relay"]
        ],
    }
    bad = copy.deepcopy(good)
    bad["services"][0]["health"] = "unhealthy"
    monkeypatch.setattr(manager, "status", lambda _: bad)
    assert not manager.finish_start(tmp_path)["configured"]
    assert not installation.selection(tmp_path)["configured"]
    monkeypatch.setattr(manager, "status", lambda _: good)
    assert manager.finish_start(tmp_path)["configured"]
    assert installation.selection(tmp_path)["configured"]


def test_legacy_prepared_stack_returns_to_onboarding_without_probing_other_services(
    tmp_path, monkeypatch
):
    manager.initialize(tmp_path, IMAGE)
    monkeypatch.setattr(manager, "compose", lambda *_a, **_k: "[]")
    monkeypatch.setattr(manager, "admin", lambda *_a, **_k: {"connectors": []})
    with patch.object(installation, "probe") as probe:
        state = manager.status(tmp_path)
    probe.assert_not_called()
    assert state["mode"] == "managed" and not state["configured"] and not state["ready"]


@respx.mock
def test_cli_connect_and_dashboard_use_only_verified_saved_endpoint(tmp_path, capsys):
    request = respx.get(URL + "/health").respond(200, json=HEALTH)
    cli.main(["--home", str(tmp_path), "connect-existing", "--url", URL])
    assert json.loads(capsys.readouterr().out)["configured"]
    cli.main(["--home", str(tmp_path), "dashboard"])
    assert json.loads(capsys.readouterr().out)["dashboard"] == URL
    request.mock(side_effect=httpx.ConnectError("private diagnostic"))
    with pytest.raises(SystemExit):
        cli.main(["--home", str(tmp_path), "dashboard"])
    failure = json.loads(capsys.readouterr().err)
    assert (
        failure["code"] == "unavailable"
        and "private diagnostic" not in failure["error"]
    )


def test_unconfigured_dashboard_never_opens_a_page(tmp_path):
    with (
        patch.object(installation, "probe") as probe,
        pytest.raises(installation.InstallationError),
    ):
        installation.dashboard(tmp_path)
    probe.assert_not_called()
