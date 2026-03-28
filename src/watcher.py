import time
import os
import sqlite3
import logging
import tkinter as tk
from tkinter import simpledialog
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Import your sync function from your init_db script
from init_db import sync_db_to_csv

# Settings
WATCH_DIR = "videos"
DB_NAME = "youtube_master.db"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def get_missing_metadata(file_name):
    """Triggers a GUI popup to collect Title and Description."""
    root = tk.Tk()
    root.withdraw()
    # Forces the popup to appear on top of all other windows
    root.attributes("-topmost", True)
    
    title = simpledialog.askstring("New Video Detected", f"No data found for: {file_name}\n\nEnter Title:")
    description = simpledialog.askstring("New Video Detected", "Enter Description (Tags/Details):")
    
    root.destroy()
    return title, description

def wait_for_file_stability(file_path):
    """Ensures the file has finished copying before processing."""
    last_size = -1
    while True:
        try:
            current_size = os.path.getsize(file_path)
            if current_size == last_size:
                break
            last_size = current_size
            time.sleep(2) # Wait 2 seconds between checks
        except OSError:
            time.sleep(1)
            continue

class VideoHandler(FileSystemEventHandler):
    def on_created(self, event):
        # Ignore folders and non-mp4 files
        if event.is_directory or not event.src_path.lower().endswith(".mp4"):
            return
        
        file_path = event.src_path
        file_name = os.path.basename(file_path)
        
        logging.info(f"Detected: {file_name}. Waiting for copy to complete...")
        wait_for_file_stability(file_path)
        
        logging.info(f"Processing stable file: {file_name}")

        try:
            with sqlite3.connect(DB_NAME) as connection:
                cursor = connection.cursor()
                
                # 1. Check if the file name already exists in our database
                cursor.execute("SELECT status FROM video_queue WHERE video_file = ?", (file_name,))
                existing_record = cursor.fetchone()

                if existing_record:
                    # Case A: File is in your pre-defined list (e.g., your 150 videos)
                    # We just flip it to 'pending' so the feeder picks it up.
                    logging.info(f"Found record for {file_name}. Activating status to 'pending'...")
                    cursor.execute(
                        "UPDATE video_queue SET status = 'pending' WHERE video_file = ?", 
                        (file_name,)
                    )
                else:
                    # Case B: Totally new file - Ask for input via Popup
                    logging.info(f"No record found for {file_name}. Requesting metadata...")
                    u_title, u_desc = get_missing_metadata(file_name)
                    
                    # Handle Cancel/Close (None) or Empty inputs
                    if u_title is None or u_title.strip() == "": u_title = file_name
                    if u_desc is None or u_desc.strip() == "": u_desc = "Uploaded via Auto-Watcher"

                    query = "INSERT INTO video_queue (video_file, title, description, status) VALUES (?, ?, ?, ?)"
                    cursor.execute(query, (file_name, u_title, u_desc, "pending"))
                
                connection.commit()
            
            # 2. Sync the Database changes back to your metadata.csv
            sync_db_to_csv()
            logging.info(f"✅ Successfully synchronized: {file_name}")
            
        except Exception as error:
            logging.error(f"Error in watcher processing: {error}")

def start_watcher():
    if not os.path.exists(WATCH_DIR): 
        os.makedirs(WATCH_DIR)
        
    observer = Observer()
    event_handler = VideoHandler()
    observer.schedule(event_handler, WATCH_DIR, recursive=False)
    
    logging.info(f"🚀 Watcher Active. Monitoring: {WATCH_DIR}")
    observer.start()
    
    try:
        while True: 
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Stopping watcher...")
        observer.stop()
    observer.join()

if __name__ == "__main__":
    start_watcher()