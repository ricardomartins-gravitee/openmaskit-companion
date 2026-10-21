"""Synthetic acceptance coverage for the explicit managed relay TLS upgrade."""

import os
import sqlite3
from importlib.resources import files
from pathlib import Path

import pytest
import yaml
from openmaskit_connector.state import read_json, write_json

from openmaskit_companion import manager, relay_tls, relay_upgrade

IMAGE = manager.IMAGE_PREFIX + "a" * 64
CONNECTOR = "paired-computer"


def managed_home(home, *, configured=True, paired=True, peers=None):
    stack = home / "stack"
    stack.mkdir(parents=True)
    (stack / "compose.yaml").write_text(
        files("openmaskit_companion").joinpath("data/compose.yaml").read_text()
    )
    (stack / ".env").write_text(
        f"OPENMASKIT_IMAGE=stable\nCOMPANION_IMAGE={IMAGE}\nCUSTOM=kept\n"
    )
    write_json(
        stack / "managed.json",
        {"schema": 1, "project": "openmaskit-companion-123456abcdef"},
    )
    write_json(
        home / "installation.json",
        {
            "schema": 1,
            "mode": "managed",
            "dashboard": manager.WEB,
            "configured": configured,
        },
    )
    write_json(
        stack / "relay/relay.json",
        {
            "admin_token": "synthetic-admin",
            "proxy_token": "synthetic-proxy",
            "custom_setting": {"kept": True},
            "connectors": peers
            if peers is not None
            else ({CONNECTOR: {"token_hash": "synthetic-hash"}} if paired else {}),
        },
    )
    if paired:
        write_json(
            home / "connection.json",
            {
                "id": CONNECTOR,
                "token": "synthetic-pairing-token",
                "endpoint": "http://127.0.0.1:9495",
                "ca_file": None,
                "display_name": "Synthetic computer",
                "extra": "preserve me",
            },
        )
    write_json(home / "connector-status.json", {"connected": False, "other": "kept"})
    return home


def mock_docker(monkeypatch, *, copy_state=True, fail_at=None):
    calls = []

    def compose(home, *args, timeout=360):
        calls.append((args, timeout))
        if fail_at and args[:1] == (fail_at,):
            raise ValueError("synthetic docker failure")
        if args[:1] == ("cp",) and copy_state:
            destination = args[-1]
            os.makedirs(destination, mode=0o700, exist_ok=True)
            with sqlite3.connect(os.path.join(destination, "store.db")) as db:
                db.execute("CREATE TABLE synthetic_state(value TEXT)")
                db.execute("INSERT INTO synthetic_state VALUES ('kept')")
            with open(os.path.join(destination, ".key"), "wb") as key:
                key.write(b"synthetic-key")
            os.chmod(os.path.join(destination, ".key"), 0o600)
        if args[:1] == ("run",):
            return '{"upgraded_connections": 2}'
        return ""

    monkeypatch.setattr(manager, "compose", compose)
    monkeypatch.setattr(relay_upgrade, "preflight", lambda image: None)
    return calls


def test_upgrade_preserves_private_state_settings_and_only_prepares_tls(
    tmp_path, monkeypatch
):
    home = managed_home(tmp_path)
    calls = mock_docker(monkeypatch)
    (home / "rules.json").write_text('{"rule":"synthetic"}')
    (home / "backups/old/keep.txt").parent.mkdir(parents=True)
    (home / "backups/old/keep.txt").write_text("old backup must not nest")
    stages = []
    original_write_json = relay_upgrade.write_json

    def track_progress(path, data):
        if Path(path).name == "progress.json":
            stages.append(data["stage"])
        return original_write_json(path, data)

    monkeypatch.setattr(relay_upgrade, "write_json", track_progress)

    result = relay_upgrade.upgrade(home, IMAGE)

    assert result["prepared"] and result["upgraded"]
    assert result["upgraded_connections"] == 2
    assert [call[0][0] for call in calls] == ["config", "stop", "cp", "run"]
    assert all(call[0][0] != "start" for call in calls)
    connection = read_json(home / "connection.json")
    assert connection == {
        "id": CONNECTOR,
        "token": "synthetic-pairing-token",
        "endpoint": manager.RELAY,
        "ca_file": str(home / "stack/tls/ca.pem"),
        "display_name": "Synthetic computer",
        "extra": "preserve me",
    }
    assert read_json(home / "connector-status.json") == {
        "connected": False,
        "other": "kept",
    }
    relay = read_json(home / "stack/relay/relay.json")
    assert relay["admin_token"] == "synthetic-admin"
    assert relay["proxy_token"] == "synthetic-proxy"
    assert relay["custom_setting"] == {"kept": True}
    assert relay["connectors"] == {CONNECTOR: {"token_hash": "synthetic-hash"}}
    assert (home / "rules.json").read_text() == '{"rule":"synthetic"}'
    assert "CUSTOM=kept\n" in (home / "stack/.env").read_text()
    assert f"COMPANION_IMAGE={IMAGE}\n" in (home / "stack/.env").read_text()
    assert (
        read_json(home / "stack/managed.json")["project"]
        == "openmaskit-companion-123456abcdef"
    )
    backup = Path(result["backup"])
    assert backup.parent == home / "backups"
    assert not (backup / "companion/backups").exists()
    assert os.stat(result["backup"]).st_mode & 0o777 == 0o700
    assert os.stat(backup / "openmaskit").st_mode & 0o777 == 0o700
    assert os.stat(backup / "openmaskit/.key").st_mode & 0o077 == 0
    assert read_json(backup / "progress.json")["stage"] == "prepared_for_verified_tls"
    assert stages == [
        "configuration_backed_up",
        "installation_backed_up",
        "configuration_prepared",
        "connections_migrated",
        "prepared_for_verified_tls",
    ]
    assert (home / "backups/old/keep.txt").read_text() == "old backup must not nest"
    assert relay_tls.validate_stack(home) is None


