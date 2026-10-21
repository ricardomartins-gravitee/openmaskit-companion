"""Offline, transactional URL-only migration for the pinned OpenMaskit store."""

import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit


def upgrade_urls(database, connector):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", connector):
        raise ValueError("Invalid paired connector identity")
    if not database.is_file() or database.is_symlink():
        raise ValueError("An existing OpenMaskit database is required")
    changed = 0
    with sqlite3.connect(database) as store:
        store.execute("BEGIN IMMEDIATE")
        rows = store.execute(
            "SELECT id,config_json FROM mcp_servers WHERE source='custom'"
        ).fetchall()
        for target, original in rows:
            config = json.loads(original)
            if not isinstance(config, dict) or config.get("transport") != "http":
                continue
            url = urlsplit(config.get("url", ""))
            if (
                url.scheme != "http"
                or url.hostname != "connector-relay"
                or url.port != 9495
                or url.username is not None
                or url.password is not None
                or url.query
                or url.fragment
                or not re.fullmatch(
                    r"/mcp/" + re.escape(connector) + r"/[a-z][a-z0-9-]{0,47}", url.path
                )
            ):
                continue
            config["url"] = url._replace(scheme="https").geturl()
            result = store.execute(
                "UPDATE mcp_servers SET config_json=? WHERE id=? AND config_json=?",
                (json.dumps(config), target, original),
            )
            if result.rowcount != 1:
                raise ValueError("Stored connection changed during TLS migration")
            changed += 1
    return changed


if __name__ == "__main__":
    import sys

    count = upgrade_urls(Path.home() / ".openmaskit/store.db", sys.argv[1])
    print(json.dumps({"upgraded_connections": count}))
