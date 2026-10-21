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

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from openmaskit_connector.state import read_json, write_json

from openmaskit_companion import installation, manager

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_IMAGE = "openmaskit-connector:candidate"


def main(image, candidate_image=None, isolated_ports=False):
    if candidate_image not in (None, CANDIDATE_IMAGE):
        raise ValueError("Only the fixed synthetic candidate image is allowed")
    probes = [socket.socket() for _ in range(3)]
    try:
        for probe, port in zip(probes, (9493, 9494, 9495)):
            probe.bind(("127.0.0.1", 0 if isolated_ports else port))
        web, mcp, relay = [probe.getsockname()[1] for probe in probes]
    finally:
        for probe in probes:
            probe.close()
    if isolated_ports:
        # Overrides exist only inside this synthetic test process/driver.
        manager.WEB = installation.MANAGED_URL = f"http://127.0.0.1:{web}"
        manager.RELAY = f"http://127.0.0.1:{relay}"
    (ROOT / ".runtime").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="manager-acceptance-", dir=ROOT / ".runtime"
    ) as directory:
        home = Path(directory)
        connector = None
        entry = [sys.executable, "-m", "openmaskit_companion.cli"]
        if isolated_ports:
            driver = home / "synthetic-driver.py"
            driver.write_text(
                "from openmaskit_companion import manager,installation,cli\n"
                f"manager.WEB=installation.MANAGED_URL={manager.WEB!r}\n"
                f"manager.RELAY={manager.RELAY!r}\n"
                "cli.main()\n"
            )
            entry = [sys.executable, str(driver)]

        def cli(*arguments, text=None, at=None):
            result = subprocess.run(
                [
                    *entry,
                    "--home",
                    str(at or home),
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
            assert cli("prepare-managed", "--image", image)["initialized"]
            assert not cli("status")["configured"]
            if isolated_ports:
                path = home / "stack/compose.yaml"
                text = path.read_text()
                for old, new in [(9493, web), (9494, mcp)]:
                    text = text.replace(f'"{old}"', f'"{new}"').replace(
                        f"127.0.0.1:{old}:{old}", f"127.0.0.1:{new}:{new}"
                    )
                path.write_text(
                    text.replace("127.0.0.1:9495:9495", f"127.0.0.1:{relay}:9495")
                )
            if candidate_image is not None:
                # This isolated synthetic fixture tests an unpublished relay candidate.
                # Production setup still rejects mutable/unapproved image references.
                env_file = home / "stack/.env"
                entries = env_file.read_text().splitlines()
                env_file.write_text(
                    "\n".join(
                        "COMPANION_IMAGE=" + CANDIDATE_IMAGE
                        if line.startswith("COMPANION_IMAGE=")
                        else line
                        for line in entries
                    )
                    + "\n"
                )
            marker = read_json(home / "stack/managed.json")
            assert marker["project"].startswith(manager.PROJECT + "-")
            status = cli("start")
            assert len(status["services"]) == 3 and all(
                row["health"] == "healthy" for row in status["services"]
            )
            code = cli("pairing-code", "--name", "Synthetic acceptance")["code"]
            assert cli(
                "pair", "--endpoint", manager.RELAY, "--code-stdin", text=code + "\n"
            )["paired"]
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
                    *entry,
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
            # Connect a second, independent Companion home as a read-only viewer.
            # Seed real rules/settings in the synthetic server and compare them after attach.
            with httpx.Client(base_url=manager.WEB, trust_env=False, timeout=10) as api:
                csrf = api.get("/api/csrf").json()["token"]
                headers = {"Origin": manager.WEB, "X-CSRF-Token": csrf}
                api.post(
                    "/api/targets/synthetic-fixture/rules/create",
                    headers=headers,
                    json={
                        "tool_name": "*",
                        "field_path": "messages.author",
                        "alias_prefix": "header",
                    },
                ).raise_for_status()
                api.post(
                    "/api/privacy/providers/create",
                    headers=headers,
                    json={
                        "name": "Synthetic analyzer",
                        "endpoint": "http://presidio-analyzer:3000",
                    },
                ).raise_for_status()
                rules_before = api.get("/api/targets/synthetic-fixture/rules").json()
                settings_before = api.get("/api/privacy").json()
                viewer = home / "viewer"
                assert cli("connect-existing", "--url", manager.WEB, at=viewer)[
                    "configured"
                ]
                viewed = cli("status", at=viewer)
                assert viewed["ready"] and viewed["mode"] == "existing"
                assert (
                    not viewed["can_manage_services"]
                    and not (viewer / "stack").exists()
                )
                assert cli("dashboard", at=viewer)["dashboard"] == manager.WEB
                assert (
                    api.get("/api/targets/synthetic-fixture/rules").json()
                    == rules_before
                )
                assert api.get("/api/privacy").json() == settings_before
            assert cli("status")["ready"], (
                "Attaching must leave the original managed services running"
            )
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
                    f"http://127.0.0.1:{mcp}/synthetic-fixture/mcp"
                ) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        response = await session.call_tool(
                            "greet", {"name": "Synthetic acceptance"}
                        )
                        assert response.content[0].text == "Hello Synthetic acceptance"

            asyncio.run(call())
            # Reproduce app Quit/relaunch: old upstream sessions must be restored,
            # without replaying a call or changing the saved masking/check config.
            connector.terminate()
            connector.wait(timeout=15)
            assert cli("docker-status")["ready"]
            cli("start-dependencies")
            connector = subprocess.Popen(
                [*entry, "--home", str(home), "connect"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 20
            while not cli("connector-status")["connected"]:
                assert connector.poll() is None and time.monotonic() < deadline
                time.sleep(0.1)
            cli("start-installed")
            assert cli("refresh-connections", "--wait-ready")["refreshed"] == 1
            assert cli("wait-services")["ready"]
            asyncio.run(call())
            with httpx.Client(base_url=manager.WEB, trust_env=False, timeout=10) as api:
                assert (
                    api.get("/api/targets/synthetic-fixture/rules").json()
                    == rules_before
                )
                assert api.get("/api/privacy").json() == settings_before
            cli("stop")
            assert not any(
                row["state"] == "running" for row in cli("status")["services"]
            )
            print(
                "PASS: actual manager CLI setup/start/pair/approve/connect/register/status/stop,"
            )
            print(
                "idempotent registration, read-only attachment, automatic-start ordering, connector restart/reconnect preserving rules/settings, private status, isolated project and live host MCP round trip."
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
    parser.add_argument("--image")
    parser.add_argument(
        "--isolated-ports",
        action="store_true",
        help="Use ephemeral ports without displacing an installed Companion",
    )
    parser.add_argument(
        "--candidate-image",
        choices=[CANDIDATE_IMAGE],
        help="Unpublished image used only in the disposable test stack",
    )
    args = parser.parse_args()
    if not args.image and not args.candidate_image:
        parser.error("--image or --candidate-image is required")
    main(
        args.image or manager.IMAGE_PREFIX + "0" * 64,
        args.candidate_image,
        args.isolated_ports,
    )
