"""Headless entry point, also used by the native companion app."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import sys
from pathlib import Path

from . import __version__, manager
from .state import Profile, default_home, identifier, read_json, write_json


def parser():
    root = argparse.ArgumentParser(
        description="Manage OpenMaskit and locally approved MCP connections"
    )
    root.add_argument("--home", type=Path, default=default_home())
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="action", required=True)
    commands.add_parser("status")
    setup = commands.add_parser("setup")
    setup.add_argument(
        "--image",
        required=True,
        help="Companion release image, pinned by sha256 digest",
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
    relay = commands.add_parser("relay")
    relay.add_argument("--state", type=Path, required=True)
    relay.add_argument("--host", default="127.0.0.1")
    relay.add_argument("--port", type=int, default=9495)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    home = args.home.expanduser().absolute()
    try:
        if args.action == "status":
            result = manager.status(home)
        elif args.action == "setup":
            result = manager.initialize(home, args.image)
        elif args.action == "start":
            manager.compose(home, "up", "--detach", "--wait", "--wait-timeout", "300")
            result = manager.status(home)
        elif args.action == "stop":
            manager.compose(home, "stop", "--timeout", "45")
            result = manager.status(home)
        elif args.action == "pairing-code":
            result = manager.admin(home, "POST", "/admin/pairings", {"name": args.name})
        elif args.action == "pair":
            code = (
                sys.stdin.readline().strip()
                if args.code_stdin
                else getpass.getpass("Pairing code: ")
            )
            result = manager.pair(home, args.endpoint, code)
        elif args.action == "approve":
            raw = json.loads(args.profile.read_text())
            raw["name"] = args.name
            profile = Profile.model_validate(raw)
            if not args.yes:
                print(
                    f"Approve {args.id}: {profile.command} ({len(profile.args)} arguments).",
                    file=sys.stderr,
                )
                print(
                    "This MCP runs with your user permissions. Review the local profile file first.",
                    file=sys.stderr,
                )
                if input("Type approve to continue: ") != "approve":
                    raise ValueError("Approval cancelled")
            saved = read_json(home / "profiles.json")
            if args.id not in saved and len(saved) >= 32:
                raise ValueError("Profile limit reached")
            saved[args.id] = profile.model_dump()
            write_json(home / "profiles.json", saved)
            result = {"approved": args.id, "restart_connector": True}
        elif args.action == "forget":
            saved = read_json(home / "profiles.json")
            saved.pop(args.id, None)
            write_json(home / "profiles.json", saved)
            result = {"removed": args.id, "restart_connector": True}
        elif args.action == "profiles":
            from .connector import profiles

            result = {
                "profiles": [
                    {"id": key, "name": value.name}
                    for key, value in profiles(home).items()
                ]
            }
        elif args.action == "connect":
            from .connector import run

            asyncio.run(run(home))
            return
        elif args.action == "revoke":
            result = manager.admin(home, "POST", "/admin/revoke", {"id": args.id})
        elif args.action == "register":
            from .connector import profiles

            if args.id not in profiles(home):
                raise ValueError("Approve this MCP locally before registering it")
            result = manager.register_target(home, args.id, args.name)
        elif args.action == "relay":
            import uvicorn

            from .relay import create_app

            uvicorn.run(
                create_app(args.state),
                host=args.host,
                port=args.port,
                access_log=False,
                ws_max_size=1_048_576,
                log_level="warning",
            )
            return
        print(json.dumps(result))
    except KeyboardInterrupt:
        pass
    except asyncio.CancelledError:
        pass
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
