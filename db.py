import os
import json
import subprocess
from dotenv import load_dotenv

load_dotenv()

# We refactor db.py to act as a bridge using the MCP Toolbox binary.
# This ensures existing apps like app.py still work while using the new architecture.

def run_toolbox_query(sql, params=None):
    """Bridge to toolbox.exe execute_sql tool."""
    # Note: Gen AI Toolbox execute_sql typically takes 'query' as a parameter.
    # We serialize the query with any potential parameters (if the tool supports it).
    # Since this is a Go CLI tool, we invoke it via subprocess.
    
    # Example format: toolbox invoke execute_sql '{"query": "SELECT * FROM users"}'
    try:
        cmd = ["toolbox.exe", "invoke", "execute_sql", json.dumps({"query": sql}), "--tools-file", "tools.yaml"]
        res = subprocess.run(cmd, env=os.environ, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"Toolbox Error: {res.stderr}")
            return []
        
        # The output is likely JSON results
        return json.loads(res.stdout).get("result", [])
    except Exception as e:
        print(f"Database/Toolbox Error: {e}")
        return []

def init_db():
    """Initializes tables using toolbox."""
    # The agent/toolbox can create them if missing.
    # If the database is already provisioned (as Oracle ATP typically is), we don't need this.
    pass

def add_user(user_id, first_name, username=""):
    sql = f"INSERT INTO users (id, first_name, username) VALUES ('{user_id}', '{first_name}', '{username}')"
    # Note: Use parameter binding if the toolbox supports it, or just run query.
    return run_toolbox_query(sql)

def get_user_by_id_or_username(identifier):
    clean_id = identifier.lstrip('@')
    sql = f"SELECT id, first_name, username FROM users WHERE id = '{identifier}' OR username = '{clean_id}'"
    rows = run_toolbox_query(sql)
    if rows:
        row = rows[0]
        return {"id": row.get('ID') or row.get('id'), "first_name": row.get('FIRST_NAME') or row.get('first_name'), "username": row.get('USERNAME') or row.get('username')}
    return None

def add_test_result(user_id, test_type, value, unit, test_date, is_confirmed=False):
    conf_flag = 1 if is_confirmed else 0
    sql = f"INSERT INTO test_results (user_id, test_type, value, unit, test_date, is_confirmed) VALUES ('{user_id}', '{test_type}', {value}, '{unit}', TO_DATE('{test_date}', 'YYYY-MM-DD'), {conf_flag})"
    return run_toolbox_query(sql)

def get_test_results(user_id):
    sql = f"SELECT id, user_id, test_type, value, unit, test_date, is_confirmed FROM test_results WHERE user_id = '{user_id}' ORDER BY test_date DESC"
    rows = run_toolbox_query(sql)
    results = []
    # Map back to dict
    for row in rows:
        # Standardize keys (Oracle returns UPPERCASE by default often)
        results.append({
            "id": row.get('ID') or row.get('id'),
            "user_id": row.get('USER_ID') or row.get('user_id'),
            "test_type": row.get('TEST_TYPE') or row.get('test_type'),
            "value": row.get('VALUE') or row.get('value'),
            "unit": row.get('UNIT') or row.get('unit'),
            "test_date": row.get('TEST_DATE') or row.get('test_date'),
            "is_confirmed": bool(row.get('IS_CONFIRMED') or row.get('is_confirmed'))
        })
    return results

def confirm_result(result_id):
    sql = f"UPDATE test_results SET is_confirmed = 1 WHERE id = {result_id}"
    return run_toolbox_query(sql)

def delete_result(result_id):
    sql = f"DELETE FROM test_results WHERE id = {result_id}"
    return run_toolbox_query(sql)
