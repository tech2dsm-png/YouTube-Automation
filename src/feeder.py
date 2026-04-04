import os
import sqlite3
import logging
import shutil
import pandas as pd
import csv
import time
from datetime import datetime
from dotenv import load_dotenv

# Google API tools
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Script to sync data to Google Sheets
import cloud_sync_init 

load_dotenv()

# --- Where everything is located ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_NAME = os.path.join(BASE_DIR, os.getenv("DB_PATH", "youtube_master.db"))
CSV_NAME = os.path.join(BASE_DIR, os.getenv("METADATA_CSV", "metadata.csv"))
SOURCE_FOLDER = os.path.join(BASE_DIR, os.getenv("DIR_VIDEOS", "videos"))
DONE_FOLDER = os.path.join(BASE_DIR, os.getenv("DIR_DRIVE_TEMP", "uploaded-to-drive"))
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
TOKEN_FILE = os.path.join(BASE_DIR, "credentials", "token.json")
CLIENT_SECRETS_FILE = os.path.join(BASE_DIR, os.getenv("CLIENT_SECRETS_PATH", "credentials/client_secrets.json"))

# Permissions for Drive and YouTube
SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/youtube.upload']

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [FEEDER] - %(message)s')

def get_authenticated_service():
    """ Log in to Google Services """
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def run_feeder():
    """ Upload videos from laptop to Google Drive """
    
    # Create the 'done' folder if it doesn't exist yet
    if not os.path.exists(DONE_FOLDER): 
        os.makedirs(DONE_FOLDER)
        
    service = get_authenticated_service()
    work_was_done = False 

    try:
        # Connect to the local database
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. Find the next 5 videos waiting to be uploaded
        cursor.execute("SELECT id, video_file FROM video_queue WHERE status = 'pending' LIMIT 5")
        queue = cursor.fetchall()

        if not queue:
            logging.info("Nothing to upload right now.")
            conn.close()
            return

        for row in queue:
            v_id, v_file = row['id'], row['video_file']
            local_path = os.path.normpath(os.path.join(SOURCE_FOLDER, v_file))
            dest_path = os.path.normpath(os.path.join(DONE_FOLDER, v_file))

            # Make sure the file actually exists on the laptop
            if not os.path.exists(local_path):
                logging.warning(f"File missing: {v_file}")
                continue

            # 2. Start the upload to Google Drive
            logging.info(f"Uploading: {v_file}")
            media = MediaFileUpload(local_path, mimetype='video/mp4', resumable=True)
            request = service.files().create(
                body={'name': v_file, 'parents': [GOOGLE_DRIVE_FOLDER_ID]},
                media_body=media, fields='id'
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"Progress: {int(status.progress() * 100)}%", end='\r')

            # 3. Update Database (Status and Published_at date)
            drive_id = response.get('id')
            # We record the current time as the "Drive Upload Date"
            now_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            cursor.execute("""
                UPDATE video_queue 
                SET status='uploaded-to-drive', 
                    drive_id=?, 
                    published_at=? 
                WHERE id=?
            """, (drive_id, now_time, v_id))
            conn.commit()

            # 4. Cleanup: Move the file to the 'done' folder
            try:
                # Close the file so Windows lets us move it
                if hasattr(media, '_fd') and media._fd:
                    media._fd.close()
                
                time.sleep(1) # Small pause to prevent "File in Use" errors
                
                # If the file is already in the 'done' folder, delete it so we can overwrite
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                
                shutil.move(local_path, dest_path)
                logging.info(f"✅ Finished: {v_file} is now in the cloud.")
                work_was_done = True
            except Exception as move_error:
                logging.error(f"Could not move file {v_file}: {move_error}")

        # 5. Refresh the CSV and Google Sheets
        if work_was_done:
            logging.info("Updating your CSV and Google Sheets dashboard...")
            df_final = pd.read_sql_query("SELECT * FROM video_queue ORDER BY id ASC", conn)
            df_final.to_csv(CSV_NAME, index=False, quoting=csv.QUOTE_ALL, encoding='utf-8')
            
            # This pushes the new 'uploaded-to-drive' status to the web
            cloud_sync_init.run_sync()

        conn.close()

    except Exception as e:
        logging.error(f"Something went wrong: {e}")

if __name__ == "__main__":
    run_feeder()