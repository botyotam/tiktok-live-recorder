import asyncio
import logging
import os
import re

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config import TELEGRAM_BOT_TOKEN, AUTHORIZED_USER_ID, RECORDINGS_DIR, API_ID, API_HASH, SESSION_STRING, CHANNEL_ID
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from recorder import TikTokRecorder

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

recorder = TikTokRecorder()

# Inisialisasi Telethon Client
telethon_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# Decorator for authorized users only
def authorized_only(func):
    async def wrapper(update: Update, context):
        if update.effective_user.id != AUTHORIZED_USER_ID:
            logger.info(f"Unauthorized access attempt from user ID: {update.effective_user.id}")
            return
        return await func(update, context)
    return wrapper

@authorized_only
async def start_command(update: Update, context):
    await update.message.reply_text(
        "Halo! Saya adalah bot perekam live TikTok. Kirimkan username TikTok (misal: `@username`) atau URL live TikTok untuk memulai perekaman. \n\nPerintah yang tersedia:\n/record <username/URL> - Memulai perekaman\n/stop - Menghentikan rekaman aktif\n/status - Melihat status rekaman\n/save - Mengunggah rekaman ke Telegram dan menghapus file lokal"
    )

@authorized_only
async def record_command(update: Update, context):
    if not context.args:
        await update.message.reply_text("Mohon berikan username TikTok atau URL live TikTok.")
        return

    identifier = context.args[0]
    chat_id = update.effective_chat.id
    
    # Send initial checking message
    checking_msg = await update.message.reply_text(f"🔍 Sedang mengecek akun {identifier}...")

    success, message = await recorder.start_recording(chat_id, identifier)
    
    # Edit the checking message with the result
    await checking_msg.edit_text(message)

@authorized_only
async def stop_command(update: Update, context):
    chat_id = update.effective_chat.id
    logger.info(f"Stop command received for chat_id: {chat_id}")
    success, message = await recorder.stop_recording(chat_id)
    await update.message.reply_text(message)

@authorized_only
async def status_command(update: Update, context):
    chat_id = update.effective_chat.id
    status_message = await recorder.get_recording_status(chat_id)
    await update.message.reply_text(status_message)

@authorized_only
async def save_command(update: Update, context):
    chat_id = update.effective_chat.id
    file_path = recorder.get_recording_file(chat_id)

    if not file_path or (not os.path.exists(file_path) and not os.path.exists(file_path + ".part")):
        await update.message.reply_text("Tidak ada rekaman aktif atau file tidak ditemukan.")
        return

    # Prioritize completed file, otherwise use part file
    if not os.path.exists(file_path) and os.path.exists(file_path + ".part"):
        file_path = file_path + ".part"

    try:
        file_size = os.path.getsize(file_path)
        # Telegram Bot API has a 50MB limit for files sent via bot.send_document
        # For larger files, users typically need to use a custom bot API server or upload to a cloud storage.
        await update.message.reply_text("Sedang mengunggah file ke Telegram (via Telethon), mohon tunggu...")
        try:
            await telethon_client.start()
            await telethon_client.send_file(CHANNEL_ID, file_path, caption=f"Rekaman TikTok dari @{recorder.active_recordings[chat_id]['username']}")
            await telethon_client.disconnect()
            await update.message.reply_text("File berhasil diunggah ke channel. Menghapus file lokal...")
            recorder.delete_recording_file(file_path)
            recorder.clear_recording_info(chat_id)
            await update.message.reply_text("File lokal berhasil dihapus.")
        except Exception as e:
            logger.error(f"Gagal mengunggah file {file_path} via Telethon: {e}")
            await update.message.reply_text(f"❌ Gagal mengunggah file via Telethon: {e}. Pastikan SESSION_STRING dan CHANNEL_ID sudah benar, atau coba lagi nanti.")
        finally:
            if telethon_client.is_connected():
                await telethon_client.disconnect()
    except Exception as e:
        logger.error(f"Gagal mengunggah file {file_path}: {e}")
        await update.message.reply_text(f"Gagal mengunggah file: {e}")

@authorized_only
async def handle_message(update: Update, context):
    text = update.message.text
    chat_id = update.effective_chat.id

    # Check if it's a TikTok username or URL
    if re.match(r"^@?[a-zA-Z0-9._-]+" , text) or re.match(r"https?://(www.)?tiktok.com/.*", text):
        # Send initial checking message
        checking_msg = await update.message.reply_text(f"🔍 Sedang mengecek akun {text}...")
        
        success, message = await recorder.start_recording(chat_id, text)
        
        # Edit the checking message with the result
        await checking_msg.edit_text(message)
    else:
        await update.message.reply_text("Saya hanya bisa memproses username TikTok atau URL live TikTok.")

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("record", record_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("save", save_command))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
