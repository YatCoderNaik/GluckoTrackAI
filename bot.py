import os
import telebot
import json
from datetime import datetime
from google import genai
from google.genai import types
from db import add_user, add_test_result, get_test_results
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    print("Warning: TELEGRAM_BOT_TOKEN is not set in .env! The bot will not start correctly.")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN or "DUMMY_TOKEN")

# GenAI client setup
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

APP_URL = os.getenv('APP_URL', 'http://localhost:8501')

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = str(message.from_user.id)
    first_name = message.from_user.first_name
    username = message.from_user.username or ""
    
    add_user(user_id, first_name, username)
    
    bot.reply_to(message, f"Welcome {first_name}! I'm GlucoTrack AI. Send me your diabetic test reports (images or PDFs) and I'll help you track them.\n\nLog in to your dashboard at {APP_URL} using your ID ({user_id}) or username.")

@bot.message_handler(content_types=['photo', 'document'])
def handle_docs_photo(message):
    try:
        user_id = str(message.from_user.id)
        
        file_id = ""
        mime_type = ""
        
        if message.content_type == 'photo':
            file_id = message.photo[-1].file_id
            mime_type = "image/jpeg"
        elif message.content_type == 'document':
            file_id = message.document.file_id
            mime_type = message.document.mime_type
            
        if not file_id:
            return
            
        bot.reply_to(message, "Analyzing your report using Gemini... Please wait.")
        
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        prompt = f'''
            Analyze this medical report for diabetic test results. 
            Extract only diabetic related tests like HbA1c, Fasting Blood Sugar (FBS), Post-Prandial Blood Sugar (PPBS), Random Blood Sugar (RBS).
            Return the results in a JSON format:
            {{
                "results": [
                    {{
                        "testType": "HbA1c",
                        "value": 6.5,
                        "unit": "%",
                        "testDate": "YYYY-MM-DD"
                    }}
                ]
            }}
            If no diabetic tests are found, return an empty list.
            If the date is missing, use {datetime.now().strftime("%Y-%m-%d")}.
        '''
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(
                    data=downloaded_file,
                    mime_type=mime_type,
                ),
                prompt
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        
        analysis = json.loads(response.text)
        results = analysis.get("results", [])
        
        if not results:
            bot.reply_to(message, "I couldn't find any diabetic test results in this document. Please make sure it's a valid report.")
            return
            
        summary = "I found the following results:\n\n"
        for res in results:
            add_test_result(
                user_id=user_id,
                test_type=res.get("testType"),
                value=res.get("value"),
                unit=res.get("unit"),
                test_date=res.get("testDate"),
                is_confirmed=False
            )
            summary += f"- {res.get('testType')}: {res.get('value')} {res.get('unit')} ({res.get('testDate')})\n"
            
        summary += "\nI've saved these as 'Pending Confirmation'. You can view and confirm them on the dashboard."
        bot.reply_to(message, summary)
        
    except Exception as e:
        print(f"Error processing file: {e}")
        bot.reply_to(message, "Sorry, I encountered an error while processing your file. Ensure my API keys are correct.")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    text = message.text.lower()
    user_id = str(message.from_user.id)
    
    if "sugar" in text or "level" in text or "average" in text:
        try:
            bot.reply_to(message, "Let me check your records...")
            
            results = get_test_results(user_id)
            confirmed_results = [r for r in results if r['is_confirmed']]
            
            if not confirmed_results:
                bot.reply_to(message, "You don't have any confirmed test results yet. Upload a report and confirm it on the dashboard.")
                return
                
            history_data = [
                { "testType": r['test_type'], "value": r['value'], "unit": r['unit'], "date": r['test_date'] }
                for r in confirmed_results
            ]
            
            prompt = f'''
                The user is asking: "{message.text}"
                Here are their confirmed diabetic test results:
                {json.dumps(history_data)}
                
                Provide a helpful, concise answer based on this data. 
                If they ask for an average, calculate it. 
                If they ask for trends, describe them.
                Be encouraging but remind them to consult a doctor for medical advice.
            '''
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            
            bot.reply_to(message, response.text)
            
        except Exception as e:
            print(f"Error handling query: {e}")
            bot.reply_to(message, "I encountered an error while retrieving your data.")
    else:
        bot.reply_to(message, "I'm GlucoTrack AI. Send me a medical report image or PDF to track your sugar levels, or ask me questions about your history.")

if __name__ == "__main__":
    if TELEGRAM_BOT_TOKEN:
        print("Starting Telegram Bot...")
        bot.polling(none_stop=True)
    else:
        print("Failed to start bot. Please add TELEGRAM_BOT_TOKEN to your .env file.")
