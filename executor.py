import logging
import time
import sys
import os
from datetime import datetime

# 1. CONFIGURE LOGGING
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [MASTER-EXECUTOR] - %(message)s'
)

# 2. IMPORT CORE LOGIC FROM SRC FOLDER
try:
    from src import init_db
    from src import feeder
    from src import cloud_sync_init
except ImportError as e:
    logging.error(f"CRITICAL ERROR: Could not find scripts in the 'src' folder. {e}")
    logging.info("Make sure 'src' contains an empty file named __init__.py")
    sys.exit(1)

def run_complete_pipeline():
    """
    Orchestrates the 3-step automation pipeline from the src package.
    """
    start_time = datetime.now()
    logging.info("🚀 STARTING COMPLETE AUTOMATION PIPELINE")

    try:
        # --- STEP 1: DATABASE & FOLDER INTEGRITY ---
        logging.info("--- STEP 1: Initializing Database (src/init_db.py) ---")
        init_db.run_setup()
        
        # --- STEP 2: DRIVE UPLOADS ---
        logging.info("--- STEP 2: Running Drive Feeder (src/feeder.py) ---")
        feeder.run_feeder()

        # --- STEP 3: ANALYTICS SYNC ---
        logging.info("--- STEP 3: Syncing to Google Sheets (src/cloud_sync_init.py) ---")
        cloud_sync_init.run_sync()

        # --- FINAL SUMMARY ---
        end_time = datetime.now()
        duration = end_time - start_time
        
        logging.info("✅ PIPELINE EXECUTION FINISHED SUCCESSFULLY")
        logging.info(f"Total Time Taken: {duration}")
        print("\nYour Power BI Dashboard is now updated with the latest data.")

    except Exception as error:
        logging.error(f"❌ PIPELINE FAILED: {error}")
        print("\nCheck the logs above to see which step caused the issue.")

if __name__ == "__main__":
    run_complete_pipeline()