import os
import asyncio
import threading
import functools

from flask import Flask
from pydub import AudioSegment
import openai

# New imports for PTB v20+ (Application, handlers, filters)
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Load API keys from environment variables (set these in Render dashboard)
TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN")
openai.api_key = os.getenv("OPENAI_API_KEY")

# Flask app for keep-alive heartbeat (Render expects an HTTP server on $PORT)
app = Flask(__name__)
@app.route('/')
def keep_alive():
    return "Bot is running", 200

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

# Start Flask server in a background thread (non-blocking)
threading.Thread(target=run_flask, daemon=True).start()

# --- Define bot command and message handlers (async for PTB v20+):
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /start command."""
    # In PTB v20+, sending messages is async, so we use await
    await update.message.reply_text(
        "Hello! I am your AI bot. Send a text or voice message and I'll reply with GPT. "
        "Use /setpersonality to change my style."
    )

async def set_personality(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /setpersonality <persona> command to set the bot's personality."""
    persona = " ".join(context.args)
    if not persona:
        await update.message.reply_text("Usage: /setpersonality <personality description>")
        return
    # Store the personality in user_data (per-user persistent context)
    context.user_data["personality"] = persona
    await update.message.reply_text(f"Personality set! I will now respond with the style: \"{persona}\"")

async def say(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /say <message> command to get a GPT-based response to a prompt."""
    user_message = " ".join(context.args)
    if not user_message:
        await update.message.reply_text("Usage: /say <message>")
        return
    # Build the OpenAI ChatCompletion request with optional personality
    personality = context.user_data.get("personality")
    messages = []
    if personality:
        # Include persona as a system message so GPT knows the style
        messages.append({"role": "system", "content": personality})
    messages.append({"role": "user", "content": user_message})
    # Call OpenAI GPT (this is blocking, so run it in an executor to avoid freezing the bot)
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        functools.partial(openai.ChatCompletion.create, model="gpt-3.5-turbo", messages=messages)
    )
    reply_text = response['choices'][0]['message']['content'].strip()
    await update.message.reply_text(reply_text)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for regular text messages (not commands)."""
    user_message = update.message.text.strip()
    # Build messages for GPT, including personality if set
    personality = context.user_data.get("personality")
    messages = []
    if personality:
        messages.append({"role": "system", "content": personality})
    messages.append({"role": "user", "content": user_message})
    # Call OpenAI to get a response (run in executor to avoid blocking)
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        functools.partial(openai.ChatCompletion.create, model="gpt-3.5-turbo", messages=messages)
    )
    reply_text = response['choices'][0]['message']['content'].strip()
    await update.message.reply_text(reply_text)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for voice messages: transcribe with Whisper, then reply with GPT."""
    voice_file = await context.bot.get_file(update.message.voice.file_id)  # Async get file
    # Download the voice file to disk (async). Use unique name to avoid collisions.
    ogg_path = f"voice_{update.effective_chat.id}_{update.message.message_id}.ogg"
    await voice_file.download(custom_path=ogg_path)  # PTB v20+: File.download is async
    # Convert OGG (Opus) to WAV using pydub (requires ffmpeg in environment)
    audio = AudioSegment.from_file(ogg_path)
    wav_path = f"voice_{update.effective_chat.id}_{update.message.message_id}.wav"
    audio.export(wav_path, format="wav")
    # Transcribe audio to text via OpenAI Whisper API (blocking call offloaded to executor)
    def transcribe(path):
        with open(path, "rb") as audio_file:
            return openai.Audio.transcribe("whisper-1", audio_file)
    loop = asyncio.get_running_loop()
    transcript = await loop.run_in_executor(None, transcribe, wav_path)
    transcribed_text = transcript.get("text", "").strip()
    # Clean up temp audio files
    try:
        os.remove(ogg_path)
        os.remove(wav_path)
    except OSError:
        pass
    if not transcribed_text:
        await update.message.reply_text("⚠️ Sorry, I couldn't transcribe that voice message.")
        return
    # Prepare GPT query with the transcribed text
    personality = context.user_data.get("personality")
    messages = []
    if personality:
        messages.append({"role": "system", "content": personality})
    messages.append({"role": "user", "content": transcribed_text})
    # Call GPT to generate a reply (in executor to avoid blocking the event loop)
    response = await loop.run_in_executor(
        None,
        functools.partial(openai.ChatCompletion.create, model="gpt-3.5-turbo", messages=messages)
    )
    reply_text = response['choices'][0]['message']['content'].strip()
    await update.message.reply_text(reply_text)

# --- Set up the Telegram bot application (ApplicationBuilder replaces Updater in v20+):
application = ApplicationBuilder().token(TOKEN).concurrent_updates(True).build()
# Register handlers with the application (no Dispatcher needed in v20+)
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("setpersonality", set_personality))
application.add_handler(CommandHandler("say", say))
# Use new filters module (lowercase) instead of Filters class
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
application.add_handler(MessageHandler(filters.VOICE, handle_voice))

# Run the bot until it is stopped (replaces updater.start_polling() & updater.idle())
if __name__ == "__main__":
    application.run_polling()
