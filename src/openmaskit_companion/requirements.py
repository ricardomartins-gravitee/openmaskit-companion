"""Read-only runtime checks. Never install, start, or change Docker here."""

import os
import subprocess  # nosec B404
import sys
from pathlib import Path


def desktop_installed():
    return any(
        path.is_dir()
        for path in (
            Path("/Applications/Docker.app"),
            Path.home() / "Applications/Docker.app",
        )
    )


def command_ready(arguments, *, flags=(), environment=None):
    try:
        # Fixed Docker subcommands; callers first validate the local context.
        result = subprocess.run(  # nosec B603
            arguments, capture_output=True, text=True, timeout=5, env=environment
        )
        return result.returncode == 0 and all(
            flag in result.stdout.split() for flag in flags
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def check(find_binary, validate_context, *, environment=None):
    environment = os.environ if environment is None else environment
    checks = []

    def record(key, title, ready, detail, *, blocked=False):
        checks.append(
            {
                "id": key,
                "title": title,
                "state": "blocked"
                if blocked
                else ("ready" if ready else "needs_attention"),
                "detail": "Available" if ready else detail,
            }
        )

    desktop = sys.platform != "darwin" or desktop_installed()
    if sys.platform == "darwin":
        record(
            "desktop",
            "Docker Desktop",
            desktop,
            "Install Docker Desktop, then check again.",
        )
    binary = None
    try:
        binary = find_binary()
    except (ValueError, OSError):
        pass
    record(
        "cli",
        "Docker command tools",
        bool(binary),
        "Reinstall Docker Desktop's command tools.",
    )
    local = False
    if desktop and binary:
        try:
            validate_context(binary, environment)
            local = True
        except (ValueError, OSError, subprocess.TimeoutExpired):
            pass
    record(
        "context",
        "Local Docker connection",
        local,
        "Select Docker Desktop's local context, then check again.",
        blocked=not (desktop and binary),
    )
    compose = local and command_ready(
        [binary, "compose", "up", "--help"],
        flags=("--wait", "--wait-timeout", "--pull"),
        environment=environment,
    )
    record(
        "compose",
        "Docker Compose",
        compose,
        "Install or update Docker Desktop to include current Docker Compose tools.",
        blocked=not local,
    )
    daemon = local and command_ready(
        [binary, "info", "--format", "{{.ServerVersion}}"], environment=environment
    )
    record(
        "daemon",
        "Docker engine",
        daemon,
        "Open Docker Desktop and wait for its engine to start.",
        blocked=not local,
    )
    return {"ready": all(row["state"] == "ready" for row in checks), "checks": checks}
