"""Run the real MCP bridge tests with the packaged executable as connector."""
import os
import platform
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
binary = root / "dist/openmaskit-companion" / ("openmaskit-companion.exe" if platform.system() == "Windows" else "openmaskit-companion")
subprocess.run([str(binary), "--version"], check=True)
subprocess.run([sys.executable, "-m", "pytest", "tests/test_bridge_integration.py", "-q"],
    cwd=root, env={**os.environ, "COMPANION_BINARY": str(binary)}, check=True)
