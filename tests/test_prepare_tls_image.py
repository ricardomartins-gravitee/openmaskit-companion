"""Synthetic tests for TLS image checks during managed onboarding."""

import pytest
from openmaskit_connector.state import write_json

from openmaskit_companion import installation, manager, relay_upgrade

IMAGE = manager.IMAGE_PREFIX + "b" * 64


def fake_local_docker(monkeypatch):
    monkeypatch.setattr(manager, "docker_binary", lambda: "/synthetic/docker")
    monkeypatch.setattr(manager, "local_docker", lambda *_: None)


def fingerprint(root):
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def test_incompatible_image_fails_before_any_onboarding_state_is_written(
    tmp_path, monkeypatch
):
    fake_local_docker(monkeypatch)
    calls = []

    def reject_image(image):
        calls.append(image)
        raise ValueError("synthetic relay does not support TLS")

    monkeypatch.setattr(relay_upgrade, "preflight", reject_image)
    with pytest.raises(ValueError, match="does not support TLS"):
        manager.prepare_managed(tmp_path, IMAGE)

    assert calls == [IMAGE]
    assert not list(tmp_path.iterdir())
    assert not (tmp_path / "stack").exists()
    assert not (tmp_path / "installation.json").exists()


def test_fresh_verified_image_is_preflighted_before_initialize_and_selection(
    tmp_path, monkeypatch
):
    fake_local_docker(monkeypatch)
    events = []
    real_initialize = manager.initialize

    monkeypatch.setattr(
        relay_upgrade, "preflight", lambda image: events.append(("preflight", image))
    )

    def observe_initialize(home, image):
        events.append(("initialize", image))
        return real_initialize(home, image)

    monkeypatch.setattr(manager, "initialize", observe_initialize)

    result = manager.prepare_managed(tmp_path, IMAGE)

    assert events == [("preflight", IMAGE), ("initialize", IMAGE)]
    assert result == {"dashboard": manager.WEB, "initialized": True}
    assert installation.selection(tmp_path) == {
        "mode": "managed",
        "configured": False,
        "dashboard": manager.WEB,
    }
    assert (tmp_path / "stack/managed.json").is_file()
    assert (tmp_path / "stack/tls.json").is_file()


def test_existing_managed_stack_skips_preflight_and_preserves_stack_files(
    tmp_path, monkeypatch
):
    manager.initialize(tmp_path, IMAGE)
    installation.save(tmp_path, "managed", manager.WEB, configured=False)
    before = fingerprint(tmp_path / "stack")
    fake_local_docker(monkeypatch)
    monkeypatch.setattr(
        relay_upgrade,
        "preflight",
        lambda image: pytest.fail("existing managed image must not be preflighted"),
    )

    manager.prepare_managed(tmp_path, IMAGE)

    assert fingerprint(tmp_path / "stack") == before


def test_local_docker_guard_runs_before_preflight_or_state_changes(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(manager, "docker_binary", lambda: "/synthetic/docker")
    monkeypatch.setattr(
        manager,
        "local_docker",
        lambda *_: (_ for _ in ()).throw(ValueError("remote Docker context")),
    )
    monkeypatch.setattr(
        relay_upgrade,
        "preflight",
        lambda image: pytest.fail("preflight must not use a rejected Docker context"),
    )

    with pytest.raises(installation.InstallationError, match="Open Docker Desktop"):
        manager.prepare_managed(tmp_path, IMAGE)

    assert not list(tmp_path.iterdir())


def test_existing_unrecognized_stack_is_not_preflighted_or_rewritten(
    tmp_path, monkeypatch
):
    stack = tmp_path / "stack"
    stack.mkdir()
    marker = stack / "managed.json"
    write_json(marker, {"schema": 1, "project": "other-project"})
    (stack / "saved-rules.json").write_text('{"synthetic":"keep"}')
    before = fingerprint(stack)
    fake_local_docker(monkeypatch)
    monkeypatch.setattr(
        relay_upgrade,
        "preflight",
        lambda image: pytest.fail("existing state must not be preflighted"),
    )

    with pytest.raises(ValueError, match="Invalid Companion installation marker"):
        manager.prepare_managed(tmp_path, IMAGE)

    assert fingerprint(stack) == before
    assert not (tmp_path / "installation.json").exists()
