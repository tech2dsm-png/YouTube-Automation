import os
import sqlite3
import pandas as pd
import logging
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

# --- Configuration (Standard: Centralized Paths) ---
DB_PATH = os.getenv("DB_PATH", "youtube_master.db")
CSV_PATH = os.getenv("METADATA_CSV", "metadata.csv")
TOKEN_FILE = os.path.join("credentials", "token.json")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [STATS-SYNC] - %(message)s')

def get_authenticated_youtube():
    """
    Reuses the token.json from your feeder.py.
    This eliminates the need for a YOUTUBE_API_KEY in .env.
    """
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE)
    
    # Refresh token if expired
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            logging.error("No valid token.json found. Please run feeder.py first.")
            return None
            
    return build("youtube", "v3", credentials=creds)

def update_stats():
    """
    Batch updates metrics for published videos.
    Syncs SQLite -> CSV for Power BI.
    """
    youtube = get_authenticated_youtube()
    if not youtube:
        return

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()

            # 1. Target only videos that actually exist on YouTube
            cursor.execute("SELECT youtube_id FROM video_queue WHERE status='published' AND youtube_id IS NOT NULL")
            rows = cursor.fetchall()

            if not rows:
                logging.info("Zero published videos found in DB. Nothing to track.")
                return

            all_ids = [row[0] for row in rows]
            logging.info(f"Syncing stats for {len(all_ids)} videos...")

            # 2. Batch Logic: 50 IDs per single API call (Quota Efficiency)
            for i in range(0, len(all_ids), 50):
                batch_ids = ",".join(all_ids[i:i+50])
                
                request = youtube.videos().list(
                    part="statistics",
                    id=batch_ids
                )
                response = request.execute()

                for item in response.get('items', []):
                    y_id = item['id']
                    stats = item['statistics']
                    
                    # Ensure numeric types for Power BI aggregations
                    v = int(stats.get('viewCount', 0))
                    l = int(stats.get('likeCount', 0))
                    c = int(stats.get('commentCount', 0))

                    cursor.execute("""
                        UPDATE video_queue 
                        SET views = ?, likes = ?, comments = ? 
                        WHERE youtube_id = ?
                    """, (v, l, c, y_id))

            conn.commit()
            logging.info("SQLite Database updated with fresh metrics.")

            # 3. Synchronize Master CSV (The Power BI Source)
            df = pd.read_sql_query("SELECT * FROM video_queue", conn)
            df.to_csv(CSV_PATH, index=False)
            logging.info(f"✅ Success: {CSV_PATH} is now in sync with YouTube.")

    except Exception as e:
        logging.error(f"Stats Sync Failed: {e}")

if __name__ == "__main__":
    update_stats()