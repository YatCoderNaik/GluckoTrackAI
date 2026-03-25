import os
import json
import subprocess
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

        ### CRITICAL RULES:
        - NEVER include a trailing semicolon (`;`) at the end of your SQL commands. This causes an "ORA-00933: SQL command not properly ended" error.
        - Ensure all SQL is compatible with Oracle Database.
        - **Case-Insensitive Filtering**: ALWAYS use `UPPER()` on text columns in WHERE clauses.
          Example: `WHERE UPPER(TEST_TYPE) = UPPER('glucose')` instead of `WHERE TEST_TYPE = 'glucose'`.
          This applies to TEST_TYPE, USERNAME, and any other text-based filter.
        - **Efficient Queries**: NEVER use `SELECT *` or fetch all raw rows. ALWAYS prefer aggregation.
          When asked about trends, spikes, highs, lows, or patterns, use GROUP BY with EXTRACT(MONTH/YEAR FROM TEST_DATE), MAX, MIN, AVG, COUNT.
          Only return individual rows when the user explicitly asks for a detailed list or a specific date's reading, AND the expected result set is small (< 10 rows).
          Examples:
            - "When did glucose spike above 100?" → `SELECT EXTRACT(YEAR FROM TEST_DATE) AS YR, EXTRACT(MONTH FROM TEST_DATE) AS MO, COUNT(*) AS SPIKE_DAYS, MAX(VALUE) AS PEAK, MIN(VALUE) AS LOW, ROUND(AVG(VALUE),1) AS AVG_VAL FROM TEST_RESULTS WHERE ... AND VALUE > 100 GROUP BY EXTRACT(YEAR FROM TEST_DATE), EXTRACT(MONTH FROM TEST_DATE) ORDER BY YR, MO`
            - "Which month had the highest glucose?" → `SELECT EXTRACT(MONTH FROM TEST_DATE) AS MO, MAX(VALUE) AS MAX_VAL FROM TEST_RESULTS WHERE ... GROUP BY EXTRACT(MONTH FROM TEST_DATE) ORDER BY MAX_VAL DESC FETCH FIRST 1 ROWS ONLY`
            - "Average HbA1c per year?" → `SELECT EXTRACT(YEAR FROM TEST_DATE), ROUND(AVG(VALUE),1) FROM ... GROUP BY EXTRACT(YEAR FROM TEST_DATE)`

        Tables available:
        - `TEST_RESULTS` (ID, USER_ID, TEST_TYPE, VALUE, UNIT, TEST_DATE, IS_CONFIRMED)
        - `USERS` (ID, FIRST_NAME, USERNAME)

        When storing data:
        - **Deduplication**: When performing an `INSERT` (if not told otherwise), check if a record with the same `USER_ID`, `TEST_TYPE`, `VALUE`, and `TEST_DATE` already exists to avoid duplicates.
        - **Persistence**: After every `INSERT`, `UPDATE`, or `DELETE`, you MUST issue a separate `COMMIT` command via the `execute_sql_via_toolbox` tool to ensure the transaction is saved.
        - `ID` is handled by the DB.
        - `USER_ID` is the user's ID.
        - `TEST_DATE` should be in 'YYYY-MM-DD' format using `TO_DATE`.
        - `IS_CONFIRMED` should be 0 (false) for new extracted reports until the user confirms them.
    ''',
    # Matches the user's successful Vertex discovery (gemini-2.5-flash)
    model=VertexADCGemini(model="gemini-2.5-flash"),
    tools=[execute_sql_via_toolbox]
)
