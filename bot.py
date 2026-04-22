import os
import logging
import tempfile
import asyncio
import base64
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
import yt_dlp

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_CHAT_IDS = set(
    int(x.strip())
    for x in os.getenv("CHAT_IDS", os.getenv("CHAT_ID", "")).split(",")
    if x.strip()
)
COOKIES_BASE64 = os.getenv("COOKIES_BASE64", "")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

SUPPORTED_DOMAINS = ("instagram.com", "facebook.com", "fb.watch", "fb.com")

COOKIES_FILE = "/tmp/cookies.txt"

if COOKIES_BASE64:
    with open(COOKIES_FILE, "w") as f:
        f.write(base64.b64decode(COOKIES_BASE64).decode("utf-8"))
    logging.info("Куки загружены из переменной окружения.")


def is_supported_url(text: str) -> bool:
    return any(domain in text for domain in SUPPORTED_DOMAINS)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_CHAT_IDS:
        return

    text = update.message.text.strip()
    if not is_supported_url(text):
        await update.message.reply_text("Пришли ссылку на Instagram или Facebook.")
        return

    status_msg = await update.message.reply_text("⏬ Скачиваю...")

    with tempfile.TemporaryDirectory() as tmpdir:
        output_template = os.path.join(tmpdir, "%(id)s.%(ext)s")
        ydl_opts = {
            "outtmpl": output_template,
            "format": "best[filesize<50M]/best",
            "quiet": False,
            "no_warnings": False,
        }

        if COOKIES_BASE64 and os.path.exists(COOKIES_FILE):
            ydl_opts["cookiefile"] = COOKIES_FILE

        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, lambda: _download(text, ydl_opts))
        except Exception as e:
            logging.error(f"Download error: {e}")
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
            return

        files = os.listdir(tmpdir)
        if not files:
            await status_msg.edit_text("❌ Файл не найден после скачивания.")
            return

        filepath = os.path.join(tmpdir, files[0])
        file_size = os.path.getsize(filepath)

        if file_size > 50 * 1024 * 1024:
            await status_msg.edit_text("❌ Видео больше 50 МБ — Telegram не позволяет отправить такой файл.")
            return

        await status_msg.edit_text("📤 Отправляю...")
        with open(filepath, "rb") as f:
            await update.message.reply_video(
                video=f,
                supports_streaming=True,
                caption=info.get("title", ""),
            )
        await status_msg.delete()


def _download(url: str, opts: dict) -> dict:
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return info or {}


def main():
    asyncio.set_event_loop(asyncio.new_event_loop())
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logging.info("Бот запущен. Жду ссылки...")
    app.run_polling()


if __name__ == "__main__":
    main()