@pytest.mark.parametrize(
    "image",
    [
        "latest",
        manager.IMAGE_PREFIX + "A" * 64,
        manager.IMAGE_PREFIX + "a" * 63,
        "--privileged",
        manager.IMAGE_PREFIX + "a" * 64 + " --privileged",
        manager.IMAGE_PREFIX + "a" * 64 + ";echo unsafe",
        manager.IMAGE_PREFIX + "a" * 63 + "\n",
        manager.IMAGE_PREFIX + "a" * 62 + "00/../../other",
    ],
)
def test_bad_image_is_rejected_before_side_effects(tmp_path, monkeypatch, image):
    home = managed_home(tmp_path)
    calls = mock_docker(monkeypatch)
    with pytest.raises(ValueError):
        relay_upgrade.upgrade(home, image)
    assert calls == []
    assert not (home / "backups").exists()
    assert (home / "stack/compose.yaml").read_text().find("--tls-cert") == -1


def test_external_and_unconfigured_installations_are_rejected_before_docker(
    tmp_path, monkeypatch
):
    home = managed_home(tmp_path)
    calls = mock_docker(monkeypatch)
    write_json(
        home / "installation.json",
        {
            "schema": 1,
            "mode": "existing",
            "dashboard": "http://127.0.0.1:9473",
            "configured": True,
        },
    )
    with pytest.raises(ValueError):
        relay_upgrade.upgrade(home, IMAGE)
    assert calls == []
    write_json(
        home / "installation.json",
        {"schema": 1, "mode": "managed", "dashboard": manager.WEB, "configured": False},
    )
    with pytest.raises(ValueError):
        relay_upgrade.upgrade(home, IMAGE)
    assert calls == []
    assert not (home / "backups").exists()


def test_connected_connector_or_extra_peer_fails_before_backup_and_stop(
    tmp_path, monkeypatch
):
    home = managed_home(tmp_path)
    calls = mock_docker(monkeypatch)
    write_json(home / "connector-status.json", {"connected": True})
    with pytest.raises(ValueError, match="Stop the local connector"):
        relay_upgrade.upgrade(home, IMAGE)
    assert [args[0][0] for args in calls] == ["config"]
    assert not (home / "backups").exists()

    calls.clear()
    write_json(home / "connector-status.json", {"connected": False})
    write_json(
        home / "stack/relay/relay.json",
        {"connectors": {CONNECTOR: {}, "other-peer": {}}},
    )
    with pytest.raises(ValueError, match="Additional paired computers"):
        relay_upgrade.upgrade(home, IMAGE)
    assert [args[0][0] for args in calls] == ["config"]
    assert not (home / "backups").exists()


def test_compose_conflict_and_preflight_failure_do_not_stop_services(
    tmp_path, monkeypatch
):
    home = managed_home(tmp_path)
    calls = mock_docker(monkeypatch)
    compose = yaml.safe_load((home / "stack/compose.yaml").read_text())
    compose["services"]["openmaskit"]["entrypoint"] = ["custom"]
    (home / "stack/compose.yaml").write_text(yaml.safe_dump(compose))
    with pytest.raises(ValueError, match="custom OpenMaskit entrypoint"):
        relay_upgrade.upgrade(home, IMAGE)
    assert [args[0][0] for args in calls] == ["config"]
    assert not (home / "backups").exists()

    (home / "stack/compose.yaml").write_text(
        files("openmaskit_companion").joinpath("data/compose.yaml").read_text()
    )
    monkeypatch.setattr(
        relay_upgrade,
        "preflight",
        lambda image: (_ for _ in ()).throw(ValueError("unsupported TLS")),
    )
    calls.clear()
    with pytest.raises(ValueError, match="unsupported TLS"):
        relay_upgrade.upgrade(home, IMAGE)
    assert [args[0][0] for args in calls] == ["config"]
    assert not (home / "backups").exists()


