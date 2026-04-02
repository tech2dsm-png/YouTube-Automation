import os
import sqlite3
import logging
import shutil
import csv
import time
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# Google Auth & API Libraries
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- Load Environment Variables ---
load_dotenv()

CLIENT_SECRETS_FILE = os.getenv("CLIENT_SECRETS_PATH")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
DB_NAME = os.getenv("DB_PATH")
CSV_NAME = os.getenv("METADATA_CSV")
SOURCE_FOLDER = os.getenv("DIR_VIDEOS")
DONE_FOLDER = os.getenv("DIR_DRIVE_TEMP")

TOKEN_FILE = os.path.join("credentials", "token.json")

SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/youtube.upload'
]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def get_authenticated_service():
    """Handles the browser login and saves a token for future use."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            logging.warning(f"Token corrupted: {e}. Re-authenticating...")
            if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            
    return build('drive', 'v3', credentials=creds)

def update_system_snapshot(conn):
    """Logs a snapshot of the current pipeline state for Power BI analytics."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM video_queue WHERE status = 'pending'")
        pending = cursor.fetchone()[0]
        
        # Matches your logic: 'uploaded-to-drive' is your staged state
        cursor.execute("SELECT COUNT(*) FROM video_queue WHERE status = 'uploaded-to-drive'")
        staged = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM video_queue WHERE status = 'published'")
        published = cursor.fetchone()[0]
        
        cursor.execute('''
            INSERT INTO system_snapshots (pending_count, staged_count, published_count)
            VALUES (?, ?, ?)
        ''', (pending, staged, published))
        logging.info(f"📸 Snapshot recorded: P:{pending}, S:{staged}, Pub:{published}")
    except Exception as e:
        logging.error(f"Snapshot failed: {e}")

def sync_db_to_csv():
    """Updates the metadata.csv to match the 14-column database schema."""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            df = pd.read_sql_query("SELECT * FROM video_queue", conn)
            df.to_csv(CSV_NAME, index=False, quoting=csv.QUOTE_ALL, encoding='utf-8')
            logging.info(f"CSV synced: {CSV_NAME}")
    except Exception as e:
        logging.error(f"Failed to sync CSV: {e}")

def run_feeder():
    """Finds pending videos, uploads them, and handles status updates."""
    if not os.path.exists(DONE_FOLDER): os.makedirs(DONE_FOLDER)

    service = get_authenticated_service()
    success_count = 0
    failed_count = 0

    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT video_file FROM video_queue WHERE status = 'pending'")
            pending_rows = cursor.fetchall()

            if not pending_rows:
                logging.info("No pending videos. Taking snapshot and exiting.")
                update_system_snapshot(conn)
                conn.commit()
                return

            logging.info(f"Found {len(pending_rows)} videos. Starting upload...")

            for row in pending_rows:
                video_file = row['video_file']
                local_path = os.path.join(SOURCE_FOLDER, video_file)
                
                if not os.path.exists(local_path):
                    logging.warning(f"File not found on disk: {video_file}")
                    continue

                logging.info(f"Uploading to Drive: {video_file}...")

                file_metadata = {
                    'name': video_file,
                    'parents': [GOOGLE_DRIVE_FOLDER_ID]
                }

                media = MediaFileUpload(local_path, mimetype='video/mp4', resumable=True)
                request = service.files().create(body=file_metadata, media_body=media, fields='id')

                response = None
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        print(f"Progress: {int(status.progress() * 100)}%", end='\r')

                drive_id = response.get('id')

                # CORRECTED: Only update status and drive_id. Do NOT overwrite created_at.
                cursor.execute('''
                    UPDATE video_queue 
                    SET status = 'uploaded-to-drive', 
                        drive_id = ?
                    WHERE video_file = ?
                ''', (drive_id, video_file))
                conn.commit()
                
                # Cleanup and Move
                del media
                del request
                time.sleep(2) 

                abs_src = os.path.abspath(local_path)
                abs_dst = os.path.abspath(os.path.join(DONE_FOLDER, video_file))
                
                try:
                    shutil.move(abs_src, abs_dst)
                    logging.info(f"Success! {video_file} moved to Drive Temp.")
                    success_count += 1
                except Exception as e:
                    logging.error(f"Move failed for {video_file}: {e}")
                    failed_count += 1

            # Take final snapshot after all uploads in this session are done
            update_system_snapshot(conn)
            conn.commit()

        sync_db_to_csv()
        logging.info(f"Run Complete. Uploaded: {success_count}, Failed: {failed_count}")

    except Exception as e:
        logging.error(f"Feeder failed: {e}")

if __name__ == "__main__":
    run_feeder()