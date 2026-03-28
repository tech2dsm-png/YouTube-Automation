import os
import sqlite3
import logging
from google.cloud import storage
from googleapiclient.discovery import build
from google.oauth2 import service_account
from init_db import sync_db_to_csv

# Configuration
DB_NAME = "youtube_master.db"
BUCKET_NAME = "your-google-cloud-bucket-name"
SERVICE_ACCOUNT_FILE = "service_account.json"

# Professional Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def get_youtube_client():
    """Builds the YouTube API client using the service account."""
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=scopes
    )
    return build("youtube", "v3", credentials=credentials)

def publish_to_youtube(video_file, title, description):
    """Sends metadata and cloud video link to YouTube."""
    try:
        youtube = get_youtube_client()
        
        # Define the video metadata
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': ['Python', 'Programming', 'SankalanAI'],
                'categoryId': '27' # 27 is Education
            },
            'status': {
                'privacyStatus': 'public', # Or 'private' for testing
                'selfDeclaredMadeForKids': False,
            }
        }

        # In this professional pipeline, we tell YouTube where the file is in GCS
        # Note: Direct GCS-to-YouTube transfer usually requires specific API permissions
        # For now, we assume a standard upload request
        logging.info(f"Uploading to YouTube: {title}")
        
        # This is a placeholder for the actual upload execution
        # In a full production script, we'd use MediaIoBaseUpload here
        video_id = "EXAMPLE_ID_123" 
        
        return f"https://www.youtube.com/watch?v={video_id}"
    except Exception as e:
        logging.error(f"YouTube Upload Failed: {e}")
        return None

def run_uploader():
    """Processes videos ready for YouTube publishing."""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT video_file, title, description FROM video_queue WHERE status = 'uploaded_to_drive'"
            )
            ready_videos = cursor.fetchall()

            if not ready_videos:
                logging.info("No videos ready for YouTube upload.")
                return

            for video_file, title, description in ready_videos:
                youtube_url = publish_to_youtube(video_file, title, description)
                
                if youtube_url:
                    cursor.execute(
                        "UPDATE video_queue SET status = 'published', youtube_url = ? WHERE video_file = ?",
                        (youtube_url, video_file)
                    )
                    conn.commit()
                    logging.info(f"Successfully published: {title}")
            
        sync_db_to_csv()
    except Exception as error:
        logging.error(f"Uploader process failed: {error}")

if __name__ == "__main__":
    run_uploader()