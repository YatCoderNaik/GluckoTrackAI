import streamlit as st
import pandas as pd
import plotly.express as px
import os
import json
import asyncio
import sys
import threading
from datetime import datetime
from dotenv import load_dotenv
from google.genai import types

# Add root to sys.path for agent imports
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.append(APP_DIR)

load_dotenv(os.path.join(APP_DIR, ".env"), override=True)

# Import our agents and runners
try:
    from orchestrator.agent import get_agent_runner
    from database_expert.agent import database_expert
    from google.adk import Runner
    from google.adk.sessions import InMemorySessionService
except ImportError as e:
    st.error(f"Error importing agents: {e}")
    st.stop()

st.set_page_config(page_title="GlucoTrack AI Dashboard", page_icon="📈", layout="wide")

# --- Persistent event loop running in a background thread ---
# cached_resource ensures this is created ONCE across all Streamlit reruns,
# so every async call always targets the same loop — no more
# "Future attached to a different loop" errors.
@st.cache_resource
def _get_event_loop():
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    return loop

_loop = _get_event_loop()

# --- Helper to run agents ---
def get_runners():
    """Creates fresh runners — called inside coroutines on the persistent loop."""
    orchestrator_runner = get_agent_runner()
    db_runner = Runner(app_name="gluco_db", agent=database_expert, session_service=InMemorySessionService())
    return orchestrator_runner, db_runner

def sync_run(coro):
    """Submits a coroutine to the persistent background loop and blocks until done."""
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result()

