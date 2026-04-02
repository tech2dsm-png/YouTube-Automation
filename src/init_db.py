import sqlite3
import pandas as pd
import os
import logging
import csv
from datetime import datetime
from dotenv import load_dotenv

# Load paths from .env for consistency with executor.py
load_dotenv()
DB_NAME = os.getenv("DB_PATH", "youtube_master.db")
CSV_NAME = os.getenv("METADATA_CSV", "metadata.csv")
VIDEO_FOLDER = os.getenv("DIR_VIDEOS", "videos")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def update_system_snapshot():
    """Captures a moment in time for the Power BI burn-down chart."""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM video_queue WHERE status = 'pending'")
            pending = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM video_queue WHERE status = 'uploaded-to-drive'")
            staged = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM video_queue WHERE status = 'published'")
            published = cursor.fetchone()[0]
            
            cursor.execute("""
                INSERT INTO system_snapshots (pending_count, staged_count, published_count)
                VALUES (?, ?, ?)
            """, (pending, staged, published))
            logging.info(f"📸 Snapshot Created: Pending: {pending}, Staged: {staged}, Published: {published}")
    except Exception as e:
        logging.error(f"Snapshot failed: {e}")

def sync_db_to_csv():
    """Writes everything from our database back to the CSV for human backup."""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            query = "SELECT * FROM video_queue"
            df = pd.read_sql_query(query, conn)
            df.to_csv(CSV_NAME, index=False, quoting=csv.QUOTE_ALL, encoding='utf-8')
            logging.info(f"CSV Backup Updated: {CSV_NAME}")
    except Exception as e:
        logging.error(f"Could not update CSV: {e}")

def get_human_input(file_name):
    """Triggers manual input for new video files detected in the folder."""
    print(f"\n--- NEW VIDEO DETECTED: {file_name} ---")
    title = input("What should the YouTube Title be? ").strip()
    if not title:
        return None, None
        
    print("Paste Description (Type 'SAVE' on a new line when done):")
    desc_lines = []
    while True:
        line = input()
        if line.strip().upper() == 'SAVE': break
        desc_lines.append(line)
    description = "\n".join(desc_lines)
    return title, description

def run_setup():
    if not os.path.exists(VIDEO_FOLDER): os.makedirs(VIDEO_FOLDER)

    try:
        # 1. Load CSV Data
        csv_data = pd.DataFrame()
        if os.path.exists(CSV_NAME) and os.path.getsize(CSV_NAME) > 0:
            csv_data = pd.read_csv(CSV_NAME, encoding='utf-8', keep_default_na=False)
            logging.info(f"Found {len(csv_data)} records in CSV.")

        # 2. Database Schema
        with sqlite3.connect(DB_NAME) as connection:
            connection.execute('''
                CREATE TABLE IF NOT EXISTS video_queue (
                    video_file TEXT PRIMARY KEY,
                    title TEXT,
                    description TEXT,
                    status TEXT DEFAULT 'pending', 
                    drive_id TEXT DEFAULT '',
                    youtube_url TEXT DEFAULT '',
                    youtube_id TEXT DEFAULT '',
                    scheduled_at TEXT DEFAULT '',
                    published_at TEXT DEFAULT '',
                    views INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            connection.execute('''
                CREATE TABLE IF NOT EXISTS system_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    pending_count INTEGER,
                    staged_count INTEGER,
                    published_count INTEGER
                )
            ''')

            # 3. Import CSV records into DB (One-time or Update)
            if not csv_data.empty:
                for _, row in csv_data.iterrows():
                    v_file = str(row.get('video_file', ''))
                    if not v_file: continue
                    
                    connection.execute('''
                        INSERT INTO video_queue (
                            video_file, title, description, status, drive_id, youtube_url, 
                            youtube_id, scheduled_at, published_at, views, likes, comments
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(video_file) DO UPDATE SET
                            status = excluded.status WHERE video_queue.status IS NULL
                    ''', (
                        v_file, str(row.get('title', '')), str(row.get('description', '')),
                        str(row.get('status', 'pending')), str(row.get('drive_id', '')), 
                        str(row.get('youtube_url', '')), str(row.get('youtube_id', '')),
                        str(row.get('scheduled_at', '')), str(row.get('published_at', '')),
                        int(row.get('views', 0)), int(row.get('likes', 0)), int(row.get('comments', 0))
                    ))

            # 4. ENHANCED FOLDER SCAN (The Fix)
            valid_ext = ('.mp4', '.mov', '.mkv', '.avi')
            files_on_disk = [f for f in os.listdir(VIDEO_FOLDER) if f.lower().endswith(valid_ext)]
            
            for file_name in files_on_disk:
                cursor = connection.cursor()
                cursor.execute("SELECT status FROM video_queue WHERE video_file = ?", (file_name,))
                result = cursor.fetchone()

                if result is None:
                    # Case A: File is completely new to the system
                    title, description = get_human_input(file_name)
                    if title:
                        connection.execute('''
                            INSERT INTO video_queue (video_file, title, description, status)
                            VALUES (?, ?, ?, 'pending')
                        ''', (file_name, title, description))
                elif result[0] not in ['uploaded-to-drive', 'published']:
                    # Case B: File exists in DB but is not yet processed. Force to 'pending'.
                    connection.execute("UPDATE video_queue SET status = 'pending' WHERE video_file = ?", (file_name,))
            
            connection.commit()

        # 5. Finalize
        update_system_snapshot()
        sync_db_to_csv()
        logging.info("✅ Pipeline setup complete.")

    except Exception as error:
        logging.error(f"Setup failed: {error}")

if __name__ == "__main__":
    run_setup()