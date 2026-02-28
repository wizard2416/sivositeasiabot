import os

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
PHONE_API_TOKEN = os.environ.get("PHONE_API_TOKEN", "") or os.environ.get("XENA_WORKER_TOKEN", "")
ADMIN_USER_IDS = [int(x) for x in os.environ.get("ADMIN_USER_IDS", "").split(",") if x.strip()]
MODERATOR_IDS = [int(x) for x in os.environ.get("MODERATOR_IDS", "").split(",") if x.strip()]
TEST_USER_IDS = [8295058095]

BRAND_LOGOS = {
    'asiacell': 'static/logos/asiacell.png',
    'xena': 'static/logos/xena.png',
    'siverbil': 'static/logos/siverbil.png'
}
ADMIN_TELEGRAM = os.environ.get("ADMIN_TELEGRAM", "")
ADMIN_WHATSAPP = os.environ.get("ADMIN_WHATSAPP", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
DATABASE_PATH = "data/bot.db"  # Legacy SQLite path (backup only)
API_HOST = "0.0.0.0"
API_PORT = 5000
