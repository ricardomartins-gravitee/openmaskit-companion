"""Build a standalone CLI and, on macOS, an explicitly unsigned development app."""

import argparse
import json
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if platform.system() != "Darwin":
        raise SystemExit("OpenMaskit Companion is a macOS application")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image", help="Published connector relay image pinned by digest"
    )
    args = parser.parse_args()
    entry = ROOT / ".runtime/bundle-entry.py"
    entry.parent.mkdir(exist_ok=True)
    entry.write_text("from openmaskit_companion.cli import main\nmain()\n")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--name",
            "openmaskit-companion",
            "--collect-all",
            "openmaskit_companion",
            "--collect-all",
            "openmaskit_connector",
            "--copy-metadata",
            "openmaskit-connector",
            "--collect-submodules",
            "uvicorn",
            str(entry),
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [
            "swift",
            "build",
            "--package-path",
            str(ROOT / "desktop/macos"),
            "-c",
            "release",
        ],
        check=True,
    )
    app = ROOT / "dist/OpenMaskit Companion.app/Contents"
    (app / "MacOS").mkdir(parents=True, exist_ok=True)
    resources = app / "Resources"
    resources.mkdir(exist_ok=True)
    shutil.copy2(
        ROOT / "desktop/macos/.build/release/OpenMaskitCompanion",
        app / "MacOS/OpenMaskitCompanion",
    )
    shutil.copytree(
        ROOT / "dist/openmaskit-companion",
        resources / "backend/openmaskit-companion",
        dirs_exist_ok=True,
    )
    connector = json.loads((ROOT / "dependencies/connector.json").read_text())
    from importlib.metadata import version

    if version("openmaskit-connector") != connector["version"]:
        raise ValueError("Installed connector does not match the reviewed version")
    release = json.loads(
        (ROOT / "src/openmaskit_companion/data/release.json").read_text()
    )
    release["connector"] = connector
    if args.image:
        from openmaskit_companion.manager import image_digest

        release["companion_image"] = image_digest(args.image)
    (resources / "release.json").write_text(json.dumps(release, indent=2))
    with (app / "Info.plist").open("wb") as out:
        plistlib.dump(
            {
                "CFBundleIdentifier": "io.github.ricardomartins-gravitee.openmaskit-companion",
                "CFBundleName": "OpenMaskit Companion",
                "CFBundleExecutable": "OpenMaskitCompanion",
                "CFBundlePackageType": "APPL",
                "CFBundleShortVersionString": "0.1.0",
                "CFBundleVersion": "1",
                "LSMinimumSystemVersion": "14.0",
                "NSHighResolutionCapable": True,
            },
            out,
        )
    print("Development app built. Not distribution-signed or notarized.")


if __name__ == "__main__":
    main()
