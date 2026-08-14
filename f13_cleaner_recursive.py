import pandas as pd
from pathlib import Path

def clean_all_csvs_in_directory(root_directory, dump_directory = None):
    """
    Recursively finds all CSVs in the given directory, removes 'Key.f13' 
    rows from them, and saves the cleaned versions with a prefix.
    """
    # Convert the string path to a Path object
    root_path = Path(root_directory)
    dump_path = Path(dump_directory)
    # Check if the directory exists

    if not dump_path.is_dir():
            dump_path.mkdir()
            print(f"The directory '{dump_path}' has been created.")
            

    if not root_path.is_dir():
        print(f"Error: The directory '{root_directory}' does not exist.")
        return

    # Tracking statistics
    files_processed = 0
    total_f13_removed = 0
    
    # .rglob("*.csv") finds all CSV files in the root folder AND all subfolders
    for filepath in root_path.rglob("*.csv"):
        # Optional: Skip files that have already been cleaned to avoid double processing
            
        try:
            # Read the CSV
            df = pd.read_csv(filepath)

            # Save the unmodified version for backup
            if dump_path:
                df.to_csv(dump_path / filepath.name, index=False)
            
            # Check if 'Details' column exists to avoid errors on unrelated CSVs
            if 'Details' not in df.columns:
                continue
                
            original_count = len(df)
            
            # Filter out F13 presses
            cleaned_df = df[df['Details'] != 'Key.f13']
            cleaned_count = len(cleaned_df)
            removed_count = original_count - cleaned_count
            
            # Only save a new file if we actually removed something (optional, but saves space)
            if removed_count > 0:
                output_filepath = filepath.parent / filepath.name
                
                cleaned_df.to_csv(output_filepath, index=False)
                
                total_f13_removed += removed_count
                files_processed += 1
                print(f"Cleaned '{filepath.name}' (-{removed_count} rows)")
                
        except Exception as e:
            print(f"Error processing {filepath.name}: {e}")

    # Final Summary
    print("-" * 30)
    print("🧹 BATCH CLEANING COMPLETE")
    print(f"Total files cleaned: {files_processed}")
    print(f"Total F13 rows removed: {total_f13_removed}")

# Replace this with the path to your main folder containing all the subfolders
# For Windows, use raw strings like r"C:\Users\Name\Documents\Logs"
target_directory = r"E:\Steam_Recordings"
backup_directory = r"E:\Steam_Recordings\Old_Input_Logs"

clean_all_csvs_in_directory(target_directory, backup_directory)