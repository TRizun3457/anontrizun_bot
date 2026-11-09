This Telegram bot is designed for exchanging anonymous messages with its owner.

The bot also offers additional features, such as achievements, financial support for the bot’s owner, and possibly interesting designs and fun features.
## Автосборка Rust-модуля

При запуске `python main.py` бот сам сравнивает время изменения исходников `database_rs` (код и миграции) с собранным модулем. Если модуль устарел или не собран, запускается `maturin develop --release`, при необходимости ставится maturin. Нужен установленный Rust (cargo). Отключить: `AUTO_BUILD=0` в `.env`.

