"""Exercise a real legacy HTTP relay to verified TLS upgrade in a disposable stack.

Requires Docker, the locally built ``openmaskit-connector:candidate`` image,
and the pinned OpenMaskit image in ``data/release.json``. All state and volumes
are synthetic and scoped to one generated Compose project.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import yaml
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from openmaskit_connector.pairing import pair
from openmaskit_connector.state import private_dir, read_json, write_json

from openmaskit_companion import installation, manager, relay_upgrade

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_IMAGE = "openmaskit-connector:candidate"
FAKE_PINNED_IMAGE = manager.IMAGE_PREFIX + "0" * 64


def reserve_ports():
    sockets = [socket.socket() for _ in range(3)]
    try:
        for item in sockets:
            item.bind(("127.0.0.1", 0))
        return [item.getsockname()[1] for item in sockets]
    finally:
        for item in sockets:
            item.close()


def legacy_compose(home: Path, web: int, mcp: int, relay: int):
    """Restore the packaged pre-TLS Compose definition with isolated host ports."""
    path = home / "stack/compose.yaml"
    # Initialize created TLS files. Remove only those generated files so the
    # initialized project accurately represents an existing legacy install.
    for relative in (
        "stack/tls",
        "stack/tls.json",
        "stack/secure_openmaskit.py",
        "tls-authority",
    ):
        target = home / relative
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)
    template = (ROOT / "src/openmaskit_companion/data/compose.yaml").read_text()
    config = yaml.safe_load(template)
    proxy = config["services"]["openmaskit"]
    proxy["environment"]["OPENMASKIT_WEB_PORT"] = str(web)
    proxy["environment"]["OPENMASKIT_MCP_PORT"] = str(mcp)
    proxy["command"] = [
        {"9493": str(web), "9494": str(mcp)}.get(str(value), value)
        for value in proxy["command"]
    ]
    proxy["ports"] = [f"127.0.0.1:{web}:{web}", f"127.0.0.1:{mcp}:{mcp}"]
    config["services"]["connector-relay"]["ports"] = [f"127.0.0.1:{relay}:9495"]
    path.write_text(yaml.safe_dump(config, sort_keys=False))


def api_client(base: str):
    return httpx.Client(
        base_url=base,
        trust_env=False,
        timeout=30,
    )


def post(api: httpx.Client, path: str, data: dict):
    if "X-CSRF-Token" not in api.headers:
        token_response = api.get("/api/csrf")
        token_response.raise_for_status()
        api.headers["Origin"] = str(api.base_url).rstrip("/")
        api.headers["X-CSRF-Token"] = token_response.json()["token"]
    response = api.post(path, json=data)
    response.raise_for_status()
    return response.json()


def table_snapshot(database: Path):
    """Capture every SQLite table and its schema in a deterministic value form."""
    with sqlite3.connect(database) as db:
        names = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            if not row[0].startswith("sqlite_")
        ]
        snapshot = {}
        for name in names:
            escaped = '"' + name.replace('"', '""') + '"'
            columns = [row[1] for row in db.execute(f"PRAGMA table_info({escaped})")]
            rows = [tuple(row) for row in db.execute(f"SELECT * FROM {escaped}")]
            snapshot[name] = {
                "columns": columns,
                "rows": sorted(rows, key=repr),
            }
        return snapshot


def expect_only_target_url_upgrade(before, target_id: str, old_url: str):
    """Build the exact expected full DB snapshot after the allowed URL edit."""
    # Keep actual SQLite value types, including BLOBs, while copying the structure.
    import copy

    expected = copy.deepcopy(before)
    table = expected.get("mcp_servers")
    assert table is not None, "OpenMaskit store has no mcp_servers table"
    columns = table["columns"]
    assert "id" in columns and "config_json" in columns
    id_index, config_index = columns.index("id"), columns.index("config_json")
    changed = 0
    rows = []
    for row in table["rows"]:
        values = list(row)
        if values[id_index] == target_id:
            config = json.loads(values[config_index])
            assert config.get("url") == old_url
            config["url"] = old_url.replace("http://", "https://", 1)
            values[config_index] = json.dumps(config)
            changed += 1
        rows.append(tuple(values))
    assert changed == 1, f"Expected exactly one saved target row; found {changed}"
    table["rows"] = sorted(rows, key=repr)
    return expected


async def mcp_call(port: int, target: str, tool: str, arguments: dict):
    async with streamable_http_client(f"http://127.0.0.1:{port}/{target}/mcp") as (
        read,
        write,
        _,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(tool, arguments)


def main(candidate_image: str = CANDIDATE_IMAGE):
    if candidate_image != CANDIDATE_IMAGE:
        raise ValueError(
            "Only the fixed synthetic connector candidate image is allowed"
        )

    web_port, mcp_port, relay_port = reserve_ports()
    manager.WEB = installation.MANAGED_URL = f"http://127.0.0.1:{web_port}"
    manager.MCP = f"http://127.0.0.1:{mcp_port}"
    manager.RELAY = f"https://127.0.0.1:{relay_port}"

    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    original_preflight = relay_upgrade.preflight
    original_set_image = relay_upgrade._set_image

    with tempfile.TemporaryDirectory(
        prefix="relay-upgrade-acceptance-", dir=runtime
    ) as directory:
        home = Path(directory)
        home.chmod(0o700)
        connector = None
        project = None

        def run_connector(*args, timeout=30):
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "openmaskit_connector.cli",
                    "--home",
                    str(home),
                    *args,
                ],
                text=True,
                capture_output=True,
                timeout=timeout,
            )
            if result.returncode:
                raise RuntimeError("Synthetic connector action failed: " + args[0])
            return json.loads(result.stdout) if result.stdout.strip() else {}

        def candidate_preflight(image):
            assert image == FAKE_PINNED_IMAGE
            binary = manager.docker_binary()
            manager.local_docker(binary, os.environ)
            result = subprocess.run(
                [
                    binary,
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--read-only",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges",
                    candidate_image,
                    "relay",
                    "--help",
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if (
                result.returncode
                or "--tls-cert" not in result.stdout
                or "--tls-key" not in result.stdout
            ):
                raise RuntimeError("The fixed candidate image does not support TLS")

        def set_candidate_image(destination, image):
            assert image == FAKE_PINNED_IMAGE
            original_set_image(destination, candidate_image)

        try:
            # initialize() supplies valid Companion-owned layout and secrets.
            # A fake digest is never pulled: the disposable .env is immediately
            # set to the fixed, already-built candidate image below.
            assert manager.initialize(home, FAKE_PINNED_IMAGE)["initialized"]
            legacy_compose(home, web_port, mcp_port, relay_port)
            env_file = home / "stack/.env"
            env_lines = env_file.read_text().splitlines()
            env_file.write_text(
                "\n".join(
                    "COMPANION_IMAGE=" + candidate_image
                    if line.startswith("COMPANION_IMAGE=")
                    else line
                    for line in env_lines
                )
                + "\n"
            )
            installation.save(home, "managed", manager.WEB)
            marker = read_json(home / "stack/managed.json")
            project = marker["project"]
            assert project.startswith(manager.PROJECT + "-")

            manager.compose(home, "up", "--detach", "--wait", "--wait-timeout", "300")
            running = manager.status(home)
            assert len(running["services"]) == 3 and all(
                service["health"] == "healthy" for service in running["services"]
            )

            settings = read_json(home / "stack/relay/relay.json")
            legacy_relay = f"http://127.0.0.1:{relay_port}"
            with httpx.Client(
                base_url=legacy_relay, trust_env=False, timeout=10
            ) as api:
                response = api.post(
                    "/admin/pairings",
                    headers={"Authorization": "Bearer " + settings["admin_token"]},
                    json={"name": "Synthetic upgrade acceptance"},
                )
                response.raise_for_status()
                code = response.json()["code"]
            paired_result = pair(home, legacy_relay, code)
            paired = read_json(home / "connection.json")
            assert paired_result["paired"] and paired["endpoint"] == legacy_relay

            profile = home / "synthetic-profile.json"
            write_json(
                profile,
                {
                    "command": sys.executable,
                    "args": [str(ROOT / "tests/fixture_mcp.py")],
                },
            )
            run_connector(
                "approve",
                "fixture",
                "--name",
                "Synthetic fixture",
                "--profile",
                str(profile),
                "--yes",
            )
            connector = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "openmaskit_connector.cli",
                    "--home",
                    str(home),
                    "connect",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 20
            while True:
                if connector.poll() is not None:
                    raise RuntimeError("Synthetic legacy connector exited unexpectedly")
                with httpx.Client(
                    base_url=legacy_relay, trust_env=False, timeout=5
                ) as api:
                    response = api.get(
                        "/admin/connectors",
                        headers={"Authorization": "Bearer " + settings["admin_token"]},
                    )
                    response.raise_for_status()
                    records = response.json()["connectors"]
                if any(
                    row["id"] == paired["id"] and row["connected"] for row in records
                ):
                    break
                assert time.monotonic() < deadline, "Legacy connector did not pair"
                time.sleep(0.1)

            target_id = "synthetic-fixture"
            legacy_target_url = (
                f"http://connector-relay:9495/mcp/{paired['id']}/fixture"
            )
            with api_client(manager.WEB) as api:
                target = post(
                    api,
                    "/api/targets/custom",
                    {
                        "name": "Synthetic fixture",
                        "transport": "http",
                        "url": legacy_target_url,
                        "headers": {
                            "Authorization": {
                                "type": "secret",
                                "value": "Bearer " + settings["proxy_token"],
                            }
                        },
                    },
                )
                assert target["connected"], "Legacy HTTP MCP target did not connect"
                target_id = target.get("server_id", target_id)
                post(
                    api,
                    f"/api/targets/{target_id}/rules/create",
                    {
                        "tool_name": "*",
                        "field_path": "messages.author",
                        "alias_prefix": "header",
                    },
                )
                provider = post(
                    api,
                    "/api/privacy/providers/create",
                    {
                        "name": "Synthetic analyzer",
                        "endpoint": "http://presidio-analyzer:3000",
                    },
                )
                check = post(
                    api,
                    "/api/privacy/checks/create",
                    {
                        "name": "Synthetic names",
                        "provider_id": provider["id"],
                        "entities": ["PERSON"],
                    },
                )
                post(
                    api,
                    f"/api/targets/{target_id}/privacy/assignments/create",
                    {"check_id": check["id"]},
                )
                before_rules = api.get(f"/api/targets/{target_id}/rules").json()
                before_privacy = api.get("/api/privacy").json()

            # Verify masking and alias reversal before the upgrade, then stop all
            # processes so the persistent volume has a stable SQLite snapshot.
            baseline = asyncio.run(
                mcp_call(mcp_port, target_id, "greet", {"name": "Sarah Johnson"})
            )
            assert "Sarah Johnson" not in baseline.model_dump_json()
            assert "person_1" in baseline.model_dump_json()
            reversed_alias = asyncio.run(
                mcp_call(mcp_port, target_id, "digest", {"text": "person_1"})
            )
            assert (
                reversed_alias.content[0].text
                == hashlib.sha256(b"Sarah Johnson").hexdigest()
            )

            connector.terminate()
            connector.wait(timeout=15)
            connector = None
            write_json(home / "connector-status.json", {"connected": False})
            manager.compose(home, "stop", "--timeout", "45")

            before_dir = private_dir(home / "snapshot-before")
            manager.compose(
                home,
                "cp",
                "openmaskit:/home/openmaskit/.openmaskit/.",
                str(before_dir),
                timeout=180,
            )
            before_db = before_dir / "store.db"
            before_key = before_dir / ".key"
            assert before_db.is_file() and before_key.is_file()
            before_tables = table_snapshot(before_db)
            expected_tables = expect_only_target_url_upgrade(
                before_tables, target_id, legacy_target_url
            )
            key_before = before_key.read_bytes()
            relay_before = read_json(home / "stack/relay/relay.json")
            connection_before = read_json(home / "connection.json")
            profiles_before = read_json(home / "profiles.json")

            relay_upgrade.preflight = candidate_preflight
            relay_upgrade._set_image = set_candidate_image
            upgraded = relay_upgrade.upgrade(home, FAKE_PINNED_IMAGE)
            assert upgraded["upgraded"] and upgraded["upgraded_connections"] == 1
            assert read_json(home / "stack/relay/relay.json") == relay_before
            connection_after = read_json(home / "connection.json")
            expected_connection = dict(connection_before)
            expected_connection.update(
                endpoint=manager.RELAY,
                ca_file=str(home / "stack/tls/ca.pem"),
            )
            assert connection_after == expected_connection
            assert read_json(home / "profiles.json") == profiles_before

            after_dir = private_dir(home / "snapshot-after")
            manager.compose(
                home,
                "cp",
                "openmaskit:/home/openmaskit/.openmaskit/.",
                str(after_dir),
                timeout=180,
            )
            after_db = after_dir / "store.db"
            assert (
                after_db.is_file() and (after_dir / ".key").read_bytes() == key_before
            )
            assert table_snapshot(after_db) == expected_tables, (
                "OpenMaskit store changed outside the owned target URL scheme"
            )

            # Resume only this generated project with its verified TLS config.
            manager.compose(
                home,
                "up",
                "--detach",
                "--pull",
                "never",
                "--wait",
                "--wait-timeout",
                "300",
                "presidio-analyzer",
                "connector-relay",
            )
            connector = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "openmaskit_connector.cli",
                    "--home",
                    str(home),
                    "connect",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 20
            while not manager.connector_status(home)["connected"]:
                if connector.poll() is not None:
                    raise RuntimeError("Synthetic TLS connector exited unexpectedly")
                assert time.monotonic() < deadline, "TLS connector did not reconnect"
                time.sleep(0.1)
            manager.compose(home, "up", "--detach", "--pull", "never", "openmaskit")
            manager.wait_dashboard(home)
            deadline = time.monotonic() + 45
            while True:
                services = manager.status(home)["services"]
                if len(services) == 3 and all(
                    service["health"] == "healthy" for service in services
                ):
                    break
                assert time.monotonic() < deadline, json.dumps(services)
                time.sleep(0.5)
            finished = manager.finish_start(home)
            assert finished["ready"] and finished["relay_tls"], json.dumps(finished)
            assert manager.refresh_connections(home)["refreshed"] == 1
            assert manager.keep_connections(home) == {
                "connected": True,
                "checked": 1,
                "failed": 0,
            }

            masked = asyncio.run(
                mcp_call(mcp_port, target_id, "greet", {"name": "Sarah Johnson"})
            )
            assert "Sarah Johnson" not in masked.model_dump_json()
            assert "person_1" in masked.model_dump_json()
            digest = asyncio.run(
                mcp_call(mcp_port, target_id, "digest", {"text": "person_1"})
            )
            assert (
                digest.content[0].text == hashlib.sha256(b"Sarah Johnson").hexdigest()
            )
            with api_client(manager.WEB) as api:
                assert api.get(f"/api/targets/{target_id}/rules").json() == before_rules
                assert api.get("/api/privacy").json() == before_privacy

            manager.compose(home, "stop", "--timeout", "45")
            print(
                "PASS: legacy HTTP pairing and target; URL-only migration with full SQLite/key preservation; verified TLS restart, connector reconnection, keepalive, masking, alias reversal, rules and privacy settings."
            )
        finally:
            relay_upgrade.preflight = original_preflight
            relay_upgrade._set_image = original_set_image
            if connector is not None and connector.poll() is None:
                connector.terminate()
                try:
                    connector.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    connector.kill()
                    connector.wait()
            if project and (home / "stack/managed.json").is_file():
                manager.compose(home, "down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=CANDIDATE_IMAGE)
    main(parser.parse_args().image)
