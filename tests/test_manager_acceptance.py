"""The container fixture accepts only its fixed synthetic candidate image."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def helper():
    spec = importlib.util.spec_from_file_location(
        "manager_acceptance", ROOT / "scripts/manager_acceptance.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "candidate",
    [
        "other-image:latest",
        "openmaskit-connector:candidate\nCOMPOSE_FILE=../../other.yaml",
        "openmaskit-connector:candidate\rCOMPOSE_PROJECT_NAME=other",
        "../../other",
    ],
)
def test_invalid_candidate_is_rejected_before_any_state_or_service_access(
    monkeypatch, candidate
):
    module = helper()
    monkeypatch.setattr(
        module.socket,
        "socket",
        lambda *a, **kw: pytest.fail("Invalid input must fail before opening sockets"),
    )
    monkeypatch.setattr(
        module.tempfile,
        "TemporaryDirectory",
        lambda *a, **kw: pytest.fail("Invalid input must fail before creating state"),
    )
    with pytest.raises(ValueError, match="fixed synthetic"):
        module.main(None, candidate)
