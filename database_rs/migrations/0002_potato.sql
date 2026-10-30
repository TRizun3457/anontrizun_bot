-- Rotten Potato game. Idempotent: the Python store re-applies this file on start.
CREATE TABLE IF NOT EXISTS potato_players (
    user_id INTEGER PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1,
    received INTEGER NOT NULL DEFAULT 0,
    passed INTEGER NOT NULL DEFAULT 0,
    exploded INTEGER NOT NULL DEFAULT 0,
    best_pass_streak INTEGER NOT NULL DEFAULT 0,
    pass_streak INTEGER NOT NULL DEFAULT 0,
    fastest_pass_sec INTEGER
);

CREATE TABLE IF NOT EXISTS potato_games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    starter_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    holder_id INTEGER,
    holder_since INTEGER,
    expires_at INTEGER,
    pass_count INTEGER NOT NULL DEFAULT 0,
    duration_sec INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_potato_one_active_per_chat
    ON potato_games(chat_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS potato_history (
    game_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (game_id, user_id)
);

CREATE TABLE IF NOT EXISTS potato_achievements (
    user_id INTEGER NOT NULL,
    ach_id TEXT NOT NULL,
    unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, ach_id)
);
