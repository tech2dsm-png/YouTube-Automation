import os
import sqlite3
import logging
import json
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.oauth2.credentials import Credentials
import google.auth.transport.requests

# Import your sync script to update Power BI/Google Sheets
try:
    from src import cloud_sync_init
except ImportError:
    # Fallback if src folder structure is different
    cloud_sync_init = None

# Configuration from Environment Variables (GitHub Secrets)
DB_NAME = os.getenv("DB_PATH", "youtube_master.db")
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [UPLOADER] - %(message)s')

def get_google_creds():
    """Builds credentials from the Refresh Token stored in GitHub Secrets."""
    token_json = os.getenv("GOOGLE_YOUTUBE_TOKEN")
    if not token_json:
        raise Exception("GOOGLE_YOUTUBE_TOKEN secret is missing!")
    
    info = json.loads(token_json)
    creds = Credentials.from_authorized_user_info(info)
    
    # Refresh the token if it's expired
    if creds.expired and creds.refresh_token:
        creds.refresh(google.auth.transport.requests.Request())
    return creds

def download_from_drive(drive_service, file_name, local_path):
    """Finds the video in the specified Drive folder and downloads it."""
    query = f"name = '{file_name}' and '{DRIVE_FOLDER_ID}' in parents"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])

    if not items:
        logging.error(f"File {file_name} not found on Google Drive.")
        return False

    file_id = items[0]['id']
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.FileIO(local_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    
    done = False
    while not done:
        status, done = downloader.next_chunk()
        logging.info(f"Downloading {file_name}: {int(status.progress() * 100)}%")
    return True

def publish_to_youtube(youtube, local_path, title, description):
    """Performs the actual byte-stream upload to YouTube."""
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': ['Python', 'Data Analytics', 'SankalanAI'],
            'categoryId': '27'
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False,
        }
    }

    media = MediaFileUpload(local_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    
    logging.info(f"🚀 Starting YouTube Upload: {title}")
    response = request.execute()
    return response.get("id")

def run_uploader():
    """Main process to pick ONE staged video and publish it."""
    try:
        creds = get_google_creds()
        drive_service = build("drive", "v3", credentials=creds)
        youtube_service = build("youtube", "v3", credentials=creds)

        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            
            # LIMIT 1 ensures we only post one video per day at 7 AM IST
            cursor.execute("""
                SELECT video_file, title, description 
                FROM video_queue 
                WHERE status = 'uploaded-to-drive' 
                ORDER BY id ASC 
                LIMIT 1
            """)
            
            video = cursor.fetchone()

            if not video:
                logging.info("No videos found with status 'uploaded-to-drive'.")
                return

            video_file, title, description = video
            local_temp = f"temp_{video_file}"
            
            if download_from_drive(drive_service, video_file, local_temp):
                video_id = publish_to_youtube(youtube_service, local_temp, title, description)
                
                if video_id:
                    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
                    cursor.execute(
                        "UPDATE video_queue SET status = 'published', youtube_url = ? WHERE video_file = ?",
                        (youtube_url, video_file)
                    )
                    conn.commit()
                    logging.info(f"✅ Successfully Published to YouTube: {youtube_url}")
                    
                    # Run the sync to update Google Sheets / Power BI immediately
                    if cloud_sync_init:
                        logging.info("Syncing analytics to Google Sheets...")
                        cloud_sync_init.run_sync()
                
                # Cleanup: Delete the temp video file from the GitHub Runner
                if os.path.exists(local_temp):
                    os.remove(local_temp)
            
    except Exception as e:
        logging.error(f"Uploader process failed: {e}")

if __name__ == "__main__":
    run_uploader()