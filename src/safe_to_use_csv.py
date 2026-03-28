import pandas as pd

def test_csv_integrity(file_path):
    try:
        # 1. Test if the file is readable
        df = pd.read_csv("metadata.csv")
        
        # 2. Check for missing values in critical columns
        critical_cols = ['id', 'video_file', 'title', 'description']
        missing = df[critical_cols].isnull().sum()
        
        # 3. Check for duplicate IDs or filenames
        dup_ids = df['id'].duplicated().sum()
        dup_files = df['video_file'].duplicated().sum()
        
        print(" CSV Structure is valid.")
        print(f" Total Rows: {len(df)}")
        print(f" Missing Data:\n{missing}")
        print(f" Duplicates: {dup_ids} IDs, {dup_files} Files")
        
        if missing.sum() == 0 and dup_ids == 0:
            print("\n Status: SAFE TO USE")
        
    except Exception as e:
        print(f" ERROR: CSV is corrupted or formatted incorrectly.\nDetails: {e}")

test_csv_integrity('metadata.csv')