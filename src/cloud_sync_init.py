import sqlite3
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import os
import traceback
import logging
from dotenv import load_dotenv

# --- Load Environment Variables ---
load_dotenv()

# Use the same environment variables as feeder.py for consistency
DB_PATH = os.getenv("DB_PATH", "youtube_master.db") 
JSON_KEY_FILE = os.getenv("SERVICE_ACCOUNT_JSON", os.path.join("credentials", "service-account.json"))

# This must match the name at the very top of your Google Sheet browser tab
SHEET_NAME = "Youtube_Automation"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def migrate_all_to_cloud():
    """Syncs the 14-column video_queue and system_snapshots to Google Sheets"""
    try:
        # 1. Authenticate with Google
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        
        if not os.path.exists(JSON_KEY_FILE):
            logging.error(f"❌ Key file not found at: {JSON_KEY_FILE}")
            return

        creds = Credentials.from_service_account_file(JSON_KEY_FILE, scopes=scopes)
        client = gspread.authorize(creds)
        
        logging.info(f"Connecting to Google Sheet: {SHEET_NAME}...")
        spreadsheet = client.open(SHEET_NAME)
        
        # 2. Get Data from Local SQL Database
        if not os.path.exists(DB_PATH):
            logging.error(f"❌ Database file not found at: {DB_PATH}")
            return

        conn = sqlite3.connect(DB_PATH)
        
        # Fetch ALL 14 columns from the main queue
        df_videos = pd.read_sql_query("SELECT * FROM video_queue", conn)
        
        # Fetch Snapshots for the Power BI Burn-down chart
        df_snapshots = pd.read_sql_query("SELECT * FROM system_snapshots", conn)
        
        conn.close()

        # 3. Sync Main Video Data (Worksheet: Video_Queue)
        if not df_videos.empty:
            try:
                sheet_main = spreadsheet.worksheet("Video_Queue")
            except gspread.exceptions.WorksheetNotFound:
                logging.info("Worksheet 'Video_Queue' not found. Creating it...")
                sheet_main = spreadsheet.add_worksheet(title="Video_Queue", rows="1000", cols="20")
            
            sheet_main.clear()
            
            # Clean data for Sheets: replace NaN with empty strings
            df_videos = df_videos.fillna("").astype(str)
            all_main_data = [df_videos.columns.values.tolist()] + df_videos.values.tolist()
            
            # Update the sheet (using the list of lists format)
            sheet_main.update(values=all_main_data, range_name='A1')
            logging.info(f"✅ Synced {len(df_videos)} videos to 'Video_Queue' tab.")
        else:
            logging.warning("Video_Queue table is empty. Nothing to sync.")

        # 4. Sync Snapshot Data (Worksheet: Snapshots)
        if not df_snapshots.empty:
            try:
                sheet_snap = spreadsheet.worksheet("Snapshots")
            except gspread.exceptions.WorksheetNotFound:
                logging.info("Worksheet 'Snapshots' not found. Creating it...")
                sheet_snap = spreadsheet.add_worksheet(title="Snapshots", rows="1000", cols="10")
            
            sheet_snap.clear()
            
            df_snapshots = df_snapshots.fillna("").astype(str)
            all_snap_data = [df_snapshots.columns.values.tolist()] + df_snapshots.values.tolist()
            
            sheet_snap.update(values=all_snap_data, range_name='A1')
            logging.info(f"✅ Synced {len(df_snapshots)} snapshots to 'Snapshots' tab.")

        logging.info("🚀 SUCCESS! Google Sheets is now 100% in sync with your local DB.")

    except Exception:
        logging.error("--- DETAILED ERROR LOG ---")
        traceback.print_exc()

def run_sync():
    """Alias for orchestrator"""
    migrate_all_to_cloud()

if __name__ == "__main__":
    run_sync()