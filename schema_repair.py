import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

LEGACY_COLUMNS = (
    ("potato_games", "kind"),
    ("potato_players", "hide_stats"),
    ("potato_players", "rot_exploded"),
)
LEGACY_MIGRATION_VERSION = 3


def repair_legacy_schema(db_path: str) -> bool:
    path = Path(db_path)
    if db_path == ":memory:" or not path.exists():
        return False
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "potato_games" not in tables:
            return False
        if "_sqlx_migrations" in tables:
            recorded = conn.execute(
                "SELECT 1 FROM _sqlx_migrations WHERE version = ? AND success = 1",
                (LEGACY_MIGRATION_VERSION,),
            ).fetchone()
            if recorded:
                return False
        present = [
            (table, column)
            for table, column in LEGACY_COLUMNS
            if table in tables
            and column
            in {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        ]
        if not present:
            return False
        backup = path.with_name(f"{path.name}.bak-{int(time.time())}")
        dest = sqlite3.connect(backup)
        try:
            conn.backup(dest)
        finally:
            dest.close()
        conn.execute("DROP INDEX IF EXISTS idx_potato_one_normal_per_chat")
        for table, column in present:
            conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        conn.commit()
        logger.warning(
            "Старая схема картошки исправлена (копия БД: %s). Удалены колонки: %s",
            backup.name,
            ", ".join(f"{t}.{c}" for t, c in present),
        )
        return True
    finally:
        conn.close()
