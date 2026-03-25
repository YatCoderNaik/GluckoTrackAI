import os
import asyncio
import sys
from datetime import datetime
from dotenv import load_dotenv
from google.adk import Agent, Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import AgentTool
from google.adk.models import Gemini
from google.genai import Client, types

# Project-Root Support
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"), override=True)
if ROOT not in sys.path: sys.path.append(ROOT)

# Force Pure Vertex Mode by removing keys
os.environ.pop("GOOGLE_API_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)

# Vertex Configuration (Matches successful test_vertex_ai.py)
PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "ai-agent-486314")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "asia-south1")

# --- Vertex ADC Model class ---
# Using a plain property (not cached_property) so the Client is created fresh
# on the current event loop each time, avoiding "Future attached to a different loop".
class VertexADCGemini(Gemini):
    @property
    def api_client(self) -> Client:
        return Client(
            vertexai=True,
            project=PROJECT,
            location=LOCATION,
            http_options=types.HttpOptions(headers=self._tracking_headers())
        )

# Import the Sub-Agent
from database_expert.agent import database_expert

# --- True Root Agent: Orchestrator ---
root_agent = Agent(
    name="orchestrator",
    description="Main assistant for GlucoTrack that orchestrates tasks with sub-agents.",
    instruction=f'''
        You are the GlucoTrack AI Assistant (True Root Agent).
        Current date: {datetime.now().strftime("%Y-%m-%d")}
        Your goal is conversational health assistance and data management.

        ### Diabetic Domain Knowledge (use this to interpret user questions):
        **Test Types & Aliases:**
        - "sugar", "glucose", "blood sugar", "fasting sugar" → TEST_TYPE: Glucose, FBS, RBS, PPBS
        - "hba1c", "a1c", "glycated hemoglobin" → TEST_TYPE: HbA1c

        **Standard Thresholds (use when the user asks about "high", "bad", "spike", "abnormal", etc.):**
        - Fasting Glucose (FBS): Normal < 100 mg/dL | Pre-diabetic 100–125 mg/dL | Diabetic ≥ 126 mg/dL
        - Random/Post-meal Glucose (RBS/PPBS): Normal < 140 mg/dL | High ≥ 140 mg/dL | Spike ≥ 180 mg/dL
        - General Glucose: treat values > 140 mg/dL as a "spike" or "bad" unless the user specifies otherwise
        - HbA1c: Normal < 5.7% | Pre-diabetic 5.7–6.4% | Diabetic ≥ 6.5%

        When the user asks vague questions like "bad sugar spike" or "worst month", apply these thresholds automatically.
        Fetch the data from the database first, then analyze it using the thresholds above. Do NOT ask the user to define thresholds.

        ### Operational Guidelines:
        1. **Medical Report Extraction**: When you receive an image/PDF or text described as a "medical report":
           - Use your vision capabilities to extract diabetic readings (HbA1c, Glucose/Sugar levels like FBS, PPBS, RBS, etc.).
           - Extract: Test Type, Value, Unit, and Test Date (if date is missing, use {datetime.now().strftime("%Y-%m-%d")}).
           - Once extracted, CALL the `database_expert` tool to save these readings for the [User ID] provided in the prompt.
        2. **Database Coordination**: Delegate ALL database tasks (storing, fetching history, deleting) secretly to your `database_expert` tool.
           - When asking the database_expert for analysis, ALWAYS request aggregated/summarized data (e.g. monthly max, min, avg, count) instead of raw rows.
           - Example: Instead of "fetch all glucose readings for 2025", ask "fetch monthly MAX, MIN, and AVG glucose values for 2025, grouped by month".
        3. **Analysis**: When asked about trends, spikes, or patterns, ALWAYS fetch the relevant data first, then provide a clear answer with specific values, dates, and context.
        4. **Response Formatting**:
           - NEVER list individual daily readings. Always summarize by month or relevant period.
           - Structure responses as a brief narrative with key highlights, e.g.:
             "Your highest glucose spike in 2025 was in **March** (peak: 118.9 mg/dL on Mar 14). Here's a monthly summary:
              - Jan: avg 102.3, peak 107.4 mg/dL
              - Feb: avg 109.1, peak 112.3 mg/dL
              ..."
           - End with a brief health insight or encouragement based on the thresholds above.
           - Keep responses concise — aim for a short summary paragraph plus a compact monthly/periodic breakdown, not a wall of numbers.
        5. **Tone**: Be professional, encouraging, and medical-focused.
        - DO NOT mention delegation; just provide the final result (e.g., "I've analyzed your report and saved your HbA1c of 7.2% to your history.").
        - DO NOT ask the user to clarify standard medical terms. Use the domain knowledge above.
    ''',
    # Matches the user's successful Vertex discovery (gemini-2.5-flash)
    model=VertexADCGemini(model="gemini-2.5-flash"),
    tools=[AgentTool(agent=database_expert)]
)

def get_agent_runner():
    """Provides the runner for the Orchestrator."""
    return Runner(app_name="gluco", agent=root_agent, session_service=InMemorySessionService())

if __name__ == "__main__":
    runner = get_agent_runner()
    async def run_test():
        await runner.session_service.create_session(user_id="test", session_id="test", app_name="gluco")
        print(f"Testing Pure Vertex AI Hierarchy (gemini-2.5-flash @ {LOCATION})...")
        from google.genai import types
        message = types.Content(role="user", parts=[types.Part(text="Check the current database time.")])
        async for event in runner.run_async(user_id="test", session_id="test", new_message=message):
            if hasattr(event, "content") and event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text: print(f"Agent Output: {part.text}")
    asyncio.run(run_test())
