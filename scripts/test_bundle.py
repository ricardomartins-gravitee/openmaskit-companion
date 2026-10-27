"""Exercise the packaged app's connector backend contract."""

import os
import subprocess
import sys
from pathlib import Path

from bundle import verify_development_bundle

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "dist/OpenMaskit Companion.app"
CONNECTOR = APP / "Contents/Resources/backend/openmaskit-companion/openmaskit-companion"

verify_development_bundle(APP)
subprocess.run([str(CONNECTOR), "--version"], check=True)
subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_app_contract.py", "-q"],
    cwd=ROOT,
    env={**os.environ, "COMPANION_BINARY": str(CONNECTOR)},
    check=True,
)
