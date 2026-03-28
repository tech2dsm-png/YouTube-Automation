import streamlit as st
import pandas as pd
import sqlite3
import os
import subprocess
from datetime import datetime
from feeder import run_feeder
from uploader import run_uploader

# Configuration
DB_NAME = "youtube_master.db"

# Page Layout
st.set_page_config(page_title="SankalanTech Operations", layout="wide")

def get_stats():
    """Retrieves high-level metrics with flexible status detection for Drive/Cloud."""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            df = pd.read_sql_query("SELECT status FROM video_queue", conn)
            # Normalize status: handle case sensitivity and hidden spaces
            df['status'] = df['status'].astype(str).str.strip().str.lower()
            
            return {
                "total": len(df),
                "pending": len(df[df['status'] == 'pending']),
                "cloud": len(df[df['status'].str.contains('cloud|drive', na=False)]),
                "published": len(df[df['status'] == 'published'])
            }
    except Exception:
        return {"total": 0, "pending": 0, "cloud": 0, "published": 0}

def get_full_data(order='ASC'):
    """Fetches all records for the main data table in specified order."""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            query = f"""
                SELECT id, video_file, title, description, status, youtube_url, created_at 
                FROM video_queue 
                ORDER BY id {order}
            """
            df = pd.read_sql_query(query, conn)
            return df
    except Exception as e:
        st.error(f"Database Query Error: {e}")
        return pd.DataFrame()

# --- HEADER & KPI SECTION ---
st.title("🚀 SankalanTech YouTube Automation")
st.markdown("Operational Control Interface for Content Distribution")

stats = get_stats()
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Total Library", stats['total'])
kpi2.metric("Pending Local", stats['pending'])
kpi3.metric("Staged (Drive/Cloud)", stats['cloud'])
kpi4.metric("Live on YouTube", stats['published'])

st.divider()

# --- CONTROL PANEL ---
col_left, col_right = st.columns([1, 3])

with col_left:
    st.subheader("Process Execution")
    
    # Updated width='stretch' for 2026 Streamlit standards
    if st.button("🔄 Sync CSV Metadata", width="stretch"):
        with st.spinner("Re-syncing Database from CSV..."):
            subprocess.run(["python", "init_db.py"])
            st.success("Metadata Synced!")
            st.rerun()

    if st.button("📤 Initialize Cloud/Drive Feed", width="stretch"):
        with st.spinner("Executing Local-to-Drive transfer..."):
            run_feeder()
            st.success("Feeder Cycle Complete")
            st.rerun()

    if st.button("🎥 Initialize YouTube Publish", width="stretch"):
        with st.spinner("Executing Publishing Cycle..."):
            run_uploader()
            st.success("Uploader Cycle Complete")
            st.rerun()

with col_right:
    st.subheader("Queue Management")
    sort_order = st.selectbox("Sort by ID", options=["Descending", "Ascending"])
    order = "DESC" if sort_order == "Descending" else "ASC"
    
    data = get_full_data(order=order)

    if not data.empty:
        # Updated width='stretch' for the dataframe
        st.dataframe(
            data,
            width="stretch",
            hide_index=True,
            column_config={
                "title": st.column_config.TextColumn("Video Title", width="large"),
                "description": st.column_config.TextColumn("YouTube Description", width="medium"),
                "youtube_url": st.column_config.LinkColumn("YouTube Link"),
                "status": st.column_config.TextColumn("Current Status"),
                "created_at": st.column_config.TextColumn("Date Added")
            }
        )
    else:
        st.info("Queue is empty. Place videos in the /videos folder and click 'Sync CSV Metadata'.")

# --- LOGS SECTION ---
st.divider()
if st.checkbox("Show System Logs"):
    log_path = os.path.join("logs", "executor.log")
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            st.code(f.read()[-3000:], language='text') 
    else:
        st.info("No log data available at logs/executor.log.")