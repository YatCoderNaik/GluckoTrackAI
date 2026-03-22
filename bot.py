import os
import asyncio
from datetime import datetime
from google.genai import types
from dotenv import load_dotenv
from telebot.async_telebot import AsyncTeleBot
from agent import get_agent_runner

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
APP_URL = os.getenv('APP_URL', 'http://localhost:8501')

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env!")

# Use AsyncTeleBot so everything runs in the SAME event loop as the ADK runner
bot = AsyncTeleBot(TELEGRAM_BOT_TOKEN)

# Create a single runner and session service shared across all requests
runner = get_agent_runner()

async def ensure_session(user_id: str):
    """Creates an ADK session for the user if one doesn't already exist."""
    session = await runner.session_service.get_session(
        app_name="gluco_track_app",
        user_id=user_id,
        session_id=user_id
    )
    if not session:
        print(f"[Bot] Creating new session for user: {user_id}")
        await runner.session_service.create_session(
            app_name="gluco_track_app",
            user_id=user_id,
            session_id=user_id
        )

async def call_agent(user_id: str, content_text: str, parts=None) -> str:
    """
    Sends a message to the ADK Root Agent and collects the response.
    Uses run_async to stay in the same event loop as the MCP Toolbox.
    """
    await ensure_session(user_id)

    if parts:
        message_content = types.Content(role="user", parts=parts)
    else:
        message_content = types.Content(role="user", parts=[types.Part(text=content_text)])

    full_response = ""
    try:
        # run_async keeps everything in the same event loop — no threading conflicts
        async for event in runner.run_async(
            user_id=user_id,
            session_id=user_id,
            new_message=message_content
        ):
            # Extract text from model response events
            if hasattr(event, "content") and event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        full_response += part.text
    except Exception as e:
        print(f"[Agent Error] {e}")
        return f"Sorry, I encountered an error: {e}"

    return full_response.strip() or "I processed your request but had no text response."


@bot.message_handler(commands=['start'])
async def send_welcome(message):
    user_id = str(message.from_user.id)
    first_name = message.from_user.first_name
    username = message.from_user.username or ""

    prompt = (
        f"A new user has started the bot. "
        f"Telegram ID: {user_id}, Name: {first_name}, Username: @{username}. "
        f"Please greet them warmly and let them know they can share their diabetic test results "
        f"(blood sugar, HbA1c, cholesterol, etc.) as text or upload a photo/PDF of their report."
    )
    response = await call_agent(user_id, prompt)
    await bot.reply_to(message, f"{response}\n\n📊 Dashboard: {APP_URL}")


@bot.message_handler(content_types=['photo', 'document'])
async def handle_report(message):
    user_id = str(message.from_user.id)
    await bot.reply_to(message, "📋 Analyzing your report... Please wait.")

    try:
        if message.content_type == 'photo':
            file_id = message.photo[-1].file_id
            mime_type = "image/jpeg"
        else:
            file_id = message.document.file_id
            mime_type = message.document.mime_type

        file_info = await bot.get_file(file_id)
        downloaded_file = await bot.download_file(file_info.file_path)

        prompt_text = (
            f"User {user_id} has sent a medical report image/document. "
            f"Please extract any diabetic test results (blood glucose, HbA1c, cholesterol, etc.) "
            f"and save them to the database using the execute_sql tool."
        )
        parts = [
            types.Part(text=prompt_text),
            types.Part.from_bytes(data=downloaded_file, mime_type=mime_type)
        ]
        response = await call_agent(user_id, prompt_text, parts=parts)
        await bot.reply_to(message, response)

    except Exception as e:
        print(f"[Report Error] {e}")
        await bot.reply_to(message, "❌ Sorry, I couldn't process that report. Please try again.")


@bot.message_handler(func=lambda message: True)
async def handle_text(message):
    user_id = str(message.from_user.id)
    response = await call_agent(user_id, message.text)
    await bot.reply_to(message, response)


if __name__ == "__main__":
    print("🚀 Starting GlucoTrack AI Bot with ADK (async mode)...")
    asyncio.run(bot.polling(none_stop=True))
