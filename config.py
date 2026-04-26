import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID", 123456789))  # Ganti dengan Telegram User ID Anda
RECORDINGS_DIR = "./recordings/"

# Timeout untuk ffmpeg (dalam detik)
FFMPEG_TIMEOUT = 300

# Pastikan TELEGRAM_BOT_TOKEN dan AUTHORIZED_USER_ID telah diatur
if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set or is default. Please configure it.")
if AUTHORIZED_USER_ID == 123456789:
    raise ValueError("AUTHORIZED_USER_ID environment variable not set or is default. Please configure it.")
