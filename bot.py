import os
import asyncio
import sys
from datetime import datetime
from google.genai import types
from dotenv import load_dotenv
from telebot.async_telebot import AsyncTeleBot

# Set Project Paths correctly relative to this root launcher
# We now follow the Python-First layout: orchestrator/ and database_expert/
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.append(APP_DIR)

# Load context-specific environment (Root Design)
load_dotenv(os.path.join(APP_DIR, ".env"), override=True)

# Now safe to import from our app hierarchy
try:
    from orchestrator.agent import get_agent_runner
    print("Successfully loaded Orchestrator (Parent Agent) from orchestrator/agent.py")
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
APP_URL = os.getenv('APP_URL', 'http://localhost:8501')

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env!")

bot = AsyncTeleBot(TELEGRAM_BOT_TOKEN)
runner = get_agent_runner()

async def ensure_session(user_id: str):
    session = await runner.session_service.get_session(app_name="gluco", user_id=user_id, session_id=user_id)
    if not session:
        await runner.session_service.create_session(app_name="gluco", user_id=user_id, session_id=user_id)

async def call_agent(user_id: str, content_text: str, parts=None) -> str:
    await ensure_session(user_id)
    # Prepend User context to help the agent know who is talking
    user_context = f"[User ID: {user_id}] "
    if parts:
        # If parts exist, prepend context to the first text part or add a new one
        if parts[0].text:
            parts[0].text = user_context + parts[0].text
        else:
            parts.insert(0, types.Part(text=user_context))
    else:
        content_text = user_context + content_text

    msg = types.Content(role="user", parts=parts or [types.Part(text=content_text)])
    full_response = ""
    try:
        async for event in runner.run_async(user_id=user_id, session_id=user_id, new_message=msg):
            if hasattr(event, "content") and event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text: full_response += part.text
    except Exception as e: return f"Error: {e}"
    return full_response.strip() or "Processed, but no text response."

@bot.message_handler(commands=['start'])
async def send_welcome(message):
    user_id = str(message.from_user.id)
    resp = await call_agent(user_id, f"Greet me ({message.from_user.first_name}) warmly and tell me about my GlucoTrack dashboard.")
    await bot.reply_to(message, resp)

@bot.message_handler(content_types=['photo', 'document'])
async def handle_report(message):
    user_id = str(message.from_user.id)
    try:
        file_id = message.photo[-1].file_id if message.content_type == 'photo' else message.document.file_id
        mime = "image/jpeg" if message.content_type == 'photo' else message.document.mime_type
        file_info = await bot.get_file(file_id)
        data = await bot.download_file(file_info.file_path)
        parts = [types.Part(text="I've attached a medical report image. Please extract the diabetic readings and save them."), types.Part.from_bytes(data=data, mime_type=mime)]
        resp = await call_agent(user_id, "", parts=parts)
        await bot.reply_to(message, resp)
    except Exception as e: await bot.reply_to(message, "❌ Report processing failed.")

@bot.message_handler(func=lambda message: True)
async def handle_text(message):
    user_id = str(message.from_user.id)
    resp = await call_agent(user_id, message.text)
    await bot.reply_to(message, resp)

if __name__ == "__main__":
    print("🚀 Starting GlucoTrack AI Bot in Multi-Agent Hierarchy mode (Parent/Sub-Agent)...")
    asyncio.run(bot.polling(none_stop=True))
