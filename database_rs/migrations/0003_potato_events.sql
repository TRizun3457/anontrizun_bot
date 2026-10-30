ALTER TABLE potato_games ADD COLUMN kind TEXT NOT NULL DEFAULT 'normal';
ALTER TABLE potato_players ADD COLUMN hide_stats INTEGER NOT NULL DEFAULT 0;
ALTER TABLE potato_players ADD COLUMN rot_exploded INTEGER NOT NULL DEFAULT 0;

DROP INDEX IF EXISTS idx_potato_one_active_per_chat;
CREATE UNIQUE INDEX IF NOT EXISTS idx_potato_one_normal_per_chat
    ON potato_games(chat_id) WHERE status = 'active' AND kind = 'normal';

CREATE TABLE IF NOT EXISTS potato_chat_cooldown (
    chat_id INTEGER PRIMARY KEY,
    last_started INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS potato_rot_days (
    day TEXT PRIMARY KEY,
    is_rot INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS potato_rot_spawns (
    day TEXT NOT NULL,
    spawn_at INTEGER NOT NULL,
    launched INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, spawn_at)
);

CREATE TABLE IF NOT EXISTS potato_auto (
    key TEXT PRIMARY KEY,
    next_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS potato_schema (
    version INTEGER PRIMARY KEY
);
INSERT OR IGNORE INTO potato_schema (version) VALUES (3);
