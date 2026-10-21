"""Package only the reviewed first-party connector source; registry installs stay binary-only."""

import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from email.parser import BytesParser
from pathlib import Path

from connector_release import validate_pin
from packaging.utils import canonicalize_name, parse_wheel_filename

ROOT = Path(__file__).resolve().parents[1]


def verify_wheel(directory, pin):
    wheels = list(directory.glob("*.whl"))
    if len(wheels) != 1 or wheels[0].is_symlink():
        raise ValueError("Exactly one regular connector wheel is required")
    wheel = wheels[0]
    name, version, _, tags = parse_wheel_filename(wheel.name)
    if (
        name != "openmaskit-connector"
        or str(version) != pin["version"]
        or {str(tag) for tag in tags} != {"py3-none-any"}
    ):
        raise ValueError("Only the pinned pure-Python connector package is accepted")
    with zipfile.ZipFile(wheel) as package:
        metadata = BytesParser().parsebytes(
            package.read(f"openmaskit_connector-{version}.dist-info/METADATA")
        )
        if (
            canonicalize_name(metadata["Name"]) != name
            or metadata["Version"] != pin["version"]
        ):
            raise ValueError("Connector wheel metadata does not match its reviewed pin")
        if any(
            Path(member).suffix in {".so", ".dll", ".dylib", ".pyd"}
            for member in package.namelist()
        ):
            raise ValueError(
                "Connector source packaging must not compile native libraries"
            )
    return wheel


def install(pin, runtime):
    validate_pin(pin)
    source = ROOT / ".runtime/connector-source"
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True, timeout=10
    ).strip()
    if revision != pin["commit"]:
        raise ValueError(
            "Connector checkout does not match the immutable dependency pin"
        )
    dirty = subprocess.check_output(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=all"],
        text=True,
        timeout=10,
    )
    if dirty.strip():
        raise ValueError("Connector checkout must be clean before packaging")
    with tempfile.TemporaryDirectory(
        prefix="connector-wheel-", dir=runtime
    ) as temporary:
        directory = Path(temporary)
        subprocess.run(
            [
                "uv",
                "build",
                str(source),
                "--no-sources",
                "--no-build-isolation",
                "--wheel",
                "--out-dir",
                str(directory),
            ],
            check=True,
            timeout=180,
        )
        wheel = verify_wheel(directory, pin)
        checksum = hashlib.sha256(wheel.read_bytes()).hexdigest()
        requirements = directory / "install.txt"
        requirements.write_text(f"{wheel.as_uri()} --hash=sha256:{checksum}\n")
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(ROOT / ".venv/bin/python"),
                "--no-deps",
                "--no-build",
                "--require-hashes",
                "--requirement",
                str(requirements),
            ],
            check=True,
            timeout=180,
        )


def main():
    pin = json.loads((ROOT / "dependencies/connector.json").read_text())
    runtime = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    install(pin, runtime)


if __name__ == "__main__":
    main()
