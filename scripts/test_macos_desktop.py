"""Native adapter acceptance with Command Line Tools, without XCTest or other apps."""

import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
package = root / "desktop/macos"
subprocess.run(["swift", "build", "--package-path", str(package)], check=True)
binary_path = Path(
    subprocess.check_output(
        ["swift", "build", "--package-path", str(package), "--show-bin-path"], text=True
    ).strip()
)
output = root / ".runtime/desktop-core-check"
output.parent.mkdir(exist_ok=True)
subprocess.run(
    [
        "swiftc",
        "-parse-as-library",
        "-I",
        str(binary_path / "Modules"),
        str(package / "Acceptance/DesktopCoreAcceptance.swift"),
        str(binary_path / "CompanionDesktopCore.build/AppPreferences.swift.o"),
        str(binary_path / "CompanionPolicy.build/MenuBarPolicy.swift.o"),
        "-o",
        str(output),
    ],
    check=True,
)
subprocess.run([str(output)], check=True)

startup = root / ".runtime/startup-core-check"
subprocess.run(
    [
        "swiftc",
        "-parse-as-library",
        "-I",
        str(binary_path / "Modules"),
        str(package / "Acceptance/StartupAcceptance.swift"),
        str(binary_path / "CompanionDesktopCore.build/ServiceStartup.swift.o"),
        str(binary_path / "CompanionDesktopCore.build/BackendProcess.swift.o"),
        str(binary_path / "CompanionPolicy.build/InstallationState.swift.o"),
        "-o",
        str(startup),
    ],
    check=True,
)
subprocess.run([str(startup)], check=True)

instance = root / ".runtime/instance-core-check"
subprocess.run(
    [
        "swiftc",
        "-parse-as-library",
        "-I",
        str(binary_path / "Modules"),
        str(package / "Acceptance/InstanceAcceptance.swift"),
        str(binary_path / "CompanionDesktopCore.build/DesktopInstanceLock.swift.o"),
        "-o",
        str(instance),
    ],
    check=True,
)
subprocess.run([str(instance)], check=True, timeout=30)
