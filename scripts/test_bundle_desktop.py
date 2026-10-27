"""Run the real packaged GUI through setup completion with a synthetic backend.

This exercises process lifetime, not visual icon placement. It refuses to run
beside another Companion and never opens Docker, an MCP, or existing app data.
"""

import argparse
import fcntl
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from bundle import verify_development_bundle

FIXTURE = """#!/usr/bin/env python3
import json, pathlib, sys
assert sys.argv[1] == "--home"
home = pathlib.Path(sys.argv[2])
assert (home / "synthetic-desktop-acceptance").is_file()
assert sys.argv[3:] == ["status"], "Only synthetic existing-mode status is allowed"
configured = (home / "configured").exists()
with (home / "polls.jsonl").open("a") as log:
    log.write(json.dumps({"configured": configured}) + "\\n")
print(json.dumps({"mode": "existing" if configured else "unconfigured",
    "configured": configured, "initialized": False, "ready": configured,
    "paired": False, "can_manage_services": False, "health": "healthy",
    "dashboard": "http://127.0.0.1:19473", "server_count": 0,
    "connectors": [], "services": []}))
"""


def polls(home):
    path = home / "polls.jsonl"
    if not path.exists():
        return []
    # A helper can still be completing its final line at the time of this read.
    return [
        json.loads(line)
        for line in path.read_text().splitlines(keepends=True)
        if line.endswith("\n")
    ]


def wait_for(process, condition, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "The packaged Companion exited during desktop acceptance"
            )
        if condition():
            return
        time.sleep(0.1)
    raise TimeoutError(
        "The packaged Companion did not finish its synthetic desktop transition"
    )


def check_no_running_companion():
    lock = (
        Path.home()
        / "Library/Application Support/OpenMaskit Companion/Runtime/desktop.lock"
    )
    if lock.exists():
        with lock.open("rb") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError(
                    "Quit the running Companion before packaged GUI acceptance"
                ) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, type=Path)
    args = parser.parse_args()
    app = args.app.resolve()
    verify_development_bundle(app)
    check_no_running_companion()
    with tempfile.TemporaryDirectory(
        prefix="companion-desktop-acceptance-"
    ) as temporary:
        home = Path(temporary)
        (home / "synthetic-desktop-acceptance").touch()
        helper = home / "fixture-backend"
        helper.write_text(FIXTURE)
        helper.chmod(0o700)
        environment = {
            **os.environ,
            "COMPANION_HOME": str(home),
            "COMPANION_BACKEND": str(helper),
        }
        process = subprocess.Popen(
            [str(app / "Contents/MacOS/OpenMaskitCompanion")],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            # Two complete refreshes ensure the first unconfigured reply has
            # been processed, rather than racing its onboarding presentation.
            wait_for(process, lambda: len(polls(home)) >= 2)
            assert all(not poll["configured"] for poll in polls(home))
            (home / "configured").touch()
            # Production configurationChanged closes the actual onboarding
            # window. Subsequent refreshes prove its native process survives.
            wait_for(process, lambda: sum(p["configured"] for p in polls(home)) >= 3)
            print(
                json.dumps(
                    {
                        "packaged_gui_survived_onboarding_completion": True,
                        "background_refreshes_after_completion": 3,
                        "synthetic_backend_only": True,
                        "visual_icon_acceptance": "required separately",
                    }
                )
            )
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=8)


if __name__ == "__main__":
    main()
