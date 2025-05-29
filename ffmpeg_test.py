# This is for testing ffmpeg

import subprocess
import time
import os
import threading
import queue
import re # Import re for parsing duration and progress

# --- Configuration ---
INPUT_FILE = r"Z:\AAAAA01\t.wav"
OUTPUT_FILE = r"Z:\AAAAA01\t.mp3"
LOG_FILE_DIR = "ffmpeg_logs" # New variable for directory
LOG_FILE_NAME = "ffmpeg_test_log.txt" # New variable for filename
LOG_FILE_PATH = os.path.join(LOG_FILE_DIR, LOG_FILE_NAME) # Construct the full path
FFMPEG_EXE = "ffmpeg"  # Assuming ffmpeg is in PATH
FFPROBE_EXE = "ffprobe" # Assuming ffprobe is in PATH

# --- Helper Function to Get Media Duration ---
def get_media_duration(input_file, ffprobe_path, log_file_handle):
    """Gets the media duration in seconds using ffprobe."""
    command = [
        ffprobe_path,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_file
    ]
    try:
        log_message_cmd = f"[INFO] Getting duration with command: {' '.join(command)}"
        print(log_message_cmd)
        log_file_handle.write(log_message_cmd + "\n")

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        stdout, stderr = process.communicate(timeout=15) # 15 seconds timeout for ffprobe

        if process.returncode == 0 and stdout:
            duration_str = stdout.strip()
            if duration_str and duration_str.lower() != 'n/a':
                duration_seconds = float(duration_str)
                log_message_dur = f"[INFO] Detected duration: {duration_seconds:.2f} seconds"
                print(log_message_dur)
                log_file_handle.write(log_message_dur + "\n")
                return duration_seconds
            else:
                log_message_err = f"[ERROR] ffprobe returned empty or N/A duration: {duration_str}"
                print(log_message_err)
                log_file_handle.write(log_message_err + "\n")
                return None
        else:
            log_message_fail = f"[ERROR] ffprobe failed. Exit code: {process.returncode}. Stderr: {stderr.strip()}"
            print(log_message_fail)
            log_file_handle.write(log_message_fail + "\n")
            return None
    except subprocess.TimeoutExpired:
        log_message_timeout = "[ERROR] ffprobe command timed out."
        print(log_message_timeout)
        log_file_handle.write(log_message_timeout + "\n")
        return None
    except FileNotFoundError:
        log_message_fnf = f"[ERROR] {ffprobe_path} not found. Please ensure it is in PATH."
        print(log_message_fnf)
        log_file_handle.write(log_message_fnf + "\n")
        return None
    except Exception as e:
        log_message_exc = f"[ERROR] Exception in get_media_duration: {e}"
        print(log_message_exc)
        log_file_handle.write(log_message_exc + "\n")
        return None

# --- Helper Function to Read Stream ---
def stream_reader(pipe, q, stream_name, log_file_handle):
    """Reads lines from a pipe and puts them into a queue."""
    try:
        for line in iter(pipe.readline, ''):
            message = f"[{stream_name}] {line.strip()}"
            print(message)
            log_file_handle.write(message + "\n")
            q.put(message)
    except Exception as e:
        error_message = f"[{stream_name} ERROR] Error reading stream: {e}"
        print(error_message)
        log_file_handle.write(error_message + "\n")
        q.put(error_message)
    finally:
        pipe.close()

