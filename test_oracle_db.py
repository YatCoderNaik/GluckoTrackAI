from db import get_connection

def test_connection():
    try:
        print("Attempting to connect to Oracle Cloud Database...")
        # get_connection() automatically loads variables from .env
        conn = get_connection()
        c = conn.cursor()
        
        # A simple test query that works on any Oracle database
        c.execute("SELECT 'Connection Successful!', sysdate FROM DUAL")
        result = c.fetchone()
        
        print("\n--- Success ---")
        print(f"Message: {result[0]}")
        print(f"Database Time (sysdate): {result[1]}")
        print(f"Oracle Server Version: {conn.version}")
        print("----------------")
        
        conn.close()
        
    except Exception as e:
        print("\n--- Connection Error ---")
        print(f"Failed to connect: {e}")
        print("\nPlease ensure:")
        print("1. Your Oracle Wallet files are inside the folder specified by LOCAL_WALLET_DIR (default: ./wallet).")
        print("2. DB_USER, DB_PASSWORD, and DB_DSN (your tnsnames.ora alias) are correct in .env.")
        print("------------------------")

if __name__ == "__main__":
    test_connection()
