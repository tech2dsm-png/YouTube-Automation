
import os
import shutil
import sqlite3
from init_db import sync_db_to_csv

def drip_feed_publish(count=2):
    conn = sqlite3.connect("youtube_master.db")
    cursor = conn.cursor()
    
    # Grab the next 2 videos from GC storage
    cursor.execute("SELECT video_file, title, description FROM video_queue WHERE status = 'GC storage' LIMIT ?", (count,))
    rows = cursor.fetchall()
    
    for file_name, title, desc in rows:
        print(f"🚀 Publishing to YouTube: {title}")
        
        # --- [Placeholder for YouTube API Upload Code] ---
        video_url = f"https://youtu.be/example_{file_name}" 
        
        # Update State
        cursor.execute("UPDATE video_queue SET status = 'published', youtube_url = ? WHERE video_file = ?", 
                       (video_url, file_name))
        
        # Physical Housekeeping
        local_path = os.path.join("videos", file_name)
        if os.path.exists(local_path):
            if not os.path.exists("uploaded"): os.makedirs("uploaded")
            shutil.move(local_path, os.path.join("uploaded", file_name))
            print(f"📦 {file_name} moved to 'uploaded' folder.")
            
    conn.commit()
    conn.close()
    sync_db_to_csv()

if __name__ == "__main__":
    drip_feed_publish()
