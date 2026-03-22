import streamlit as st
import pandas as pd
import plotly.express as px
import os
from datetime import datetime
import json
from google import genai
from google.genai import types
from db import init_db, get_user_by_id_or_username, get_test_results, confirm_result, delete_result, add_test_result, add_user
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="GlucoTrack AI", page_icon="📈", layout="wide")

# Initialize DB on start
init_db()

if 'user' not in st.session_state:
    st.session_state.user = None

def login():
    st.markdown("<h1 style='text-align: center; color: #10b981;'>GlucoTrack AI</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Enter your ID or Username to access your health dashboard</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.container(border=True):
            st.subheader("Login")
            identifier = st.text_input("ID or Username", placeholder="e.g. 123456789 or @username")
            if st.button("Access Dashboard", use_container_width=True, type="primary"):
                user = get_user_by_id_or_username(identifier)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("User not found. Try creating a new account.")
        
        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.subheader("Create an Account")
            new_id = st.text_input("New ID (e.g. phone number)", key="new_id")
            new_first_name = st.text_input("First Name", key="new_first")
            new_username = st.text_input("Username (optional)", key="new_user")
            if st.button("Register", use_container_width=True):
                if new_id and new_first_name:
                    add_user(new_id, new_first_name, new_username)
                    st.success("Account created! You can now log in using your ID or username.")
                else:
                    st.error("Please provide at least ID and First Name.")

if not st.session_state.user:
    login()
    st.stop()

# --- Main App ---
user = st.session_state.user

# Header
col1, col2 = st.columns([10, 1])
with col1:
    st.title(f"Welcome, {user['first_name']}!")
with col2:
    if st.button("Logout"):
        st.session_state.user = None
        st.rerun()

# Fetch latest results each time
results = get_test_results(user['id'])

confirmed_results = [r for r in results if r['is_confirmed']]
pending_results = [r for r in results if not r['is_confirmed']]

# Calculate latest stats
latest_hba1c = next((r for r in confirmed_results if r['test_type'] and 'hba1c' in r['test_type'].lower()), None)
latest_sugar = next((r for r in confirmed_results if r['test_type'] and ('sugar' in r['test_type'].lower() or 'fbs' in r['test_type'].lower() or 'rbs' in r['test_type'].lower())), None)

st.markdown("---")
# Quick Stats
c1, c2, c3 = st.columns(3)
with c1:
    with st.container(border=True):
        st.markdown("**Latest HbA1c 📈**")
        st.subheader(f"{latest_hba1c['value']} %" if latest_hba1c else "--")
with c2:
    with st.container(border=True):
        st.markdown("**Latest Glucose 🩸**")
        st.subheader(f"{latest_sugar['value']} mg/dL" if latest_sugar else "--")
with c3:
    with st.container(border=True):
        st.markdown("**Pending Reports 🕒**")
        st.subheader(f"{len(pending_results)}")


tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "History", "Upload Report", "AI Chat"])

with tab1:
    st.subheader("Trends Over Time")
    if confirmed_results:
        df = pd.DataFrame(confirmed_results)
        df['test_date'] = pd.to_datetime(df['test_date'])
        # Sort so line chart connects properly
        df = df.sort_values('test_date')
        
        fig = px.line(df, x='test_date', y='value', color='test_type', markers=True, title="Test Results History")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No confirmed test results to display. Upload a report to get started!")

    if pending_results:
        st.markdown("### Pending Confirmation")
        st.warning(f"You have {len(pending_results)} reports pending confirmation.")
        for r in pending_results:
            with st.container(border=True):
                col_info, col_btn1, col_btn2 = st.columns([6, 1, 1])
                with col_info:
                    st.write(f"**{r['test_type']}**: {r['value']} {r['unit']} (Date: {r['test_date']})")
                with col_btn1:
                    if st.button("Confirm", key=f"conf_{r['id']}", type="primary"):
                        confirm_result(r['id'])
                        st.rerun()
                with col_btn2:
                    if st.button("Delete", key=f"del_{r['id']}"):
                        delete_result(r['id'])
                        st.rerun()

with tab2:
    st.subheader("Test History")
    if confirmed_results:
        df_history = pd.DataFrame(confirmed_results)
        df_history = df_history[['test_date', 'test_type', 'value', 'unit']]
        df_history.columns = ['Date', 'Test Type', 'Value', 'Unit']
        st.dataframe(df_history, use_container_width=True, hide_index=True)
    else:
        st.info("No confirmed test results yet.")

with tab3:
    st.subheader("Upload Medical Report")
    st.write("Upload an image or PDF of your lab report to automatically extract diabetic test results using Google Gemini.")
    uploaded_file = st.file_uploader("Choose a file", type=['jpg', 'jpeg', 'png', 'pdf'])
    
    if uploaded_file is not None:
        if st.button("Analyze Report", type="primary"):
            with st.spinner("Analyzing report..."):
                try:
                    # Initialize Gemini API
                    api_key = os.getenv("GEMINI_API_KEY")
                    if not api_key:
                        st.error("GEMINI_API_KEY is not set in the environment or `.env` file.")
                    else:
                        client = genai.Client(api_key=api_key)
                        
                        file_bytes = uploaded_file.read()
                        mime_type = uploaded_file.type
                        
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
                                    data=file_bytes,
                                    mime_type=mime_type,
                                ),
                                prompt
                            ],
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                            ),
                        )
                        
                        try:
                            analysis = json.loads(response.text)
                            extracted = analysis.get("results", [])
                            
                            if not extracted:
                                st.warning("No diabetic tests found in the report.")
                            else:
                                for res in extracted:
                                    add_test_result(
                                        user_id=user['id'],
                                        test_type=res.get("testType"),
                                        value=res.get("value"),
                                        unit=res.get("unit"),
                                        test_date=res.get("testDate"),
                                        is_confirmed=False
                                    )
                                st.success(f"Extracted {len(extracted)} results! Please confirm them in the Dashboard.")
                                # Allow user to see what matched without rerunning immediately
                                for r in extracted:
                                    st.write(f"- {r.get('testType')}: {r.get('value')} {r.get('unit')}")
                                
                        except json.JSONDecodeError as je:
                            st.error("Failed to parse the Gemini API response.")
                            st.write(response.text)
                            
                except Exception as e:
                    st.error(f"Error during analysis: {e}")

with tab4:
    st.subheader("AI Health Assistant")
    st.write("Ask questions about your test history!")
    
    with st.container(border=True):
        st.markdown("**Tip:** You can ask me things like *\"What was my average sugar level last month?\"* or *\"Show me my HbA1c trend.\"*")
        user_query = st.text_input("Your question:")
        if st.button("Ask Assistant", type="primary"):
            if user_query:
                api_key = os.getenv("GEMINI_API_KEY")
                if not api_key:
                    st.error("GEMINI_API_KEY is not set.")
                else:
                    with st.spinner("Thinking..."):
                        try:
                            client = genai.Client(api_key=api_key)
                            
                            # Build the context
                            history_data = [
                                { "testType": r['test_type'], "value": r['value'], "unit": r['unit'], "date": r['test_date'] }
                                for r in confirmed_results
                            ]
                            
                            prompt = f'''
                                The user is asking: "{user_query}"
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
                            
                            st.markdown(f"**Assistant:**\n{response.text}")
                        except Exception as e:
                            st.error(f"Error interacting with Assistant: {e}")
