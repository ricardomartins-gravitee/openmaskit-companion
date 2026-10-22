"""macOS desktop manager and adapter to the separately versioned connector."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from openmaskit_connector.state import identifier

from . import __version__, installation, manager


def default_home():
    return Path.home() / ".openmaskit-companion"


def parser():
    root = argparse.ArgumentParser(
        description="Manage OpenMaskit and locally approved MCP connections"
    )
    root.add_argument("--home", type=Path, default=default_home())
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="action", required=True)
    commands.add_parser("status")
    commands.add_parser("prerequisites")
    commands.add_parser("dashboard")
    commands.add_parser("docker-status")
    commands.add_parser("connector-status")
    commands.add_parser("keep-connections")
    refresh = commands.add_parser("refresh-connections")
    refresh.add_argument("--wait-ready", action="store_true")
    commands.add_parser("start-dependencies")
    commands.add_parser("start-installed")
    commands.add_parser("wait-services")
    attach = commands.add_parser("connect-existing")
    attach.add_argument("--url", required=True)
    prepare = commands.add_parser("prepare-managed")
    prepare.add_argument("--image", required=True)
    setup = commands.add_parser("setup")
    setup.add_argument(
        "--image",
        required=True,
        help="Connector relay release image, pinned by sha256 digest",
    )
    for action in ("start", "stop"):
        commands.add_parser(action)
    code = commands.add_parser("pairing-code")
    code.add_argument("--name", default="My computer")
    pair = commands.add_parser("pair")
    pair.add_argument("--endpoint", default=manager.RELAY)
    pair.add_argument(
        "--code-stdin",
        action="store_true",
        help="Read the pairing code from stdin instead of prompting",
    )
    approve = commands.add_parser("approve")
    approve.add_argument("id", type=identifier)
    approve.add_argument("--name", required=True)
    approve.add_argument(
        "--profile",
        type=Path,
        required=True,
        help="Local JSON containing the executable, arguments and environment",
    )
    approve.add_argument(
        "--yes",
        action="store_true",
        help="Confirm approval for this exact local profile",
    )
    forget = commands.add_parser("forget")
    forget.add_argument("id", type=identifier)
    commands.add_parser("profiles")
    commands.add_parser("connect")
    revoke = commands.add_parser("revoke")
    revoke.add_argument("id", type=identifier)
    register = commands.add_parser("register")
    register.add_argument("id", type=identifier)
    register.add_argument("--name", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    home = args.home.expanduser().absolute()
    if args.action in {"pair", "approve", "forget", "profiles", "connect"}:
        from openmaskit_connector.cli import main as connector_main

        if args.action in {"pair", "connect"}:
            try:
                installation.require_managed(home)
            except installation.InstallationError as error:
                print(
                    json.dumps({"error": str(error), "code": error.code}),
                    file=sys.stderr,
                )
                raise SystemExit(1) from None
        supplied = list(sys.argv[1:] if argv is None else argv)
        connector_main(["--home", str(home), *supplied])
        return
    try:
        if args.action == "status":
            result = manager.status(home)
        elif args.action == "prerequisites":
            result = manager.prerequisites()
        elif args.action == "docker-status":
            result = manager.docker_ready(home)
        elif args.action == "connector-status":
            result = manager.connector_status(home)
        elif args.action == "keep-connections":
            result = manager.keep_connections(home)
        elif args.action == "refresh-connections":
            if args.wait_ready:
                manager.wait_dashboard(home)
            result = manager.refresh_connections(home)
        elif args.action in {"start-dependencies", "start-installed", "wait-services"}:
            installation.require_configured_managed(home)
            services = (
                ["presidio-analyzer", "connector-relay"]
                if args.action == "start-dependencies"
                else []
            )
            waiting = (
                []
                if args.action == "start-installed"
                else ["--wait", "--wait-timeout", "120"]
            )
            manager.compose(
                home,
                "up",
                "--detach",
                "--pull",
                "never",
                *waiting,
                *services,
                timeout=180,
            )
            result = (
                manager.finish_start(home)
                if args.action == "wait-services"
                else {"ready": True}
            )
        elif args.action == "connect-existing":
            result = installation.connect_existing(home, args.url)
        elif args.action == "dashboard":
            selected = installation.selection(home)
            if selected["mode"] == "managed":
                result = manager.status(home)
                if not result["configured"] or not result["ready"]:
                    raise installation.InstallationError("unavailable")
            else:
                result = installation.dashboard(home)
        elif args.action == "prepare-managed":
            result = manager.prepare_managed(home, args.image)
        elif args.action == "setup":
            installation.require_managed(home)
            result = manager.initialize(home, args.image)
        elif args.action == "start":
            manager.compose(home, "up", "--detach", "--wait", "--wait-timeout", "300")
            result = manager.finish_start(home)
        elif args.action == "stop":
            manager.compose(home, "stop", "--timeout", "45")
            result = manager.status(home)
        elif args.action == "pairing-code":
            result = manager.admin(home, "POST", "/admin/pairings", {"name": args.name})
        elif args.action == "revoke":
            result = manager.admin(home, "POST", "/admin/revoke", {"id": args.id})
        elif args.action == "register":
            from openmaskit_connector.connector import profiles

            if args.id not in profiles(home):
                raise ValueError("Approve this MCP locally before registering it")
            result = manager.register_target(home, args.id, args.name)
        print(json.dumps(result))
    except KeyboardInterrupt:
        pass
    except asyncio.CancelledError:
        pass
    except installation.InstallationError as error:
        print(json.dumps({"error": str(error), "code": error.code}), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        # Do not expose server error bodies, command arguments or local secrets.
        print(
            json.dumps(
                {
                    "error": "Action could not be completed. Check setup, pairing, local profile validity and service availability."
                }
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
