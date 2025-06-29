import os
import json
import threading
from flask import Flask, request
from telegram import Update, Voice
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from telegram.helpers import escape_markdown
from telegram.constants import ParseMode
from telegram.files.inputfile import InputFile
from openai import OpenAI
from pydub import AudioSegment
import requests

# ENVIRONMENT VARIABLES
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_PROJECT = os.environ["OPENAI_PROJECT"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]

# Initialize OpenAI
client = OpenAI(api_key=OPENAI_API_KEY, organization=OPENAI_PROJECT)

# Flask app to keep the service alive
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "✅ MansourAI bot is alive!"

# Create necessary folders
os.makedirs("memory", exist_ok=True)
os.makedirs("audio", exist_ok=True)

# MEMORY HANDLING
def get_memory(user_id):
    path = f"memory/{user_id}.json"
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {"history": [], "personality": "You are a helpful assistant."}

def save_memory(user_id, memory):
    with open(f"memory/{user_id}.json", "w") as f:
        json.dump(memory, f)

# COMMAND: /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello! I'm MansourAI, powered by GPT-4o. Send me a message or voice note!")

# COMMAND: /setpersonality
async def set_personality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    personality = " ".join(context.args)
    memory = get_memory(user_id)
    memory["personality"] = personality
    save_memory(user_id, memory)
    await update.message.reply_text(f"🧠 Personality updated to:\n\n“{personality}”")

# TEXT HANDLER
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_input = update.message.text

    memory = get_memory(user_id)
    memory["history"].append({"role": "user", "content": user_input})

    messages = [{"role": "system", "content": memory["personality"]}] + memory["history"]

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        reply = response.choices[0].message.content
        memory["history"].append({"role": "assistant", "content": reply})
        save_memory(user_id, memory)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"⚠️ GPT error: {e}")

# VOICE HANDLER
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    voice: Voice = update.message.voice
    file = await voice.get_file()
    voice_path = f"audio/{user_id}.ogg"
    mp3_path = f"audio/{user_id}.mp3"
    await file.download_to_drive(voice_path)

    # Convert .ogg to .mp3
    AudioSegment.from_file(voice_path).export(mp3_path, format="mp3")

    # Transcribe using Whisper
    try:
        with open(mp3_path, "rb") as f:
            transcript = client.audio.transcriptions.create(model="whisper-1", file=f)
        update.message.text = transcript.text
        await handle_text(update, context)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Voice transcription failed: {e}")

# COMMAND: /say
async def tts_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text[5:]  # after "/say "
    user_id = update.effective_user.id

    try:
        speech = client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=text
        )
        output_path = f"audio/{user_id}_reply.mp3"
        speech.stream_to_file(output_path)
        await update.message.reply_voice(voice=InputFile(output_path))
    except Exception as e:
        await update.message.reply_text(f"⚠️ TTS failed: {e}")

# TELEGRAM BOT LAUNCHER
async def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpersonality", set_personality))
    app.add_handler(CommandHandler("say", tts_reply))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("🤖 GPT-4o bot (Memory + Voice + TTS) is running via webhook...")
    await app.initialize()
    await app.start()
    await app.bot.set_webhook(f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}")
    await app.updater.start_polling()  # Required to keep webhook alive internally

if __name__ == "__main__":
    threading.Thread(target=flask_app.run, kwargs={"host": "0.0.0.0", "port": 8080}).start()
    import asyncio
    asyncio.run(main())
