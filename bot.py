import os
import asyncio
import sys
import logging
from aiohttp import web
from datetime import datetime
from google.genai import types
from dotenv import load_dotenv
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Update

# Set Project Paths correctly relative to this root launcher
# We now follow the Python-First layout: orchestrator/ and database_expert/
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.append(APP_DIR)

# Load context-specific environment (Root Design)
load_dotenv(os.path.join(APP_DIR, ".env"), override=True)

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Now safe to import from our app hierarchy
try:
    from orchestrator.agent import get_agent_runner
    print("Successfully loaded Orchestrator (Parent Agent) from orchestrator/agent.py")
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
APP_URL = os.getenv('APP_URL', 'http://localhost:8501')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # Public URL of your Cloud Run service
PORT = int(os.getenv('PORT', 8080))
MODE = os.getenv('MODE', 'polling').lower() # 'polling' or 'webhook'

logger.info(f"Loaded Configuration: MODE={MODE}, PORT={PORT}, WEBHOOK_URL={'SET' if WEBHOOK_URL else 'MISSING'}")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set!")

# Use AsyncTeleBot so everything runs in the SAME event loop as the ADK runner
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

# --- Webhook Server ---
async def handle_webhook(request):
    logger.info(f"Received request on: {request.path}")
    if request.match_info.get('token') != TELEGRAM_BOT_TOKEN:
        logger.warning(f"Invalid token on request: {request.match_info.get('token')}")
        return web.Response(status=403)
    
    try:
        data = await request.json()
        logger.info(f"Webhook data: {data}")
        update = Update.de_json(data)
        await bot.process_new_updates([update])
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
    return web.Response()

async def handle_root(request):
    return web.Response(text="GlucoTrack AI Bot is running!")

async def start_webhook():
    app = web.Application()
    app.router.add_get('/', handle_root)
    app.router.add_post(f'/webhook/{{token}}', handle_webhook)
    
    # Set webhook if URL provided
    if WEBHOOK_URL:
        full_webhook_url = f"{WEBHOOK_URL}/webhook/{TELEGRAM_BOT_TOKEN}"
        logger.info(f"Attempting to set webhook to: {full_webhook_url}")
        try:
            success = await bot.set_webhook(url=full_webhook_url)
            logger.info(f"Webhook set result: {success}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
    else:
        logger.warning("WEBHOOK_URL not set. Webhook will not be registered.")
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"Webhook server started on port {PORT}")
    
    # Keep alive
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    if MODE == 'webhook':
        print(f"🚀 Starting GlucoTrack AI Bot in WEBHOOK mode (Port {PORT})...")
        asyncio.run(start_webhook())
    else:
        print("🚀 Starting GlucoTrack AI Bot in POLLING mode...")
        # Clear any existing webhook to enable polling
        asyncio.run(bot.remove_webhook())
        asyncio.run(bot.polling(none_stop=True))
