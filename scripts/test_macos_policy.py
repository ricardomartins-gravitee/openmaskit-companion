"""Check visibility policy even when the local Command Line Tools lack XCTest."""

import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
runtime = root / ".runtime"
runtime.mkdir(exist_ok=True)
binary = runtime / "menubar-policy-check"
subprocess.run(
    [
        "swiftc",
        str(root / "desktop/macos/Sources/CompanionPolicy/MenuBarPolicy.swift"),
        str(root / "desktop/macos/Acceptance/MenuBarAcceptance.swift"),
        "-o",
        str(binary),
    ],
    check=True,
)
subprocess.run([str(binary)], check=True)

installation_binary = runtime / "installation-policy-check"
subprocess.run(
    [
        "swiftc",
        str(root / "desktop/macos/Sources/CompanionPolicy/InstallationState.swift"),
        str(root / "desktop/macos/Acceptance/InstallationAcceptance.swift"),
        "-o",
        str(installation_binary),
    ],
    check=True,
)
subprocess.run([str(installation_binary)], check=True)