def direct_db_query(sql: str):
    """Executes SQL directly via the toolbox binary, bypassing the LLM agent.
    Use this for data-heavy reads where routing through an agent is wasteful/slow."""
    import subprocess, re
    toolbox_bin = "toolbox"
    local_exe = os.path.join(APP_DIR, "toolbox.exe")
    if os.path.exists(local_exe):
        toolbox_bin = local_exe
    args = [toolbox_bin, "invoke", "oracle_execute_sql", json.dumps({"sql": sql}),
            "--tools-file", os.path.join(APP_DIR, "tools.yaml")]
    try:
        res = subprocess.run(args, capture_output=True, text=True, cwd=APP_DIR, timeout=30)
        if res.returncode == 0:
            output = res.stdout.strip()
            # Toolbox prints INFO log lines to stdout before the JSON payload.
            # Extract the first valid JSON array or object from the output.
            match = re.search(r'(\[.*\]|\{.*\})', output, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            return output
        else:
            print(f"Toolbox Error: {res.stderr}")
            return []
    except Exception as e:
        print(f"Direct DB query error: {e}")
        return []

async def call_agent(runner, user_id, content_text, parts=None):
    # Ensure session exists
    session = await runner.session_service.get_session(app_name=runner.app_name, user_id=user_id, session_id=user_id)
    if not session:
        await runner.session_service.create_session(app_name=runner.app_name, user_id=user_id, session_id=user_id)
    
    # Prepend context
    user_context = f"[User ID: {user_id}] "
    if parts:
        if parts[0].text:
            parts[0].text = user_context + parts[0].text
        else:
            parts.insert(0, types.Part(text=user_context))
    else:
        content_text = user_context + content_text

    msg = types.Content(role="user", parts=parts or [types.Part(text=content_text)])
    full_response = ""
    try:
        async for event in runner.run_async(user_id=user_id, session_id=user_id, new_message=msg):
            if hasattr(event, "content") and event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text: full_response += part.text
    except Exception as e:
        return f"Error: {e}"
    return full_response.strip()

# Helper to execute SQL via Database Expert (Structured)
async def db_query(user_id, query_instruction):
    _, db_runner = get_runners()  # Fresh runner inside the current event loop
    prompt = f"{query_instruction}. Return the result as a raw JSON string if it's a list or object, or a plain message if it's an action. If it's data, use a format like [{{...}}, {{...}}]."
    response = await call_agent(db_runner, user_id, prompt)
    # Clean response (sometimes agents wrap in ```json ... ```)
    clean_resp = response.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(clean_resp)
    except:
        return response

async def process_bulk_upload(records, user_id, runner):
    """Processes bulk upload using standard INSERTs followed by a deduplication cleanup."""
    batch_size = 20
    success_count = 0
    status_text = st.empty()
    
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        status_text.text(f"Processing batch {i//batch_size + 1} of {(len(records)//batch_size)+1}...")
        
        # 1. Construct the Multi-Row INSERT statement
        select_stmts = []
        for rec in batch:
            try:
                dt_obj = pd.to_datetime(rec['TEST_DATE'], dayfirst=True)
                dt_str = dt_obj.strftime('%Y-%m-%d')
            except:
                dt_str = str(rec['TEST_DATE'])
            
            val = rec['VALUE']
            tt = str(rec['TEST_TYPE']).replace("'", "''")
            unit = str(rec.get('UNIT', '')).replace("'", "''")
            
            select_stmts.append(
                f"SELECT '{user_id}', '{tt}', {val}, '{unit}', TO_DATE('{dt_str}', 'YYYY-MM-DD'), 1 FROM DUAL"
            )
        
        insert_values_query = " UNION ALL ".join(select_stmts)
        insert_sql = f"""
BEGIN
    INSERT INTO TEST_RESULTS (USER_ID, TEST_TYPE, VALUE, UNIT, TEST_DATE, IS_CONFIRMED)
    {insert_values_query};
    COMMIT;
END;
"""
        print(f"\n--- DEBUG: SENDING BATCH {i//batch_size + 1} ---\n{insert_sql}\n-----------------------")
        
        instruction = (
            f"Batch {i//batch_size + 1}: Execute this PL/SQL block to insert {len(batch)} records for User {user_id}. "
            "It is vital that this is executed exactly as provided. The block includes an internal COMMIT."
            f"\n\nSQL:\n{insert_sql}"
        )
        resp = await call_agent(runner, user_id, instruction)
        print(f"--- DEBUG: AGENT RESPONSE ---\n{resp}\n-----------------------")
        
        success_count += len(batch)

    # 2. Final Deduplication Step
    status_text.text("Cleaning up duplicates...")
    cleanup_sql = f"""
BEGIN
    DELETE FROM TEST_RESULTS
    WHERE USER_ID = '{user_id}' 
    AND ROWID NOT IN (
        SELECT MIN(ROWID)
        FROM TEST_RESULTS
        WHERE USER_ID = '{user_id}'
        GROUP BY USER_ID, TEST_TYPE, VALUE, UNIT, TEST_DATE
    );
    COMMIT;
END;
"""
    print(f"\n--- DEBUG: SENDING CLEANUP ---\n{cleanup_sql}\n-----------------------")
    cleanup_instruction = (
        f"Cleanup: Execute this PL/SQL block to remove duplicate test results for User {user_id}. "
        "The block includes an internal COMMIT."
        f"\n\nSQL:\n{cleanup_sql}"
    )
    resp = await call_agent(runner, user_id, cleanup_instruction)
    print(f"--- DEBUG: CLEANUP RESPONSE ---\n{resp}\n-----------------------")
    
    status_text.empty()
    return success_count

# --- App Logic ---
if 'user' not in st.session_state:
    st.session_state.user = None

def login():
    st.markdown("<h1 style='text-align: center; color: #10b981;'>GlucoTrack AI Dashboard</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Enter your Telegram ID or Username to access your health data</p>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.container(border=True):
            st.subheader("Login")
            identifier = st.text_input("Telegram ID or Username", placeholder="e.g. 12345678 or @username")
            if st.button("Access Dashboard", width="stretch", type="primary"):
                if identifier:
                    with st.spinner("Checking user..."):
                        clean_id = identifier.lstrip('@')
                        user_data = direct_db_query(
                            f"SELECT ID, FIRST_NAME, USERNAME FROM USERS "
                            f"WHERE ID = '{clean_id}' OR USERNAME = '{clean_id}'"
                        )
                        
                        # Handle potential list or dict, and normalize keys to lowercase for the app
                        if isinstance(user_data, list) and len(user_data) > 0:
                            user_data = user_data[0]
                        
                        if isinstance(user_data, dict):
                            # Normalize keys to lowercase for consistent app usage
                            normalized_user = {k.lower(): v for k, v in user_data.items()}
                            if normalized_user.get('id'):
                                st.session_state.user = normalized_user
                                st.rerun()
                            else:
                                st.error("User found but data is incomplete.")
                        else:
                            st.error("User not found. Please register via the Telegram Bot first.")
                else:
                    st.warning("Please enter an identifier.")

if not st.session_state.user:
    login()
    st.stop()

# --- Main Dashboard ---
user = st.session_state.user

# --- Sidebar: Bulk Upload ---
with st.sidebar:
    st.header("Bulk Upload")
    st.write("Upload a CSV or Excel file with your historical records.")
    st.info("Required columns: `TEST_TYPE`, `VALUE`, `UNIT`, `TEST_DATE`")
    
    bulk_file = st.file_uploader("Choose a file", type=['csv', 'xlsx'])
    
    if bulk_file:
        try:
            if bulk_file.name.endswith('.csv'):
                df_upload = pd.read_csv(bulk_file)
            else:
                df_upload = pd.read_excel(bulk_file)
            
            # Basic Validation
            required_cols = {'TEST_TYPE', 'VALUE', 'UNIT', 'TEST_DATE'}
            actual_cols = {c.upper() for c in df_upload.columns}
            if not required_cols.issubset(actual_cols):
                st.error(f"Missing columns. Required: {required_cols}")
            else:
                if st.button("Upload Records", width="stretch"):
                    with st.spinner("Processing records..."):
                        # Normalize columns
                        df_upload.columns = [c.upper() for c in df_upload.columns]
                        records = df_upload.to_dict('records')
                        
                        async def _upload():
                            _, fresh_db_runner = get_runners()
                            return await process_bulk_upload(records, user['id'], fresh_db_runner)
                        
                        total_processed = sync_run(_upload())
                        
                        st.success(f"Successfully processed {total_processed} records.")
                        st.rerun()
        except Exception as e:
            st.error(f"Error parsing file: {e}")

col_title, col_logout = st.columns([10, 1])
with col_title:
    st.title(f"Welcome, {user.get('first_name', 'User')}!")
with col_logout:
    if st.button("Logout"):
        st.session_state.user = None
        st.rerun()

# Fetch Data
with st.spinner("Loading health data..."):
    results = direct_db_query(
        f"SELECT ID, USER_ID, TEST_TYPE, VALUE, UNIT, "
        f"TO_CHAR(TEST_DATE, 'YYYY-MM-DD') AS TEST_DATE, IS_CONFIRMED "
        f"FROM TEST_RESULTS WHERE USER_ID = '{user['id']}' ORDER BY TEST_DATE DESC"
    )
    if not isinstance(results, list):
        results = []

confirmed_results = [r for r in results if r.get('IS_CONFIRMED') == 1 or r.get('is_confirmed') == 1]
pending_results = [r for r in results if not (r.get('IS_CONFIRMED') == 1 or r.get('is_confirmed') == 1)]

# Quick Stats
st.markdown("---")
c1, c2, c3 = st.columns(3)

# Extract latest values (helper) - made more robust for key casing and keywords
def get_latest(data, keywords):
    for r in data:
        # Normalize keys to uppercase for reliable lookup (Oracle default)
        normalized_r = {str(k).upper(): v for k, v in r.items()}
        tt = str(normalized_r.get('TEST_TYPE', '')).lower()
        if any(kw.lower() in tt for kw in keywords):
            val = normalized_r.get('VALUE')
            unit = normalized_r.get('UNIT', '')
            return f"{val} {unit}"
    return "--"

with c1:
    with st.container(border=True):
        st.markdown("**Latest HbA1c 📈**")
        st.subheader(get_latest(confirmed_results, ['hba1c']))
with c2:
    with st.container(border=True):
        st.markdown("**Latest Glucose 🩸**")
        # Support 'glucose', 'sugar', 'fbs', 'rbs', 'ppbs'
        st.subheader(get_latest(confirmed_results, ['glucose', 'sugar', 'fbs', 'rbs', 'ppbs']))
with c3:
    with st.container(border=True):
        st.markdown("**Pending Reports 🕒**")
        st.subheader(f"{len(pending_results)}")

tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "History", "Upload Report", "AI Chat"])

