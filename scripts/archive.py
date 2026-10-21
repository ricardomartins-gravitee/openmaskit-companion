"""Archive the tested macOS app and write its SHA-256 checksum."""

import hashlib
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "dist/OpenMaskit Companion.app"


def main():
    if platform.system() != "Darwin":
        raise RuntimeError("The companion app archive can only be made on macOS")
    if not APP.is_dir():
        raise FileNotFoundError("The tested companion app bundle is missing")
    downloads = ROOT / "dist/downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    label = platform.machine().lower()
    archive = downloads / f"openmaskit-companion-macos-{label}.zip"
    subprocess.run(
        [
            "ditto",
            "-c",
            "-k",
            "--sequesterRsrc",
            "--keepParent",
            str(APP),
            str(archive),
        ],
        check=True,
    )
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (downloads / "SHA256SUMS.txt").write_text(f"{checksum}  {archive.name}\n")


if __name__ == "__main__":
    main()
