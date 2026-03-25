# GlucoTrack AI: Personalized Diabetic Health Assistant

GlucoTrack AI is an advanced, multi-agent health monitoring system designed to help users track and analyze their diabetic health data (Glucose and HbA1c) seamlessly. It combines conversational AI with powerful data extraction and visualization capabilities.

## Dual-Interface Support

Access your health data through two convenient platforms:

1. **Telegram Bot (`@GluckoTrack_AI`)**: 
   - **Quick Access**: Chat directly with the AI, upload photos of lab reports, and get instant feedback.
   - **Real-time Notifications**: Receive updates and interact with your health data on the go.
   - **Mobile Friendly**: The primary way to log daily readings or snap pictures of medical reports.

2. **Streamlit Dashboard**:
   - **Deep Analysis**: A web-based interface for visualizing long-term trends using interactive Plotly charts.
   - **Bulk Management**: Upload historical data via Excel/CSV files and manage pending records.
   - **Historical Review**: A detailed table view of all confirmed test results with easy filtering.

---

## Key Features

### 🤖 Intelligent Multi-Agent Architecture
- **Orchestrator Agent**: Your primary point of contact. It understands medical context, interprets vague queries ("Is my sugar bad?"), and provides encouraging health insights.
- **Database Expert**: A specialized agent that optimizes SQL queries for Oracle Database, ensuring efficient data aggregation and deduplication.

### 📄 AI-Powered Report Extraction (Vision)
- **Automatic Logging**: Simply upload an image or PDF of your lab report. The system's vision capabilities extract Test Type, Value, Unit, and Date automatically.
- **Human-in-the-loop**: Extracted readings are marked as "Pending" until you confirm them via the Streamlit dashboard or Telegram.

### 📊 Advanced Data Insights
- **Trend Visualization**: Interactive line charts for HbA1c and Glucose (FBS, PPBS, RBS) trends over time.
- **Smart Aggregation**: Instead of raw lists, the AI provides monthly summaries (Max, Min, Avg) to highlight spikes or progress.
- **Diabetic Domain Knowledge**: Built-in awareness of standard medical thresholds (Normal vs. Pre-diabetic vs. Diabetic).

### 🗄️ Enterprise-Grade Persistence
- **Oracle Database Integration**: Securely stores all user and health data in Oracle Cloud.
- **Bulk Upload**: Support for migrating large historical datasets from Excel (`.xlsx`) or CSV files.
- **Deduplication**: Intelligent checks to prevent duplicate records for the same test on the same date.

---

## Getting Started

### Prerequisites
- Python 3.11+
- Google Cloud Project with Vertex AI enabled
- Oracle Autonomous Database (with Wallet)
- Telegram Bot Token (from `@BotFather`)

### Installation
1. Clone the repository and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up your environment variables in a `.env` file:
   ```ini
   GOOGLE_CLOUD_PROJECT=your-project-id
   GOOGLE_CLOUD_LOCATION=your-location
   TELEGRAM_BOT_TOKEN=your-bot-token
   DB_USER=your-db-user
   DB_PASSWORD=your-db-password
   DB_DSN=your-db-dsn
   ```

### Running Locally
- **To start the Dashboard**: `streamlit run app.py`
- **To start the Bot**: `python bot.py` (ensure `MODE=polling` in `.env`)

---

## Deployment
GlucoTrack AI is designed to run on **Google Cloud Run**. It is deployed as two separate services (Bot and Dashboard) to ensure high availability and independent scaling. Refer to `DEPLOY.md` for detailed cloud deployment instructions.
