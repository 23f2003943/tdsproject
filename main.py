import os
import json
import threading
import telebot
from fastapi import FastAPI
from fastapi.responses import FileResponse
import uvicorn
from dotenv import load_dotenv

from agent import solve_question

load_dotenv()

# Setup FastAPI
app = FastAPI()

LOG_FILE = "run.jsonl"

@app.get("/run.jsonl")
def get_log_file():
    if os.path.exists(LOG_FILE):
        return FileResponse(LOG_FILE, media_type="application/jsonl")
    return {"error": "Log file not found"}

@app.get("/")
def health_check():
    return {"status": "ok"}

# Setup Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

def log_run(question: str, answer_obj: dict):
    """Appends the run to the JSONL log file."""
    log_entry = {
        "question": question,
        "answer": answer_obj
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    question = message.text
    print(f"Received question: {question}")
    
    # Let the LLM solve it
    answer_obj = solve_question(question)
    
    # Log the interaction
    log_run(question, answer_obj)
    
    # Construct the final reply format
    public_url = os.getenv("PUBLIC_URL", "http://localhost:8000")
    log_url = f"{public_url.rstrip('/')}/run.jsonl"
    
    final_reply = {
        "answer": answer_obj,
        "log_url": log_url
    }
    
    reply_str = json.dumps(final_reply)
    print(f"Sending reply: {reply_str}")
    bot.reply_to(message, reply_str)

def run_bot():
    if bot:
        print("Starting Telegram bot polling...")
        bot.infinity_polling()
    else:
        print("BOT_TOKEN not set. Telegram bot will not start.")

if __name__ == "__main__":
    # Start the bot in a separate thread so it doesn't block FastAPI
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Start the web server
    port = int(os.getenv("PORT", 8000))
    print(f"Starting web server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
