import os

# Token bot dari BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "8429800345:AAG1msHIiec1gTtYq09H7JWTHkKMZf0sM9I")

# Telegram ID admin (integer, bukan string)
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "7111874161"))

# Minimal top up (dalam rupiah)
MIN_TOPUP = 20000

# Path lokal gambar QRIS (disimpan di folder assets/)
QRIS_IMAGE_PATH = "assets/qris.png"

# URL database PostgreSQL dari Railway (ENV: DATABASE_URL)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@host:port/dbname")
