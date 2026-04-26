import asyncio
import logging
import os
import re

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config import TELEGRAM_BOT_TOKEN, AUTHORIZED_USER_ID, RECORDINGS_DIR
from recorder import TikTokRecorder

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

recorder = TikTokRecorder()

# Decorator for authorized users only
def authorized_only(func):
    async def wrapper(update: Update, context):
        if update.effective_user.id != AUTHORIZED_USER_ID:
            logger.info(f"Unauthorized access attempt from user ID: {update.effective_user.id}")
            # Silent ignore
            return
        return await func(update, context)
    return wrapper

@authorized_only
async def start_command(update: Update, context):
    await update.message.reply_text(
        "Halo! Kirimkan username TikTok atau URL live TikTok untuk memulai perekaman."
    )

@authorized_only
async def record_command(update: Update, context):
    if not context.args:
        await update.message.reply_text("Mohon berikan username TikTok atau URL live TikTok.")
        return

    identifier = context.args[0]
    chat_id = update.effective_chat.id

    success, message = await recorder.start_recording(chat_id, identifier)
    await update.message.reply_text(message)

@authorized_only
async def stop_command(update: Update, context):
    chat_id = update.effective_chat.id
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

    if not file_path or not os.path.exists(file_path):
        await update.message.reply_text("Tidak ada rekaman aktif atau file tidak ditemukan.")
        return

    try:
        await update.message.reply_document(document=open(file_path, 'rb'))
        await update.message.reply_text("File berhasil diunggah. Menghapus file lokal...")
        recorder.delete_recording_file(file_path)
        recorder.clear_recording_info(chat_id)
        await update.message.reply_text("File lokal berhasil dihapus.")
    except Exception as e:
        logger.error(f"Gagal mengunggah file {file_path}: {e}")
        await update.message.reply_text(f"Gagal mengunggah file: {e}")

@authorized_only
async def handle_message(update: Update, context):
    text = update.message.text
    chat_id = update.effective_chat.id

    # Check if it's a TikTok username or URL
    if re.match(r"^@?[a-zA-Z0-9._-]+" , text) or re.match(r"https?://(www.)?tiktok.com/.*", text):
        success, message = await recorder.start_recording(chat_id, text)
        await update.message.reply_text(message)
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
