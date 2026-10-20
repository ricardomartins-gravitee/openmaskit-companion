"""Development downloads; checksums do not claim platform code signing."""

import hashlib
import platform
import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
downloads = root / "dist/downloads"
downloads.mkdir(exist_ok=True)
label = platform.system().lower() + "-" + platform.machine().lower()
shutil.make_archive(
    str(downloads / ("openmaskit-companion-cli-" + label)),
    "zip",
    root / "dist",
    "openmaskit-companion",
)
if platform.system() == "Darwin":
    subprocess.run(
        [
            "ditto",
            "-c",
            "-k",
            "--sequesterRsrc",
            "--keepParent",
            str(root / "dist/OpenMaskit Companion.app"),
            str(downloads / ("openmaskit-companion-development-" + label + ".zip")),
        ],
        check=True,
    )
checksums = {
    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
    for path in downloads.glob("*.zip")
}
(downloads / "SHA256SUMS.txt").write_text(
    "".join(f"{value}  {key}\n" for key, value in sorted(checksums.items()))
)
