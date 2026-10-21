"""Contract tests for the Mac app's actual backend, including packaged builds."""

import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from openmaskit_connector.relay import create_app
from openmaskit_connector.state import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "action",
    [
        "docker-status",
        "start-dependencies",
        "start-installed",
        "wait-services",
        "connector-status",
        "keep-connections",
        "refresh-connections",
    ],
)
def test_packaged_startup_helpers_never_initialize_a_fresh_installation(
    tmp_path, action
):
    result = subprocess.run(
        command(tmp_path, action), text=True, capture_output=True, timeout=30
    )
    assert result.returncode == 1
    assert json.loads(result.stderr)["code"] == "not_configured"
    assert not list(tmp_path.iterdir())


def command(home, *args):
    executable = os.environ.get("COMPANION_BINARY")
    prefix = (
        [executable]
        if executable
        else [sys.executable, "-m", "openmaskit_companion.cli"]
    )
    return [*prefix, "--home", str(home), *args]


def invoke(home, *args, text=None):
    result = subprocess.run(
        command(home, *args), input=text, text=True, capture_output=True, timeout=30
    )
    assert result.returncode == 0, "App backend action failed: " + args[0]
    return json.loads(result.stdout)


def test_approved_profiles_survive_the_repository_split(tmp_path):
    profile = tmp_path / "synthetic-profile.json"
    write_json(profile, {"command": sys.executable, "args": ["synthetic"]})
    assert (
        invoke(
            tmp_path,
            "approve",
            "fixture",
            "--name",
            "Fixture",
            "--profile",
            str(profile),
            "--yes",
        )["approved"]
        == "fixture"
    )
    original = (tmp_path / "profiles.json").read_bytes()
    assert invoke(tmp_path, "profiles") == {
        "profiles": [{"id": "fixture", "name": "Fixture"}]
    }
    assert (tmp_path / "profiles.json").read_bytes() == original
    assert invoke(tmp_path, "forget", "fixture")["removed"] == "fixture"
    assert read_json(tmp_path / "profiles.json") == {}


def test_app_default_home_remains_the_existing_companion_directory(
    monkeypatch, tmp_path
):
    from openmaskit_connector import cli as connector_cli

    from openmaskit_companion import cli

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    calls = []
    monkeypatch.setattr(connector_cli, "main", lambda args: calls.append(args))
    cli.main(["profiles"])
    assert calls == [["--home", str(tmp_path / ".openmaskit-companion"), "profiles"]]


@asynccontextmanager
async def relay(home):
    settings = {
        "admin_token": secrets.token_urlsafe(32),
        "proxy_token": secrets.token_urlsafe(32),
        "connectors": {},
    }
    path = home / "relay/relay.json"
    write_json(path, settings)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(path),
            access_log=False,
            log_level="critical",
            ws_max_size=1_048_576,
        )
    )
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{sock.getsockname()[1]}", settings
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 15)
        sock.close()


