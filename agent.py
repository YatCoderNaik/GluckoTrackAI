import os
import json
import asyncio
import subprocess
from datetime import datetime
from dotenv import load_dotenv
from google.genai import types
from google.adk import Agent, Runner
from google.adk.sessions import InMemorySessionService

load_dotenv()

# Official Google MCP Toolbox Binary Integration
def execute_sql_via_toolbox(sql: str) -> str:
    """Executes SQL via the official toolbox.exe binary."""
    try:
        env = os.environ.copy()
        # Official command format for toolbox invoke
        args = ["toolbox.exe", "invoke", "oracle_execute_sql", json.dumps({"sql": sql}), "--tools-file", "tools.yaml"]
        res = subprocess.run(args, env=env, capture_output=True, text=True)
        if res.returncode == 0:
            return res.stdout.strip()
        else:
            return f"Binary Error: {res.stderr}"
    except Exception as e:
        return f"System Error: {str(e)}"

# Root Agent Definition
root_agent = Agent(
    name="gluco_track_assistant",
    instruction=f'''
        You are the GlucoTrack AI Assistant. You help users manage diabetic health tracking using the Oracle database.
        Current date: {datetime.now().strftime("%Y-%m-%d")}
        Your database tool is: `execute_sql_via_toolbox`.
        
        Tables available:
        - `TEST_RESULTS` (ID, USER_ID, TEST_TYPE, VALUE, UNIT, TEST_DATE, IS_CONFIRMED)
        - `USERS` (ID, FIRST_NAME, USERNAME)
    ''',
    model="gemini-2.5-flash", # Updated to the newest model verified by the user
    tools=[execute_sql_via_toolbox]
)

def get_agent_runner():
    """Provides the agent runner instance with in-memory session service."""
    return Runner(app_name="gluco_track_app", agent=root_agent, session_service=InMemorySessionService())

if __name__ == "__main__":
    runner = get_agent_runner()
    async def run_test():
        # Ensure a session is created for testing
        await runner.session_service.create_session(
            user_id="test_user", 
            session_id="test_session", 
            app_name="gluco_track_app"
        )
        print("Testing Root Agent with official Google MCP Toolbox binary and Gemini 2.5...")
        message = types.Content(role="user", parts=[types.Part(text="Check the current time in the database.")])
        try:
            async for event in runner.run_async(user_id="test_user", session_id="test_session", new_message=message):
                if hasattr(event, "content") and event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text: 
                            print(f"Agent: {part.text}")
        except Exception as e: 
            print(f"Agent Error: {e}")
    asyncio.run(run_test())
