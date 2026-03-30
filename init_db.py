import sqlite3
import pandas as pd
import os
import logging

# Basic settings
DB_NAME = "youtube_master.db"
CSV_NAME = "metadata.csv"
VIDEO_FOLDER = "videos"

# Professional logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def sync_db_to_csv():
    """Exports the database state back to the CSV file to keep them in mirror."""
    try:
        with sqlite3.connect(DB_NAME) as connection:
            # Export all columns to keep CSV and DB identical
            data = pd.read_sql_query("SELECT * FROM video_queue", connection)
            data.to_csv(CSV_NAME, index=False)
            logging.info(f"CSV synchronized: {CSV_NAME}")
    except Exception as error:
        logging.error(f"Synchronization failed: {error}")

def run_setup():
    """Initializes the database and imports/updates CSV data with status detection."""
    schema = '''
        CREATE TABLE IF NOT EXISTS video_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_file TEXT UNIQUE,
            title TEXT,
            description TEXT,
            status TEXT DEFAULT 'pending', 
            youtube_url TEXT,
            created_at TEXT
        )
    '''
    try:
        # 1. Ensure DB Schema exists
        with sqlite3.connect(DB_NAME) as connection:
            connection.execute(schema)
            logging.info("Database schema is ready.")

        # 2. Process CSV data
        if os.path.exists(CSV_NAME) and os.path.getsize(CSV_NAME) > 0:
            # Using utf-8 to handle f-string syntax and emojis in your descriptions
            csv_data = pd.read_csv(CSV_NAME, encoding='utf-8')
            
            needed = ['video_file', 'title', 'description', 'status', 'youtube_url', 'created_at']
            # fillna('') is crucial: it prevents "nan" from being written to your YouTube metadata
            clean_data = csv_data[[c for c in csv_data.columns if c in needed]].copy().fillna('')

            # --- AUTO-STATUS LOGIC ---
            found_count = 0
            for index, row in clean_data.iterrows():
                file_name = str(row['video_file']).strip()
                file_path = os.path.join(VIDEO_FOLDER, file_name)
                
                # Check if the .mp4 actually exists in your /videos folder
                if os.path.exists(file_path):
                    clean_data.at[index, 'status'] = 'pending'
                    found_count += 1
                else:
                    # Keep as 'none' if no physical file exists and it's not already staged
                    curr_status = str(row['status']).lower()
                    if curr_status in ['nan', '', 'none']:
                        clean_data.at[index, 'status'] = 'none'

            logging.info(f"Scan complete: Found {found_count} physical files in /{VIDEO_FOLDER}")

            # --- UPSERT LOGIC (The Fix for truncated/missing text) ---
            with sqlite3.connect(DB_NAME) as connection:
                for _, row in clean_data.iterrows():
                    # The 'ON CONFLICT' block is the key: it forces an update of title/desc
                    sql = '''
                        INSERT INTO video_queue (video_file, title, description, status, youtube_url, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(video_file) DO UPDATE SET
                            title = excluded.title,
                            description = excluded.description,
                            status = excluded.status,
                            youtube_url = excluded.youtube_url,
                            created_at = excluded.created_at
                    '''
                    connection.execute(sql, (
                        str(row['video_file']),
                        str(row['title']),
                        str(row['description']),
                        str(row['status']),
                        str(row['youtube_url']),
                        str(row['created_at'])
                    ))
                logging.info("Database synchronized: Titles and Descriptions updated from CSV.")

        # 3. Final sync back to CSV
        sync_db_to_csv()
        logging.info("System setup and status scan complete.")

    except Exception as error:
        logging.error(f"Setup failed: {error}")

if __name__ == "__main__":
    run_setup()