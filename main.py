import os
import json
import threading
from flask import Flask
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI
from pydub import AudioSegment
import requests

# 🔐 ENV variables
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_PROJECT = os.environ["OPENAI_PROJECT"]

# 🧠 Setup OpenAI
client = OpenAI(api_key=OPENAI_API_KEY, organization=OPENAI_PROJECT)

# 🚀 Flask app to keep alive
flask_app = Flask(__name__)
@flask_app.route("/")
def home():
    return "✅ MansourAI bot is alive!"

def keep_alive():
    flask_app.run(host="0.0.0.0", port=8080)

# 🗂 Memory directory
if not os.path.exists("memory"):
    os.makedirs("memory")

# 🧠 Get or create memory
def get_memory(user_id):
    path = f"memory/{user_id}.json"
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    else:
        return {"history": [], "personality": "You are a helpful assistant."}

def save_memory(user_id, memory):
    with open(f"memory/{user_id}.json", "w") as f:
        json.dump(memory, f)

# 💬 Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello! I'm MansourAI, powered by GPT-4o. Send a message or voice note to begin.")

# 🧠 Set personality
async def set_personality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    personality = " ".join(context.args)
    memory = get_memory(user_id)
    memory["personality"] = personality
    save_memory(user_id, memory)
    await update.message.reply_text(f"🧠 Personality updated to:\n\n“{personality}”")

# 🧠 Chat handler
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_input = update.message.text

    memory = get_memory(user_id)
    memory["history"].append({"role": "user", "content": user_input})

    messages = [{"role": "system", "content": memory["personality"]}] + memory["history"]

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
        )
        reply = response.choices[0].message.content
        memory["history"].append({"role": "assistant", "content": reply})
        save_memory(user_id, memory)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

# 🎙 Voice input
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    voice = await update.message.voice.get_file()
    voice_path = f"audio/{user_id}.ogg"
    mp3_path = f"audio/{user_id}.mp3"

    if not os.path.exists("audio"):
        os.makedirs("audio")

    await voice.download_to_drive(voice_path)

    # Convert to mp3 using pydub
    AudioSegment.from_file(voice_path).export(mp3_path, format="mp3")

    # Transcribe using Whisper
    try:
        with open(mp3_path, "rb") as f:
            transcript = client.audio.transcriptions.create(model="whisper-1", file=f)
        update.message.text = transcript.text
        await handle_text(update, context)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Transcription failed: {e}")

# 🔊 Voice reply
async def tts_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text[5:]  # remove "/say "
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

# 🚀 Launch the bot
async def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpersonality", set_personality))
    app.add_handler(CommandHandler("say", tts_reply))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("🤖 GPT-4o bot (Memory + Voice Input + Voice Reply) running...")
    await app.run_polling()

if __name__ == "__main__":
    threading.Thread(target=keep_alive).start()

import asyncio

if __name__ == "__main__":
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(main())  # non-blocking if loop is running
        loop.run_forever()
    except RuntimeError:
        asyncio.run(main())
