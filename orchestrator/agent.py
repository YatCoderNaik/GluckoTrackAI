import os
import asyncio
import sys
from datetime import datetime
from functools import cached_property
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

# --- Optimized Vertex ADC Model class ---
class VertexADCGemini(Gemini):
    @cached_property
    def api_client(self) -> Client:
        # Perfect Match to successful test script (gemini-2.5-flash @ Mumbai)
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
        Your goal is conversational assistance and medical guidance.
        - Delegate ALL database tasks secretly to your `database_expert` tool.
        - DO NOT talk about delegation; just provide final outcomes.
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
