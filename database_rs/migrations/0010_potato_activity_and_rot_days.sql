ALTER TABLE potato_players ADD COLUMN miss_streak INTEGER NOT NULL DEFAULT 0;
ALTER TABLE potato_players ADD COLUMN dormant INTEGER NOT NULL DEFAULT 0;
ALTER TABLE potato_players ADD COLUMN last_received_at INTEGER;

ALTER TABLE potato_extra ADD COLUMN share_fastest INTEGER NOT NULL DEFAULT 1;

ALTER TABLE potato_rot_days ADD COLUMN announce_at INTEGER NOT NULL DEFAULT 0;
ALTER TABLE potato_rot_days ADD COLUMN announced INTEGER NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS idx_potato_players_flagged
    ON potato_players(user_id) WHERE miss_streak > 0 OR dormant = 1;

INSERT OR IGNORE INTO potato_schema (version) VALUES (10);
