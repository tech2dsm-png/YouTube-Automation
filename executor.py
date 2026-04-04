import logging
import time
import sys
from datetime import datetime
from dotenv import load_dotenv

# 1. INITIALIZE ENVIRONMENT
load_dotenv()

# 2. CONFIGURE LOGGING
# We use a professional format to track the execution flow across all modules
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [EXECUTOR] - %(levelname)s - %(message)s'
)

# 3. IMPORT PIPELINE STAGES
try:
    from src import init_db
    from src import feeder
    from src import cloud_sync_init
except ImportError as e:
    logging.error(f"Module Discovery Failed: {e}")
    logging.info("Suggestion: Ensure 'src/__init__.py' exists and your terminal is in the project root.")
    sys.exit(1)

def run_pipeline():
    """
    The Master Entry Point. Executes the discovery, migration, 
    and analytics sync in a single atomic cycle.
    """
    start_time = datetime.now()
    logging.info("🚀 EXECUTOR: Starting Production Pipeline")

    try:
        # --- STAGE 1: LOCAL STATE SYNC ---
        # Scans CSV and Folder to mark videos as 'pending' in SQLite
        logging.info("--- STAGE 1: Refreshing Local Database ---")
        init_db.run_setup()
        
        # --- STAGE 2: ASSET MIGRATION ---
        # Uploads to Drive and moves physical files to 'uploaded-to-drive'
        logging.info("--- STAGE 2: Processing Video Queue ---")
        feeder.process_queue()

        # Cooldown to ensure SQLite file locks are released by the OS
        time.sleep(1)

        # --- STAGE 3: CLOUD MIRRORING ---
        # Pushes the finalized SQLite state to Google Sheets for Power BI
        logging.info("--- STAGE 3: Updating Cloud Dashboard ---")
        cloud_sync_init.migrate_all_to_cloud()

        # --- EXECUTION SUMMARY ---
        duration = datetime.now() - start_time
        logging.info(f"✅ PIPELINE SUCCESSFUL | Total Duration: {duration}")
        print("\n[COMPLETE] All systems are synced. Check your Google Sheet/Power BI for updates.")

    except Exception as error:
        logging.error(f"❌ CRITICAL FAILURE IN PIPELINE: {error}")
        print("\n[FAIL] Pipeline halted. Review the logs above for the specific error point.")

if __name__ == "__main__":
    run_pipeline()