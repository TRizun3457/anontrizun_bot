This Telegram bot is designed for exchanging anonymous messages with its owner.

The bot also offers additional features, such as achievements, financial support for the bot’s owner, and possibly interesting designs and fun features.

## 🥔 Rotten Potato (Гнилая картошка)

* `/potata` in the allowed group chat (anyone) or in a private chat with the bot (admin; optional
  `/potata <minutes>`, 10–360) starts a game. A random eligible bot user gets an anonymous
  message and has 10 min – 6 h (random unless the admin sets it) to press **Pass** — the potato goes
  to another random user. When time runs out it explodes.
* `/potata_info` (private chat) or *Settings → 🥔 Гнилая картошка*: stats (received / passed in
  time / exploded, best streak, fastest pass) and game-only achievements. Only VIP users can hide
  the game from themselves (opt-out); an opt-out is ignored if VIP is lost.
* Storage: `database_rs/migrations/0002_potato.sql`; logic in `potato/`; tests in `tests/`
  (`python -m pytest`).
* Build the Rust extension with `maturin develop` (or `uv sync`) before running `main.py`.
