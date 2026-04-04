import sqlite3
import pandas as pd
import os
import logging
import csv
from datetime import datetime
from dotenv import load_dotenv

# This script handles pushing our final data to Google Sheets
import cloud_sync_init 

# Load environment settings
load_dotenv()

# --- Setup Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_NAME = os.path.join(BASE_DIR, os.getenv("DB_PATH", "youtube_master.db"))
CSV_NAME = os.path.join(BASE_DIR, os.getenv("METADATA_CSV", "metadata.csv"))
VIDEO_FOLDER = os.path.join(BASE_DIR, os.getenv("DIR_VIDEOS", "videos"))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SYSTEM-INIT] - %(message)s')

def run_setup():
    """
    Main pipeline: Syncs Video Folder -> CSV -> SQLite DB -> Snapshots -> Google Sheets.
    Uses standard SQL commands to ensure compatibility with all SQLite versions.
    """
    
    if not os.path.exists(VIDEO_FOLDER): 
        os.makedirs(VIDEO_FOLDER)
        logging.info(f"Created folder: {VIDEO_FOLDER}")

    try:
        # 1. Check if Metadata exists
        if not os.path.exists(CSV_NAME) or os.path.getsize(CSV_NAME) == 0:
            logging.warning("Metadata CSV is missing or empty. Nothing to sync.")
            return
        
        # 2. Load the CSV and Folder contents
        df_csv = pd.read_csv(CSV_NAME, encoding='utf-8', keep_default_na=False)
        files_on_disk = {f for f in os.listdir(VIDEO_FOLDER) if f.lower().endswith(('.mp4', '.mov', '.mkv'))}

        with sqlite3.connect(DB_NAME) as conn:
            # --- CREATE TABLES ---
            conn.execute('''
                CREATE TABLE IF NOT EXISTS video_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_file TEXT NOT NULL UNIQUE,
                    title TEXT, description TEXT, status TEXT DEFAULT '', 
                    drive_id TEXT DEFAULT '', youtube_url TEXT DEFAULT '', 
                    youtube_id TEXT DEFAULT '', scheduled_at DATETIME, 
                    published_at DATETIME, views INTEGER DEFAULT 0, 
                    likes INTEGER DEFAULT 0, comments INTEGER DEFAULT 0, 
                    created_at DATETIME
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS system_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    pending_count INTEGER, 
                    staged_count INTEGER, 
                    published_count INTEGER
                )
            ''')

            # 3. Load existing DB records to compare
            df_db = pd.read_sql_query("SELECT * FROM video_queue", conn)
            
            # --- SELECTIVE UPDATE LOGIC ---
            updates_to_make = []
            
            for _, csv_row in df_csv.iterrows():
                v_file = str(csv_row['video_file'])
                db_match = df_db[df_db['video_file'] == v_file]

                # Scenario A: Totally NEW video (Not in Database)
                if db_match.empty:
                    if v_file in files_on_disk:
                        csv_row['status'] = "pending"
                        v_path = os.path.join(VIDEO_FOLDER, v_file)
                        csv_row['created_at'] = datetime.fromtimestamp(os.stat(v_path).st_ctime).strftime('%Y-%m-%d %H:%M:%S')
                    updates_to_make.append(csv_row)
                    continue

                # Scenario B: Existing video (Check if update is needed)
                db_row = db_match.iloc[0]
                needs_update = False
                
                if v_file in files_on_disk and str(db_row['status']).strip() in ["", "0", "nan"]:
                    csv_row['status'] = "pending"
                    v_path = os.path.join(VIDEO_FOLDER, v_file)
                    csv_row['created_at'] = datetime.fromtimestamp(os.stat(v_path).st_ctime).strftime('%Y-%m-%d %H:%M:%S')
                    needs_update = True
                
                if str(csv_row['title']) != str(db_row['title']) or str(csv_row['description']) != str(db_row['description']):
                    needs_update = True

                if needs_update:
                    updates_to_make.append(csv_row)

            # --- APPLY DATABASE UPDATES (Standard SQL Fix) ---
            if updates_to_make:
                df_changes = pd.DataFrame(updates_to_make)
                df_changes.to_sql('staging_updates', conn, if_exists='replace', index=False)

                # Part 1: Update existing records that are still in "pending" or "empty" state
                conn.execute("""
                    UPDATE video_queue
                    SET title = (SELECT title FROM staging_updates WHERE staging_updates.video_file = video_queue.video_file),
                        description = (SELECT description FROM staging_updates WHERE staging_updates.video_file = video_queue.video_file),
                        status = (SELECT status FROM staging_updates WHERE staging_updates.video_file = video_queue.video_file),
                        created_at = (SELECT created_at FROM staging_updates WHERE staging_updates.video_file = video_queue.video_file)
                    WHERE video_file IN (SELECT video_file FROM staging_updates)
                    AND (status IN ('pending', '', '0') OR status IS NULL)
                """)

                # Part 2: Insert brand new records
                conn.execute("""
                    INSERT INTO video_queue (video_file, title, description, status, created_at)
                    SELECT video_file, title, description, status, created_at FROM staging_updates
                    WHERE video_file NOT IN (SELECT video_file FROM video_queue)
                """)

                logging.info(f"Successfully synced {len(updates_to_make)} records to the database.")
            else:
                logging.info("No changes detected. Skipping database writes.")

            # --- SNAPSHOT LOGIC ---
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) FILTER(WHERE status='pending'), 
                    COUNT(*) FILTER(WHERE status='uploaded-to-drive'), 
                    COUNT(*) FILTER(WHERE status='published') 
                FROM video_queue
            """)
            p_now, s_now, pub_now = cursor.fetchone()

            cursor.execute("SELECT pending_count, staged_count, published_count FROM system_snapshots ORDER BY id DESC LIMIT 1")
            last_snap = cursor.fetchone()

            if not last_snap or (p_now, s_now, pub_now) != last_snap:
                conn.execute("INSERT INTO system_snapshots (pending_count, staged_count, published_count) VALUES (?, ?, ?)", (p_now, s_now, pub_now))
                logging.info("📊 Snapshot saved: Video counts updated.")

            # Mirror DB state back to CSV
            df_final = pd.read_sql_query("SELECT * FROM video_queue ORDER BY id ASC", conn)
            df_final.to_csv(CSV_NAME, index=False, quoting=csv.QUOTE_ALL, encoding='utf-8')

        # 4. Cloud Sync
        logging.info("☁️ Mirroring data to Google Sheets...")
        cloud_sync_init.run_sync()

    except Exception as e:
        logging.error(f"Pipeline failed: {e}")

if __name__ == "__main__":
    run_setup()