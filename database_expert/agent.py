import os
import json
import subprocess
from functools import cached_property
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.models import Gemini
from google.genai import Client, types

# Project-Root relative paths
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"), override=True)

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
        # Perfect Match to successful test script
        return Client(
            vertexai=True,
            project=PROJECT,
            location=LOCATION,
            http_options=types.HttpOptions(headers=self._tracking_headers())
        )

def execute_sql_via_toolbox(sql: str) -> str:
    """Useful tool to execute SQL queries on the Oracle database via the official toolbox.exe."""
    try:
        env = os.environ.copy()
        args = [os.path.join(ROOT, "toolbox.exe"), "invoke", "oracle_execute_sql", json.dumps({"sql": sql}), "--tools-file", os.path.join(ROOT, "tools.yaml")]
        res = subprocess.run(args, env=env, capture_output=True, text=True, cwd=ROOT)
        return res.stdout.strip() if res.returncode == 0 else f"Binary Error: {res.stderr}"
    except Exception as e:
        return f"System Error: {str(e)}"

# --- Specialized Sub-Agent: Database Expert ---
database_expert = Agent(
    name="database_expert",
    description="Assistant that specializes in Oracle database activities for GlucoTrack.",
    instruction='''
        You are a Database Expert. Your sole responsibility is to interact with the Oracle database via SQL.
        Use the `execute_sql_via_toolbox` tool to perform all SQL operations.
    ''',
    # Matches the user's successful Vertex discovery (gemini-2.5-flash)
    model=VertexADCGemini(model="gemini-2.5-flash"),
    tools=[execute_sql_via_toolbox]
)
