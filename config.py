import os
import sys

from dotenv import load_dotenv

load_dotenv()

token = os.getenv("BOT_TOKEN")
if not token:
    raise ValueError("BOT_TOKEN не найден в файле .env!")

admin_id_raw = os.getenv("ADMIN_ID")
if not admin_id_raw:
    raise ValueError("ADMIN_ID не найден в файле .env!")

try:
    ADMIN_ID: int = int(admin_id_raw)
except ValueError:
    sys.exit("Ошибка конфигурации: ADMIN_ID в .env должен быть целым числом.")

allowed_chat_id_raw = os.getenv("ALLOWED_CHAT_ID")
ALLOWED_CHAT_ID: int | None = None
if allowed_chat_id_raw:
    try:
        ALLOWED_CHAT_ID = int(allowed_chat_id_raw)
    except ValueError:
        sys.exit(
            "Ошибка конфигурации: ALLOWED_CHAT_ID в .env должен быть целым числом."
        )

BOT_TOKEN: str = token
ALLOWED_CHAT_LINK: str = os.getenv("ALLOWED_CHAT_LINK", "https://t.me/trizunchat")
DB_NAME: str = os.getenv("DB_NAME", "bot_data.db")