async def test_app_backend_pairs_and_runs_external_connector(tmp_path):
    async with relay(tmp_path) as (endpoint, settings):
        async with httpx.AsyncClient(base_url=endpoint, trust_env=False) as api:
            api.headers["Authorization"] = "Bearer " + settings["admin_token"]
            response = await api.post("/admin/pairings", json={"name": "Synthetic Mac"})
            code = response.json()["code"]
            paired = await asyncio.to_thread(
                invoke,
                tmp_path,
                "pair",
                "--endpoint",
                endpoint,
                "--code-stdin",
                text=code + "\n",
            )
            assert paired["paired"]
            profile = tmp_path / "fixture.json"
            write_json(
                profile,
                {
                    "command": sys.executable,
                    "args": [str(ROOT / "tests/fixture_mcp.py")],
                },
            )
            await asyncio.to_thread(
                invoke,
                tmp_path,
                "approve",
                "fixture",
                "--name",
                "Fixture",
                "--profile",
                str(profile),
                "--yes",
            )
            process = await asyncio.create_subprocess_exec(
                *command(tmp_path, "connect"),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                async with asyncio.timeout(20):
                    while True:
                        online = (await api.get("/admin/connectors")).json()[
                            "connectors"
                        ]
                        if any(row["connected"] for row in online):
                            break
                        assert process.returncode is None
                        await asyncio.sleep(0.05)
                async with (
                    httpx.AsyncClient(
                        headers={"Authorization": "Bearer " + settings["proxy_token"]},
                        trust_env=False,
                    ) as mcp_http,
                    streamable_http_client(
                        f"{endpoint}/mcp/{paired['id']}/fixture", http_client=mcp_http
                    ) as (read, write, _),
                ):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(
                            "greet", {"name": "Synthetic Mac"}
                        )
                        assert result.content[0].text == "Hello Synthetic Mac"
                assert code not in json.dumps(
                    await asyncio.to_thread(invoke, tmp_path, "profiles")
                )
            finally:
                if process.returncode is None:
                    process.terminate()
                await asyncio.wait_for(process.wait(), 15)
            async with asyncio.timeout(10):
                while any(
                    row["connected"]
                    for row in (await api.get("/admin/connectors")).json()["connectors"]
                ):
                    await asyncio.sleep(0.05)


def test_backend_default_home_reads_existing_companion_profiles_only(tmp_path):
    write_json(
        tmp_path / ".openmaskit-companion/profiles.json",
        {"existing": {"name": "Existing Mac", "command": sys.executable}},
    )
    write_json(
        tmp_path / ".openmaskit-connector/profiles.json",
        {"standalone": {"name": "Standalone", "command": sys.executable}},
    )
    executable = os.environ.get("COMPANION_BINARY")
    prefix = (
        [executable]
        if executable
        else [sys.executable, "-m", "openmaskit_companion.cli"]
    )
    result = subprocess.run(
        [*prefix, "profiles"],
        env={**os.environ, "HOME": str(tmp_path)},
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "profiles": [{"id": "existing", "name": "Existing Mac"}]
    }


async def test_packaged_connection_preserves_settings_and_supports_offline_restart(
    tmp_path,
):
    """An actual CLI process connects without creating a stack or mutating a store."""
    import sqlite3

    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    store = tmp_path / "existing-openmaskit.db"
    with sqlite3.connect(store) as database:
        database.executescript(
            "CREATE TABLE rules (path TEXT, prefix TEXT); INSERT INTO rules VALUES ('messages.author','header'); CREATE TABLE settings (name TEXT,value TEXT); INSERT INTO settings VALUES ('analyzer','synthetic-presidio');"
        )
    before = store.read_bytes()
    requests = []

    async def health(request):
        requests.append((request.method, request.url.path))
        return JSONResponse(
            {
                "status": "healthy",
                "database": {"connected": True},
                "targets": [{"initialized": True}],
            }
        )

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    address = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(
        uvicorn.Config(
            Starlette(routes=[Route("/health", health)]),
            access_log=False,
            log_level="critical",
        )
    )
    task = asyncio.create_task(server.serve(sockets=[sock]))
    home = tmp_path / "viewer"
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        connected = await asyncio.to_thread(
            invoke, home, "connect-existing", "--url", address
        )
        assert connected["configured"]
        state = await asyncio.to_thread(invoke, home, "status")
        assert state["ready"] and state["mode"] == "existing"
        assert not state["can_manage_services"]
        assert (await asyncio.to_thread(invoke, home, "dashboard"))[
            "dashboard"
        ] == address
        assert not (home / "stack").exists()
        assert store.read_bytes() == before
        assert all(item == ("GET", "/health") for item in requests)
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 15)
        sock.close()
    state = await asyncio.to_thread(invoke, home, "status")
    assert state["configured"] and not state["ready"] and state["dashboard"] == address
    assert store.read_bytes() == before
