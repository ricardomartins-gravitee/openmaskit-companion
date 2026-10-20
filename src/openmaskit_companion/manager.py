"""Host-side lifecycle manager. Every Docker command is scoped to our project."""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
from importlib.resources import files
from pathlib import Path

import httpx

from .state import local_endpoint, private_dir, read_json, write_json

PROJECT = "openmaskit-companion"
WEB = "http://127.0.0.1:9493"
RELAY = "http://127.0.0.1:9495"
IMAGE_PREFIX = "ghcr.io/ricardomartins-gravitee/openmaskit-companion@sha256:"


def image_digest(value: str) -> str:
    if not value.startswith(IMAGE_PREFIX):
        raise ValueError("Use a companion release image pinned by digest")
    suffix = value[len(IMAGE_PREFIX):]
    if len(suffix) != 64 or any(c not in "0123456789abcdef" for c in suffix):
        raise ValueError("Invalid release digest")
    return value


def docker_binary():
    options = [shutil.which("docker"), str(Path.home() / ".docker/bin/docker"),
               "/Applications/Docker.app/Contents/Resources/bin/docker"]
    for option in options:
        if option and Path(option).is_file():
            return str(Path(option).resolve())
    raise ValueError("Open Docker Desktop to manage containers")


def local_docker(binary, environment):
    endpoint = None if environment.get("DOCKER_CONTEXT") else environment.get("DOCKER_HOST")
    if not endpoint:
        command = [binary, "context", "inspect"]
        if context := environment.get("DOCKER_CONTEXT"):
            command.append(context)
        result = subprocess.run([*command, "--format", "{{json .Endpoints.docker.Host}}"],
            capture_output=True, text=True, timeout=10, env=environment)
        if result.returncode:
            raise ValueError("Docker context is unavailable")
        endpoint = json.loads(result.stdout)
    if not isinstance(endpoint, str) or not endpoint.startswith(("unix://", "npipe://")):
        raise ValueError("This release manages a local Docker socket only")


def initialize(home: Path, image: str):
    image_digest(image)
    stack = private_dir(home / "stack")
    if (stack / "managed.json").exists():
        raise ValueError("A managed installation already exists")
    if any(stack.iterdir()):
        raise ValueError("Installation directory must be empty")
    settings = {"admin_token": secrets.token_urlsafe(32), "proxy_token": secrets.token_urlsafe(32), "connectors": {}}
    write_json(stack / "relay" / "relay.json", settings)
    (stack / "compose.yaml").write_text(files("openmaskit_companion").joinpath("data/compose.yaml").read_text())
    release = json.loads(files("openmaskit_companion").joinpath("data/release.json").read_text())
    env = {"OPENMASKIT_IMAGE": release["openmaskit_image"], "COMPANION_IMAGE": image,
           "LOCAL_UID": str(os.getuid() if hasattr(os, "getuid") else 10001),
           "LOCAL_GID": str(os.getgid() if hasattr(os, "getgid") else 10001)}
    (stack / ".env").write_text("".join(f"{key}={value}\n" for key, value in env.items()))
    (stack / ".env").chmod(0o600)
    project = PROJECT + "-" + secrets.token_hex(6)
    write_json(stack / "managed.json", {"project": project, "schema": 1, "automatic_updates": False, "release": release})
    return {"dashboard": WEB, "initialized": True}


def compose(home: Path, *arguments, timeout=360):
    stack = home / "stack"
    marker = read_json(stack / "managed.json")
    project = marker.get("project")
    if (marker.get("schema") != 1
            or not isinstance(project, str)
            or (project != PROJECT and re.fullmatch(re.escape(PROJECT) + r"-[0-9a-f]{12}", project) is None)):
        raise ValueError("Set up a companion-managed installation first")
    if stack.is_symlink() or (stack / "compose.yaml").is_symlink() or (stack / ".env").is_symlink():
        raise ValueError("Managed paths must not be symbolic links")
    # No user-supplied project names, files, shell fragments or global cleanup.
    binary = docker_binary()
    environment = {key: value for key, value in os.environ.items() if key not in {
        "OPENMASKIT_IMAGE", "COMPANION_IMAGE", "LOCAL_UID", "LOCAL_GID", "COMPOSE_FILE", "COMPOSE_PROFILES"}}
    environment["COMPOSE_IGNORE_ORPHANS"] = "true"
    environment["PATH"] = str(Path(binary).parent) + os.pathsep + environment.get("PATH", "")
    local_docker(binary, environment)
    result = subprocess.run([binary, "compose", "--project-name", project,
        "--project-directory", str(stack), "--file", str(stack / "compose.yaml"),
        "--env-file", str(stack / ".env"), *arguments],
        capture_output=True, text=True, timeout=timeout,
        env=environment)
    if result.returncode:
        raise ValueError("Docker could not complete this action; check Docker Desktop and the managed containers")
    return result.stdout


