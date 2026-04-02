import os
import time
import logging
import sqlite3
import sys
import tkinter as tk
from tkinter import simpledialog
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

# Path Fix
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import init_db
    import cloud_sync_init
except ImportError:
    from src import init_db
    from src import cloud_sync_init

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCH_DIR = os.path.join(BASE_DIR, "videos")
DB_PATH = os.path.join(BASE_DIR, "youtube_master.db")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [WATCHER] - %(message)s')

def get_topmost_metadata(file_name):
    """Forcefully brings the metadata entry popup to the front of all Windows apps."""
    root = tk.Tk()
    root.withdraw()
    
    # Force to front
    root.attributes('-topmost', True)
    root.update()
    root.deiconify()
    root.lift()
    root.focus_force()

    title = simpledialog.askstring(
        "YouTube Metadata Entry", 
        f"New Video Detected: {file_name}\n\nEnter Title:", 
        parent=root
    )
    
    if not title:
        root.destroy()
        return None, None
        
    description = simpledialog.askstring(
        "YouTube Metadata Entry", 
        "Enter Description:", 
        parent=root
    )
    
    root.destroy()
    return title, description

class VideoHandler(FileSystemEventHandler):
    def process_video(self, file_path):
        if file_path.lower().endswith(('.mp4', '.mov', '.mkv')):
            file_name = os.path.basename(file_path)
            logging.info(f"✨ Processing video: {file_name}")
            
            # Increased delay to ensure Windows releases the file handle
            time.sleep(3)

            title, description = get_topmost_metadata(file_name)
            
            if title:
                try:
                    with sqlite3.connect(DB_PATH) as conn:
                        conn.execute("""
                            INSERT INTO video_queue (video_file, title, description, status)
                            VALUES (?, ?, ?, 'pending')
                            ON CONFLICT(video_file) DO UPDATE SET
                                title = excluded.title,
                                description = excluded.description,
                                status = 'pending'
                        """, (file_name, title, description))
                    
                    init_db.sync_db_to_csv()
                    init_db.update_system_snapshot()
                    cloud_sync_init.run_sync()
                    logging.info(f"🚀 Success: {file_name} is synced.")
                except Exception as e:
                    logging.error(f"❌ Sync Error: {e}")
            else:
                logging.warning(f"⚠️ Skipped: {file_name}")

    def on_created(self, event):
        if not event.is_directory:
            self.process_video(event.src_path)

    def on_moved(self, event):
        # Handles cases where files are moved into the folder
        if not event.is_directory:
            self.process_video(event.dest_path)

def start_watcher():
    if not os.path.exists(WATCH_DIR):
        os.makedirs(WATCH_DIR)
        
    event_handler = VideoHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_DIR, recursive=False)
    
    logging.info(f"📡 Monitoring: {WATCH_DIR}")
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    start_watcher()