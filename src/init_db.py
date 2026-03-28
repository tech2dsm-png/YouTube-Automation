import sqlite3
import pandas as pd
import os
import logging
import csv
from datetime import datetime

# Settings
DB_NAME = "youtube_master.db"
CSV_NAME = "metadata.csv"
VIDEO_FOLDER = "videos"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def sync_db_to_csv():
    """Updates the metadata.csv to match the database. 
    This function is called by watcher.py and feeder.py."""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            # Explicitly select columns to maintain CSV structure
            query = """
                SELECT id, video_file, title, description, status, drive_id, youtube_url, created_at 
                FROM video_queue
            """
            df = pd.read_sql_query(query, conn)
            df.to_csv(CSV_NAME, index=False, quoting=csv.QUOTE_ALL, encoding='utf-8')
            logging.info(f"✅ CSV synchronized: {CSV_NAME}")
    except Exception as e:
        logging.error(f"Failed to sync CSV: {e}")

def get_human_input(file_name):
    """Asks for Title and Description if a video is found in folder but not in CSV."""
    print(f"\n--- NEW VIDEO FOUND ON DISK: {file_name} ---")
    print("This file is not in your metadata.csv. Please provide details:")
    
    title = input("Enter Video Title: ").strip()
    if not title:
        logging.warning(f"Skipping {file_name} because no title was provided.")
        return None, None
        
    print("Enter Description (Paste text + hashtags. Type 'SAVE' on a new line to finish):")
    desc_lines = []
    while True:
        line = input()
        if line.strip().upper() == 'SAVE':
            break
        desc_lines.append(line)
    description = "\n".join(desc_lines)
    
    return title, description

def run_setup():
    """Main setup logic to sync folder, CSV, and Database."""
    if not os.path.exists(VIDEO_FOLDER):
        os.makedirs(VIDEO_FOLDER)

    try:
        # 1. Load your master CSV data safely
        if os.path.exists(CSV_NAME) and os.path.getsize(CSV_NAME) > 0:
            csv_data = pd.read_csv(CSV_NAME, encoding='utf-8', keep_default_na=False)
            logging.info(f"Loaded {len(csv_data)} existing rows from {CSV_NAME}.")
        else:
            columns = ['id', 'video_file', 'title', 'description', 'status', 'drive_id', 'youtube_url', 'created_at']
            csv_data = pd.DataFrame(columns=columns)
            logging.info("Created a fresh metadata structure.")

        # 2. Database Table Creation & CSV Import
        with sqlite3.connect(DB_NAME) as connection:
            connection.execute('''
                CREATE TABLE IF NOT EXISTS video_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_file TEXT UNIQUE,
                    title TEXT,
                    description TEXT,
                    status TEXT DEFAULT '', 
                    drive_id TEXT DEFAULT '',
                    youtube_url TEXT DEFAULT '',
                    created_at TEXT DEFAULT ''
                )
            ''')
            
            for _, row in csv_data.iterrows():
                v_file = str(row.get('video_file', ''))
                if not v_file: continue

                connection.execute('''
                    INSERT INTO video_queue (video_file, title, description, status, drive_id, youtube_url, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(video_file) DO UPDATE SET
                        title = excluded.title,
                        description = excluded.description
                ''', (v_file, str(row.get('title', '')), str(row.get('description', '')),
                      str(row.get('status', '')), str(row.get('drive_id', '')), 
                      str(row.get('youtube_url', '')), str(row.get('created_at', ''))))
            
            connection.commit()

            # 3. MATCHING LOGIC: Check Folder vs Database
            valid_extensions = ('.mp4', '.mov', '.mkv', '.avi')
            files_on_disk = [f for f in os.listdir(VIDEO_FOLDER) if f.lower().endswith(valid_extensions)]
            
            known_query = pd.read_sql_query("SELECT video_file FROM video_queue", connection)
            known_files = known_query['video_file'].tolist()

            for file_name in files_on_disk:
                timestamp = datetime.now().strftime("%d-%m-%Y %H:%M")
                
                if file_name not in known_files:
                    title, description = get_human_input(file_name)
                    if title:
                        connection.execute('''
                            INSERT INTO video_queue (video_file, title, description, status, created_at)
                            VALUES (?, ?, ?, 'pending', ?)
                        ''', (file_name, title, description, timestamp))
                
                else:
                    connection.execute('''
                        UPDATE video_queue 
                        SET status = 'pending', 
                            created_at = CASE WHEN (created_at = '' OR created_at IS NULL) THEN ? ELSE created_at END
                        WHERE video_file = ? AND (status = '' OR status IS NULL)
                    ''', (timestamp, file_name))
            
            connection.commit()

        # 4. Final step: Save everything back to CSV
        sync_db_to_csv()
        logging.info("Process complete.")

    except Exception as error:
        logging.error(f"Setup failed: {error}")

if __name__ == "__main__":
    run_setup()