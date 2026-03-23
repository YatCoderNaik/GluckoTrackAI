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
    """Useful tool to execute SQL queries on the Oracle database via the official toolbox binary."""
    try:
        env = os.environ.copy()
        # Find the correct binary name
        toolbox_bin = "toolbox"
        local_exe = os.path.join(ROOT, "toolbox.exe")
        if os.path.exists(local_exe):
            toolbox_bin = local_exe
        
        # In Cloud Run, 'toolbox' is in /usr/local/bin/
        args = [toolbox_bin, "invoke", "oracle_execute_sql", json.dumps({"sql": sql}), "--tools-file", os.path.join(ROOT, "tools.yaml")]
        
        # Log the command for debugging in Cloud Run logs
        print(f"Executing: {' '.join(args)}")
        
        res = subprocess.run(args, env=env, capture_output=True, text=True, cwd=ROOT)
        if res.returncode == 0:
            print(f"Toolbox Output: {res.stdout.strip()}")
            return res.stdout.strip()
        else:
            print(f"Toolbox Error: {res.stderr}")
            return f"Binary Error: {res.stderr}"
    except Exception as e:
        print(f"Toolbox Exception: {str(e)}")
        return f"System Error: {str(e)}"

# --- Specialized Sub-Agent: Database Expert ---
database_expert = Agent(
    name="database_expert",
    description="Assistant that specializes in Oracle database activities for GlucoTrack.",
    instruction='''
        You are a Database Expert. Your sole responsibility is to interact with the Oracle database via SQL.
        Use the `execute_sql_via_toolbox` tool to perform all SQL operations.

        Tables available:
        - `TEST_RESULTS` (ID, USER_ID, TEST_TYPE, VALUE, UNIT, TEST_DATE, IS_CONFIRMED)
        - `USERS` (ID, FIRST_NAME, USERNAME)

        When storing data:
        - **Deduplication**: Before performing an `INSERT`, always check if a record with the same `USER_ID`, `TEST_TYPE`, `VALUE`, and `TEST_DATE` already exists.
        - If a duplicate is found, DO NOT insert it. Instead, return a message: "This reading for [TEST_TYPE] on [TEST_DATE] has already been recorded."
        - **Persistence**: After every `INSERT` or `UPDATE` operation, you MUST issue a separate `COMMIT` command via the `execute_sql_via_toolbox` tool to ensure the transaction is saved.
        - `ID` is usually auto-generated or handled by the DB.
        - `USER_ID` is the user's ID.
        - `TEST_DATE` should be in 'YYYY-MM-DD' format.
        - `IS_CONFIRMED` should be 0 (false) for new extracted reports until the user confirms them.
    ''',
    # Matches the user's successful Vertex discovery (gemini-2.5-flash)
    model=VertexADCGemini(model="gemini-2.5-flash"),
    tools=[execute_sql_via_toolbox]
)
