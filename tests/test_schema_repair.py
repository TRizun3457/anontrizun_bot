import asyncio
import sqlite3
from pathlib import Path

import pytest

from potato.store import PotatoStore
from schema_repair import repair_legacy_schema

MIGRATIONS = Path(__file__).resolve().parent.parent / "database_rs" / "migrations"


def sql(name: str) -> str:
    return (MIGRATIONS / name).read_text(encoding="utf-8")


def legacy_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(sql("0001_init.sql"))
    conn.executescript(sql("0002_potato.sql"))
    conn.executescript(sql("0003_potato_events.sql"))
    conn.execute("INSERT INTO users (user_id) VALUES (1)")
    conn.execute("INSERT INTO potato_players (user_id, passed) VALUES (1, 7)")
    conn.commit()
    conn.close()


def test_legacy_schema_is_repaired_so_sqlx_style_migration_applies(tmp_path):
    path = str(tmp_path / "legacy.db")
    legacy_db(path)
    conn = sqlite3.connect(path)
    with pytest.raises(sqlite3.OperationalError):
        conn.executescript(sql("0003_potato_events.sql"))
    conn.close()

    assert repair_legacy_schema(path) is True
    assert list(tmp_path.glob("legacy.db.bak-*"))

    conn = sqlite3.connect(path)
    conn.executescript(sql("0003_potato_events.sql"))
    assert conn.execute("SELECT passed FROM potato_players").fetchone() == (7,)
    conn.close()


def test_no_repair_when_sqlx_recorded_migration(tmp_path):
    path = str(tmp_path / "ok.db")
    legacy_db(path)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE _sqlx_migrations (version BIGINT PRIMARY KEY, success BOOLEAN)"
    )
    conn.execute("INSERT INTO _sqlx_migrations VALUES (3, 1)")
    conn.commit()
    conn.close()
    assert repair_legacy_schema(path) is False
    assert not list(tmp_path.glob("*.bak-*"))


def test_no_repair_for_fresh_or_missing_db(tmp_path):
    assert repair_legacy_schema(str(tmp_path / "missing.db")) is False
    assert repair_legacy_schema(":memory:") is False
    fresh = str(tmp_path / "fresh.db")
    conn = sqlite3.connect(fresh)
    conn.executescript(sql("0001_init.sql"))
    conn.close()
    assert repair_legacy_schema(fresh) is False


def test_repair_is_idempotent(tmp_path):
    path = str(tmp_path / "twice.db")
    legacy_db(path)
    assert repair_legacy_schema(path) is True
    assert repair_legacy_schema(path) is False


def test_store_verify_mode_requires_schema_and_accepts_full_schema(tmp_path):
    path = str(tmp_path / "v.db")
    conn = sqlite3.connect(path)
    conn.executescript(sql("0001_init.sql"))
    conn.close()
    with pytest.raises(RuntimeError) as err:
        asyncio.run(PotatoStore(path).init(apply_migrations=False))
    assert "maturin develop" in str(err.value)

    full = str(tmp_path / "full.db")
    conn = sqlite3.connect(full)
    conn.executescript(sql("0001_init.sql"))
    for name in (
        "0002_potato.sql",
        "0003_potato_events.sql",
        "0004_potato_extras.sql",
    ):
        conn.executescript(sql(name))
    conn.close()
    store = PotatoStore(full)
    asyncio.run(store.init(apply_migrations=False))
