ALTER TABLE users ADD COLUMN code_refreshed_at INTEGER;

UPDATE users SET anon_code = anon_code || '-' || user_id
WHERE anon_code IS NOT NULL
  AND user_id NOT IN (
      SELECT MIN(user_id) FROM users WHERE anon_code IS NOT NULL GROUP BY anon_code
  );

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_anon_code
    ON users(anon_code) WHERE anon_code IS NOT NULL;