# --- Main Execution ---
def main():
    print(f"Starting FFmpeg conversion:")
    print(f"  Input: {INPUT_FILE}")
    print(f"  Output: {OUTPUT_FILE}")
    print(f"  Log File: {LOG_FILE_PATH}")

    if not os.path.exists(INPUT_FILE):
        print(f"ERROR: Input file not found: {INPUT_FILE}")
        return

    # Ensure output directory exists (it does in this case, Z:\AAAAA01)
    # output_dir = os.path.dirname(OUTPUT_FILE)
    # if not os.path.exists(output_dir):
    #     os.makedirs(output_dir, exist_ok=True)

    ffmpeg_command = [
        FFMPEG_EXE,
        "-i", INPUT_FILE,
        "-b:a", "256k",      # Audio bitrate
        "-vn",               # No video
        "-y",                # Overwrite output without asking
        "-progress", "pipe:1", # Send progress to stdout
        "-loglevel", "error",  # Send only errors to stderr (stats also go to stderr with -stats)
        "-stats",            # Print encoding stats periodically to stderr
        OUTPUT_FILE
    ]

    print(f"Executing command: {' '.join(ffmpeg_command)}")

    try:
        # Ensure log directory exists
        if not os.path.exists(LOG_FILE_DIR):
            os.makedirs(LOG_FILE_DIR, exist_ok=True)
            print(f"Created log directory: {LOG_FILE_DIR}")
            
        with open(LOG_FILE_PATH, 'w', encoding='utf-8') as log_file:
            log_file.write(f"--- FFmpeg Test Log ---\n")
            log_file.write(f"Input: {INPUT_FILE}\n")
            log_file.write(f"Output: {OUTPUT_FILE}\n")
            log_file.write(f"Command: {' '.join(ffmpeg_command)}\n")
            log_file.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            log_file.write("-" * 30 + "\n")
            log_file.flush() # Ensure header is written

            # Get media duration first
            total_duration_seconds = get_media_duration(INPUT_FILE, FFPROBE_EXE, log_file)
            total_duration_ms = None
            if total_duration_seconds is not None:
                total_duration_ms = total_duration_seconds * 1000
            else:
                print("[WARNING] Could not get media duration. Progress percentage will not be available.")
                log_file.write("[WARNING] Could not get media duration. Progress percentage will not be available.\n")

            process = subprocess.Popen(
                ffmpeg_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace', # Handle potential encoding errors
                bufsize=1,  # Line buffered
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            stdout_q = queue.Queue()
            stderr_q = queue.Queue()

            stdout_thread = threading.Thread(target=stream_reader, args=(process.stdout, stdout_q, "STDOUT", log_file))
            stderr_thread = threading.Thread(target=stream_reader, args=(process.stderr, stderr_q, "STDERR", log_file))

            stdout_thread.start()
            stderr_thread.start()
            
            progress_ended = False

            print("--- FFmpeg Output Start ---")
            log_file.write("--- FFmpeg Output Start ---\n")

            # Keep checking queues while threads are alive
            while stdout_thread.is_alive() or stderr_thread.is_alive() or not stdout_q.empty() or not stderr_q.empty():
                try:
                    # Check stdout queue
                    while not stdout_q.empty():
                        line = stdout_q.get_nowait()
                        if "progress=end" in line:
                            progress_ended = True
                        # Line is already printed and logged by stream_reader
                        
                        # Calculate and print progress if duration is known
                        if total_duration_ms and "out_time_ms=" in line:
                            try:
                                current_time_value_str = line.split("out_time_ms=")[1].split()[0]
                                # The value from out_time_ms seems to be in microseconds, convert to ms
                                current_time_ms = int(current_time_value_str) / 1000.0 
                                if total_duration_ms > 0:
                                    percentage = (current_time_ms / total_duration_ms) * 100
                                    progress_message = f"[PROGRESS] {percentage:.1f}%"
                                    print(progress_message)
                                    log_file.write(progress_message + "\n")
                            except (IndexError, ValueError) as e:
                                err_parse = f"[WARNING] Could not parse progress line: {line} - Error: {e}"
                                print(err_parse)
                                log_file.write(err_parse + "\n")

                    # Check stderr queue
                    while not stderr_q.empty():
                        line = stderr_q.get_nowait()
                        # Line is already printed and logged by stream_reader

                except queue.Empty:
                    pass # No new messages in queues
                
                # Check if process has terminated and threads are done reading
                if process.poll() is not None and not stdout_thread.is_alive() and not stderr_thread.is_alive():
                    break
                
                time.sleep(0.1) # Small delay to avoid busy-waiting


            # Wait for threads to finish (they should finish once pipes are closed by Popen)
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)

            # Final process cleanup and status
            process.wait(timeout=10) # Wait for the process to terminate completely
            
            print("--- FFmpeg Output End ---")
            log_file.write("--- FFmpeg Output End ---\n")

            if process.returncode == 0:
                success_msg = f"FFmpeg process completed successfully. Exit code: {process.returncode}"
                print(success_msg)
                log_file.write(success_msg + "\n")
                if not progress_ended:
                    warn_msg = "Warning: 'progress=end' not detected in stdout, but process exited successfully."
                    print(warn_msg)
                    log_file.write(warn_msg + "\n")
                # Ensure final progress is 100% if successful and duration was known
                elif total_duration_ms and progress_ended:
                    final_progress_message = "[PROGRESS] 100.0% (Completed)"
                    print(final_progress_message)
                    log_file.write(final_progress_message + "\n")
            else:
                error_msg = f"FFmpeg process failed. Exit code: {process.returncode}"
                print(error_msg)
                log_file.write(error_msg + "\n")

            log_file.write(f"--- Log End ---\n")

    except FileNotFoundError:
        error_msg = f"ERROR: {FFMPEG_EXE} not found. Please ensure it's in your system PATH."
        print(error_msg)
        # Also try to write to log if possible, though file might not be open yet
        try:
            with open(LOG_FILE_PATH, 'a', encoding='utf-8') as log_f_err:
                log_f_err.write(error_msg + "\n")
        except:
            pass
    except Exception as e:
        error_msg = f"An unexpected error occurred: {e}"
        print(error_msg)
        try:
            with open(LOG_FILE_PATH, 'a', encoding='utf-8') as log_f_err:
                log_f_err.write(error_msg + "\n")
        except:
            pass

if __name__ == "__main__":
    main()
