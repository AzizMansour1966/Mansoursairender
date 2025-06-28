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
    return "✅ Mansour
