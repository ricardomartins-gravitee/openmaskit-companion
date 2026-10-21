"""Resolve only the attested connector release matching the app's reviewed pin."""

import hashlib
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "ricardomartins-gravitee/openmaskit-connector"
IMAGE_PREFIX = f"ghcr.io/{REPOSITORY}@sha256:"
MAX_METADATA_BYTES = 16 * 1024


def validate_pin(pin):
    if (
        pin.get("repository") != REPOSITORY
        or not re.fullmatch(r"[0-9a-f]{40}", pin.get("commit", ""))
        or not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", pin.get("version", ""))
        or pin.get("protocol") != 1
    ):
        raise ValueError("Invalid reviewed connector dependency pin")


def validate_metadata(data, pin):
    validate_pin(pin)
    if (
        data.get("schema") != 1
        or data.get("protocol") != pin["protocol"]
        or data.get("commit") != pin["commit"]
        or data.get("version") != pin["version"]
        or not isinstance(data.get("relay_image"), str)
        or not re.fullmatch(
            re.escape(IMAGE_PREFIX) + r"[0-9a-f]{64}", data["relay_image"]
        )
    ):
        raise ValueError(
            "Connector release does not match the reviewed version and protocol"
        )
    return data["relay_image"]


class GitHubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from urllib.parse import urlsplit

        target = urlsplit(newurl)
        if (
            target.scheme != "https"
            or target.netloc != "release-assets.githubusercontent.com"
        ):
            raise ValueError("Release download redirected outside GitHub HTTPS assets")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def release_metadata(pin, directory):
    validate_pin(pin)
    tag = "connector-v" + pin["version"]
    api_url = f"https://api.github.com/repos/{REPOSITORY}/releases/tags/{tag}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "openmaskit-companion-build",
    }
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = "Bearer " + token
    api = urllib.request.build_opener(urllib.request.ProxyHandler({}), GitHubRedirect())
    with api.open(
        urllib.request.Request(api_url, headers=headers), timeout=60
    ) as response:
        release = json.loads(response.read(1024 * 1024))
    assets = [
        asset
        for asset in release.get("assets", [])
        if asset["name"] == "connector-release.json"
    ]
    if release.get("draft") or release.get("tag_name") != tag or len(assets) != 1:
        raise ValueError(
            "The pinned connector release has no unique published metadata"
        )
    asset = assets[0]
    url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/connector-release.json"
    if (
        asset.get("browser_download_url") != url
        or not 0 < asset["size"] <= MAX_METADATA_BYTES
    ):
        raise ValueError("Invalid connector release metadata asset")
    with api.open(url, timeout=60) as response:
        content = response.read(MAX_METADATA_BYTES + 1)
    if (
        len(content) != asset["size"]
        or asset.get("digest") != "sha256:" + hashlib.sha256(content).hexdigest()
    ):
        raise ValueError("Connector release metadata checksum mismatch")
    path = directory / "connector-release.json"
    if path.is_symlink():
        raise ValueError("Release metadata cannot be a symbolic link")
    path.write_bytes(content)
    subprocess.run(
        [
            "gh",
            "attestation",
            "verify",
            str(path),
            "--repo",
            REPOSITORY,
            "--source-ref",
            "refs/heads/main",
            "--source-digest",
            pin["commit"],
            "--signer-workflow",
            f"{REPOSITORY}/.github/workflows/validate.yml",
            "--deny-self-hosted-runners",
        ],
        check=True,
        timeout=180,
    )
    return validate_metadata(json.loads(content), pin)


def main():
    pin = json.loads((ROOT / "dependencies/connector.json").read_text())
    directory = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    image = release_metadata(pin, directory)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"relay-image={image}\n")
    print("Verified the pinned connector release and its immutable relay image")


if __name__ == "__main__":
    main()
