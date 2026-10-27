"""The packaged GUI probe must stay synthetic and fail on early app exit."""

import fcntl
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def probe(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("test_bundle_desktop")


def test_desktop_backend_allows_only_synthetic_status(probe, tmp_path):
    helper = tmp_path / "fixture-backend.py"
    helper.write_text(probe.FIXTURE)
    command = [sys.executable, str(helper), "--home", str(tmp_path)]
    assert (
        subprocess.run([*command, "status"], capture_output=True, timeout=5).returncode
        != 0
    )
    (tmp_path / "synthetic-desktop-acceptance").touch()
    initial = subprocess.run(
        [*command, "status"], capture_output=True, check=True, timeout=5
    )
    assert json.loads(initial.stdout)["configured"] is False
    (tmp_path / "configured").touch()
    configured = subprocess.run(
        [*command, "status"], capture_output=True, check=True, timeout=5
    )
    assert json.loads(configured.stdout)["mode"] == "existing"
    assert probe.polls(tmp_path) == [{"configured": False}, {"configured": True}]
    assert (
        subprocess.run([*command, "start"], capture_output=True, timeout=5).returncode
        != 0
    )
    assert len(probe.polls(tmp_path)) == 2


def test_old_poll_records_cannot_hide_an_exited_app(probe):
    with subprocess.Popen([sys.executable, "-c", "pass"]) as process:
        process.wait(timeout=5)
        with pytest.raises(RuntimeError, match="exited"):
            probe.wait_for(process, lambda: True, timeout=1)


def test_gui_probe_refuses_to_run_beside_another_companion(
    probe, monkeypatch, tmp_path
):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    lock = (
        tmp_path
        / "Library/Application Support/OpenMaskit Companion/Runtime/desktop.lock"
    )
    lock.parent.mkdir(parents=True)
    with lock.open("w") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="Quit the running Companion"):
            probe.check_no_running_companion()
    probe.check_no_running_companion()


def test_partially_written_poll_does_not_fail_or_count_as_completion(probe, tmp_path):
    assert probe.polls(tmp_path) == []
    (tmp_path / "polls.jsonl").write_text('{"configured":false}\n{"configured":tr')
    assert probe.polls(tmp_path) == [{"configured": False}]