with tab1:
    st.subheader("Trends Over Time")
    if confirmed_results:
        df = pd.DataFrame(confirmed_results)
        df.columns = [c.upper() for c in df.columns]
        df['TEST_DATE'] = pd.to_datetime(df['TEST_DATE'])
        df = df.sort_values('TEST_DATE')

        for test_type, group_df in df.groupby('TEST_TYPE'):
            fig = px.line(group_df, x='TEST_DATE', y='VALUE', markers=True,
                          title=f"{test_type} Trend",
                          labels={'TEST_DATE': 'Date', 'VALUE': f'{test_type} Value'})
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No confirmed test results to display. Upload a report via Telegram or the tab above!")

    if pending_results:
        st.markdown("### Pending Confirmation")
        for r in pending_results:
            rid = r.get('ID') or r.get('id')
            tt = r.get('TEST_TYPE') or r.get('test_type')
            val = r.get('VALUE') or r.get('value')
            unit = r.get('UNIT') or r.get('unit')
            dt = r.get('TEST_DATE') or r.get('test_date')
            
            with st.container(border=True):
                col_info, col_btn1, col_btn2 = st.columns([6, 1, 1])
                with col_info:
                    st.write(f"**{tt}**: {val} {unit} (Date: {dt})")
                with col_btn1:
                    if st.button("Confirm", key=f"conf_{rid}", type="primary"):
                        direct_db_query(f"UPDATE TEST_RESULTS SET IS_CONFIRMED = 1 WHERE ID = {rid}")
                        direct_db_query("COMMIT")
                        st.rerun()
                with col_btn2:
                    if st.button("Delete", key=f"del_{rid}"):
                        direct_db_query(f"DELETE FROM TEST_RESULTS WHERE ID = {rid}")
                        direct_db_query("COMMIT")
                        st.rerun()

