"""
Manages the queue and execution of media conversion tasks using FFmpeg.
"""
import os
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Any, Tuple # Added Any for file_info type hint, Tuple for queue items
import time # For timestamp in log file
import queue as Queue # Explicitly import queue to avoid conflict with self.queue
from qt_base_app.models.logger import Logger

from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool, QTimer

# --- NEW: Import SettingsManager and setting definition ---
from qt_base_app.models.settings_manager import SettingsManager, SettingType
from music_player.models.settings_defs import CONVERSION_MP3_BITRATE_KEY, DEFAULT_CONVERSION_MP3_BITRATE
# --- END NEW ---

@dataclass
class ConversionTask:
    """Holds information for a single file conversion task."""
    input_filepath: Path
    output_filepath: Path
    original_filename: str
    task_id: str # Unique ID for the task, e.g., derived from input_filepath
    status: str = "pending" # pending, converting, completed, failed
    progress: float = 0.0 # 0.0 to 1.0
    error_message: Optional[str] = None
    total_duration_ms: Optional[int] = None # To be fetched by ffprobe

class ConversionWorkerSignals(QObject):
    """Signals emitted by the ConversionWorker."""
    worker_progress = pyqtSignal(str, float) # task_id, percentage
    worker_completed = pyqtSignal(str, Path)   # task_id, output_filepath
    worker_failed = pyqtSignal(str, str)     # task_id, error_message
    worker_duration_found = pyqtSignal(str, int) # task_id, duration_ms

