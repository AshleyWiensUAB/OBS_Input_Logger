import cv2
import pandas as pd

# Provide input base with no file extension
input_base = r"F:\Ashley Wiens Data\Steam_Recordings\Counter-Strike 2\Counter-Strike 2_Spanish_AW"
frames_to_remove = 386
fps = 30

def remove_exact_frames_no_audio(input_stub, frames_to_remove):

    input_file = input_stub + ".mp4"
    output_file = input_stub + "_cleaned.mp4"

    # Open the video
    cap = cv2.VideoCapture(input_file)
    
    # Get video properties to set up the output writer
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Set up the video writer (mp4v is standard for MP4)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_file, fourcc, fps, (width, height))
    
    # 1. Skip the requested number of frames
    for _ in range(frames_to_remove):
        success, _ = cap.read()
        if not success:
            print("Video has fewer frames than the amount requested to remove.")
            return


    

# 2. Read and write the remaining frames
    frames_processed = 0
    
    while True:
        success, frame = cap.read()
        if not success:
            print(f"\nFinished! Processed {frames_processed} frames.")
            break # End of video
            
        out.write(frame)
        frames_processed += 1
        
        # Print an update every 500 frames so it doesn't look frozen
        if frames_processed % 500 == 0:
            print(f"Processed {frames_processed} frames so far...", end='\r')


    # Clean up
    cap.release()
    out.release()

def remove_frames_from_csv(input_stub, frames_to_remove, fps):
    input_csv = input_stub + ".csv"
    output_csv = input_stub +"_cleaned.csv"
    time_to_remove = frames_to_remove / fps

    try:
        df = pd.read_csv(input_csv)
        df['Timestamp (s)'] = df['Timestamp (s)'] - time_to_remove
        df['Frame'] = df['Frame'] - frames_to_remove

        cleaned_df = df[(df['Frame'] > 0.0) & (df['Timestamp (s)'] > 0.0)]


        cleaned_df.to_csv(output_csv, index=False)
        


    except Exception as e:
        print(f"Error processing {input_csv}: {e}")



# Example usage: Remove the first 30 frames
remove_exact_frames_no_audio(input_base, frames_to_remove)
remove_frames_from_csv(input_base, frames_to_remove, fps)
