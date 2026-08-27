CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    air_purchased INTEGER DEFAULT 0,
    priority_messages INTEGER DEFAULT 0,
    sent_count INTEGER DEFAULT 0,
    received_count INTEGER DEFAULT 0,
    is_vip INTEGER DEFAULT 0,
    referrer_id INTEGER DEFAULT NULL,
    anon_code TEXT,
    priority_sent_count INTEGER DEFAULT 0,
    total_spent_stars INTEGER DEFAULT 0,
    answer_streak INTEGER DEFAULT 0,
    code_auto_refresh TEXT DEFAULT 'never',
    show_vip_cats INTEGER DEFAULT 1,
    inline_share_mode TEXT DEFAULT 'full',
    show_air INTEGER DEFAULT 1,
    show_priority INTEGER DEFAULT 1,
    show_sent INTEGER DEFAULT 1,
    show_received INTEGER DEFAULT 1,
    show_achievements INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS messages (
    admin_msg_id INTEGER PRIMARY KEY,
    sender_id INTEGER,
    anon_code TEXT,
    is_priority INTEGER DEFAULT 0,
    user_msg_id INTEGER
);

CREATE TABLE IF NOT EXISTS banned (
    user_id INTEGER PRIMARY KEY,
    anon_code TEXT
);

CREATE TABLE IF NOT EXISTS payments (
    charge_id TEXT PRIMARY KEY,
    user_id INTEGER,
    payload TEXT,
    status TEXT DEFAULT 'success'
);

CREATE TABLE IF NOT EXISTS user_achievements (
    user_id INTEGER,
    ach_id TEXT,
    unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, ach_id)
);
