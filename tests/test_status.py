import json

from openmaskit_companion import manager
from openmaskit_companion.state import write_json


def managed_home(tmp_path):
    write_json(tmp_path / "stack/managed.json", {
        "project": manager.PROJECT, "schema": 1, "automatic_updates": False,
        "release": {"relay": "synthetic"},
    })
    return tmp_path


def test_status_summarizes_services_without_exposing_state(monkeypatch, tmp_path):
    home = managed_home(tmp_path)
    secret = "synthetic-admin-token"
    monkeypatch.setattr(manager, "compose", lambda *_args, **_kwargs:
                        json.dumps([{"Service": "openmaskit", "State": "running", "Health": "healthy",
                                     "Command": secret}]))
    monkeypatch.setattr(manager, "admin", lambda *_args, **_kwargs: {
        "connectors": [{"id": "computer-test", "name": "Synthetic", "connected": True,
                        "profiles": ["fixture"], "token": secret}]})
    result = manager.status(home)
    assert result["services"] == [{"name": "openmaskit", "state": "running", "health": "healthy"}]
    assert result["connectors"][0]["id"] == "computer-test"
    assert secret not in json.dumps(result)


def test_status_handles_invalid_docker_response_and_redacts_errors(monkeypatch, tmp_path):
    home = managed_home(tmp_path)
    monkeypatch.setattr(manager, "compose", lambda *_args, **_kwargs: "not-json synthetic-secret")

    def fail_admin(*_args, **_kwargs):
        raise ValueError("synthetic admin token in upstream error")

    monkeypatch.setattr(manager, "admin", fail_admin)
    result = manager.status(home)
    assert result["services"] == []
    assert result["error"] == "Docker is unavailable"
    assert result["connectors"] == []
    assert "synthetic-secret" not in json.dumps(result)
    assert "synthetic admin token" not in json.dumps(result)
