import os
import logging
import asyncio
import threading
import requests
from flask import Flask

from openai import OpenAI
from pydub import AudioSegment
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# === ENV ===
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_PROJECT = os.environ.get("OPENAI_PROJECT")
PORT = int(os.environ.get("PORT", 8080))

# === Logging ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# === Flask ===
flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return "MansourAI is live"

def keep_alive():
    flask_app.run(host="0.0.0.0", port=PORT)

# === OpenAI ===
client = OpenAI(api_key=OPENAI_API_KEY, organization=OPENAI_PROJECT)

# === Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hi! I'm MansourAI. Send me a voice message!")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await context.bot.get_file(update.message.voice.file_id)
    file_path = "voice.ogg"
    await file.download_to_drive(file_path)

    sound = AudioSegment.from_file(file_path)
    wav_path = "voice.wav"
    sound.export(wav_path, format="wav")

    with open(wav_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(model="whisper-1", file=audio_file)
        user_message = transcript.text

    await update.message.reply_text(f"🗣️ You said: {user_message}")

    messages = [{"role": "user", "content": user_message}]
    response = client.chat.completions.create(
        model="gpt-4o", messages=messages
    )

    reply = response.choices[0].message.content
    await update.message.reply_text(f"🤖 {reply}")

# === Telegram App ===
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    logging.info("🤖 GPT-4o bot (Memory + Voice Input + Voice Reply) running...")
    await app.run_polling()

# === Run ===
if __name__ == "__main__":
    threading.Thread(target=keep_alive).start()

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        asyncio.ensure_future(main())
    else:
        loop.run_until_complete(main())
