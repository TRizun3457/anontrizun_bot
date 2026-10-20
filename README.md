This Telegram bot is designed for exchanging anonymous messages with its owner.

The bot also offers additional features, such as achievements, financial support for the bot’s owner, and possibly interesting designs and fun features.

## Requirements

- Rust 1.94 or newer (edition 2024)
- No system dependencies: TLS uses `rustls` and SQLite is bundled, so the binary is self-contained.

## Configuration

Copy `.env.example` to `.env` and fill in the values:

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `BOT_TOKEN` | yes | – | Telegram bot token |
| `ADMIN_ID` | yes | – | Numeric id of the bot owner |
| `ALLOWED_CHAT_ID` | no | – | Group the bot is restricted to (private chats are always allowed) |
| `ALLOWED_CHAT_LINK` | no | `https://t.me/trizunchat` | Link advertised to users of other chats |
| `DB_NAME` | no | `bot_data.db` | SQLite database file |

`RUST_LOG` controls logging verbosity (`info` by default).

## Build and run

```bash
cargo run --release
```

The bot polls Telegram until it receives `Ctrl+C` (`SIGINT`) or `SIGTERM`.

## Tests

```bash
cargo test --locked
cargo fmt --check
cargo clippy --all-targets -- -D warnings
```

The test suite covers the database layer, the configuration parsing, the command
parsing, the rate limiter, and byte-for-byte comparisons of every user-visible
string against golden fixtures generated from the original implementation.

## Database

`migrations/0001_init.sql` reproduces the original SQLite schema exactly, so an
existing `bot_data.db` keeps working without any migration. The checksum test in
`tests/migration.rs` fails if the schema file ever changes.

## Releases

GitHub Actions lints and tests every push, and uploads self-contained
`anontrizun_bot` builds for Linux `x86_64` and Windows `x86_64` as artifacts
(`anontrizun_bot-linux-x86_64`, `anontrizun_bot-windows-x86_64`), together with
`README.md`, `LICENSE` and `.env.example`.

## License

GPL-3.0-only, see [LICENSE](LICENSE).
