import os
from dotenv import load_dotenv

# Muat environment variables dari file .env jika ada
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", 0)) # ID channel atau grup tempat file akan diunggah
AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID", 123456789))  # Ganti dengan Telegram User ID Anda
RECORDINGS_DIR = "./recordings/"

# Timeout untuk ffmpeg (dalam detik)
FFMPEG_TIMEOUT = 300

# Pastikan TELEGRAM_BOT_TOKEN dan AUTHORIZED_USER_ID telah diatur
if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set or is default. Please configure it.")
if AUTHORIZED_USER_ID == 123456789:
    raise ValueError("AUTHORIZED_USER_ID environment variable not set or is default. Please configure it.")

# Validasi untuk Telethon
if not API_ID or not API_HASH:
    raise ValueError("API_ID and API_HASH environment variables must be set for Telethon.")
if not SESSION_STRING:
    raise ValueError("SESSION_STRING environment variable must be set for Telethon.")
if not CHANNEL_ID:
    raise ValueError("CHANNEL_ID environment variable must be set for Telethon.")