def test_incomplete_store_backup_fails_closed_and_does_not_restart_plaintext(
    tmp_path, monkeypatch
):
    home = managed_home(tmp_path)
    # Simulate `docker cp` producing no required store/key files.
    calls = []
    monkeypatch.setattr(relay_upgrade, "preflight", lambda image: None)
    monkeypatch.setattr(
        manager, "compose", lambda home, *args, timeout=360: calls.append(args) or ""
    )
    with pytest.raises(ValueError, match="complete OpenMaskit backup"):
        relay_upgrade.upgrade(home, IMAGE)
    assert [call[0] for call in calls] == ["config", "stop", "cp"]
    assert not (home / "stack/tls.json").exists()
    assert read_json(home / "connection.json")["endpoint"] == "http://127.0.0.1:9495"


@pytest.mark.parametrize(
    ("failure", "expected_stage"),
    [("stop", "configuration_backed_up"), ("run", "configuration_prepared")],
)
def test_post_backup_docker_failures_keep_backup_and_never_restore_plaintext(
    tmp_path, monkeypatch, failure, expected_stage
):
    home = managed_home(tmp_path)
    calls = mock_docker(monkeypatch, fail_at=failure)
    with pytest.raises(ValueError, match="synthetic docker failure"):
        relay_upgrade.upgrade(home, IMAGE)
    assert [call[0][0] for call in calls] == ["config", "stop"] + (
        ["cp", "run"] if failure == "run" else []
    )
    backups = list((home / "backups").glob("relay-tls-*"))
    assert len(backups) == 1
    assert read_json(backups[0] / "progress.json")["stage"] == expected_stage
    if failure == "stop":
        assert not (home / "stack/tls.json").exists()
        assert not (home / "stack/tls-upgrade.json").exists()
        assert (
            read_json(home / "connection.json")["endpoint"] == "http://127.0.0.1:9495"
        )
    else:
        assert (home / "stack/tls.json").is_file()
        assert (home / "stack/tls-upgrade.json").is_file()
        assert read_json(home / "connection.json")["endpoint"] == manager.RELAY
        assert not manager.tls_ready(home)
    assert all(call[0][0] != "start" for call in calls)


def test_preparation_failure_blocks_tls_and_retry_runs_url_migration(
    tmp_path, monkeypatch
):
    home = managed_home(tmp_path)
    calls = mock_docker(monkeypatch)
    original_set_image = relay_upgrade._set_image
    should_fail = True

    def fail_once(home, image):
        nonlocal should_fail
        if should_fail:
            should_fail = False
            raise OSError("synthetic image metadata write failure")
        original_set_image(home, image)

    monkeypatch.setattr(relay_upgrade, "_set_image", fail_once)
    with pytest.raises(OSError, match="metadata write failure"):
        relay_upgrade.upgrade(home, IMAGE)

    assert [call[0][0] for call in calls] == ["config", "stop", "cp"]
    pending = home / "stack/tls-upgrade.json"
    assert pending.is_file()
    assert not manager.tls_ready(home)
    assert read_json(home / "connection.json")["endpoint"] == "http://127.0.0.1:9495"

    # The relay stack is already TLS-prepared; a retry must still reach SQL migration.
    result = relay_upgrade.upgrade(home, IMAGE)
    assert result["upgraded"] is True
    assert [call[0][0] for call in calls].count("run") == 1
    assert not pending.exists()
    assert manager.tls_ready(home)
    assert read_json(home / "connection.json")["endpoint"] == manager.RELAY


def test_already_upgraded_state_is_idempotent_without_stop_or_backup(
    tmp_path, monkeypatch
):
    home = managed_home(tmp_path)
    relay_tls.prepare_stack(home)
    connection = read_json(home / "connection.json")
    connection.update(endpoint=manager.RELAY, ca_file=str(home / "stack/tls/ca.pem"))
    write_json(home / "connection.json", connection)
    calls = mock_docker(monkeypatch)
    result = relay_upgrade.upgrade(home, IMAGE)
    assert result == {"prepared": True, "upgraded": False}
    assert [args[0][0] for args in calls] == ["config"]
    assert not (home / "backups").exists()


def test_invalid_existing_tls_material_fails_before_stop_or_backup(
    tmp_path, monkeypatch
):
    home = managed_home(tmp_path)
    relay_tls.provision(home)
    ca = home / "stack/tls/ca.pem"
    ca.write_bytes(b"invalid synthetic certificate")
    calls = mock_docker(monkeypatch)

    with pytest.raises(ValueError):
        relay_upgrade.upgrade(home, IMAGE)

    assert [args[0][0] for args in calls] == ["config"]
    assert not (home / "backups").exists()
    assert (home / "stack/tls/ca.pem").read_bytes() == b"invalid synthetic certificate"
    assert read_json(home / "connection.json")["endpoint"] == "http://127.0.0.1:9495"
