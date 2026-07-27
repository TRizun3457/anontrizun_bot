import os

from dotenv import load_dotenv

load_dotenv()

token = os.getenv("BOT_TOKEN")
if not token:
    raise ValueError("BOT_TOKEN не найден в файле .env!")

admin_id_raw = os.getenv("ADMIN_ID")
if not admin_id_raw:
    raise ValueError("ADMIN_ID не найден в файле .env!")

allowed_chat_id_raw = os.getenv("ALLOWED_CHAT_ID")
if not allowed_chat_id_raw:
    raise ValueError("ALLOWED_CHAT_ID не найден в файле .env!")

BOT_TOKEN: str = token
ADMIN_ID: int = int(admin_id_raw)
ALLOWED_CHAT_ID: int = int(allowed_chat_id_raw)

BOT_USERNAME: str = os.getenv("BOT_USERNAME", "anontrizun_bot")
ALLOWED_CHAT_LINK: str = os.getenv("ALLOWED_CHAT_LINK", "https://t.me/trizunchat")
DB_NAME: str = os.getenv("DB_NAME", "bot_data.db")
