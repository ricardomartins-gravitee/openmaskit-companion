"""Installation selection and read-only discovery; never imports an OpenMaskit store."""

from __future__ import annotations

import ipaddress
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from openmaskit_connector.state import read_json, write_json

MANAGED_URL = "http://127.0.0.1:9493"
DEFAULT_EXISTING_URL = "http://127.0.0.1:9473"
MESSAGES = {
    "invalid_url": "Enter a local OpenMaskit address, such as http://127.0.0.1:9473. Paths, credentials and remote hosts are not supported.",
    "unavailable": "OpenMaskit could not be reached. Start your existing installation and check its address, then try again.",
    "not_openmaskit": "This address did not return a supported OpenMaskit health response. Check the dashboard address.",
    "database_unavailable": "OpenMaskit is reachable but its database is unavailable. Check the existing installation and retry.",
    "invalid_selection": "The saved installation connection could not be read. Your OpenMaskit data has not been changed.",
    "external_installation": "This installation is managed outside Companion. Use its existing service controls.",
    "not_configured": "Choose an installation in Settings before opening OpenMaskit.",
    "docker_unavailable": "Open Docker Desktop, then retry setup. Your existing OpenMaskit installation has not been changed.",
}


class InstallationError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(MESSAGES[code])


def local_url(value):
    try:
        if not isinstance(value, str) or any(
            ord(c) < 33 or ord(c) > 126 for c in value
        ):
            raise ValueError
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or url.username is not None
            or url.password is not None
        ):
            raise ValueError
        if url.path not in {"", "/"} or url.query or url.fragment:
            raise ValueError
        host = url.hostname
        if host == "localhost":
            host = "127.0.0.1"
        if not host or not ipaddress.ip_address(host).is_loopback:
            raise ValueError
        port = (
            url.port if url.port is not None else (443 if url.scheme == "https" else 80)
        )
        if not 1 <= port <= 65535:
            raise ValueError
        host = f"[{host}]" if ":" in host else host
        return f"{url.scheme}://{host}:{port}"
    except (ValueError, TypeError):
        raise InstallationError("invalid_url") from None


def selection(home: Path):
    path = home / "installation.json"
    if path.exists() or path.is_symlink():
        try:
            if path.is_symlink():
                raise ValueError
            data = read_json(path)
            if not isinstance(data, dict):
                raise ValueError
            if (
                data.get("schema") != 1
                or data.get("mode") not in {"existing", "managed"}
                or type(data.get("configured")) is not bool
            ):
                raise ValueError
            url = local_url(data["dashboard"])
            if data["mode"] == "managed" and url != MANAGED_URL:
                raise ValueError
            if (
                data["mode"] == "managed"
                and not (home / "stack/managed.json").is_file()
            ):
                raise ValueError
            return {
                "mode": data["mode"],
                "configured": data["configured"],
                "dashboard": url,
            }
        except (ValueError, OSError, KeyError, TypeError):
            raise InstallationError("invalid_selection") from None
    if (home / "stack/managed.json").is_file():
        # Existing managed installations remain selected without rewriting their state.
        return {"mode": "managed", "configured": True, "dashboard": MANAGED_URL}
    return {"mode": "unconfigured", "configured": False, "dashboard": None}


def save(home, mode, url, *, configured=True):
    path = home / "installation.json"
    if path.is_symlink():
        raise InstallationError("invalid_selection")
    write_json(
        path,
        {
            "schema": 1,
            "mode": mode,
            "dashboard": local_url(url),
            "configured": configured,
        },
    )


def require_managed(home):
    if selection(home)["mode"] == "existing":
        raise InstallationError("external_installation")


def probe(value):
    url = local_url(value)
    try:
        deadline = time.monotonic() + 5
        with httpx.Client(trust_env=False, timeout=3, follow_redirects=False) as api:
            with api.stream("GET", url + "/health") as response:
                if response.status_code not in {200, 503}:
                    raise InstallationError("not_openmaskit")
                body = bytearray()
                for chunk in response.iter_bytes():
                    if time.monotonic() > deadline:
                        raise InstallationError("unavailable")
                    body.extend(chunk)
                    if len(body) > 1_048_576:
                        raise InstallationError("not_openmaskit")
                data = json.loads(body)
        if not isinstance(data, dict) or data.get("status") not in {
            "healthy",
            "degraded",
            "unhealthy",
        }:
            raise ValueError
        database = data.get("database")
        targets = data.get("targets")
        if (
            not isinstance(database, dict)
            or type(database.get("connected")) is not bool
            or not isinstance(targets, list)
        ):
            raise ValueError
        if any(
            not isinstance(row, dict) or type(row.get("initialized")) is not bool
            for row in targets
        ):
            raise ValueError
        if not database["connected"]:
            raise InstallationError("database_unavailable")
        return {
            "dashboard": url,
            "ready": True,
            "health": data["status"],
            "server_count": len(targets),
        }
    except httpx.HTTPError:
        raise InstallationError("unavailable") from None
    except InstallationError:
        raise
    except (ValueError, TypeError):
        raise InstallationError("not_openmaskit") from None


def connect_existing(home, url):
    result = probe(url)
    save(home, "existing", result["dashboard"])
    return {**result, "mode": "existing", "configured": True}


def dashboard(home):
    selected = selection(home)
    if not selected["configured"]:
        raise InstallationError("not_configured")
    return probe(selected["dashboard"])
