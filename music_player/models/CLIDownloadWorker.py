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
import shutil
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from qt_base_app.models.logger import Logger
import threading
import psutil

# Import yt-dlp updater PathManager to locate yt-dlp.exe
try:
    from .yt_dlp_updater.file_manager import PathManager as YtDlpPathManager
    YTDLP_PATH_MANAGER_AVAILABLE = True
except ImportError:
    YTDLP_PATH_MANAGER_AVAILABLE = False

# Stream picking (no-cookies probe -> explicit IDs)
from .StreamPicker import SelectionPolicy as StreamSelectionPolicy, pick_for_url as stream_pick_for_url

# --- Define Subtitle Extensions --- 
# Used to filter out subtitle files when determining the final media file
# in the fallback logic if the Merger step doesn't specify it.
SUBTITLE_EXTENSIONS = {
    ".vtt", ".srt", ".ass", ".ssa", ".sub", ".ttml", ".srv1", ".srv2", ".srv3", ".json3"
}
# -------------------------------

# --- Define Progress Regex ---
# Matches lines like: [download]  10.5% of 12.34MiB at 500.00KiB/s ETA 00:15
# or              : [download]   5.0% of Unknown Size at 250.0KiB/s ETA Unknown
# or              : [download] 100% of    7.52MiB in 00:00:03 at 2.00MiB/s
PROGRESS_REGEX = re.compile(
    r"\s*\[download\]\s+"                # "[download]" prefix
    r"(?P<percent>\d+(?:\.\d+)?)%\s+"   # Percentage (integer or float, non-capturing group for decimal)
    r"of.*?at\s+"                       # "of ... at " (covers 'in ...' implicitly)
    r"(?P<speed>[^\s]+)"                # Speed (greedy should be fine here)
    r"(?:\s+ETA\s+(?P<eta>[^\s]+))?"    # Optional ETA part (non-capturing outer group)
)

# Matches subtitle download progress lines like: [download]    1.00KiB at   90.79KiB/s (00:00:00)
SUBTITLE_PROGRESS_REGEX = re.compile(
    r"\s*\[download\]\s+"               # "[download]" prefix
    r"(?P<size>[\d.]+\w+)\s+"           # Downloaded size (e.g., "1.00KiB", "255.00KiB")
    r"at\s+"                            # "at " separator
    r"(?P<speed>[^\s]+)"                # Speed (e.g., "90.79KiB/s")
    r"(?:\s+\((?P<time>[^)]+)\))?"      # Optional time in parentheses (e.g., "(00:00:00)")
)
# ---------------------------

