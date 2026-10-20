"""Exercise actual setup/start/pair/approve/register/status/stop with synthetic data.

Requires the new per-installation project namespace. Never adopts an existing
stack. The generated installation, aliases, state and volume are disposable.
"""

import argparse
import asyncio
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from openmaskit_companion import manager
from openmaskit_companion.state import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


def main(image):
    # Fixed product ports must be free; the acceptance never displaces a service.
    for port in (9493, 9494, 9495):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    (ROOT / ".runtime").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="manager-acceptance-", dir=ROOT / ".runtime"
    ) as directory:
        home = Path(directory)
        connector = None

        def cli(*arguments, text=None):
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "openmaskit_companion.cli",
                    "--home",
                    str(home),
                    *arguments,
                ],
                input=text,
                text=True,
                capture_output=True,
                timeout=360,
            )
            if result.returncode:
                raise RuntimeError(
                    "Synthetic manager CLI action failed: " + arguments[0]
                )
            return json.loads(result.stdout)

        try:
            assert cli("setup", "--image", image)["initialized"]
            marker = read_json(home / "stack/managed.json")
            assert marker["project"].startswith(manager.PROJECT + "-")
            status = cli("start")
            assert len(status["services"]) == 3 and all(
                row["health"] == "healthy" for row in status["services"]
            )
            code = cli("pairing-code", "--name", "Synthetic acceptance")["code"]
            assert cli("pair", "--code-stdin", text=code + "\n")["paired"]
            profile = home / "synthetic-profile.json"
            write_json(
                profile,
                {
                    "command": sys.executable,
                    "args": [str(ROOT / "tests/fixture_mcp.py")],
                },
            )
            assert (
                cli(
                    "approve",
                    "fixture",
                    "--name",
                    "Synthetic fixture",
                    "--profile",
                    str(profile),
                    "--yes",
                )["approved"]
                == "fixture"
            )
            connector = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "openmaskit_companion.cli",
                    "--home",
                    str(home),
                    "connect",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 20
            while not any(
                row["connected"]
                for row in manager.admin(home, "GET", "/admin/connectors")["connectors"]
            ):
                assert connector.poll() is None and time.monotonic() < deadline
                time.sleep(0.1)
            assert cli("register", "fixture", "--name", "Synthetic fixture")[
                "connected"
            ]
            assert cli("register", "fixture", "--name", "Synthetic fixture")[
                "connected"
            ], "Registration retry must be idempotent"
            settings = read_json(home / "stack/relay/relay.json")
            paired = read_json(home / "connection.json")
            status = json.dumps(cli("status"))
            assert all(
                secret not in status
                for secret in [
                    settings["admin_token"],
                    settings["proxy_token"],
                    paired["token"],
                ]
            )

            async def call():
                async with streamable_http_client(
                    "http://127.0.0.1:9494/synthetic-fixture/mcp"
                ) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        response = await session.call_tool(
                            "greet", {"name": "Synthetic acceptance"}
                        )
                        assert response.content[0].text == "Hello Synthetic acceptance"

            asyncio.run(call())
            cli("stop")
            assert not any(
                row["state"] == "running" for row in cli("status")["services"]
            )
            print(
                "PASS: actual manager CLI setup/start/pair/approve/connect/register/status/stop,"
            )
            print(
                "idempotent registration, private status, isolated project and live host MCP round trip."
            )
        finally:
            if connector is not None and connector.poll() is None:
                connector.terminate()
                try:
                    connector.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    connector.kill()
                    connector.wait()
            marker = read_json(home / "stack/managed.json")
            if str(marker.get("project", "")).startswith(manager.PROJECT + "-"):
                manager.compose(home, "down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    main(parser.parse_args().image)
