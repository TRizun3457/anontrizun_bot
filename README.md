This Telegram bot is designed for exchanging anonymous messages with its owner.

The bot also offers additional features, such as achievements, financial support for the bot’s owner, and possibly interesting designs and fun features.

## 🥔 Гнилая картошка

* `/potata` в разрешённом чате (может любой участник) или в личных сообщениях с ботом (только админ,
  можно указать минуты: `/potata 45`, от 10 до 360) запускает игру. Случайный пользователь бота
  анонимно получает картошку и от 10 минут до 6 часов (случайно, если админ не задал время) должен
  нажать кнопку передачи — картошка уйдёт другому случайному пользователю. Не успел — она взрывается.
* `/potata_info` в личке с ботом или «Настройки → 🥔 Гнилая картошка»: статистика (получено,
  передано вовремя, взорвалось, лучшая серия, самая быстрая передача) и достижения игры.
  Скрыть игру от себя могут только VIP; если VIP пропал, скрытие перестаёт действовать.
* Хранение: `database_rs/migrations/0002_potato.sql`, логика в `potato/`, тесты в `tests/`
  (`python -m pytest`).
* Перед запуском `main.py` соберите Rust-модуль: `maturin develop` (или `uv sync`).
