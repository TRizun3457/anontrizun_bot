CREATE INDEX IF NOT EXISTS idx_potato_games_status ON potato_games(status, expires_at);
CREATE INDEX IF NOT EXISTS idx_potato_games_starter ON potato_games(starter_id, status);
CREATE INDEX IF NOT EXISTS idx_potato_games_holder ON potato_games(holder_id, status);
