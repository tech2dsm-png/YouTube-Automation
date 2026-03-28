YouTube Automation Pipeline
This project automates the process of uploading technical tutorials from a local environment to YouTube using Google Drive as a middle-man.

How it Works:
Step 1: Videos are processed locally and moved to an uploaded-to-drive state.

Step 2: Metadata is synced from a local SQLite database to Google Sheets.

Step 3: A GitHub Action runs on a schedule to download the video from Drive and post it to YouTube automatically.

Tech Stack:
Python (Google API, Pandas, SQLite)

GitHub Actions (Scheduling & Automation)

Google Cloud (Drive API, YouTube Data API v3, Sheets API)