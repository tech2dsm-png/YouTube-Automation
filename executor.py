import os
import shutil
import sqlite3
from init_db import run_setup, sync_db_to_csv

def drip_feed_publish(count=2):
    """
    Identifies videos marked as 'uploaded-to-drive' and moves them 
    through the publication pipeline.
    """
    # Connect to the local SQLite instance
    conn = sqlite3.connect("youtube_master.db")
    cursor = conn.cursor()
    
    # Select candidate videos based on the specific Drive status
    cursor.execute("""
        SELECT video_file, title, description 
        FROM video_queue 
        WHERE status = 'uploaded-to-drive' 
        LIMIT ?
    """, (count,))
    
    rows = cursor.fetchall()
    
    if not rows:
        print("Notification: No records identified with 'uploaded-to-drive' status.")
        return

    for file_name, title, desc in rows:
        print(f"Initiating publication for: {title}")
        
        # --- [Placeholder for YouTube Data API Integration] ---
        # This section will be replaced by the authenticated upload logic.
        video_url = f"https://youtu.be/example_{file_name}" 
        
        # Transition status to 'published' and archive the generated URL
        cursor.execute("""
            UPDATE video_queue 
            SET status = 'published', youtube_url = ? 
            WHERE video_file = ?
        """, (video_url, file_name))
        
        # Workspace management: Relocate processed local files if present
        local_path = os.path.join("videos", file_name)
        if os.path.exists(local_path):
            if not os.path.exists("uploaded"): 
                os.makedirs("uploaded")
            shutil.move(local_path, os.path.join("uploaded", file_name))
            print(f"File {file_name} archived to the 'uploaded' directory.")
        else:
            print(f"Note: {file_name} is not present in the local workspace; proceeding with cloud-only metadata.")
            
    conn.commit()
    conn.close()
    
    # Re-synchronize the database state with the master CSV file
    sync_db_to_csv()
    print("Database and CSV synchronization finalized.")

if __name__ == "__main__":
    # Ensure the database schema is provisioned from the CSV source 
    # to prevent 'no such table' exceptions in transient environments.
    print("Synchronizing project state...")
    run_setup()
    
    # Execute the core publishing logic
    drip_feed_publish()