import os
import sqlite3
import logging
import traceback
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# Load settings from the .env file
load_dotenv()

# --- Folder and File Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, os.getenv("DB_PATH", "youtube_master.db"))
JSON_KEY_FILE = os.path.join(BASE_DIR, os.getenv("SERVICE_ACCOUNT_JSON", "credentials/service-account.json"))
SHEET_NAME = "Youtube_Automation"

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [CLOUD-SYNC] - %(message)s')

def migrate_all_to_cloud():
    """
    Mirrors the local SQLite database to Google Sheets accurately.
    """
    try:
        # 1. Authentication with Google
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        if not os.path.exists(JSON_KEY_FILE):
            logging.error(f"Service Account JSON missing at: {JSON_KEY_FILE}")
            return

        creds = Credentials.from_service_account_file(JSON_KEY_FILE, scopes=scopes)
        client = gspread.authorize(creds)
        
        try:
            spreadsheet = client.open(SHEET_NAME)
        except gspread.exceptions.SpreadsheetNotFound:
            logging.error(f"Could not find '{SHEET_NAME}'. Ensure the sheet is shared with the service account email.")
            return
        
        # 2. Extract and Push Data
        with sqlite3.connect(DB_PATH) as conn:
            # Check which tables exist in the local database
            tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table'", conn)['name'].tolist()
            
            # --- SYNC TABLE 1: Video Queue ---
            if "video_queue" in tables:
                # We pull everything. The 'created_at' column contains your local file dates.
                df_videos = pd.read_sql_query("SELECT * FROM video_queue ORDER BY id ASC", conn)
                sync_worksheet(spreadsheet, "Video_Queue", df_videos)
            
            # --- SYNC TABLE 2: System Snapshots ---
            if "system_snapshots" in tables:
                # Mirror system_snapshots table to the 'Snapshots' tab
                df_snapshots = pd.read_sql_query("SELECT * FROM system_snapshots ORDER BY id DESC", conn)
                sync_worksheet(spreadsheet, "Snapshots", df_snapshots)

        logging.info("🚀 Synchronization complete. Data is now identical across Local and Cloud.")

    except Exception as e:
        logging.error(f"Sync failed: {e}")
        traceback.print_exc()

def sync_worksheet(spreadsheet, tab_title, df):
    """
    Refreshes a specific Google Sheet tab with the provided DataFrame data.
    """
    if df is None or df.empty:
        logging.warning(f"No data to sync for '{tab_title}'.")
        return

    try:
        # Locate the tab
        ws = spreadsheet.worksheet(tab_title)
    except gspread.exceptions.WorksheetNotFound:
        # Create it if it's missing (helps on first run)
        ws = spreadsheet.add_worksheet(title=tab_title, rows="1000", cols="20")
        logging.info(f"Created new tab: {tab_title}")

    # Step 1: Wipe old data to ensure no ghost rows remain
    ws.clear()
    
    # Step 2: Format data for Google Sheets
    # We convert everything to string to preserve formatting (especially timestamps)
    df_clean = df.fillna("").astype(str)
    
    # Step 3: Prepare the batch update (Headers + Data rows)
    data_to_push = [df_clean.columns.values.tolist()] + df_clean.values.tolist()
    
    # Step 4: Batch Update to Google
    # 'USER_ENTERED' is key: it tells Google to interpret the date strings as actual Dates.
    ws.update(data_to_push, value_input_option='USER_ENTERED') 
    logging.info(f"✅ Tab '{tab_title}' updated with {len(df)} records.")

def run_sync():
    migrate_all_to_cloud()

if __name__ == "__main__":
    run_sync()