DROP INDEX IF EXISTS idx_potato_one_normal_per_chat;

CREATE UNIQUE INDEX IF NOT EXISTS idx_potato_one_auto_per_chat
    ON potato_games(chat_id)
    WHERE status = 'active' AND kind = 'normal' AND starter_id = 0;

CREATE UNIQUE INDEX IF NOT EXISTS idx_potato_one_member_per_chat
    ON potato_games(chat_id)
    WHERE status = 'active' AND kind = 'normal' AND starter_id <> 0;

INSERT OR IGNORE INTO potato_schema (version) VALUES (8);
