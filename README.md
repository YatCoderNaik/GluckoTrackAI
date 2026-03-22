# GlucoTrack AI (Python + Streamlit)

A health tracker specifically designed to monitor diabetic test results. Upload your medical reports (images or PDFs), and the Google Gemini AI will automatically extract and log your data (HbA1c, Fasting Blood Sugar, etc.). 

## Prerequisites
- Python 3.9+
- Gemini API Key

## Setup
1. Create a virtual environment and install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file in the root directory and add your key:
```ini
GEMINI_API_KEY=your_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
APP_URL=http://localhost:8501
```

3. Run the Streamlit UI:
```bash
streamlit run app.py
```

4. Run the Telegram Bot (optional):
```bash
python bot.py
```

## Features
- **Dashboard**: Track your HbA1c and Glucose levels via charts.
- **Upload Report**: Simply drop an image or PDF of your lab report to have your test results auto-extracted.
- **AI Health Assistant**: Ask questions directly about your test history.
- **Local SQLite Database**: All of your information stays securely in a local `gluco_track.db` SQLite database.
