"""
Worker class for processing downloads using the yt-dlp CLI.
"""
import os
import time
import re
import subprocess
import json
import shlex
import sys
import tempfile
import platform
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from qt_base_app.models.logger import Logger
import threading
import psutil

# --- Define Subtitle Extensions --- 
# Used to filter out subtitle files when determining the final media file
# in the fallback logic if the Merger step doesn't specify it.
SUBTITLE_EXTENSIONS = {
    ".vtt", ".srt", ".ass", ".ssa", ".sub", ".ttml", ".srv1", ".srv2", ".srv3", ".json3"
}
# -------------------------------

class CLIDownloadWorker(QObject):
    """Worker object for processing a single download using the yt-dlp CLI.
    Designed to be moved to a separate QThread.
    """
    
    # Define signals (same as the PythonDownloadWorker for API compatibility)
    progress_signal = pyqtSignal(str, float, str)  # url, progress percent, status text
    complete_signal = pyqtSignal(str, str, str)    # url, output_dir, filename
    error_signal = pyqtSignal(str, str)            # url, error message
    log_signal = pyqtSignal(str)                   # log message
    processing_signal = pyqtSignal(str, str)       # url, status message
    # Add finished signal
    finished = pyqtSignal()                        # Emitted when processing is done (success or fail)
    
    def __init__(self, url, format_options, output_dir, parent=None):
        """
        Initialize the download worker.
        
        Args:
            url (str): The URL to download from
            format_options (dict): Options dictionary for yt-dlp (format, cookies, etc.)
            output_dir (str): Directory where downloaded files will be saved
            parent (QObject, optional): Parent QObject for proper memory management
        """
        super().__init__(parent)
        self.url = url
        self.format_options = format_options
        self.output_dir = output_dir
        self.cancelled = False
        self.logger = Logger.instance()
        self.downloaded_filename = None  # Final intended filename (set by Merger or later logic)
        self.temporary_filenames = [] # List to store potential temp/stream filenames
        self.process = None
        self._process_lock = threading.Lock() # Add lock for thread safety
    
    @pyqtSlot() # Make run a slot
    def run(self):
        """Public slot to start the download process. Calls the internal method."""
        self._execute_download()
    
    def _execute_download(self):
        """Main download logic."""
        try:
            self.log_signal.emit(f"Starting CLI download for: {self.url}")
            
            # Signal that processing is starting
            self.processing_signal.emit(self.url, "Processing started...")
            
            # Build the yt-dlp command
            cmd = self._build_ytdlp_command()
            
            # Log the command (with sensitive info like cookies redacted)
            safe_cmd = self._get_safe_command_string(cmd)
            self.log_signal.emit(f"Executing yt-dlp command (see debug terminal for details)")
            # Print the command to debug terminal rather than GUI log
            print(f"DEBUG: Executing command: {safe_cmd}")
            
            # Create a temporary file for progress output
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.json') as progress_file:
                progress_file_path = progress_file.name
            
            # Set up process with hidden window on Windows
            popen_kwargs = {
                'stdout': subprocess.PIPE,
                'stderr': subprocess.PIPE,
                'text': True,
                'bufsize': 1,  # Line buffered
                'universal_newlines': True
            }
            
            # Add CREATE_NO_WINDOW flag on Windows to hide the console window
            if platform.system() == 'Windows':
                popen_kwargs['creationflags'] = 0x08000000  # CREATE_NO_WINDOW
            
            # Use lock when setting self.process
            with self._process_lock:
                self.process = subprocess.Popen(cmd, **popen_kwargs)
            
            # Initialize variables to track progress
            current_percentage = 0
            downloading_started = False
            
            # Process output in real-time - avoid accessing self.process directly in case it's set to None
            # Keep a local reference to the process that we just created for safety
            local_process = self.process  
            
            # Safety check before entering loop
            if local_process is None or self.cancelled:
                self.log_signal.emit("Process terminated before output processing started")
                # Ensure finished signal is emitted even if we exit early
                # The finally block will handle this.
                return

            # Main output processing loop
            try:
                for line in iter(local_process.stdout.readline, ''):
                    # Check for cancellation
                    if self.cancelled:
                        self.log_signal.emit(f"Cancellation detected for {self.url}, stopping output processing.")
                        break # ---> EXIT LOOP DUE TO CANCELLATION
                    
                    # Filter progress lines from debug terminal output
                    is_progress_line = False
                    # Filter out video/audio download progress lines
                    if '[download]' in line and '%' in line and any(x in line for x in ['MiB at', 'KiB at', 'B/s']):
                        is_progress_line = True
                    # Filter out subtitle download progress lines
                    elif '[download]' in line and any(x in line for x in ['KiB at', 'MiB at', 'B/s']) and line.strip().startswith('[download]'):
                        is_progress_line = True
                    # Filter intermediate progress like '1.00KiB at 57.75KiB/s'
                    elif line.strip().startswith('[download]') and any(x in line for x in ['KiB at', 'MiB at', 'B/s']):
                        is_progress_line = True
                    
                    # Only print non-progress lines to debug terminal
                    if not is_progress_line:
                        print(line.strip())
                    
                        # Try to parse progress information, destination, or merger info
                    if '[download]' in line:
                        # Check if the download has started and capture destination filename
                        if 'Destination:' in line:
                            downloading_started = True
                            output_file = line.split('Destination: ')[1].strip()
                            self.log_signal.emit(f"Downloading to: {output_file}")
                            # Store ALL potential temporary filenames reported
                            basename = os.path.basename(output_file)
                            if basename not in self.temporary_filenames:
                                self.temporary_filenames.append(basename)
                                print(f"DEBUG: Added temporary filename candidate: {basename}") # Log all candidates
                            
                            # Parse download progress (if download has started)
                        elif downloading_started and '%' in line:
                            # Extract percentage
                            match = re.search(r'(\d+\.\d+)%', line)
                            if match:
                                try:
                                    percentage = float(match.group(1))
                                    current_percentage = percentage
                                    
                                    # Extract speed and ETA
                                    speed_match = re.search(r'at\s+([^\s]+)', line)
                                    eta_match = re.search(r'ETA\s+([^\s]+)', line)
                                    
                                    speed = speed_match.group(1) if speed_match else "unknown"
                                    eta = eta_match.group(1) if eta_match else "unknown"
                                    
                                    status_text = f"Downloading: {percentage:.1f}% at {speed}, ETA: {eta}"
                                    
                                    # Emit progress update
                                    self.progress_signal.emit(self.url, percentage, status_text)
                                except Exception as e:
                                    print(f"DEBUG: Error parsing progress: {str(e)}")
                    
                        # Check for MERGER message and update filename if found
                        elif line.strip().startswith('[Merger]') and 'Merging formats into' in line:
                            match = re.search(r'Merging formats into "(.*?)"', line)
                            if match:
                                merged_filepath = match.group(1)
                                # This is the FINAL filename
                                self.downloaded_filename = os.path.basename(merged_filepath)
                                self.log_signal.emit(f"Detected final merged file: {self.downloaded_filename}")
                                print(f"DEBUG: Captured final merged filename: {self.downloaded_filename}")
                    
                    # Check for errors in real-time
                        elif 'ERROR:' in line:
                            error_msg = line.strip()
                            # Log error but continue processing output
                            self.log_signal.emit(f"Error detected during download: {error_msg}")

            except Exception as e:
                # Handle exceptions DURING the output processing loop
                self.log_signal.emit(f"Error processing stdout/stderr: {str(e)}")
                if not self.cancelled:  # Only emit error if not cancelled
                    self.error_signal.emit(self.url, f"Error processing output: {str(e)}")
                # Ensure finished is emitted via finally block
                return 
            
            # --- Code AFTER loop finishes (normally or via break) --- 
            
            # ---> Handle Cancellation Scenario FIRST <--- 
            if self.cancelled:
                self.log_signal.emit(f"Download process interrupted by cancellation for {self.url}.")
                
                # --- Deterministic Shutdown Sequence --- 
                if local_process:
                    pid_to_check = local_process.pid # Get PID before it potentially dies
                    self.log_signal.emit(f"Starting deterministic shutdown for PID: {pid_to_check or 'N/A'}")
                    
                    # 1. Send SIGTERM/SIGKILL and wait for main process
                    self.log_signal.emit("Terminating main process...")
                    local_process.terminate()
                    try:
                        local_process.wait(timeout=5)
                        self.log_signal.emit("Main process terminated gracefully.")
                    except subprocess.TimeoutExpired:
                        self.log_signal.emit("Main process kill after timeout...")
                        try:
                            local_process.kill()
                            local_process.wait(timeout=2) # Wait after kill
                            self.log_signal.emit("Main process killed.")
                        except Exception as e_kill:
                            self.log_signal.emit(f"Error during kill/wait: {e_kill}")
                    except Exception as e_term:
                        self.log_signal.emit(f"Error during terminate/wait: {e_term}")
                       
                    # 2. Close our pipe handles
                    self.log_signal.emit("Closing process pipes...")
                    for pipe in (local_process.stdout, local_process.stderr):
                        try:
                            if pipe and not pipe.closed:
                                pipe.close()
                        except Exception as e_pipe:
                            self.log_signal.emit(f"Ignoring error closing pipe: {e_pipe}")
                            pass # Ignore errors closing pipes

                    # 3. Reap children (ffmpeg etc.) using psutil
                    if pid_to_check: # Still need to check if we have a valid PID
                        self.log_signal.emit("Attempting to reap child processes...")
                        try:
                            parent = psutil.Process(pid_to_check) 
                            children = parent.children(recursive=True)
                            if children:
                                self.log_signal.emit(f"Killing {len(children)} child process(es)...")
                                for child in children:
                                    try:
                                        self.log_signal.emit(f"Killing child PID: {child.pid}")
                                        child.kill()
                                        child.wait(timeout=2)
                                    except psutil.NoSuchProcess:
                                        pass # Child already gone
                                    except Exception as e_child:
                                        self.log_signal.emit(f"Ignoring error killing child {child.pid}: {e_child}")
                            else:
                                self.log_signal.emit("No child processes found.")
                        except psutil.NoSuchProcess:
                            self.log_signal.emit(f"Main process {pid_to_check} not found for child reaping.")
                        except Exception as e_psutil:
                            self.log_signal.emit(f"Error during psutil child reaping: {e_psutil}")
                    else: 
                         self.log_signal.emit("Invalid PID, skipping child process kill.")

                else: # if not local_process
                    self.log_signal.emit("No active process found for shutdown sequence.")
                # --- End Shutdown Sequence ---
                
                # 4. Give the kernel a moment
                self.log_signal.emit("Waiting for OS file handle release...")
                time.sleep(1.0)
                    
                # --- Run Cleanup (AFTER termination is complete) --- 
                self.log_signal.emit("Proceeding with file cleanup...")
                self._cleanup_temporary_files() 
                
                # Proceed directly to finally block to emit finished signal
                # No return needed, just fall through to finally

            else:
                # ---> Handle Normal Completion or Error AFTER process finished <--- 
                # Process wait is needed here to get the return code
                return_code = None
                stderr_output = ""
                try:
                    if local_process: 
                        # Read remaining stderr first
                        try: 
                            if local_process.stderr and not local_process.stderr.closed:
                                stderr_output = local_process.stderr.read()
                        except Exception as e_stderr: 
                            self.log_signal.emit(f"Error reading final stderr: {e_stderr}")
                        
                        # Now wait for process exit code
                        self.log_signal.emit("Waiting for process to exit naturally...")
                        return_code = local_process.wait(timeout=10) # Wait longer if finishing normally
                        self.log_signal.emit(f"Process finished naturally with code: {return_code}")
                    else:
                         self.log_signal.emit("Process was None before final wait.")
                except subprocess.TimeoutExpired:
                    self.log_signal.emit("Process wait timeout expired after expected completion.")
                    return_code = -1 # Treat timeout as error
                    # Attempt to kill if timed out waiting
                    if local_process: 
                        try: 
                            local_process.kill()
                            local_process.wait(1) # Wait briefly after kill
                        except Exception as kill_err: 
                            self.log_signal.emit(f"Error during kill after timeout: {kill_err}")
                            # Ignore errors during kill after timeout
                            pass 
                except Exception as e_wait:
                    self.log_signal.emit(f"Error during final process wait: {str(e_wait)}")
                    return_code = -1
                
                # Print final stderr if any
                if stderr_output: 
                    print(f"DEBUG: Final Standard error output: {stderr_output}")
                    # Log critical errors from final stderr output
                    if "ERROR:" in stderr_output:
                        for line in stderr_output.splitlines():
                            if "ERROR:" in line: self.log_signal.emit(f"Error: {line.strip()}")

                # --- Post-Process Logic (Error/Success, only runs if NOT cancelled) --- 
    
                # ---> PROCESS ERROR (If exited with non-zero code) <--- 
                if return_code is not None and return_code != 0:
                    error_msg = f"yt-dlp process exited with code {return_code}"
                    print(f"DEBUG: {error_msg} (Cancelled: {self.cancelled})") 
                    
                    # Try to get specific error from stderr captured above
                    if stderr_output:
                        error_lines = stderr_output.splitlines()
                        specific_error_found = False
                        for line in reversed(error_lines):
                            if 'ERROR:' in line:
                                error_msg = line.strip()
                                specific_error_found = True
                                break
                
                    # Emit error signal (already confirmed not cancelled)
                    self.error_signal.emit(self.url, error_msg)
                    
                    # Cleanup might still be needed if error occurred after file creation
                    self._cleanup_temporary_files()
                    return # Exit after handling error (finally will still run) 
    
                # ---> SUCCESSFUL COMPLETION (If return_code is 0 or None) <--- 
                # Check if Merger step already set the definitive filename
                if self.downloaded_filename is None:
                    # --- Fallback Filename Logic --- 
                    # Filter out subtitle files from the tracked temporary names
                    media_filenames = [
                        f for f in self.temporary_filenames
                        if os.path.splitext(f)[1].lower() not in SUBTITLE_EXTENSIONS
                    ]
                    if media_filenames:
                        # Assume the last tracked *media* destination was the final file
                        self.downloaded_filename = media_filenames[-1]
                        self.log_signal.emit(f"Assuming last tracked media destination is final file: {self.downloaded_filename}")
                    else:
                        # If only subtitles were tracked or none at all
                        self.log_signal.emit("No media filename captured directly via tracking.")
                        # Note: Disk scan fallback was removed as unreliable. We rely on Merger or last media file.
                        # If we reach here, self.downloaded_filename remains None.

                if self.downloaded_filename:
                     final_filepath = os.path.join(self.output_dir, self.downloaded_filename)
                     if not os.path.exists(final_filepath):
                          self.log_signal.emit(f"Warning: Final file '{self.downloaded_filename}' not found at expected location.")
                     self.complete_signal.emit(self.url, self.output_dir, self.downloaded_filename)
                     # Update timestamp
                     if os.path.isfile(final_filepath):
                        try:
                            current_time = time.time()
                            os.utime(final_filepath, (current_time, current_time))
                        except Exception as e:
                            self.log_signal.emit(f"Failed to update final file timestamp: {str(e)}")
                else:
                     self.error_signal.emit(self.url, "Download finished but could not determine output filename.")
            
        except Exception as e:
            # --- Catch ALL other unexpected exceptions during execution --- 
            error_message = str(e)
            print(f"ERROR: Unhandled exception in worker {self.url}: {error_message}") # Log raw error
            # Ensure stack trace is logged if possible (requires traceback module)
            # import traceback
            # print(traceback.format_exc())
            if not self.cancelled:
                self.error_signal.emit(self.url, f"Unhandled Error in worker: {error_message}")
            else:
                self.log_signal.emit(f"Error during cancellation/shutdown: {error_message}")
        finally:
            # --- EMIT FINISHED SIGNAL --- 
            self.log_signal.emit(f"Worker finished execution for {self.url}. Emitting finished signal.")
            self.finished.emit()
            
            # Clean up the worker's process handle 
            with self._process_lock:
                self.process = None # Allow garbage collection
    
    def _build_ytdlp_command(self):
        """Build the yt-dlp command with all necessary options."""
        cmd = ["yt-dlp"]
        
        # Add the format option
        if isinstance(self.format_options, dict) and 'format' in self.format_options:
            cmd.extend(["--format", self.format_options['format']])
        elif isinstance(self.format_options, str):
            cmd.extend(["--format", self.format_options])
        else:
            cmd.extend(["--format", "best"])
        
        # Set output template
        output_template = os.path.join(self.output_dir, '%(title)s.%(ext)s')
        cmd.extend(["--output", output_template])
        
        # Add format sorting if specified
        if isinstance(self.format_options, dict) and 'format_sort' in self.format_options:
            format_sort = self.format_options['format_sort']
            if isinstance(format_sort, list):
                format_sort = ','.join(format_sort)
            cmd.extend(["--format-sort", format_sort])
        
        # Add merge format if specified and not in audio-only mode
        if isinstance(self.format_options, dict) and 'merge_output_format' in self.format_options:
            # Check if this is an audio-only download (no merging needed)
            is_audio_only = False
            if 'format' in self.format_options:
                format_str = self.format_options['format']
                # Audio-only format typically starts with 'bestaudio' with no '+' for merging
                if format_str.startswith('bestaudio') and '+' not in format_str:
                    is_audio_only = True
                    print(f"DEBUG: Detected audio-only format, skipping merge-output-format")
            
            # Only add merge-output-format for video downloads that require merging
            if not is_audio_only:
                cmd.extend(["--merge-output-format", self.format_options['merge_output_format']])
                print(f"DEBUG: Using merge-output-format: {self.format_options['merge_output_format']}")
        
        # --- Refactored Subtitle Logic ---
        subtitles_requested = False
        subtitle_langs_specified = None
        subtitle_format_specified = None
    
        if isinstance(self.format_options, dict):
            # Determine if any subtitle functionality is enabled
            # Check toggles OR if a non-empty language list is provided
            if (self.format_options.get('writesubtitles', False) or 
                self.format_options.get('writeautomaticsub', False) or 
                ('subtitleslangs' in self.format_options and self.format_options['subtitleslangs'])): 
                subtitles_requested = True
                self.log_signal.emit("Subtitle download requested.") # Log request
                
            # Get specific lang/format if provided, regardless of toggles
            if 'subtitleslangs' in self.format_options:
                langs = self.format_options['subtitleslangs']
                if isinstance(langs, list):
                    # Handle potential empty lists
                    non_empty_langs = [lang for lang in langs if lang]
                    if non_empty_langs:
                        subtitle_langs_specified = ','.join(non_empty_langs)
                elif isinstance(langs, str) and langs: # Handle empty strings
                     subtitle_langs_specified = langs
    
            if 'subtitlesformat' in self.format_options and self.format_options['subtitlesformat']:
                subtitle_format_specified = self.format_options['subtitlesformat']
        
        # Add subtitle command arguments ONLY if requested
        if subtitles_requested:
            cmd.append("--embed-subs") # Always embed if subs requested
            self.log_signal.emit("Using --embed-subs for subtitles.")
    
            if subtitle_langs_specified:
                cmd.extend(["--sub-langs", subtitle_langs_specified])
                self.log_signal.emit(f"Using subtitle languages: {subtitle_langs_specified}")
            else:
                # If langs specifically requested but list was empty, maybe log a warning?
                # Or default to a language? For now, just don't add the flag if no langs.
                pass 
    
            if subtitle_format_specified:
                cmd.extend(["--sub-format", subtitle_format_specified])
                self.log_signal.emit(f"Using subtitle format: {subtitle_format_specified}")
            
            # Do NOT add --write-subs or --write-auto-subs
            
        # --- End Refactored Subtitle Logic ---
        
        # Handle cookies option
        # For CLI mode, always use --cookies-from-browser firefox when cookies are enabled
        cookies_enabled = False
        if isinstance(self.format_options, dict):
            # Check if cookies are enabled directly
            if self.format_options.get('cookies') or self.format_options.get('cookies_from_browser'):
                cookies_enabled = True
            # Or if this is set from the Cookies toggle in the UI
            elif 'use_cookies' in self.format_options and self.format_options['use_cookies']:
                cookies_enabled = True
                
        if cookies_enabled:
            cmd.extend(["--cookies-from-browser", "firefox"])
            self.log_signal.emit("Using cookies from Firefox browser")
            # Important note about browser usage
            self.log_signal.emit("Note: Please ensure Firefox is closed and you're logged into YouTube in Firefox")
            # Also print to debug terminal
            print("DEBUG: Using cookies from Firefox browser")
        
        # Add network timeout options
        cmd.extend([
            "--socket-timeout", "120",
            "--retries", "10",
            "--fragment-retries", "10",
            "--extractor-retries", "5",
            "--file-access-retries", "5"
        ])
        
        # Add options to skip unavailable fragments but not abort on them
        cmd.append("--skip-unavailable-fragments")
        
        # Add other useful flags
        cmd.extend([
            "--no-mtime",        # Don't use the media timestamp
            "--progress"         # Show progress bar
        ])
        
        # Finally add the URL
        cmd.append(self.url)
        
        return cmd
    
    def _get_safe_command_string(self, cmd):
        """Create a safe version of the command for logging (redact sensitive info)."""
        safe_cmd = cmd.copy()
        
        # Redact cookies
        if "--cookies" in safe_cmd:
            cookie_index = safe_cmd.index("--cookies")
            if cookie_index + 1 < len(safe_cmd):
                safe_cmd[cookie_index + 1] = "[REDACTED]"
        
        # Redact cookies-from-browser
        if "--cookies-from-browser" in safe_cmd:
            browser_index = safe_cmd.index("--cookies-from-browser")
            if browser_index + 1 < len(safe_cmd):
                # Keep browser name but redact any profile path
                browser_info = safe_cmd[browser_index + 1]
                if os.path.sep in browser_info:
                    safe_cmd[browser_index + 1] = browser_info.split(os.path.sep)[0] + os.path.sep + "[REDACTED]"
        
        return ' '.join(shlex.quote(arg) for arg in safe_cmd)
    
    def _cleanup_temporary_files(self):
        """Helper to clean up tracked temporary files (runs in worker thread)."""
        cleaned_count = 0
        if not self.temporary_filenames:
             # Log only if there were no filenames captured
             self.log_signal.emit("No temporary filenames were tracked for cleanup.")
             return
             
        self.log_signal.emit(f"Attempting cleanup for {len(self.temporary_filenames)} tracked temporary files in {self.output_dir}")
        print(f"DEBUG: Cleanup path: {self.output_dir}")

        # Extract filename prefixes (first few chars) to use for glob matching
        prefixes = []
        for filename in self.temporary_filenames:
            try:
                # Get the first 5-8 characters to use as a prefix for matching
                # or up to the first special character
                prefix_end = min(8, len(filename))
                prefix = filename[:prefix_end]
                # Remove problematic characters for glob
                prefix = ''.join(c for c in prefix if c.isalnum() or c.isspace())
                if prefix and len(prefix) >= 2:  # At least 2 chars needed for meaningful match
                    prefixes.append(prefix)
            except Exception as e:
                print(f"DEBUG: Error extracting prefix from {filename}: {e}")

        # First try direct path removal for each tracked file
        for filename in self.temporary_filenames:
            try:
                # Construct paths for the file and its potential .part file
                file_path = os.path.join(self.output_dir, filename)
                part_file_path = file_path + ".part"
                print(f"DEBUG: Checking for: {file_path}")

                # Try to remove the .part file with exponential backoff
                removed_part = False
                for delay in (0.2, 0.5, 1, 2, 4): # Exponential backoff delays
                    try:
                        if os.path.exists(part_file_path):
                            print(f"DEBUG: Attempting remove (delay={delay}): {part_file_path}")
                            os.remove(part_file_path)
                            self.log_signal.emit(f"Removed temporary file: {os.path.basename(part_file_path)}")
                            cleaned_count += 1
                            removed_part = True
                            break # Exit retry loop if successful
                    except PermissionError:
                        self.log_signal.emit(f"File in use (delay={delay}), waiting: {os.path.basename(part_file_path)}")
                        time.sleep(delay)
                    except FileNotFoundError:
                        removed_part = True # File gone is success for cleanup
                        break 
                    except Exception as e:
                        self.log_signal.emit(f"Error removing {part_file_path}: {str(e)}")
                        removed_part = True # Assume we can't remove it, stop retrying
                        break 
                if not removed_part:
                     self.log_signal.emit(f"Failed to remove {os.path.basename(part_file_path)} after retries.")

                # Try to remove the base temporary file with exponential backoff
                removed_base = False
                # Avoid deleting the final intended file if known
                if self.downloaded_filename and filename == self.downloaded_filename:
                    print(f"DEBUG: Skipping removal of final file: {filename}")
                    continue # Skip to next filename in self.temporary_filenames
                
                for delay in (0.2, 0.5, 1, 2, 4):
                    try:
                        if os.path.exists(file_path):
                            print(f"DEBUG: Attempting remove (delay={delay}): {file_path}")
                            os.remove(file_path)
                            self.log_signal.emit(f"Removed temporary file: {filename}")
                            cleaned_count += 1
                            removed_base = True
                            break # Exit retry loop if successful
                    except PermissionError:
                        self.log_signal.emit(f"File in use (delay={delay}), waiting: {filename}")
                        time.sleep(delay)
                    except FileNotFoundError:
                        removed_base = True
                        break
                    except Exception as e:
                        self.log_signal.emit(f"Error removing {file_path}: {str(e)}")
                        removed_base = True
                        break
                if not removed_base:
                    self.log_signal.emit(f"Failed to remove {filename} after retries.")
                    
            except Exception as e:
                self.log_signal.emit(f"Error during cleanup preparation for {filename}: {str(e)}")
        
        # Fallback: Glob cleanup (remains the same, using prefixes)
        try:
            import glob
            
            if prefixes:
                self.log_signal.emit(f"Using filename prefixes for targeted glob cleanup: {', '.join(prefixes)}")
                for prefix in prefixes:
                    patterns = [
                        os.path.join(self.output_dir, f"{prefix}*.f*.mp4"),
                        os.path.join(self.output_dir, f"{prefix}*.f*.m4a"),
                        os.path.join(self.output_dir, f"{prefix}*.f*.webm"),
                        os.path.join(self.output_dir, f"{prefix}*.f*.mp4.part"),
                        os.path.join(self.output_dir, f"{prefix}*.f*.m4a.part"),
                        os.path.join(self.output_dir, f"{prefix}*.f*.webm.part")
                    ]
                    for pattern in patterns:
                        for file_path in glob.glob(pattern):
                            try:
                                if self.downloaded_filename and self.downloaded_filename in file_path:
                                    continue
                                print(f"DEBUG: Found via glob with prefix '{prefix}': {file_path}")
                                os.remove(file_path)
                                self.log_signal.emit(f"Removed temporary file via glob: {os.path.basename(file_path)}")
                                cleaned_count += 1
                            except Exception as e:
                                # Log non-permission errors more visibly?
                                self.log_signal.emit(f"Error removing glob match {os.path.basename(file_path)}: {str(e)}")
            else:
                self.log_signal.emit("No valid prefixes for targeted glob cleanup")
        except Exception as e:
            self.log_signal.emit(f"Error during fallback glob cleanup: {str(e)}")
        
        if cleaned_count > 0:
            self.log_signal.emit(f"Cleanup finished, removed {cleaned_count} files/parts.")
        else:
            if self.temporary_filenames:
                 self.log_signal.emit("Cleanup finished, no matching temporary files found or removed.")
        
    def cancel(self):
        """Cancel the download - Sets flag. Actual termination/cleanup happens in _execute_download."""
        if self.cancelled: # Prevent double execution
            return
            
        # Set the flag first - this is used by the main worker thread
        self.cancelled = True
        self.log_signal.emit(f"Cancel requested for {self.url}. Worker will terminate and cleanup.")
        
        # DO NOT start a thread here.
        # The main _execute_download loop will detect self.cancelled and handle termination/cleanup.
        