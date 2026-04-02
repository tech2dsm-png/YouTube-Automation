import sqlite3

def final_migration():
    conn = sqlite3.connect('youtube_master.db')
    cursor = conn.cursor()
    
    try:
        # 1. Automatically find what columns you HAVE right now
        cursor.execute("PRAGMA table_info(video_queue)")
        existing_cols = [col[1] for col in cursor.fetchall()]
        
        if 'id' in existing_cols:
            print("✅ The 'id' column already exists. No migration needed!")
            return

        print(f"Found columns: {existing_cols}")
        
        # 2. Rename old table to backup
        cursor.execute("DROP TABLE IF EXISTS video_queue_old")
        cursor.execute("ALTER TABLE video_queue RENAME TO video_queue_old")

        # 3. Create new table with ID + your existing structure
        col_definitions = ", ".join([f'"{name}" TEXT' for name in existing_cols])
        cursor.execute(f"CREATE TABLE video_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, {col_definitions})")

        # 4. Move data safely
        col_names = ", ".join([f'"{name}"' for name in existing_cols])
        cursor.execute(f"INSERT INTO video_queue ({col_names}) SELECT {col_names} FROM video_queue_old")

        # 5. Drop the backup
        cursor.execute("DROP TABLE video_queue_old")
        
        conn.commit()
        print("✅ SUCCESS! Database migrated. 'id' column added.")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration Failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    final_migration()