"""Build input/output verification for the same-run Intel cryptography artifact.

Compilation is an explicit CI build operation. This helper never executes source
or invokes a compiler, and consumers never install an sdist.
"""

import argparse
import hashlib
import json
import os
import re
import tarfile
import tomllib
import urllib.parse
import urllib.request
import zipfile
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def locked_source(lock=ROOT / "uv.lock"):
    packages = tomllib.loads(lock.read_text())["package"]
    package = next(p for p in packages if p["name"] == "cryptography")
    source = package["sdist"]
    url = urllib.parse.urlsplit(source["url"])
    if (
        url.scheme != "https"
        or url.netloc != "files.pythonhosted.org"
        or url.query
        or url.fragment
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", source["hash"])
        or not re.fullmatch(r"\d+\.\d+\.\d+", package["version"])
    ):
        raise ValueError("Invalid locked cryptography source")
    return package["version"], source


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def locked_openssl():
    source = json.loads((ROOT / "dependencies/openssl.json").read_text())
    version = source["version"]
    if (
        not re.fullmatch(r"\d+\.\d+\.\d+", version)
        or source["url"]
        != (
            "https://github.com/openssl/openssl/releases/download/"
            f"openssl-{version}/openssl-{version}.tar.gz"
        )
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", source["hash"])
    ):
        raise ValueError("Invalid locked OpenSSL source")
    return source


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Source download redirects are forbidden")


class GitHubReleaseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = urllib.parse.urlsplit(newurl)
        if url.scheme != "https" or url.netloc not in {
            "github.com",
            "release-assets.githubusercontent.com",
        }:
            raise ValueError("OpenSSL download redirected outside GitHub HTTPS assets")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_openssl(directory):
    source = locked_openssl()
    directory.mkdir(parents=True, exist_ok=False)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), GitHubReleaseRedirect()
    )
    with opener.open(source["url"], timeout=60) as response:
        content = response.read(64 * 1024 * 1024 + 1)
    if len(content) != source["size"]:
        raise ValueError("OpenSSL source size does not match lockfile")
    if "sha256:" + hashlib.sha256(content).hexdigest() != source["hash"]:
        raise ValueError("OpenSSL source checksum does not match lockfile")
    archive = directory / "source.tar.gz"
    archive.write_bytes(content)
    with tarfile.open(archive) as package:
        package.extractall(directory / "source", filter="data")
    upstream = directory / "source" / f"openssl-{source['version']}"
    upstream.rename(directory / "upstream")


def fetch(directory):
    version, source = locked_source()
    directory.mkdir(parents=True, exist_ok=False)
    archive = directory / "source.tar.gz"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(source["url"], timeout=60) as response:
        content = response.read(16 * 1024 * 1024 + 1)
    if len(content) != source["size"]:
        raise ValueError("Source size does not match lockfile")
    if "sha256:" + hashlib.sha256(content).hexdigest() != source["hash"]:
        raise ValueError("Source checksum does not match lockfile")
    archive.write_bytes(content)
    with tarfile.open(archive) as package:
        # Python 3.12's data filter rejects traversal, devices and escaping links.
        package.extractall(directory / "source", filter="data")
    upstream = directory / "source" / f"cryptography-{version}"
    config = tomllib.loads((upstream / "pyproject.toml").read_text())
    if config["tool"]["maturin"].get("locked") is not True:
        raise ValueError("Upstream build must enforce Cargo.lock")
    if not (upstream / "Cargo.lock").is_file():
        raise ValueError("Locked Rust dependencies are required")


def wheel_details(directory):
    from packaging.utils import parse_wheel_filename

    version, _ = locked_source()
    wheels = list(directory.glob("*.whl"))
    if len(wheels) != 1 or wheels[0].is_symlink():
        raise ValueError("Exactly one regular wheel is required")
    wheel = wheels[0]
    name, built_version, _, tags = parse_wheel_filename(wheel.name)
    if name != "cryptography" or str(built_version) != version:
        raise ValueError("Wheel does not match locked cryptography version")
    if not tags or any(
        not re.fullmatch(r"macosx_\d+_\d+_x86_64", tag.platform) for tag in tags
    ):
        raise ValueError("Wheel must target Intel macOS only")
    with zipfile.ZipFile(wheel) as package:
        metadata = package.read(f"cryptography-{version}.dist-info/METADATA")
    parsed = BytesParser().parsebytes(metadata)
    if parsed["Name"] != "cryptography" or parsed["Version"] != version:
        raise ValueError("Wheel metadata does not match lockfile")
    return wheel


def manifest(directory, commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("A full source commit is required")
    version, source = locked_source()
    wheel = wheel_details(directory)
    return {
        "commit": commit,
        "version": version,
        "source_sha256": source["hash"].removeprefix("sha256:"),
        "wheel": wheel.name,
        "wheel_sha256": digest(wheel),
        "openssl_version": locked_openssl()["version"],
        "openssl_source_sha256": locked_openssl()["hash"].removeprefix("sha256:"),
    }


def seal(directory, commit):
    data = manifest(directory, commit)
    (directory / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")


def prepare(directory, commit):
    expected = manifest(directory, commit)
    recorded = json.loads((directory / "manifest.json").read_text())
    if recorded != expected:
        raise ValueError("Wheel artifact is not from this source commit and lockfile")
    wheel = directory / expected["wheel"]
    (directory / "install.txt").write_text(
        f"{wheel.resolve().as_uri()} --hash=sha256:{expected['wheel_sha256']}\n"
    )


def sbom(directory):
    from cryptography.hazmat.backends.openssl.backend import backend

    version, _ = locked_source()
    text = backend.openssl_version_text()
    match = re.fullmatch(r"OpenSSL (\d+\.\d+\.\d+[a-z]?) .+", text)
    if not match:
        raise ValueError("Cannot identify embedded OpenSSL for vulnerability scan")
    if match[1] != locked_openssl()["version"]:
        raise ValueError("Native wheel did not link the pinned OpenSSL release")
    components = [
        {
            "type": "library",
            "name": "cryptography",
            "version": version,
            "purl": f"pkg:pypi/cryptography@{version}",
        },
        {
            "type": "library",
            "name": "openssl",
            "version": match[1],
            "purl": f"pkg:generic/openssl@{match[1]}",
            "cpe": f"cpe:2.3:a:openssl:openssl:{match[1]}:*:*:*:*:*:*:*",
        },
    ]
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": components,
    }
    (directory / "sbom.json").write_text(json.dumps(data, indent=2) + "\n")
    print(f"Embedded OpenSSL: {text}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation", choices=("fetch", "fetch-openssl", "seal", "prepare", "sbom")
    )
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.operation in ("seal", "prepare"):
        {"seal": seal, "prepare": prepare}[args.operation](
            args.directory, os.environ.get("GITHUB_SHA", "")
        )
    else:
        {"fetch": fetch, "fetch-openssl": fetch_openssl, "sbom": sbom}[args.operation](
            args.directory
        )


if __name__ == "__main__":
    main()