with tab2:
    st.subheader("Test History")
    if confirmed_results:
        df_history = pd.DataFrame(confirmed_results)
        df_history.columns = [c.upper() for c in df_history.columns]
        display_df = df_history[['TEST_DATE', 'TEST_TYPE', 'VALUE', 'UNIT']]
        st.dataframe(display_df, width="stretch", hide_index=True)
    else:
        st.info("No confirmed test results yet.")

with tab3:
    st.subheader("Upload Medical Report")
    st.write("Upload an image of your lab report. The Orchestrator Agent will extract data and save it.")
    uploaded_file = st.file_uploader("Choose a file", type=['jpg', 'jpeg', 'png'])

    if uploaded_file is not None:
        if st.button("Analyze & Save", type="primary"):
            with st.spinner("Orchestrator is analyzing the report..."):
                file_bytes = uploaded_file.read()
                mime_type = uploaded_file.type
                parts = [
                    types.Part(text="I've attached a medical report image. Please extract the diabetic readings and save them to my history."),
                    types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
                ]

                async def _analyze():
                    orch_runner, _ = get_runners()
                    return await call_agent(orch_runner, user['id'], "", parts=parts)

                resp = sync_run(_analyze())
                st.success(resp)
                if "saved" in resp.lower() or "extracted" in resp.lower():
                    st.info("Go to the Dashboard tab to confirm the new readings.")

with tab4:
    st.subheader("AI Health Assistant")
    st.write("Chat with the Orchestrator about your health data.")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask me about your trends or results..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                async def _chat():
                    orch_runner, _ = get_runners()
                    return await call_agent(orch_runner, user['id'], prompt)

                full_response = sync_run(_chat())
                st.markdown(full_response)
        st.session_state.messages.append({"role": "assistant", "content": full_response})
