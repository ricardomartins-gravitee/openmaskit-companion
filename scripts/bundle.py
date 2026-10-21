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


def copy_app_icons(resources):
    assets = ROOT / "desktop/macos/Assets"
    for name in ("AppIcon.png", "AppIcon.icns"):
        shutil.copy2(assets / name, resources / name)


def copy_design_notices(resources):
    checkout = ROOT / "desktop/macos/.build/checkouts/openmaskit-design-system"
    destination = resources / "ThirdParty/OpenMaskitDesign"
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("LICENSE", "NOTICE", "TRADEMARKS.md"):
        output = destination / name
        # SwiftPM checkouts can be read-only. Keep generated notices replaceable
        # so rebuilding an existing development bundle remains safe and repeatable.
        if output.exists():
            output.chmod(0o644)
        shutil.copyfile(checkout / name, output)


def write_info_plist(app):
    with (app / "Info.plist").open("wb") as out:
        plistlib.dump(
            {
                "CFBundleIdentifier": "io.github.ricardomartins-gravitee.openmaskit-companion",
                "CFBundleName": "OpenMaskit Companion",
                "CFBundleExecutable": "OpenMaskitCompanion",
                "CFBundlePackageType": "APPL",
                "CFBundleShortVersionString": "0.1.0",
                "CFBundleVersion": "2",
                "CFBundleIconFile": "AppIcon.icns",
                "LSMinimumSystemVersion": "14.0",
                "NSHighResolutionCapable": True,
            },
            out,
        )


def main():
    if platform.system() != "Darwin":
        raise SystemExit("OpenMaskit Companion is a macOS application")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image", help="Published connector relay image pinned by digest"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "dist",
        help="Output directory for an isolated review build",
    )
    args = parser.parse_args()
    destination = args.output_dir.resolve()
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
            "--distpath",
            str(destination),
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
    app = destination / "OpenMaskit Companion.app/Contents"
    (app / "MacOS").mkdir(parents=True, exist_ok=True)
    resources = app / "Resources"
    resources.mkdir(exist_ok=True)
    copy_design_notices(resources)
    shutil.copy2(
        ROOT / "desktop/macos/.build/release/OpenMaskitCompanion",
        app / "MacOS/OpenMaskitCompanion",
    )
    shutil.copytree(
        destination / "openmaskit-companion",
        resources / "backend/openmaskit-companion",
        dirs_exist_ok=True,
    )
    copy_app_icons(resources)
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
    write_info_plist(app)
    print("Development app built. Not distribution-signed or notarized.")


if __name__ == "__main__":
    main()
