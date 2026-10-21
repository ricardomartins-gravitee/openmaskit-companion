"""Explicit, backed-up upgrade of an existing Companion-owned relay to TLS."""

import json
import os
import shutil

# Docker preflight uses a validated local executable and fixed argument arrays.
import subprocess  # nosec B404
import tempfile
from importlib.resources import files
from pathlib import Path

from openmaskit_connector.state import identifier, private_dir, read_json, write_json

from . import installation, manager, relay_tls


def preflight(image):
    image = manager.image_digest(image)
    binary = manager.docker_binary()
    manager.local_docker(binary, os.environ)
    result = subprocess.run(  # nosec B603
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
            image,
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
        raise ValueError("The selected relay image does not support verified TLS")


def _set_image(home, image):
    path = home / "stack/.env"
    if path.is_symlink():
        raise ValueError("Managed image settings cannot be symbolic links")
    lines = path.read_text().splitlines()
    if sum(line.startswith("COMPANION_IMAGE=") for line in lines) != 1:
        raise ValueError("Review the managed relay image setting before upgrading")
    updated = (
        "\n".join(
            "COMPANION_IMAGE=" + image if line.startswith("COMPANION_IMAGE=") else line
            for line in lines
        )
        + "\n"
    )
    descriptor, temporary = tempfile.mkstemp(prefix=".relay-image-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            output.write(updated)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def upgrade(home: Path, image: str):
    installation.require_configured_managed(home)
    manager.image_digest(image)
    # Validate the original project's paths and local Docker context first.
    manager.compose(home, "config", "--quiet", timeout=20)
    pending = home / "stack/tls-upgrade.json"
    if pending.is_symlink():
        raise ValueError("Relay upgrade state cannot be a symbolic link")
    if (home / "stack/tls.json").exists():
        relay_tls.validate(home)
        try:
            relay_tls.validate_stack(home)
            paired = read_json(home / "connection.json")
            if not pending.exists() and (
                not paired
                or (
                    paired.get("endpoint") == manager.RELAY
                    and paired.get("ca_file") == str(home / "stack/tls/ca.pem")
                )
            ):
                return {"prepared": True, "upgraded": False}
        except (ValueError, OSError):
            pass
    if read_json(home / "connector-status.json").get("connected"):
        raise ValueError("Stop the local connector before upgrading relay TLS")
    paired = read_json(home / "connection.json")
    connector = identifier(paired["id"]) if paired else None
    configured = read_json(home / "stack/relay/relay.json").get("connectors", {})
    if set(configured) - ({connector} if connector else set()):
        raise ValueError(
            "Additional paired computers need an explicit certificate deployment plan"
        )
    # Check custom Compose entries before stopping any service or changing state.
    relay_tls.compose_with_tls((home / "stack/compose.yaml").read_text())
    preflight(image)
    backups = private_dir(home / "backups")
    backup = Path(tempfile.mkdtemp(prefix="relay-tls-", dir=backups))
    backup.chmod(0o700)
    shutil.copytree(
        home, backup / "companion", ignore=shutil.ignore_patterns("backups")
    )
    write_json(backup / "progress.json", {"stage": "configuration_backed_up"})
    manager.compose(home, "stop", "--timeout", "45")
    data = private_dir(backup / "openmaskit")
    manager.compose(
        home, "cp", "openmaskit:/home/openmaskit/.openmaskit/.", str(data), timeout=180
    )
    if not (data / "store.db").is_file() or not (data / ".key").is_file():
        raise ValueError("A complete OpenMaskit backup is required before upgrading")
    write_json(backup / "progress.json", {"stage": "installation_backed_up"})
    # Keep interrupted preparation visibly incomplete, including after a later
    # process launch. A retry re-runs the idempotent URL migration instead of
    # mistaking prepared TLS files for a completed database migration.
    write_json(pending, {"schema": 1, "backup": str(backup)})
    relay_tls.prepare_stack(home)
    _set_image(home, image)
    if paired:
        paired["endpoint"] = manager.RELAY
        paired["ca_file"] = str(home / "stack/tls/ca.pem")
        write_json(home / "connection.json", paired)
    relay_tls.validate_stack(home)
    write_json(backup / "progress.json", {"stage": "configuration_prepared"})
    # The app is stopped and the full volume has been copied. Only URL schemes
    # for this paired computer are changed, retaining encrypted config values,
    # IDs, active flags, rules, aliases, privacy settings, keys and audit history.
    migrated = {"upgraded_connections": 0}
    if connector:
        script = (
            files("openmaskit_companion")
            .joinpath("data/migrate_relay_tls.py")
            .read_text()
        )
        result = manager.compose(
            home,
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "--entrypoint",
            "python",
            "openmaskit",
            "-c",
            script,
            connector,
            timeout=120,
        )
        migrated = json.loads(result)
    write_json(backup / "progress.json", {"stage": "connections_migrated", **migrated})
    write_json(
        backup / "progress.json", {"stage": "prepared_for_verified_tls", **migrated}
    )
    pending.unlink()
    # Service startup and connector supervision remain with the native app.
    # A failed TLS handshake never restarts an unencrypted relay as a fallback.
    return {"prepared": True, "upgraded": True, "backup": str(backup), **migrated}