def status(home: Path):
    result = {"initialized": (home / "stack/managed.json").is_file(), "dashboard": WEB,
              "services": [], "paired": (home / "connection.json").is_file(),
              "automatic_updates": False}
    try:
        if result["initialized"]:
            raw = compose(home, "ps", "--all", "--format", "json", timeout=10)
            data = json.loads(raw) if raw.lstrip().startswith("[") else [json.loads(line) for line in raw.splitlines() if line]
            result["services"] = [{"name": row["Service"], "state": row["State"], "health": row.get("Health", "")}
                                  for row in data]
    except (ValueError, OSError, subprocess.TimeoutExpired):
        result["error"] = "Docker is unavailable"
    if result["initialized"]:
        try:
            result["connectors"] = [{key: row[key] for key in ("id", "name", "connected", "profiles") if key in row}
                for row in admin(home, "GET", "/admin/connectors")["connectors"]]
        except (ValueError, httpx.HTTPError):
            result["connectors"] = []
    return result


def admin(home: Path, method, path, body=None):
    settings = read_json(home / "stack/relay/relay.json")
    with httpx.Client(base_url=RELAY, trust_env=False, timeout=5,
                      headers={"Authorization": "Bearer " + settings["admin_token"]}) as api:
        response = api.request(method, path, json=body)
        response.raise_for_status()
        return response.json()


def pair(home: Path, endpoint: str, code: str):
    endpoint = local_endpoint(endpoint)
    with httpx.Client(trust_env=False, timeout=10) as api:
        response = api.post(endpoint + "/pair", json={"code": code})
        response.raise_for_status()
        data = response.json()
    if data.get("protocol") != 1 or not isinstance(data.get("token"), str) or len(data["token"]) < 32:
        raise ValueError("Incompatible pairing response")
    write_json(home / "connection.json", {"endpoint": endpoint, "id": data["id"], "token": data["token"]})
    return {"paired": True, "id": data["id"]}


def register_target(home: Path, profile: str, name: str):
    from .state import identifier
    config = read_json(home / "connection.json")
    secret = read_json(home / "stack/relay/relay.json")["proxy_token"]
    profile = identifier(profile)
    key = identifier(config['id'])
    online = admin(home, "GET", "/admin/connectors")["connectors"]
    if not any(row["id"] == key and row["connected"] and profile in row["profiles"] for row in online):
        raise ValueError("Start the paired connector with this approved profile first")
    url = f"http://connector-relay:9495/mcp/{key}/{profile}"
    target_id = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64]
    if not target_id:
        raise ValueError("Choose a name containing letters or numbers")
    # This performs ordinary OpenMaskit HTTP-server registration, not a private API.
    with httpx.Client(base_url=WEB, trust_env=False, timeout=30) as api:
        token = api.get("/api/csrf").json()["token"]
        response = api.post("/api/targets/custom", headers={"Origin": WEB, "X-CSRF-Token": token},
            json={"name": name, "transport": "http",
                "url": url,
                "headers": {"Authorization": {"type": "secret", "value": "Bearer " + secret}}})
        if response.status_code == 409:
            existing = api.get(f"/api/targets/custom/{target_id}")
            existing.raise_for_status()
            if existing.json()["config"].get("url") != url:
                raise ValueError("A different MCP already uses this name")
            health = api.get("/health")
            health.raise_for_status()
            target = next((row for row in health.json()["targets"] if row["name"] == target_id), None)
            if target and target["initialized"]:
                return {"id": target_id, "connected": True}
            headers = {"Origin": WEB, "X-CSRF-Token": token}
            if target:
                api.post(f"/api/targets/custom/{target_id}/deactivate", headers=headers).raise_for_status()
            response = api.post(f"/api/targets/custom/{target_id}/activate", headers=headers)
        response.raise_for_status()
        data = response.json()
        if not data["connected"]:
            raise ValueError("MCP saved but not connected; check the connector and retry")
        return {"id": data.get("server_id", target_id), "connected": True}
