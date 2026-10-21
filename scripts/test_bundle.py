"""Exercise the packaged app's connector backend contract."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "dist/OpenMaskit Companion.app"
CONNECTOR = APP / "Contents/Resources/backend/openmaskit-companion/openmaskit-companion"

subprocess.run([str(CONNECTOR), "--version"], check=True)
subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_app_contract.py", "-q"],
    cwd=ROOT,
    env={**os.environ, "COMPANION_BINARY": str(CONNECTOR)},
    check=True,
)
