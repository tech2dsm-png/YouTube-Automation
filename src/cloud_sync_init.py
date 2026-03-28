import sqlite3
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import os
import traceback

# 1. Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

# Paths to your local files
DB_PATH = os.path.join(PROJECT_ROOT, "youtube_master.db") 
JSON_KEY_FILE = os.path.join(PROJECT_ROOT, "credentials", "service-account.json") 

# This must match the name at the very top of your Google Sheet browser tab
SHEET_NAME = "Youtube_Automation"

def migrate_all_to_cloud():
    try:
        # Authenticate with Google
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        
        if not os.path.exists(JSON_KEY_FILE):
            print(f"Key file not found at: {JSON_KEY_FILE}")
            return

        creds = Credentials.from_service_account_file(JSON_KEY_FILE, scopes=scopes)
        client = gspread.authorize(creds)
        
        print(f"Connecting to sheet named: {SHEET_NAME}...")
        
        # Opening by Name (Ensure the Service Account is an Editor on this sheet)
        spreadsheet = client.open(SHEET_NAME)
        sheet = spreadsheet.sheet1
        
        # 2. Get Data from Local SQL Database
        if not os.path.exists(DB_PATH):
            print(f"Database file not found at: {DB_PATH}")
            return

        conn = sqlite3.connect(DB_PATH)
        # Selecting the specific columns needed for the automation
        query = "SELECT id, video_file, title, description, status, drive_id, youtube_url, created_at FROM video_queue"
        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            print("Database is empty. Nothing to migrate.")
            return

        # 3. Prepare data for upload
        df = df.fillna("") # Replace empty values with blank strings
        df = df.astype(str) # Convert everything to string for Google Sheets compatibility
        
        header = df.columns.values.tolist()
        data_rows = df.values.tolist()
        all_data = [header] + data_rows

        # 4. Clear and Upload
        print(f"Clearing old data and uploading {len(data_rows)} rows...")
        sheet.clear()
        
        # Uploading starting from cell A1
        sheet.update(all_data, 'A1')
        
        print("Success! Data is now in the Google Sheet.")

    except Exception:
        print("--- DETAILED ERROR LOG START ---")
        traceback.print_exc()
        print("--- DETAILED ERROR LOG END ---")

if __name__ == "__main__":
    migrate_all_to_cloud()