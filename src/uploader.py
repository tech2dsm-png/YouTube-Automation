import os
import sqlite3
import logging
import json
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.oauth2.credentials import Credentials
import google.auth.transport.requests

# Import sync script to update Google Sheets immediately after publishing
try:
    from src import cloud_sync_init
except ImportError:
    import cloud_sync_init

# Configuration
DB_NAME = os.getenv("DB_PATH", "youtube_master.db")
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [UPLOADER] - %(message)s')

def get_google_creds():
    """Builds credentials from the Refresh Token stored in Environment Variables."""
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
    """Finds the video in the specified Drive folder and downloads it to the runner."""
    query = f"name = '{file_name}' and '{DRIVE_FOLDER_ID}' in parents"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])

    if not items:
        logging.error(f"File {file_name} not found on Google Drive.")
        return False

    file_id = items[0]['id']
    request = drive_service.files().get_media(fileId=file_id)
    
    # Download stream
    with io.FileIO(local_path, 'wb') as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                logging.info(f"Downloading {file_name}: {int(status.progress() * 100)}%")
    return True

def publish_to_youtube(youtube, local_path, title, description):
    """Performs the resumable upload to YouTube."""
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': ['Data Analytics', 'Automation', 'Python'],
            'categoryId': '27' # Education
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False,
        }
    }

    media = MediaFileUpload(local_path, mimetype='video/mp4', resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    
    logging.info(f"🚀 Starting YouTube Upload: {title}")
    response = request.execute()
    return response.get("id")

def run_uploader():
    """Finds one staged video, publishes it, and updates the ecosystem."""
    try:
        creds = get_google_creds()
        drive_service = build("drive", "v3", credentials=creds)
        youtube_service = build("youtube", "v3", credentials=creds)

        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Select the oldest staged video (FIFO logic)
            cursor.execute("""
                SELECT id, video_file, title, description 
                FROM video_queue 
                WHERE status = 'uploaded-to-drive' 
                ORDER BY id ASC 
                LIMIT 1
            """)
            
            video = cursor.fetchone()

            if not video:
                logging.info("Queue empty: No videos with 'uploaded-to-drive' status.")
                return

            v_id = video['id']
            v_file = video['video_file']
            v_title = video['title']
            v_desc = video['description']
            local_temp = f"temp_{v_file}"
            
            # Step 1: Download
            if download_from_drive(drive_service, v_file, local_temp):
                
                # Step 2: Upload
                y_id = publish_to_youtube(youtube_service, local_temp, v_title, v_desc)
                
                if y_id:
                    y_url = f"https://www.youtube.com/watch?v={y_id}"
                    
                    # Step 3: Atomic Status Update
                    # Important: Update both the URL and the YouTube ID for future stats tracking
                    cursor.execute("""
                        UPDATE video_queue 
                        SET status = 'published', 
                            youtube_url = ?, 
                            youtube_id = ?,
                            published_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (y_url, y_id, v_id))
                    conn.commit()
                    
                    logging.info(f"✅ Published: {y_url}")
                    
                    # Step 4: Sync to Google Sheets
                    try:
                        logging.info("Initiating cloud sync to Google Sheets...")
                        cloud_sync_init.migrate_all_to_cloud()
                    except Exception as sync_err:
                        logging.error(f"Post-upload sync failed: {sync_err}")
                
                # Step 5: Cleanup temp file
                if os.path.exists(local_temp):
                    os.remove(local_temp)
            
    except Exception as e:
        logging.error(f"Uploader runtime error: {e}")

if __name__ == "__main__":
    run_uploader()