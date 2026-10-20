from unittest.mock import patch

import httpx
import pytest
import respx

from openmaskit_companion import manager
from openmaskit_companion.state import write_json


@pytest.fixture
def host(tmp_path):
    write_json(tmp_path / "connection.json", {"id": "computer-test", "token": "synthetic-token"})
    write_json(tmp_path / "stack/relay/relay.json", {"proxy_token": "synthetic-proxy-token"})
    return tmp_path


@respx.mock
def test_existing_openmaskit_api_registration_contract(host):
    respx.get(manager.WEB + "/api/csrf").respond(200, json={"token": "synthetic-csrf"})
    create = respx.post(manager.WEB + "/api/targets/custom").respond(201, json={"server_id": "synthetic", "connected": True, "ok": True})
    with patch.object(manager, "admin", return_value={"connectors": [{"id": "computer-test", "connected": True, "profiles": {"fixture": "Fixture"}}]}):
        assert manager.register_target(host, "fixture", "Synthetic") == {"id": "synthetic", "connected": True}
    request = create.calls[0].request
    assert request.headers["Origin"] == manager.WEB
    assert request.headers["X-CSRF-Token"] == "synthetic-csrf"
    assert b'"type":"secret"' in request.content


@respx.mock
def test_unrelated_target_is_never_replaced(host):
    respx.get(manager.WEB + "/api/csrf").respond(200, json={"token": "synthetic-csrf"})
    respx.post(manager.WEB + "/api/targets/custom").respond(409)
    respx.get(manager.WEB + "/api/targets/custom/synthetic").respond(200, json={"config": {"url": "https://other.example/mcp"}})
    with patch.object(manager, "admin", return_value={"connectors": [{"id": "computer-test", "connected": True, "profiles": {"fixture": "Fixture"}}]}):
        with pytest.raises(ValueError):
            manager.register_target(host, "fixture", "Synthetic")


@respx.mock
def test_registration_requires_connected_approved_profile(host):
    with patch.object(manager, "admin", return_value={"connectors": [{"id": "computer-test", "connected": False, "profiles": {}}]}):
        with pytest.raises(ValueError):
            manager.register_target(host, "fixture", "Synthetic")
    assert not respx.calls


@respx.mock
def test_existing_initialized_exact_target_is_idempotent(host):
    respx.get(manager.WEB + "/api/csrf").respond(200, json={"token": "synthetic-csrf"})
    create = respx.post(manager.WEB + "/api/targets/custom").respond(409)
    existing = respx.get(manager.WEB + "/api/targets/custom/synthetic").respond(
        200, json={"config": {"url": "http://connector-relay:9495/mcp/computer-test/fixture"}})
    health = respx.get(manager.WEB + "/health").respond(200, json={"targets": [
        {"name": "synthetic", "initialized": True}]})
    with patch.object(manager, "admin", return_value={"connectors": [
            {"id": "computer-test", "connected": True, "profiles": {"fixture": "Fixture"}}]}):
        assert manager.register_target(host, "fixture", "Synthetic") == {"id": "synthetic", "connected": True}
    assert create.called and existing.called and health.called
    assert not respx.post(manager.WEB + "/api/targets/custom/synthetic/deactivate").called
    assert not respx.post(manager.WEB + "/api/targets/custom/synthetic/activate").called


@respx.mock
def test_disconnected_exact_target_reactivates_without_replacing_config(host):
    url = "http://connector-relay:9495/mcp/computer-test/fixture"
    respx.get(manager.WEB + "/api/csrf").respond(200, json={"token": "synthetic-csrf"})
    respx.post(manager.WEB + "/api/targets/custom").respond(409)
    respx.get(manager.WEB + "/api/targets/custom/synthetic").respond(
        200, json={"config": {"url": url, "headers": {"Authorization": "secret"}}})
    respx.get(manager.WEB + "/health").respond(200, json={"targets": [
        {"name": "synthetic", "initialized": False}]})
    deactivate = respx.post(manager.WEB + "/api/targets/custom/synthetic/deactivate").respond(200, json={"ok": True})
    activate = respx.post(manager.WEB + "/api/targets/custom/synthetic/activate").respond(
        200, json={"server_id": "synthetic", "connected": True})
    with patch.object(manager, "admin", return_value={"connectors": [
            {"id": "computer-test", "connected": True, "profiles": {"fixture": "Fixture"}}]}):
        assert manager.register_target(host, "fixture", "Synthetic") == {"id": "synthetic", "connected": True}
    assert deactivate.called and activate.called
