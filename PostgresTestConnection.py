import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# You can also hardcode the connection string here for quick testing
POSTGRES_URL = os.getenv("POSTGRES_URL") or "postgresql://eda_user:MyStrongPassword@<REMOTE_IP>:5432/eda_memory"

def test_connection():
    try:
        conn = psycopg2.connect(POSTGRES_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print("✅ Connected to PostgreSQL Server. Version:", version[0])
        cursor.close()
        conn.close()
    except Exception as e:
        print("❌ Failed to connect to PostgreSQL Server.")
        print("Error:", str(e))

if __name__ == "__main__":
    test_connection()