class CLIDownloadWorker(QObject):
    """Worker object for processing a single download using the yt-dlp CLI.
    Designed to be moved to a separate QThread.
    """
    
    # Define signals (same as the PythonDownloadWorker for API compatibility)
    progress_signal = pyqtSignal(str, float, str)  # url, progress percent, status text
    complete_signal = pyqtSignal(str, str, str)    # url, output_dir, filename
    error_signal = pyqtSignal(str, str)            # url, error message
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
        self._process_output = [] # Store output lines for later analysis
    
    @pyqtSlot() # Make run a slot
    def run(self):
        """Public slot to start the download process. Calls the internal method."""
        self._execute_download()
    
    def _execute_download(self):
        """Main download logic."""
        try:
            self.logger.info(caller="CLIDownloadWorker", msg=f"Starting CLI download for: {self.url}")
            
            # Signal that processing is starting
            self.processing_signal.emit(self.url, "Processing started...")
            
            # Build the yt-dlp command
            cmd = self._build_ytdlp_command()
            
            # Log the command (with sensitive info like cookies redacted)
            safe_cmd = self._get_safe_command_string(cmd)
            self.logger.debug(caller="CLIDownloadWorker", msg=f"Executing command: {safe_cmd}")
            
            # Create a temporary file for progress output
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.json') as progress_file:
                progress_file_path = progress_file.name
            
            # Set up process with hidden window on Windows
            popen_kwargs = {
                'stdout': subprocess.PIPE,
                'stderr': subprocess.STDOUT,
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
                self.logger.warning(caller="CLIDownloadWorker", msg="Process terminated or cancelled before output processing started")
                # Ensure finished signal is emitted even if we exit early
                # The finally block will handle this.
                return

            # Main output processing loop
            try:
                for line in iter(local_process.stdout.readline, ''):
                    # Check for cancellation FIRST
                    if self.cancelled:
                        self.logger.info(caller="CLIDownloadWorker", msg=f"Cancellation detected for {self.url}, stopping output processing.")
                        break # ---> EXIT LOOP DUE TO CANCELLATION

                    # Store the line for later analysis
                    self._process_output.append(line)

                    # --- Refactored Parsing Logic ---
                    
                    # 1. Check for Progress Line using Main Regex (video/audio with percentages)
                    progress_match = PROGRESS_REGEX.search(line)
                    if progress_match:
                        try:
                            percentage = float(progress_match.group('percent'))
                            speed = progress_match.group('speed')
                            eta = progress_match.group('eta')
                            status_text = f"Downloading: {percentage:.1f}% at {speed}, ETA: {eta}"
                            
                            # Emit progress update
                            self.progress_signal.emit(self.url, percentage, status_text)
                            
                        except Exception as e:
                            self.logger.error(caller="CLIDownloadWorker", msg=f"Error parsing progress regex match: {str(e)} - Line: {line.strip()}")
                        continue # Move to the next line after handling progress

                    # 2. Check for Subtitle Progress Line (raw data amounts)
                    subtitle_progress_match = SUBTITLE_PROGRESS_REGEX.search(line)
                    if subtitle_progress_match:
                        try:
                            size = subtitle_progress_match.group('size')
                            speed = subtitle_progress_match.group('speed')
                            time_elapsed = subtitle_progress_match.group('time') or "ongoing"
                            status_text = f"Downloading subtitles: {size} at {speed} ({time_elapsed})"
                            
                            # For subtitle progress, we can't calculate exact percentage without knowing total size
                            # Use a small progress value to show activity without indicating actual completion
                            subtitle_progress = 5.0  # Small progress indicator
                            
                            # Emit progress update
                            self.progress_signal.emit(self.url, subtitle_progress, status_text)
                            
                        except Exception as e:
                            self.logger.error(caller="CLIDownloadWorker", msg=f"Error parsing subtitle progress regex match: {str(e)} - Line: {line.strip()}")
                        continue # Move to the next line after handling subtitle progress

                    # 3. If NOT a progress line, print it to logger and check for other keywords
                    self.logger.info(caller="CLIDownloadWorker", msg=f"[yt-dlp output] {line.strip()}") # Log non-progress lines as INFO
                    
                    # Check for Destination:
                    if '[download]' in line and 'Destination:' in line:
                        downloading_started = True
                        output_file = line.split('Destination: ')[1].strip()
                        self.logger.info(caller="CLIDownloadWorker", msg=f"Downloading to: {output_file}")
                        # Store ALL potential temporary filenames reported
                        basename = os.path.basename(output_file)
                        if basename not in self.temporary_filenames:
                            self.temporary_filenames.append(basename)
                            self.logger.debug(caller="CLIDownloadWorker", msg=f"Added temporary filename candidate: {basename}") 
                        continue # Handled, move to next line

                    # Check for Merger:
                    if line.strip().startswith('[Merger]') and 'Merging formats into' in line:
                        match = re.search(r'Merging formats into "(.*?)"', line)
                        if match:
                            merged_filepath = match.group(1)
                            # This is the FINAL filename
                            self.downloaded_filename = os.path.basename(merged_filepath)
                            self.logger.info(caller="CLIDownloadWorker", msg=f"Detected final merged file: {self.downloaded_filename}")
                            
                            # Emit progress update for merging phase
                            self.progress_signal.emit(self.url, 100.0, "Merging video+audio...")
                        continue # Handled, move to next line

                    # Check for FixupM3u8 (HLS fixup writes directly to final container)
                    if line.strip().startswith('[FixupM3u8]') and '"' in line:
                        try:
                            match = re.search(r'\"(.*?)\"', line)
                            if match:
                                final_path = match.group(1)
                                self.downloaded_filename = os.path.basename(final_path)
                                self.logger.info(caller="CLIDownloadWorker", msg=f"Detected final file from FixupM3u8: {self.downloaded_filename}")
                                # Indicate post-processing phase
                                self.progress_signal.emit(self.url, 100.0, "Fixing container...")
                        except Exception as e_fix:
                            self.logger.warning(caller="CLIDownloadWorker", msg=f"Failed to parse FixupM3u8 line: {e_fix}")
                        continue

                    # Check for Subtitle Embedding:
                    if line.strip().startswith('[EmbedSubtitle]') and 'Embedding subtitles in' in line:
                        try:
                            match = re.search(r'\"(.*?)\"', line)
                            if match:
                                final_path = match.group(1)
                                self.downloaded_filename = os.path.basename(final_path)
                                self.logger.info(caller="CLIDownloadWorker", msg=f"Detected final file from EmbedSubtitle: {self.downloaded_filename}")
                        except Exception:
                            pass
                        # Emit progress update for subtitle embedding phase
                        self.progress_signal.emit(self.url, 100.0, "Embedding subtitles...")
                        continue # Handled, move to next line
                        
                    # Check for Errors:
                    if 'ERROR:' in line:
                        error_msg = line.strip()
                        # Log error but continue processing output
                        self.logger.error(caller="CLIDownloadWorker", msg=f"Error detected during download: {error_msg}")
                        # No continue here, let it fall through if needed

                    # --- End Refactored Parsing Logic ---

            except Exception as e:
                # Handle exceptions DURING the output processing loop
                self.logger.error(caller="CLIDownloadWorker", msg=f"Error processing stdout/stderr: {str(e)}")
                if not self.cancelled:  # Only emit error if not cancelled
                    self.error_signal.emit(self.url, f"Error processing output: {str(e)}")
                # Ensure finished is emitted via finally block
                return 
            
            # --- Code AFTER loop finishes (normally or via break) --- 
            
            # ---> Handle Cancellation Scenario FIRST <--- 
            if self.cancelled:
                self.logger.info(caller="CLIDownloadWorker", msg=f"Download process interrupted by cancellation for {self.url}.")
                
                # --- Deterministic Shutdown Sequence --- 
                if local_process:
                    pid_to_check = local_process.pid # Get PID before it potentially dies
                    self.logger.info(caller="CLIDownloadWorker", msg=f"Starting deterministic shutdown for PID: {pid_to_check or 'N/A'}")
                    
                    # 1. Send SIGTERM/SIGKILL and wait for main process
                    self.logger.debug(caller="CLIDownloadWorker", msg="Terminating main process...")
                    local_process.terminate()
                    try:
                        local_process.wait(timeout=5)
                        self.logger.debug(caller="CLIDownloadWorker", msg="Main process terminated gracefully.")
                    except subprocess.TimeoutExpired:
                        self.logger.warning(caller="CLIDownloadWorker", msg="Main process kill after timeout...")
                        try:
                            local_process.kill()
                            local_process.wait(timeout=2) # Wait after kill
                            self.logger.debug(caller="CLIDownloadWorker", msg="Main process killed.")
                        except Exception as e_kill:
                            self.logger.error(caller="CLIDownloadWorker", msg=f"Error during kill/wait: {e_kill}")
                    except Exception as e_term:
                        self.logger.error(caller="CLIDownloadWorker", msg=f"Error during terminate/wait: {e_term}")
                       
                    # 2. Close our pipe handles
                    self.logger.debug(caller="CLIDownloadWorker", msg="Closing process pipes...")
                    for pipe in (local_process.stdout, local_process.stderr):
                        try:
                            if pipe and not pipe.closed:
                                pipe.close()
                        except Exception as e_pipe:
                            self.logger.warning(caller="CLIDownloadWorker", msg=f"Ignoring error closing pipe: {e_pipe}")
                            pass # Ignore errors closing pipes

                    # 3. Reap children (ffmpeg etc.) using psutil
                    if pid_to_check: # Still need to check if we have a valid PID
                        self.logger.debug(caller="CLIDownloadWorker", msg="Attempting to reap child processes...")
                        try:
                            parent = psutil.Process(pid_to_check) 
                            children = parent.children(recursive=True)
                            if children:
                                self.logger.debug(caller="CLIDownloadWorker", msg=f"Killing {len(children)} child process(es)...")
                                for child in children:
                                    try:
                                        self.logger.debug(caller="CLIDownloadWorker", msg=f"Killing child PID: {child.pid}")
                                        child.kill()
                                        child.wait(timeout=2)
                                    except psutil.NoSuchProcess:
                                        pass # Child already gone
                                    except Exception as e_child:
                                        self.logger.warning(caller="CLIDownloadWorker", msg=f"Ignoring error killing child {child.pid}: {e_child}")
                            else:
                                self.logger.debug(caller="CLIDownloadWorker", msg="No child processes found.")
                        except psutil.NoSuchProcess:
                            self.logger.warning(caller="CLIDownloadWorker", msg=f"Main process {pid_to_check} not found for child reaping.")
                        except Exception as e_psutil:
                            self.logger.error(caller="CLIDownloadWorker", msg=f"Error during psutil child reaping: {e_psutil}")
                    else: 
                         self.logger.warning(caller="CLIDownloadWorker", msg="Invalid PID, skipping child process kill.")

                else: # if not local_process
                    self.logger.warning(caller="CLIDownloadWorker", msg="No active process found for shutdown sequence.")
                # --- End Shutdown Sequence ---
                
                # 4. Give the kernel a moment
                self.logger.debug(caller="CLIDownloadWorker", msg="Waiting for OS file handle release...")
                time.sleep(1.0)
                    
                # --- Run Cleanup (AFTER termination is complete) --- 
                self.logger.info(caller="CLIDownloadWorker", msg="Proceeding with file cleanup...")
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
                            self.logger.error(caller="CLIDownloadWorker", msg=f"Error reading final stderr: {e_stderr}")
                        
                        # Now wait for process exit code
                        self.logger.debug(caller="CLIDownloadWorker", msg="Waiting for process to exit naturally...")
                        return_code = local_process.wait(timeout=10) # Wait longer if finishing normally
                        self.logger.info(caller="CLIDownloadWorker", msg=f"Process finished naturally with code: {return_code}")
                    else:
                         self.logger.warning(caller="CLIDownloadWorker", msg="Process was None before final wait.")
                except subprocess.TimeoutExpired:
                    self.logger.warning(caller="CLIDownloadWorker", msg="Process wait timeout expired after expected completion.")
                    return_code = -1 # Treat timeout as error
                    # Attempt to kill if timed out waiting
                    if local_process: 
                        try: 
                            local_process.kill()
                            local_process.wait(1) # Wait briefly after kill
                        except Exception as kill_err: 
                            self.logger.error(caller="CLIDownloadWorker", msg=f"Error during kill after timeout: {kill_err}")
                            # Ignore errors during kill after timeout
                            pass 
                except Exception as e_wait:
                    self.logger.error(caller="CLIDownloadWorker", msg=f"Error during final process wait: {str(e_wait)}")
                    return_code = -1
                
                # Log final stderr if any
                if stderr_output: 
                    self.logger.debug(caller="CLIDownloadWorker", msg=f"Final Standard error output:\n{stderr_output}")
                    # Log critical errors from final stderr output
                    if "ERROR:" in stderr_output:
                        for line in stderr_output.splitlines():
                            if "ERROR:" in line: self.logger.error(caller="CLIDownloadWorker", msg=f"Error from stderr: {line.strip()}")
            
                # --- Post-Process Logic (Error/Success, only runs if NOT cancelled) --- 
            
                # ---> PROCESS ERROR (If exited with non-zero code) <--- 
                if return_code is not None and return_code != 0:
                    # If final file exists, treat as completed with warnings
                    final_filepath = None
                    if self.downloaded_filename:
                        final_filepath = os.path.join(self.output_dir, self.downloaded_filename)
                    if final_filepath and os.path.exists(final_filepath) and os.path.getsize(final_filepath) > 0:
                        warn_msg = f"yt-dlp exited with code {return_code}, but final file exists; treating as success with warnings"
                        self.logger.warning(caller="CLIDownloadWorker", msg=warn_msg)
                        # Emit a warning-flavored completion
                        self.progress_signal.emit(self.url, 100.0, "Done (Warning)")
                        self.complete_signal.emit(self.url, self.output_dir, self.downloaded_filename)
                        # Update timestamp and perform cleanup (excluding final file)
                        try:
                            if os.path.isfile(final_filepath):
                                current_time = time.time()
                                os.utime(final_filepath, (current_time, current_time))
                        except Exception as e_touch:
                            self.logger.error(caller="CLIDownloadWorker", msg=f"Failed to update final file timestamp: {str(e_touch)}")
                        try:
                            self._cleanup_temporary_files()
                        except Exception as e_clean:
                            self.logger.warning(caller="CLIDownloadWorker", msg=f"Cleanup after warning-complete encountered an error: {str(e_clean)}")
                        return

                    # Otherwise, treat as error
                    error_msg = f"yt-dlp process exited with code {return_code}"
                    self.logger.warning(caller="CLIDownloadWorker", msg=f"{error_msg} (Cancelled: {self.cancelled}) URL: {self.url}") 
                    
                    # Try to get specific error from stderr captured above
                    if stderr_output:
                        error_lines = stderr_output.splitlines()
                        for line in reversed(error_lines):
                            if 'ERROR:' in line:
                                error_msg = line.strip()
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
                        self.logger.info(caller="CLIDownloadWorker", msg=f"Assuming last tracked media destination is final file: {self.downloaded_filename}")
                    else:
                        # If only subtitles were tracked or none at all
                        self.logger.warning(caller="CLIDownloadWorker", msg="No media filename captured directly via tracking.")
                        
                        # Check if file already exists by examining stdout output
                        already_exists, detected_filename = self._check_if_already_downloaded(self._process_output, stderr_output)
                        if already_exists:
                            self.logger.info(caller="CLIDownloadWorker", msg=f"File already exists: {detected_filename or 'unknown'}")
                            self.error_signal.emit(self.url, "Already Exists")
                            # Gracefully terminate yt-dlp process if still running
                            if local_process and local_process.poll() is None:
                                try:
                                    local_process.terminate()
                                except Exception as e:
                                    self.logger.warning(caller="CLIDownloadWorker", msg=f"Error terminating yt-dlp after already exists: {e}")
                            # Exit the method to prevent further output parsing and error emission
                            return
                        else:
                            # Check once more by looking for the "has already been downloaded" message
                            # directly in the stdout/stderr outputs
                            
                            # Check if we can find the message in merged stdout/stderr
                            all_output = ""
                            if stderr_output:
                                all_output += stderr_output
                            
                            try:
                                if local_process.stdout:
                                    local_process.stdout.seek(0)
                                    stdout_content = local_process.stdout.read()
                                    all_output += stdout_content
                            except:
                                pass  # Can't seek stdout, continue with what we have
                                
                            if "has already been downloaded" in all_output:
                                self.logger.info(caller="CLIDownloadWorker", msg=f"Detected file already exists from stdout/stderr")
                                self.error_signal.emit(self.url, "Already Exists")
                            else:
                        # Note: Disk scan fallback was removed as unreliable. We rely on Merger or last media file.
                        # If we reach here, self.downloaded_filename remains None.
                                self.error_signal.emit(self.url, "Download finished but could not determine output filename.")

                if self.downloaded_filename:
                     final_filepath = os.path.join(self.output_dir, self.downloaded_filename)
                     if not os.path.exists(final_filepath):
                          self.logger.warning(caller="CLIDownloadWorker", msg=f"Warning: Final file '{self.downloaded_filename}' not found at expected location: {final_filepath}")
                     
                     # Emit final 100% progress before completing
                     self.progress_signal.emit(self.url, 100.0, "Download completed")
                     
                     self.complete_signal.emit(self.url, self.output_dir, self.downloaded_filename)
                     
                     # Update timestamp - no subtitle cleanup needed with --embed-subs only
                     if os.path.isfile(final_filepath):
                        try:
                            current_time = time.time()
                            os.utime(final_filepath, (current_time, current_time))
                        except Exception as e:
                            self.logger.error(caller="CLIDownloadWorker", msg=f"Failed to update final file timestamp: {str(e)}")
                        # Post-success cleanup: remove sidecar subtitles and leftover temp files
                        try:
                            self._cleanup_temporary_files()
                        except Exception as e:
                            self.logger.warning(caller="CLIDownloadWorker", msg=f"Cleanup after success encountered an error: {str(e)}")
                else:
                     self.error_signal.emit(self.url, "Download finished but could not determine output filename.")
            
        except Exception as e:
            # --- Catch ALL other unexpected exceptions during execution --- 
            error_message = str(e)
            self.logger.error(caller="CLIDownloadWorker", msg=f"Unhandled exception in worker {self.url}: {error_message}", exc_info=True) # Log raw error with stack trace
            # Ensure stack trace is logged if possible (requires traceback module)
            # import traceback
            # print(traceback.format_exc())
            if not self.cancelled:
                self.error_signal.emit(self.url, f"Unhandled Error in worker: {error_message}")
            else:
                self.logger.warning(caller="CLIDownloadWorker", msg=f"Error during cancellation/shutdown: {error_message}")
        finally:
            # --- EMIT FINISHED SIGNAL --- 
            self.logger.info(caller="CLIDownloadWorker", msg=f"Worker finished execution for {self.url}. Emitting finished signal.")
            self.finished.emit()
            
            # Clean up the worker's process handle 
            with self._process_lock:
                self.process = None # Allow garbage collection
    
    def _get_ytdlp_executable_path(self):
        """
        Get the path to the yt-dlp executable.
        Uses the updater's PathManager if available, otherwise tries to find in PATH.
        
        Returns:
            str: Path to yt-dlp executable
        """
        if YTDLP_PATH_MANAGER_AVAILABLE:
            try:
                path_manager = YtDlpPathManager()
                install_path = path_manager.get_install_path()
                
                # Check if the file exists at the expected location
                if os.path.exists(install_path):
                    self.logger.debug(caller="CLIDownloadWorker", 
                                     msg=f"Using yt-dlp from updater path: {install_path}")
                    return install_path
                else:
                    self.logger.warning(caller="CLIDownloadWorker", 
                                       msg=f"yt-dlp not found at expected path: {install_path}")
            except Exception as e:
                self.logger.warning(caller="CLIDownloadWorker", 
                                   msg=f"Error getting yt-dlp path from updater: {e}")
        
        # Fallback to trying PATH
        self.logger.debug(caller="CLIDownloadWorker", 
                         msg="Falling back to searching for yt-dlp in system PATH")
        return "yt-dlp"

    def _build_ytdlp_command(self):
        """Build the yt-dlp command with all necessary options."""
        # Get the correct yt-dlp executable path
        ytdlp_path = self._get_ytdlp_executable_path()
        cmd = [ytdlp_path]

        def _is_youtube_url(url: str) -> bool:
            u = (url or "").lower()
            return ("youtube.com" in u) or ("youtu.be" in u)

        is_youtube = _is_youtube_url(self.url)

        # For YouTube downloads, enforce JS runtime + Firefox cookies (validated by probe).
        # Note: format probing for StreamPicker happens separately WITHOUT cookies.
        if is_youtube:
            node_path = shutil.which("node")
            deno_path = shutil.which("deno")
            if node_path:
                cmd.extend(["--js-runtimes", f"node:{node_path}"])
            elif deno_path:
                cmd.extend(["--js-runtimes", f"deno:{deno_path}"])
            else:
                self.logger.warning(caller="CLIDownloadWorker", msg="No JS runtime (node/deno) found on PATH; YouTube downloads may fail.")
            cmd.extend(["--cookies-from-browser", "firefox"])
        
        # Resolve the format option.
        # - Default to existing selector string (legacy)
        # - If StreamPicker hint exists, override with explicit IDs (e.g. 298+140)
        format_spec = "best"
        if isinstance(self.format_options, dict) and "format" in self.format_options:
            format_spec = str(self.format_options["format"])
        elif isinstance(self.format_options, str):
            format_spec = self.format_options

        if is_youtube and isinstance(self.format_options, dict) and self.format_options.get("stream_picker"):
            try:
                sp = self.format_options.get("stream_picker") or {}
                prefer_best_video = bool(sp.get("prefer_best_video", False))
                target_height = sp.get("target_height", None)
                target_width = sp.get("target_width", None)
                prefer_m4a = bool(sp.get("prefer_m4a", True))
                prefer_avc = bool(sp.get("prefer_avc", False))

                if prefer_best_video:
                    target_height = None
                    target_width = None

                policy = StreamSelectionPolicy(
                    target_height=(int(target_height) if target_height is not None else None),
                    target_width=(int(target_width) if target_width is not None else None),
                    prefer_protocol="https",
                    avoid_protocol_prefixes=("m3u8",),
                    prefer_video_exts=("mp4",) if prefer_m4a else ("mp4", "webm"),
                    prefer_audio_exts=("m4a",) if prefer_m4a else ("m4a", "webm"),
                    prefer_vcodec_prefixes=("avc", "h264") if prefer_avc else (),
                    prefer_protocol_over_resolution=False,
                )
                pick = stream_pick_for_url(
                    ytdlp_path=ytdlp_path,
                    url=self.url,
                    policy=policy,
                    timeout_s=120,
                )
                format_spec = pick.format_spec
                self.format_options["picked_format"] = format_spec
                self.format_options["picked_format_kind"] = pick.chosen_kind
                self.logger.info(caller="CLIDownloadWorker", msg=f"StreamPicker chose format: {format_spec} ({pick.chosen_kind})")
            except Exception as e:
                self.logger.warning(caller="CLIDownloadWorker", msg=f"StreamPicker failed; falling back to legacy selector. Error: {e}")

        cmd.extend(["--format", format_spec])
        
        # Set output template
        output_template = os.path.join(self.output_dir, '%(title)s.%(ext)s')
        cmd.extend(["--output", output_template])
        
        # Add extractor args if provided (e.g., youtube:player_client=android to avoid SABR)
        if isinstance(self.format_options, dict) and 'extractor_args' in self.format_options:
            extractor_args = self.format_options['extractor_args']
            parts = []
            if isinstance(extractor_args, dict):
                for extractor, args in extractor_args.items():
                    if isinstance(args, dict) and args:
                        kv_pairs = []
                        for k, v in args.items():
                            if v is None:
                                kv_pairs.append(f"{k}=")
                            else:
                                if isinstance(v, bool):
                                    v_str = "true" if v else "false"
                                else:
                                    v_str = str(v)
                                kv_pairs.append(f"{k}={v_str}")
                        if kv_pairs:
                            parts.append(f"{extractor}:{','.join(kv_pairs)}")
                    elif isinstance(args, str) and args:
                        parts.append(f"{extractor}:{args}")
            elif isinstance(extractor_args, str) and extractor_args:
                parts.append(extractor_args)
            
            if parts:
                cmd.extend(["--extractor-args", ';'.join(parts)])
        
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
                    self.logger.debug(caller="CLIDownloadWorker", msg=f"Detected audio-only format ({format_str}), skipping merge-output-format")
            
            # Only add merge-output-format for video downloads that require merging
            if not is_audio_only:
                cmd.extend(["--merge-output-format", self.format_options['merge_output_format']])
                self.logger.debug(caller="CLIDownloadWorker", msg=f"Using merge-output-format: {self.format_options['merge_output_format']}")
        
        # --- Simplified Subtitle Logic ---
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
                self.logger.info(caller="CLIDownloadWorker", msg="Subtitle embedding requested.") # Log request
                
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
            # Use --write-auto-subs to download automatic captions and --embed-subs to embed them
            # According to yt-dlp docs: when both are used together, subtitles are embedded 
            # and separate files are automatically deleted
            cmd.append("--write-auto-subs")
            cmd.append("--embed-subs")
            self.logger.debug(caller="CLIDownloadWorker", msg="Using --write-auto-subs and --embed-subs to download and embed automatic captions (separate files auto-deleted).")
    
            if subtitle_langs_specified:
                cmd.extend(["--sub-langs", subtitle_langs_specified])
                self.logger.debug(caller="CLIDownloadWorker", msg=f"Using subtitle languages: {subtitle_langs_specified}")
            else:
                # If langs specifically requested but list was empty, maybe log a warning?
                # Or default to a language? For now, just don't add the flag if no langs.
                pass 
    
            if subtitle_format_specified:
                cmd.extend(["--sub-format", subtitle_format_specified])
                self.logger.debug(caller="CLIDownloadWorker", msg=f"Using subtitle format: {subtitle_format_specified}")
            
        # --- End Simplified Subtitle Logic ---
        
        # Cookies:
        # - YouTube: already enforced above (firefox)
        # - Non-YouTube: keep legacy optional behavior
        if not is_youtube:
            cookies_enabled = False
            if isinstance(self.format_options, dict):
                if self.format_options.get('cookies') or self.format_options.get('cookies_from_browser'):
                    cookies_enabled = True
                elif 'use_cookies' in self.format_options and self.format_options['use_cookies']:
                    cookies_enabled = True
                    
            if cookies_enabled:
                cmd.extend(["--cookies-from-browser", "firefox"])
                self.logger.info(caller="CLIDownloadWorker", msg="Using cookies from Firefox browser")
                self.logger.info(caller="CLIDownloadWorker", msg="Note: Firefox must be closed. You must be logged into the target site in Firefox.")
        
        # Add network timeout options
        cmd.extend([
            "--socket-timeout", "120",
            "--retries", "10",
            "--fragment-retries", "10",
            "--extractor-retries", "5",
            "--file-access-retries", "5"
        ])
        
        # Continue on non-fatal errors (e.g., subtitle HTTP errors) to avoid aborting whole download
        cmd.append("--ignore-errors")
        
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
             self.logger.debug(caller="CLIDownloadWorker", msg="No temporary filenames were tracked for cleanup.")
             return
             
        self.logger.info(caller="CLIDownloadWorker", msg=f"Attempting cleanup for {len(self.temporary_filenames)} tracked temporary files in {self.output_dir}")
        self.logger.debug(caller="CLIDownloadWorker", msg=f"Cleanup path: {self.output_dir}")

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
                self.logger.error(caller="CLIDownloadWorker", msg=f"Error extracting prefix from {filename}: {e}")

        # First try direct path removal for each tracked file
        for filename in self.temporary_filenames:
            try:
                # Construct paths for the file and its potential .part file
                file_path = os.path.join(self.output_dir, filename)
                part_file_path = file_path + ".part"
                self.logger.debug(caller="CLIDownloadWorker", msg=f"Checking for: {file_path}")

                # Try to remove the .part file with exponential backoff
                removed_part = False
                if not os.path.exists(part_file_path):
                    removed_part = True # Nothing to do; treat as already cleaned
                else:
                    for delay in (0.2, 0.5, 1, 2, 4): # Exponential backoff delays
                        try:
                            self.logger.debug(caller="CLIDownloadWorker", msg=f"Attempting remove (delay={delay}): {part_file_path}")
                            os.remove(part_file_path)
                            self.logger.info(caller="CLIDownloadWorker", msg=f"Removed temporary file: {os.path.basename(part_file_path)}")
                            cleaned_count += 1
                            removed_part = True
                            break # Exit retry loop if successful
                        except PermissionError:
                            self.logger.warning(caller="CLIDownloadWorker", msg=f"File in use (delay={delay}), waiting: {os.path.basename(part_file_path)}")
                            time.sleep(delay)
                        except FileNotFoundError:
                            removed_part = True # File gone is success for cleanup
                            break 
                        except Exception as e:
                            self.logger.error(caller="CLIDownloadWorker", msg=f"Error removing {part_file_path}: {str(e)}")
                            removed_part = True # Assume we can't remove it, stop retrying
                            break 
                if not removed_part:
                     self.logger.warning(caller="CLIDownloadWorker", msg=f"Failed to remove {os.path.basename(part_file_path)} after retries.")

                # Try to remove the base temporary file with exponential backoff
                removed_base = False
                # Avoid deleting the final intended file if known
                if self.downloaded_filename and filename == self.downloaded_filename:
                    self.logger.debug(caller="CLIDownloadWorker", msg=f"Skipping removal of final file: {filename}")
                    continue # Skip to next filename in self.temporary_filenames
                
                if not os.path.exists(file_path):
                    removed_base = True # Already removed (e.g., by yt-dlp after merge)
                else:
                    for delay in (0.2, 0.5, 1, 2, 4):
                        try:
                            self.logger.debug(caller="CLIDownloadWorker", msg=f"Attempting remove (delay={delay}): {file_path}")
                            os.remove(file_path)
                            self.logger.info(caller="CLIDownloadWorker", msg=f"Removed temporary file: {filename}")
                            cleaned_count += 1
                            removed_base = True
                            break # Exit retry loop if successful
                        except PermissionError:
                            self.logger.warning(caller="CLIDownloadWorker", msg=f"File in use (delay={delay}), waiting: {filename}")
                            time.sleep(delay)
                        except FileNotFoundError:
                            removed_base = True
                            break
                        except Exception as e:
                            self.logger.error(caller="CLIDownloadWorker", msg=f"Error removing {file_path}: {str(e)}")
                            removed_base = True
                            break
                if not removed_base:
                    self.logger.warning(caller="CLIDownloadWorker", msg=f"Failed to remove {filename} after retries.")
                    
            except Exception as e:
                self.logger.error(caller="CLIDownloadWorker", msg=f"Error during cleanup preparation for {filename}: {str(e)}")
        
        # Fallback: Glob cleanup (remains the same, using prefixes)
        try:
            import glob
            
            if prefixes:
                self.logger.debug(caller="CLIDownloadWorker", msg=f"Using filename prefixes for targeted glob cleanup: {', '.join(prefixes)}")
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
                                self.logger.debug(caller="CLIDownloadWorker", msg=f"Found via glob with prefix '{prefix}': {file_path}")
                                os.remove(file_path)
                                self.logger.info(caller="CLIDownloadWorker", msg=f"Removed temporary file via glob: {os.path.basename(file_path)}")
                                cleaned_count += 1
                            except Exception as e:
                                # Log non-permission errors more visibly?
                                self.logger.warning(caller="CLIDownloadWorker", msg=f"Error removing glob match {os.path.basename(file_path)}: {str(e)}")
            else:
                self.logger.debug(caller="CLIDownloadWorker", msg="No valid prefixes for targeted glob cleanup")
        except Exception as e:
            self.logger.error(caller="CLIDownloadWorker", msg=f"Error during fallback glob cleanup: {str(e)}")
        
        if cleaned_count > 0:
            self.logger.info(caller="CLIDownloadWorker", msg=f"Cleanup finished, removed {cleaned_count} files/parts.")
        else:
            if self.temporary_filenames:
                 self.logger.info(caller="CLIDownloadWorker", msg="Cleanup finished, no matching temporary files found or removed.")
        
    def cancel(self):
        """Cancel the download - Sets flag. Actual termination/cleanup happens in _execute_download."""
        if self.cancelled: # Prevent double execution
            return
            
        # Set the flag first - this is used by the main worker thread
        self.cancelled = True
        self.logger.info(caller="CLIDownloadWorker", msg=f"Cancel requested for {self.url}. Worker will terminate and cleanup.")
        
        # DO NOT start a thread here.
        # The main _execute_download loop will detect self.cancelled and handle termination/cleanup.
        
    def _check_if_already_downloaded(self, output_lines, stderr_content=None):
        """
        Check if the output contains messages indicating the file has already been downloaded.
        
        Args:
            output_lines (list): List of output lines to check
            stderr_content (str, optional): Additional error output to check
            
        Returns:
            tuple: (already_exists, filename) - Boolean if already exists, and filename if detected
        """
        already_exists = False
        detected_filename = None
        
        # Pattern to match file paths. This pattern looks for a drive letter,
        # followed by a colon and backslash, then any characters that are not
        # invalid in a filename, and stops before " has already been downloaded".
        path_pattern = r'([A-Za-z]:\\[^"<>|:*?\r\n]+?)(?=\s+has already been downloaded)'
        
        # First check output lines
        for line in output_lines:
            if "has already been downloaded" in line:
                already_exists = True
                
                # Try to extract the filename using regex for Windows paths
                import re
                matches = re.findall(path_pattern, line)
                if matches:
                    file_path = matches[0]
                    self.logger.info(caller="CLIDownloadWorker", msg=f"Found file path: {file_path}")
                    detected_filename = os.path.basename(file_path)
                break
        
        # If not found in output lines, check stderr
        if not already_exists and stderr_content:
            if "has already been downloaded" in stderr_content:
                already_exists = True
                
                # Try to extract the filename from stderr
                import re
                matches = re.findall(path_pattern, stderr_content)
                if matches:
                    file_path = matches[0]
                    self.logger.info(caller="CLIDownloadWorker", msg=f"Found file path in stderr: {file_path}")
                    detected_filename = os.path.basename(file_path)
        
        # If we found it exists but couldn't get filename, log this
        if already_exists and not detected_filename:
            self.logger.warning(caller="CLIDownloadWorker", msg="File exists but couldn't extract filename from output")
            
        return already_exists, detected_filename
        