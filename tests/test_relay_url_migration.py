"""Regression tests for the offline URL-only SQLite migration."""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parents[1] / "src/openmaskit_companion/data/migrate_relay_tls.py"
)
SPEC = importlib.util.spec_from_file_location("migrate_relay_tls", SCRIPT)
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)
upgrade_urls = MIGRATION.upgrade_urls


def make_store(path, rows):
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE mcp_servers (id TEXT PRIMARY KEY, source TEXT, config_json TEXT, active INTEGER, alias TEXT)"
        )
        db.executemany("INSERT INTO mcp_servers VALUES (?, ?, ?, ?, ?)", rows)
        db.execute("CREATE TABLE audit_log (event TEXT)")
        db.execute("INSERT INTO audit_log VALUES ('keep audit history')")
        db.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value BLOB)")
        db.execute("INSERT INTO settings VALUES ('encryption-key-ref', X'001122')")


def config(url, **extra):
    value = {"transport": "http", "url": url, **extra}
    return json.dumps(value, separators=(",", ":"))


def rows(path):
    with sqlite3.connect(path) as db:
        return db.execute(
            "SELECT id,source,config_json,active,alias FROM mcp_servers ORDER BY id"
        ).fetchall()


def test_migrates_only_exact_paired_relay_urls_and_preserves_all_other_values(tmp_path):
    db = tmp_path / "store.db"
    target = config(
        "http://connector-relay:9495/mcp/paired-computer/weather",
        headers={"Authorization": "encrypted:synthetic-header"},
        timeout=51,
        metadata={"nested": [1, False, None]},
        retry_policy={"attempts": 0},
    )
    untouched = [
        ("paired-weather", "custom", target, 0, "weather alias"),
        (
            "other-computer",
            "custom",
            config("http://connector-relay:9495/mcp/another-computer/weather"),
            1,
            "other",
        ),
        (
            "other-profile",
            "custom",
            config("http://connector-relay:9495/mcp/paired-computer/calendar"),
            1,
            "calendar",
        ),
        (
            "wrong-port",
            "custom",
            config("http://connector-relay:9496/mcp/paired-computer/weather"),
            1,
            "wrong port",
        ),
        (
            "wrong-host",
            "custom",
            config("http://localhost:9495/mcp/paired-computer/weather"),
            1,
            "wrong host",
        ),
        (
            "inactive-nontarget",
            "custom",
            config("http://connector-relay:9495/not-mcp/paired-computer/weather"),
            0,
            "inactive",
        ),
        (
            "query",
            "custom",
            config("http://connector-relay:9495/mcp/paired-computer/weather?token=x"),
            1,
            "query",
        ),
        (
            "credentials",
            "custom",
            config("http://user:pass@connector-relay:9495/mcp/paired-computer/weather"),
            1,
            "credential",
        ),
        (
            "already-tls",
            "custom",
            config("https://connector-relay:9495/mcp/paired-computer/weather"),
            1,
            "tls",
        ),
        (
            "wrong-transport",
            "custom",
            json.dumps(
                {
                    "transport": "stdio",
                    "url": "http://connector-relay:9495/mcp/paired-computer/weather",
                }
            ),
            1,
            "stdio",
        ),
        ("marketplace", "marketplace", target, 1, "managed source"),
    ]
    make_store(db, untouched)
    before = rows(db)

    assert upgrade_urls(db, "paired-computer") == 2

    after = rows(db)
    changed = {row[0]: row for row in after}["paired-weather"]
    original = {row[0]: row for row in before}["paired-weather"]
    changed_config = json.loads(changed[2])
    original_config = json.loads(original[2])
    assert (
        changed_config["url"]
        == "https://connector-relay:9495/mcp/paired-computer/weather"
    )
    original_config["url"] = changed_config["url"]
    assert changed_config == original_config
    assert changed[0:2] == original[0:2] and changed[3:] == original[3:]
    calendar = {row[0]: row for row in after}["other-profile"]
    assert (
        json.loads(calendar[2])["url"]
        == "https://connector-relay:9495/mcp/paired-computer/calendar"
    )
    for row in after:
        if row[0] not in {"paired-weather", "other-profile"}:
            assert row == {item[0]: item for item in before}[row[0]]
    with sqlite3.connect(db) as store:
        assert store.execute("SELECT * FROM audit_log").fetchall() == [
            ("keep audit history",)
        ]
        assert store.execute("SELECT * FROM settings").fetchall() == [
            ("encryption-key-ref", b"\x00\x11\x22")
        ]


@pytest.mark.parametrize(
    "connector", ["", "Upper", "a" * 49, "-bad", "bad_name", "bad/path"]
)
def test_rejects_invalid_connector_identity_without_changing_database(
    tmp_path, connector
):
    db = tmp_path / "store.db"
    make_store(
        db,
        [
            (
                "one",
                "custom",
                config("http://connector-relay:9495/mcp/valid/name"),
                1,
                "one",
            )
        ],
    )
    before = db.read_bytes()
    with pytest.raises(ValueError, match="Invalid paired connector"):
        upgrade_urls(db, connector)
    assert db.read_bytes() == before


def test_malformed_row_rolls_back_prior_url_changes(tmp_path):
    db = tmp_path / "store.db"
    make_store(
        db,
        [
            (
                "a-valid",
                "custom",
                config("http://connector-relay:9495/mcp/paired-computer/weather"),
                1,
                "a",
            ),
            ("z-malformed", "custom", "{not json", 1, "z"),
        ],
    )
    before = rows(db)
    with pytest.raises(json.JSONDecodeError):
        upgrade_urls(db, "paired-computer")
    assert rows(db) == before


def test_requires_real_nonsymlink_database(tmp_path):
    missing = tmp_path / "missing.db"
    with pytest.raises(ValueError, match="existing OpenMaskit database"):
        upgrade_urls(missing, "paired-computer")
    real = tmp_path / "real.db"
    make_store(real, [])
    link = tmp_path / "alias.db"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="existing OpenMaskit database"):
        upgrade_urls(link, "paired-computer")