class ConversionWorker(QRunnable):
    """Worker to perform a single FFmpeg conversion in a separate thread."""
    def __init__(self, task: ConversionTask, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        super().__init__()
        self.task = task
        self.signals = ConversionWorkerSignals()
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.is_cancelled = False
        self.log_file_handle = None # For shared log file access

        # --- NEW: Get bitrate from settings --- #
        settings = SettingsManager.instance()
        self.mp3_bitrate_kbps = settings.get(CONVERSION_MP3_BITRATE_KEY, 
                                             DEFAULT_CONVERSION_MP3_BITRATE, 
                                             SettingType.INT)
        # --- END NEW ---

        # Define known progress keys to avoid spamming warnings for expected but unused keys
        self.known_progress_keys = {
            "bitrate", "total_size", "out_time_us", "out_time_ms", "out_time",
            "dup_frames", "drop_frames", "speed", "progress"
        }

    def _threaded_stream_reader(self, pipe, stream_name: str, q: Queue.Queue):
        """Reads lines from a pipe, logs them, and puts them into a queue."""
        try:
            for line in iter(pipe.readline, ''):
                stripped_line = line.strip()
                if self.log_file_handle and not self.log_file_handle.closed:
                    try:
                        self.log_file_handle.write(f"[{stream_name} RAW] {stripped_line}\\n")
                        self.log_file_handle.flush() # Flush frequently for real-time logging
                    except Exception as e_log:
                        Logger.instance().debug(caller="conversion_manager", msg=f"[ConversionWorker THREAD LOG ERR] {stream_name}: {e_log}")
                q.put((stream_name, stripped_line))
                if self.is_cancelled: # Check for cancellation within the loop
                    break
        except Exception as e:
            # Log error to main console and attempt to queue it for main thread logging
            error_msg = f"[{stream_name} THREAD ERR] Error reading stream: {e}"
            Logger.instance().error(caller="conversion_manager", msg=error_msg)
            if self.log_file_handle and not self.log_file_handle.closed:
                 try:
                    self.log_file_handle.write(error_msg + "\\n")
                    self.log_file_handle.flush()
                 except Exception as e_log_err:
                        Logger.instance().debug(caller="conversion_manager", msg=f"[ConversionWorker THREAD LOG ERR ON ERR] {stream_name}: {e_log_err}")
            q.put((stream_name, f"THREAD_ERROR: {e}")) # Signal error to main loop
        finally:
            if pipe:
                pipe.close()
            # Signal that this thread is done by putting a special marker (optional, but can be useful)
            q.put((stream_name, None)) # None indicates pipe closed for this stream
            Logger.instance().info(caller="ConversionWorker", msg=f"[ConversionWorker] {stream_name} reader thread finished.")

    def run(self):
        """Execute the FFmpeg conversion process."""
        self.task.status = "converting"
        
        log_file_path_str = "" # For logging closure error
        try:
            # --- File Logging Setup ---
            log_dir = Path("ffmpeg_logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            safe_filename = "".join(c if c.isalnum() else "_" for c in self.task.original_filename)
            log_file_path = log_dir / f"ffmpeg_conversion_{safe_filename}_{timestamp}.log"
            log_file_path_str = str(log_file_path)
            self.log_file_handle = open(log_file_path, 'w', encoding='utf-8')
            self._log_worker(f"Logging FFmpeg output to: {log_file_path}")
            # --- End File Logging Setup ---

            if not self._get_media_duration():
                # Error already emitted by _get_media_duration
                return # _get_media_duration will emit worker_failed

            command = [
                self.ffmpeg_path,
                "-i", str(self.task.input_filepath),
                "-b:a", f"{self.mp3_bitrate_kbps}k", "-vn", "-y",
                "-loglevel", "error",
                "-stats",
                "-progress", "pipe:1",
                str(self.task.output_filepath)
            ]
            self._log_worker(f"Starting FFmpeg for {self.task.original_filename}: {' '.join(command)}")
            
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8', errors='replace',
                bufsize=1, # Line buffered
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            self._log_worker(f"FFmpeg process started. PID: {process.pid}")

            if self.is_cancelled: # Check immediately after Popen
                self._log_worker("Cancelled immediately after FFmpeg process start.")
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill()
                self.signals.worker_failed.emit(self.task.task_id, "Conversion cancelled by user (at process start).")
                return

            stdout_q = Queue.Queue()
            stderr_q = Queue.Queue()

            import threading # Ensure threading is imported
            stdout_thread = threading.Thread(target=self._threaded_stream_reader, args=(process.stdout, "STDOUT", stdout_q))
            stderr_thread = threading.Thread(target=self._threaded_stream_reader, args=(process.stderr, "STDERR", stderr_q))

            stdout_thread.start()
            stderr_thread.start()

            progress_ended_flag = False
            
            # Main loop to process queue items
            # Keep running as long as process is alive or threads are alive or queues might still have data
            stdout_pipe_closed = False
            stderr_pipe_closed = False

            while True:
                if self.is_cancelled:
                    self._log_worker("Cancellation requested during processing. Terminating FFmpeg.")
                    if process.poll() is None: # Check if process is still running
                        process.terminate()
                    # Threads will exit as their pipes close or they see self.is_cancelled
                    break # Exit main processing loop

                line_processed = False
                try:
                    # Process stdout queue
                    stream_name, line = stdout_q.get_nowait()
                    line_processed = True
                    if line is None: # Pipe closed marker
                        stdout_pipe_closed = True
                        self._log_worker("STDOUT pipe closed signal received.")
                    elif "THREAD_ERROR:" in line:
                        self._log_worker(f"Error from STDOUT reader thread: {line}")
                        # Potentially treat as a major failure
                    elif line: # Actual data line
                        # self._log_worker(f"[STDOUT] {line}") # Logged by thread now
                        if "progress=end" in line:
                            self._log_worker(f"Detected 'progress=end' for {self.task.original_filename}")
                            progress_ended_flag = True
                            if self.task.progress < 1.0: # Ensure 100% is sent
                                self.task.progress = 1.0
                                self.signals.worker_progress.emit(self.task.task_id, 1.0)
                            # We can break here if FFmpeg guarantees no more important stdout after progress=end
                            # For safety, let's continue processing other queue items, but FFmpeg might close soon.
                        elif self.task.total_duration_ms and self.task.total_duration_ms > 0 and "out_time_ms=" in line:
                            self._parse_and_emit_progress(line)
                except Queue.Empty:
                    pass # stdout_q is empty

                try:
                    # Process stderr queue
                    stream_name, line = stderr_q.get_nowait()
                    line_processed = True
                    if line is None: # Pipe closed marker
                        stderr_pipe_closed = True
                        self._log_worker("STDERR pipe closed signal received.")
                    elif "THREAD_ERROR:" in line:
                        self._log_worker(f"Error from STDERR reader thread: {line}")
                    elif line: # Actual data line
                        # self._log_worker(f"[STDERR] {line}") # Logged by thread now
                        # Can add specific stderr parsing here if needed, e.g., for -stats output
                        if "Error" in line or "failed" in line.lower(): # Basic error check from stderr
                             self._log_worker(f"Potential error in STDERR: {line}")
                except Queue.Empty:
                    pass # stderr_q is empty

                # Loop termination conditions
                process_finished = process.poll() is not None
                if process_finished and stdout_pipe_closed and stderr_pipe_closed:
                    self._log_worker("Process finished and both stream pipes closed. Exiting loop.")
                    break
                
                if not line_processed and (process_finished and stdout_q.empty() and stderr_q.empty()):
                    # Process finished, threads might be done but not yet put None, queues are empty
                    # This is a fallback if pipe_closed signals are missed or threads exit uncleanly
                    self._log_worker("Process finished and queues empty. Exiting loop as fallback.")
                    break

                if not stdout_thread.is_alive() and stdout_pipe_closed and \
                   not stderr_thread.is_alive() and stderr_pipe_closed:
                   self._log_worker("Reader threads dead and pipes closed. Exiting loop.")
                   break

                time.sleep(0.05) # Short sleep to yield CPU

            # End of main processing loop

            self._log_worker("Waiting for reader threads to join...")
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
            if stdout_thread.is_alive(): self._log_worker("STDOUT reader thread did not join cleanly.")
            if stderr_thread.is_alive(): self._log_worker("STDERR reader thread did not join cleanly.")

            return_code = process.poll() # Get final return code if not already fetched
            if return_code is None: # If process hasn't terminated (e.g. due to cancellation not killing it fast enough)
                self._log_worker("Process poll is None after loop, waiting for process to terminate...")
                if not self.is_cancelled: # If not cancelled, give it a chance to finish
                     try:
                        process.wait(timeout=10) 
                        return_code = process.returncode
                     except subprocess.TimeoutExpired:
                        self._log_worker("Process wait timed out. Terminating.")
                        process.terminate()
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired: 
                            self._log_worker("Process kill after terminate timeout.")
                            process.kill()
                        return_code = process.returncode if process.returncode is not None else -1 # Indicate failure
                else: # Was cancelled, try to ensure it's dead
                    process.terminate()
                    try: process.wait(timeout=2); return_code = process.returncode
                    except subprocess.TimeoutExpired: process.kill(); return_code = -1


            self._log_worker(f"FFmpeg process ended. Return code: {return_code}")

            if self.is_cancelled: # If master cancel flag was set
                self.signals.worker_failed.emit(self.task.task_id, "Conversion cancelled by user.")
            elif return_code == 0:
                if not progress_ended_flag and self.task.progress < 1.0: # If we missed 'progress=end' but exited cleanly
                    self._log_worker("FFmpeg exited 0, but 'progress=end' not seen. Assuming success and setting 100%.")
                    self.signals.worker_progress.emit(self.task.task_id, 1.0)
                elif progress_ended_flag and self.task.progress < 1.0: # 'progress=end' seen but not yet 100%
                    self.signals.worker_progress.emit(self.task.task_id, 1.0)
                
                self.signals.worker_completed.emit(self.task.task_id, self.task.output_filepath)
            else:
                # Attempt to get final stderr if any was missed (unlikely with threaded reader)
                final_stderr = "N/A"
                # This part is risky if threads didn't close pipes properly.
                # For now, rely on what was queued or logged by threads.
                self.signals.worker_failed.emit(self.task.task_id, f"FFmpeg error (code {return_code}). Check logs at {log_file_path_str}")

        except FileNotFoundError: # For ffmpeg/ffprobe itself in Popen
            err_msg = f"FFmpeg/ffprobe not found. Ensure they are in PATH. Executable: {self.ffmpeg_path} or {self.ffprobe_path}"
            self._log_worker(f"ERROR: {err_msg}", is_critical=True)
            self.signals.worker_failed.emit(self.task.task_id, err_msg)
        except Exception as e:
            crit_err_msg = f"Critical execution error in ConversionWorker: {str(e)}"
            self._log_worker(f"CRITICAL ERROR: {crit_err_msg}", is_critical=True)
            self.signals.worker_failed.emit(self.task.task_id, crit_err_msg)
        finally:
            if self.log_file_handle and not self.log_file_handle.closed:
                try:
                    self._log_worker("Closing FFmpeg log file.", is_final=True)
                    self.log_file_handle.close()
                except Exception as e_close:
                    Logger.instance().error(caller="conversion_manager", msg=f"[ConversionWorker ERROR] Exception while closing log file {log_file_path_str}: {e_close}")
            
            # Fallback: ensure process is terminated if it's somehow still running
            if 'process' in locals() and process.poll() is None:
                self._log_worker("Process found running in final finally block. Terminating.", is_critical=True)
                process.terminate()
                time.sleep(0.1) # Give it a moment
                if process.poll() is None: process.kill()

    def _log_worker(self, message: str, is_critical: bool = False, is_final: bool = False):
        log_prefix = "[ConversionWorker]"
        if is_critical: log_prefix = "[ConversionWorker CRITICAL]"
        
        Logger.instance().debug(caller="conversion_manager", msg=f"{log_prefix} {message}")
        if self.log_file_handle and not self.log_file_handle.closed:
            try:
                self.log_file_handle.write(f"{log_prefix} {message}\\n")
                if not is_final: # Avoid flushing if we are about to close
                    self.log_file_handle.flush()
            except Exception as e:
                Logger.instance().error(caller="conversion_manager", msg=f"[ConversionWorker LOG ERR] Failed to write to worker log: {e}")

    def _get_media_duration(self) -> bool:
        """Uses ffprobe to get the media duration in milliseconds."""
        # Ensure log handle is valid before trying to use it
        if not self.log_file_handle or self.log_file_handle.closed:
            Logger.instance().debug(caller="conversion_manager", msg="[ConversionWorker CRITICAL] Log file not open in _get_media_duration.")
            # Can't emit worker_failed directly here as signals might not be connected yet
            # or it might be too early. The main run() should handle this.
            # Setting task error and returning False should be enough.
            self.task.error_message = "Log file not open for ffprobe."
            # Critical error, emit general failure for this task
            self.signals.worker_failed.emit(self.task.task_id, self.task.error_message)
            return False

        command = [
            self.ffprobe_path, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(self.task.input_filepath)
        ]
        try:
            self._log_worker(f"Getting duration with command: {' '.join(command)}")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            stdout, stderr = process.communicate(timeout=15)

            if process.returncode == 0 and stdout:
                duration_sec_str = stdout.strip()
                if not duration_sec_str or duration_sec_str.lower() == 'n/a':
                    msg = f"ffprobe returned empty or 'N/A' for duration of {self.task.original_filename}"
                    self._log_worker(msg)
                    self.signals.worker_failed.emit(self.task.task_id, msg)
                    return False
                try:
                    duration_sec = float(duration_sec_str)
                    self.task.total_duration_ms = int(duration_sec * 1000)
                    self._log_worker(f"Duration for {self.task.original_filename}: {self.task.total_duration_ms} ms")
                    self.signals.worker_duration_found.emit(self.task.task_id, self.task.total_duration_ms)
                    return True
                except ValueError:
                    msg = f"ffprobe returned invalid duration value '{duration_sec_str}' for {self.task.original_filename}"
                    self._log_worker(msg)
                    self.signals.worker_failed.emit(self.task.task_id, msg)
                    return False
            else:
                msg = f"ffprobe failed for {self.task.original_filename}. Error: {stderr.strip()}"
                self._log_worker(msg)
                self.signals.worker_failed.emit(self.task.task_id, msg)
                return False
        except subprocess.TimeoutExpired:
            msg = f"ffprobe timed out for {self.task.original_filename}"
            self._log_worker(msg)
            self.signals.worker_failed.emit(self.task.task_id, msg)
            return False
        except FileNotFoundError:
            msg = f"{self.ffprobe_path} not found. Ensure it is in PATH."
            self._log_worker(msg, is_critical=True)
            self.signals.worker_failed.emit(self.task.task_id, msg)
            return False
        except Exception as e:
            msg = f"Exception running ffprobe for {self.task.original_filename}: {e}"
            self._log_worker(msg, is_critical=True)
            self.signals.worker_failed.emit(self.task.task_id, msg)
            return False

    def _parse_and_emit_progress(self, line: str):
        """Parses a line from FFmpeg's -progress output (stdout) and emits signal."""
        # Called from the main run() loop when an stdout line is processed from the queue.
        if not (self.task.total_duration_ms and self.task.total_duration_ms > 0):
            return # Cannot calculate progress without total duration

        try:
            # Example line: out_time_ms=12345678
            if 'out_time_ms=' in line:
                value_str = line.split('out_time_ms=')[1].split()[0].strip()
                current_progress_value_us = int(value_str) # This is actually microseconds from ffmpeg's pipe:1
                current_progress_ms = current_progress_value_us / 1000.0

                progress = 0.0
                if self.task.total_duration_ms > 0: # Should always be true if we reached here
                    progress = min(1.0, current_progress_ms / self.task.total_duration_ms)
                
                # Emit progress if it has changed significantly or is 1.0
                if abs(progress - self.task.progress) > 0.005 or \
                   (progress >= 0.999 and self.task.progress < 0.999): # Check for near 1.0 too
                    self.task.progress = progress
                    self.signals.worker_progress.emit(self.task.task_id, progress)
            # else:
                # Other lines from -progress pipe:1 (bitrate, speed, etc.) can be parsed here if needed
                # For now, we only care about out_time_ms for percentage.
        except (ValueError, IndexError) as e:
            self._log_worker(f"WARNING: Malformed progress line: '{line}'. Error: {e}")

    def cancel(self):
        self._log_worker("Cancel method called.")
        self.is_cancelled = True
        # The running FFmpeg process will be terminated by the main loop in run()
        # when it detects self.is_cancelled.

class ConversionManager(QObject):
    # Signals for UI updates (from manager to UI)
    conversion_batch_started = pyqtSignal(int) # total_files
    # file_index is 0-based for the current batch
    conversion_file_started = pyqtSignal(str, str, int, int) # task_id, original_filename, file_index_in_batch, total_in_batch
    conversion_file_progress = pyqtSignal(str, float) # task_id, percentage (0.0 to 1.0)
    conversion_file_completed = pyqtSignal(str, str, str) # task_id, original_filename, output_filepath
    conversion_file_failed = pyqtSignal(str, str, str) # task_id, original_filename, error_message
    conversion_batch_finished = pyqtSignal()

    def __init__(self, parent=None, ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"):
        super().__init__(parent)
        self._task_queue: List[ConversionTask] = []
        self._active_tasks_map: Dict[str, ConversionTask] = {} # Maps task_id to task
        self._is_processing_queue = False
        self._current_batch_total = 0
        self._current_batch_processed_count = 0
        self.thread_pool = QThreadPool()
        # Consider max thread count if many conversions are added rapidly
        # self.thread_pool.setMaxThreadCount(max_concurrent_conversions)
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.active_worker: Optional[ConversionWorker] = None

    def start_conversions(self, files_info: List[Any], output_dir_str: str):
        """Adds files to the conversion queue and starts processing if not already active."""
        Logger.instance().debug(caller="ConversionManager", msg=f"[ConversionManager] Received {len(files_info)} files for conversion to '{output_dir_str}'.")
        output_dir = Path(output_dir_str)
        if not output_dir.is_dir():
            Logger.instance().debug(caller="ConversionManager", msg=f"[ConversionManager] Output directory {output_dir_str} is not valid. Aborting.")
            # Optionally emit a batch failed signal or an error signal
            return

        initial_queue_size = len(self._task_queue)
        new_tasks_added = 0

        for file_data in files_info:
            input_path_str = file_data.get('path')
            if not input_path_str:
                Logger.instance().debug(caller="ConversionManager", msg=f"[ConversionManager] Skipping item, missing 'path': {file_data}")
                continue
            
            input_filepath = Path(input_path_str)
            original_filename = input_filepath.name
            output_filename = f"{input_filepath.stem}.mp3"
            output_filepath = output_dir / output_filename
            task_id = str(input_filepath) # Use input path as unique ID for now

            # Avoid adding duplicate tasks if already in queue or active
            if any(t.task_id == task_id for t in self._task_queue) or task_id in self._active_tasks_map:
                Logger.instance().debug(caller="ConversionManager", msg=f"[ConversionManager] Task for {original_filename} already exists. Skipping.")
                continue

            task = ConversionTask(
                input_filepath=input_filepath,
                output_filepath=output_filepath,
                original_filename=original_filename,
                task_id=task_id
            )
            self._task_queue.append(task)
            new_tasks_added +=1

        if new_tasks_added == 0 and initial_queue_size == 0:
            Logger.instance().debug(caller="ConversionManager", msg="[ConversionManager] No new valid tasks to add and queue is empty.")
            return

        if not self._is_processing_queue:
            self._current_batch_total = len(self._task_queue) # Total for this new batch start
            self._current_batch_processed_count = 0
            if self._current_batch_total > 0:
                self.conversion_batch_started.emit(self._current_batch_total)
                self._process_next_task()
        else:
            # If already processing, the new tasks will be picked up. 
            # Update batch total if this is considered part of the ongoing batch
            # For simplicity now, let's assume `conversion_batch_started` is only for new batch starts.
            # A more robust approach might involve a global task counter or batch IDs.
            Logger.instance().debug(caller="ConversionManager", msg=f"[ConversionManager] Added {new_tasks_added} tasks to active queue. Current queue size: {len(self._task_queue)}")

    def _process_next_task(self):
        if not self._task_queue:
            Logger.instance().info(caller="ConversionManager", msg="[ConversionManager] Queue is empty. Batch processing finished.")
            self._is_processing_queue = False
            self.active_worker = None
            if self._current_batch_total > 0: # Ensure batch_finished is only emitted if a batch was started
                self.conversion_batch_finished.emit()
                self._current_batch_total = 0 # Reset for next batch
            return

        self._is_processing_queue = True
        task = self._task_queue.pop(0) # Get the next task from the front
        self._active_tasks_map[task.task_id] = task
        self.active_worker = ConversionWorker(task, self.ffmpeg_path, self.ffprobe_path)

        # Connect worker signals to manager's handlers
        self.active_worker.signals.worker_duration_found.connect(self._on_worker_duration_found)
        self.active_worker.signals.worker_progress.connect(self._on_worker_progress)
        self.active_worker.signals.worker_completed.connect(self._on_worker_completed)
        self.active_worker.signals.worker_failed.connect(self._on_worker_failed)

        # Emit file started (manager's signal for UI)
        # file_index_in_batch should be based on how many were processed in *this specific batch start*
        file_index_in_batch = self._current_batch_processed_count
        self.conversion_file_started.emit(task.task_id, task.original_filename, file_index_in_batch, self._current_batch_total)
        
        self.thread_pool.start(self.active_worker)

    def _on_worker_duration_found(self, task_id: str, duration_ms: int):
        if task_id in self._active_tasks_map:
            task = self._active_tasks_map[task_id]
            task.total_duration_ms = duration_ms
            Logger.instance().debug(caller="ConversionManager", msg=f"[ConversionManager] Duration updated for {task.original_filename}: {duration_ms}ms")

    def _on_worker_progress(self, task_id: str, percentage: float):
        if task_id in self._active_tasks_map:
            task = self._active_tasks_map[task_id]
            task.progress = percentage
            self.conversion_file_progress.emit(task_id, percentage)

    def _on_worker_completed(self, task_id: str, output_filepath: Path):
        if task_id in self._active_tasks_map:
            task = self._active_tasks_map.pop(task_id) # Remove from active
            task.status = "completed"
            task.progress = 1.0
            self._current_batch_processed_count += 1
            Logger.instance().info(caller="ConversionManager", msg=f"[ConversionManager] Completed: {task.original_filename} -> {output_filepath}")
            self.conversion_file_completed.emit(task_id, task.original_filename, str(output_filepath))
            self._process_next_task() # Start next one
        self.active_worker = None

    def _on_worker_failed(self, task_id: str, error_message: str):
        if task_id in self._active_tasks_map:
            task = self._active_tasks_map.pop(task_id) # Remove from active
            task.status = "failed"
            task.error_message = error_message
            self._current_batch_processed_count += 1
            # Don't print error if it's a cancellation message, it's already logged by worker
            if "cancelled by user" not in error_message.lower():
                Logger.instance().error(caller="ConversionManager", msg=f"[ConversionManager] Failed: {task.original_filename}. Error: {error_message}")
            self.conversion_file_failed.emit(task_id, task.original_filename, error_message)
            self._process_next_task() # Start next one, even if one failed
        self.active_worker = None

    def cancel_all_conversions(self):
        """Stops the current conversion and clears the queue."""
        Logger.instance().debug(caller="ConversionManager", msg="[ConversionManager] Conversion cancellation requested by user.")
        tasks_cancelled_count = 0

        # Clear pending tasks from the queue first
        if self._task_queue:
            tasks_cancelled_count += len(self._task_queue)
            Logger.instance().debug(caller="ConversionManager", msg=f"[ConversionManager] Clearing {len(self._task_queue)} pending tasks from queue due to cancellation.")
            # For each task that was pending, we could emit a failure/cancelled signal
            # This ensures the UI (batch count) can be updated if it relies on individual file signals.
            for task in list(self._task_queue): # Iterate over a copy for safe removal
                self.conversion_file_failed.emit(task.task_id, task.original_filename, "Conversion cancelled by user (was pending).")
                self._current_batch_processed_count +=1 # Account for it in batch progress
            self._task_queue.clear()
        
        # Cancel active worker if any
        if self.active_worker and hasattr(self.active_worker, 'cancel'):
            Logger.instance().debug(caller="ConversionManager", msg="[ConversionManager] Sending cancel signal to active worker.")
            self.active_worker.cancel() # This will trigger the worker to terminate and emit its own failure signal
            # The worker's failure will then call _process_next_task, which will find an empty queue
            # and then emit conversion_batch_finished if appropriate.
            tasks_cancelled_count +=1 # The active task is also considered cancelled
        elif not self._is_processing_queue and not self._task_queue:
             Logger.instance().debug(caller="ConversionManager", msg="[ConversionManager] No active conversion or pending tasks to cancel at this moment.")
             # If a batch was started but nothing was actually running/queued, and user hits cancel,
             # ensure batch_finished is still emitted to clean up UI (e.g. hide cancel button)
             if self._current_batch_total > 0 and self._current_batch_processed_count == 0:
                 Logger.instance().info(caller="ConversionManager", msg="[ConversionManager] Emitting batch_finished due to cancellation with no active/pending tasks.")
                 self.conversion_batch_finished.emit()
                 self._current_batch_total = 0 # Reset batch tracking
        
        if tasks_cancelled_count == 0 and not (self._current_batch_total > 0 and self._current_batch_processed_count == 0) :
            Logger.instance().debug(caller="ConversionManager", msg="[ConversionManager] No tasks were actively cancelled or pending to clear.")
            # If nothing was cancelled but a batch is technically in progress (e.g., one file just finished, next hasn't started)
            # and _process_next_task hasn't run yet for an empty queue, we might need to ensure batch_finished if queue is now empty.
            if not self._task_queue and not self.active_worker:
                 Logger.instance().debug(caller="ConversionManager", msg="[ConversionManager] Queue is empty and no active worker after cancel request. Forcing batch finish check.")
                 # This call will check the queue and potentially emit batch_finished
                 self._process_next_task() 

    # --- Methods to check FFmpeg/ffprobe (can be called from UI or on init) ---
    def check_ffmpeg_tools(self) -> dict:
        """Checks for ffmpeg and ffprobe executables and returns their status."""
        results = {"ffmpeg": None, "ffprobe": None, "ffmpeg_path": self.ffmpeg_path, "ffprobe_path": self.ffprobe_path}
        try:
            subprocess.run([self.ffmpeg_path, "-version"], capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            results["ffmpeg"] = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            results["ffmpeg"] = False
        except Exception as e:
            Logger.instance().error(caller="ConversionManager", msg=f"[ConversionManager] Error checking ffmpeg: {e}")
            results["ffmpeg"] = False # Mark as false on other errors too

        try:
            subprocess.run([self.ffprobe_path, "-version"], capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            results["ffprobe"] = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            results["ffprobe"] = False
        except Exception as e:
            Logger.instance().error(caller="ConversionManager", msg=f"[ConversionManager] Error checking ffprobe: {e}")
            results["ffprobe"] = False
        return results 