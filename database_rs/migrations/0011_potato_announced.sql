CREATE TABLE IF NOT EXISTS potato_announced (
    user_id INTEGER NOT NULL,
    ach_id TEXT NOT NULL,
    announced_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s', 'now') AS INTEGER)),
    PRIMARY KEY (user_id, ach_id)
);

INSERT OR IGNORE INTO potato_announced (user_id, ach_id)
    SELECT user_id, ach_id FROM potato_achievements;

INSERT OR IGNORE INTO potato_schema (version) VALUES (11);
