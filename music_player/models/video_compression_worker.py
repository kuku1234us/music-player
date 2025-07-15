"""
Worker classes for video compression operations.
"""
import os
import re
import subprocess
import time
from typing import Optional, List
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from .video_compression_task import VideoCompressionTask, CompressionStatus
from .video_file_utils import format_file_size
from .ffmpeg_utils import (
    validate_ffmpeg_path, 
    get_ffmpeg_version, 
    get_video_duration,
    build_compression_command,
    parse_ffmpeg_progress,
    parse_ffmpeg_error
)

class VideoCompressionWorkerSignals(QObject):
    """
    Signals for the VideoCompressionWorker.
    
    These signals are used to communicate progress and status updates
    from the worker thread back to the main thread.
    """
    # Worker lifecycle signals
    worker_started = pyqtSignal(str)  # task_id
    worker_finished = pyqtSignal(str)  # task_id
    worker_failed = pyqtSignal(str, str)  # task_id, error_message
    worker_cancelled = pyqtSignal(str)  # task_id
    
    # Progress signals
    progress_updated = pyqtSignal(str, float)  # task_id, progress (0.0-1.0)
    
    # Status signals
    status_message = pyqtSignal(str, str)  # task_id, message
    
    # File operation signals
    compression_started = pyqtSignal(str, str)  # task_id, input_filename
    compression_completed = pyqtSignal(str, str, str)  # task_id, input_filename, output_filename
    
class VideoCompressionWorker(QRunnable):
    """
    Worker class that performs video compression in a background thread.
    
    This class handles the actual FFmpeg execution, progress monitoring,
    and file operations for a single video compression task.
    """
    
    def __init__(self, task: VideoCompressionTask, ffmpeg_path: str = "ffmpeg"):
        """
        Initialize the worker with a compression task.
        
        Args:
            task: VideoCompressionTask to process
            ffmpeg_path: Path to FFmpeg executable
        """
        super().__init__()
        self.task = task
        self.ffmpeg_path = ffmpeg_path
        self.cancelled = False
        self.process: Optional[subprocess.Popen] = None
        self.signals = VideoCompressionWorkerSignals()
        
        # Progress tracking
        self.total_duration_seconds: Optional[float] = None
        self.last_progress_update = 0.0
        
        # FFmpeg validation
        self.ffmpeg_validated = False
        self.ffmpeg_version = ""
        
    def run(self):
        """
        Main worker method that runs in a separate thread.
        
        This method orchestrates the entire compression process:
        1. Validate inputs and FFmpeg
        2. Get video duration
        3. Execute FFmpeg compression
        4. Handle file operations
        5. Clean up
        """
        print(f"[VideoCompressionWorker] Starting compression for task: {self.task.task_id}")
        
        try:
            # Mark task as started
            self.task.mark_started()
            self.signals.worker_started.emit(self.task.task_id)
            self.signals.compression_started.emit(self.task.task_id, self.task.original_filename)
            
            # Validate inputs and FFmpeg
            self._validate_inputs()
            
            if self.cancelled:
                self._handle_cancellation()
                return
            
            # Get video duration for progress calculation
            self._get_video_duration()
            
            if self.cancelled:
                self._handle_cancellation()
                return
            
            # Execute compression
            self._compress_video()
            
            if self.cancelled:
                self._handle_cancellation()
                return
            
            # Handle file operations (rename, delete original)
            final_output_path = self._handle_file_operations()
            
            # Mark as completed
            compressed_size = 0
            if os.path.exists(final_output_path):
                compressed_size = os.path.getsize(final_output_path)
            
            self.task.mark_completed(compressed_size)
            self.signals.compression_completed.emit(
                self.task.task_id, 
                self.task.original_filename, 
                os.path.basename(final_output_path)
            )
            
            print(f"[VideoCompressionWorker] Compression completed: {self.task.original_filename}")
            
        except Exception as e:
            error_msg = str(e)
            print(f"[VideoCompressionWorker] Compression failed: {error_msg}")
            self.task.mark_failed(error_msg)
            self.signals.worker_failed.emit(self.task.task_id, error_msg)
            
            # Clean up temporary files on error
            self._cleanup_temp_files()
            
        finally:
            self.signals.worker_finished.emit(self.task.task_id)
    
    def cancel(self):
        """
        Cancel the compression operation.
        
        This method sets the cancellation flag and terminates any running FFmpeg process.
        """
        print(f"[VideoCompressionWorker] Cancellation requested for task: {self.task.task_id}")
        self.cancelled = True
        
        # Terminate FFmpeg process if running
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                # Give it a moment to terminate gracefully
                time.sleep(0.5)
                if self.process.poll() is None:
                    self.process.kill()
            except Exception as e:
                print(f"[VideoCompressionWorker] Error terminating process: {e}")
    
    def _validate_inputs(self):
        """Validate input file, output directory, and FFmpeg installation."""
        # Validate input file
        if not os.path.exists(self.task.input_path):
            raise Exception(f"Input file does not exist: {self.task.input_path}")
        
        if not os.path.isfile(self.task.input_path):
            raise Exception(f"Input path is not a file: {self.task.input_path}")
        
        # Check file size (avoid processing empty files)
        if os.path.getsize(self.task.input_path) == 0:
            raise Exception(f"Input file is empty: {self.task.input_path}")
        
        # Validate output directory
        output_dir = os.path.dirname(self.task.output_path)
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
            except Exception as e:
                raise Exception(f"Cannot create output directory {output_dir}: {e}")
        
        # Check write permissions
        if not os.access(output_dir, os.W_OK):
            raise Exception(f"No write permission for output directory: {output_dir}")
        
        # Validate FFmpeg installation
        self._validate_ffmpeg()
    
    def _validate_ffmpeg(self):
        """Validate FFmpeg installation and capabilities."""
        if self.ffmpeg_validated:
            return
        
        # Check if FFmpeg is available and working
        is_valid, error_msg = validate_ffmpeg_path(self.ffmpeg_path)
        if not is_valid:
            raise Exception(f"FFmpeg validation failed: {error_msg}")
        
        # Get version information
        self.ffmpeg_version = get_ffmpeg_version(self.ffmpeg_path) or "unknown"
        
        self.ffmpeg_validated = True
        print(f"[VideoCompressionWorker] FFmpeg validated: {self.ffmpeg_path} (version: {self.ffmpeg_version})")
    
    def _get_video_duration(self):
        """Get the total duration of the video for progress calculation."""
        self.total_duration_seconds = get_video_duration(self.task.input_path, self.ffmpeg_path)
        
        if self.total_duration_seconds:
            print(f"[VideoCompressionWorker] Video duration: {self.total_duration_seconds:.2f} seconds")
        else:
            print("[VideoCompressionWorker] Could not determine video duration")
    
    def _build_ffmpeg_command(self) -> List[str]:
        """
        Build the FFmpeg command for video compression.
        
        Returns:
            List[str]: FFmpeg command arguments
        """
        return build_compression_command(self.task.input_path, self.task.output_path, self.ffmpeg_path)
    
    def _compress_video(self):
        """Execute the FFmpeg compression command with enhanced error handling."""
        cmd = self._build_ffmpeg_command()
        
        print(f"[VideoCompressionWorker] Starting FFmpeg compression...")
        print(f"[VideoCompressionWorker] Command: {' '.join(cmd)}")
        
        try:
            # Enhanced subprocess configuration for Unicode filename support
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True,
                encoding='utf-8',           # Explicit UTF-8 encoding
                errors='replace',           # Handle encoding errors gracefully
                bufsize=1,                  # Line buffered
                # Hide console window on Windows
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # Monitor progress
            self._monitor_ffmpeg_progress()
            
            # Wait for completion
            stdout, stderr = self.process.communicate()
            
            if self.cancelled:
                return
            
            # Check return code
            if self.process.returncode != 0:
                error_msg = self._parse_ffmpeg_error(stderr, self.process.returncode)
                raise Exception(error_msg)
            
            # Verify output file was created and is valid
            self._verify_output_file()
            
        except subprocess.TimeoutExpired:
            raise Exception("FFmpeg process timed out")
        except Exception as e:
            if not self.cancelled:
                raise e
    
    def _parse_ffmpeg_error(self, stderr: str, return_code: int) -> str:
        """
        Parse FFmpeg error output to provide meaningful error messages.
        
        Args:
            stderr: FFmpeg stderr output
            return_code: Process return code
            
        Returns:
            str: Human-readable error message
        """
        return parse_ffmpeg_error(stderr, return_code)
    
    def _verify_output_file(self):
        """Verify that the output file was created successfully."""
        if not os.path.exists(self.task.output_path):
            raise Exception("Output file was not created")
        
        output_size = os.path.getsize(self.task.output_path)
        if output_size == 0:
            raise Exception("Output file is empty")
        
        # Basic sanity check - output should be smaller than input for compression
        # But allow for cases where it might be larger (e.g., very short videos)
        input_size = os.path.getsize(self.task.input_path)
        if output_size > input_size * 2:  # Allow up to 2x size increase
            print(f"[VideoCompressionWorker] Warning: Output file ({format_file_size(output_size)}) is larger than input ({format_file_size(input_size)})")
        
        print(f"[VideoCompressionWorker] Output file created: {format_file_size(output_size)}")
    
    def _monitor_ffmpeg_progress(self):
        """Monitor FFmpeg progress and emit progress signals with improved parsing."""
        if not self.process or not self.process.stderr:
            return
        
        try:
            while True:
                if self.cancelled:
                    break
                
                line = self.process.stderr.readline()
                if not line:
                    break
                
                # Parse progress from FFmpeg output
                progress = self._parse_ffmpeg_progress(line)
                if progress is not None:
                    self.task.update_progress(progress)
                    
                    # Emit progress update (throttled to avoid too many signals)
                    if progress - self.last_progress_update >= 0.01:  # Update every 1%
                        self.signals.progress_updated.emit(self.task.task_id, progress)
                        self.last_progress_update = progress
                
        except Exception as e:
            print(f"[VideoCompressionWorker] Error monitoring progress: {e}")
    
    def _parse_ffmpeg_progress(self, line: str) -> Optional[float]:
        """
        Parse FFmpeg output to extract progress percentage.
        
        Args:
            line: Line of FFmpeg output
            
        Returns:
            Optional[float]: Progress value between 0.0 and 1.0, or None
        """
        return parse_ffmpeg_progress(line, self.total_duration_seconds)
    
    def _handle_file_operations(self) -> str:
        """
        Handle file operations after successful compression with enhanced error handling.
        
        Returns:
            str: Path to the final output file
        """
        final_output_path = self.task.get_final_output_path()
        
        try:
            # Verify compressed file exists and is valid
            if not os.path.exists(self.task.output_path):
                raise Exception("Compressed file does not exist")
            
            compressed_size = os.path.getsize(self.task.output_path)
            if compressed_size == 0:
                raise Exception("Compressed file is empty")
            
            # Handle filename conflicts
            original_final_path = final_output_path
            if os.path.exists(final_output_path) and final_output_path != self.task.output_path:
                # Check if the conflict is with the original input file
                if os.path.abspath(final_output_path) == os.path.abspath(self.task.input_path):
                    # This is expected - we want to replace the original file
                    print(f"[VideoCompressionWorker] Will replace original file: {os.path.basename(final_output_path)}")
                else:
                    # Genuine conflict with a different file, need to resolve
                    base_path = Path(final_output_path)
                    counter = 1
                    while os.path.exists(final_output_path):
                        final_output_path = str(base_path.parent / f"{base_path.stem}_{counter}{base_path.suffix}")
                        counter += 1
                        if counter > 1000:  # Prevent infinite loop
                            raise Exception("Too many filename conflicts")
                    
                    if final_output_path != original_final_path:
                        print(f"[VideoCompressionWorker] Filename conflict resolved: {os.path.basename(final_output_path)}")
            
            # Handle the case where we need to replace the original file
            if os.path.abspath(final_output_path) == os.path.abspath(self.task.input_path):
                # Delete original file first since we want to replace it
                try:
                    os.remove(self.task.input_path)
                    print(f"[VideoCompressionWorker] Deleted original file: {self.task.original_filename}")
                except Exception as e:
                    print(f"[VideoCompressionWorker] Warning: Could not delete original file: {e}")
                    # If we can't delete the original, we'll need a different filename
                    base_path = Path(final_output_path)
                    counter = 1
                    while os.path.exists(final_output_path):
                        final_output_path = str(base_path.parent / f"{base_path.stem}_{counter}{base_path.suffix}")
                        counter += 1
                        if counter > 1000:  # Prevent infinite loop
                            raise Exception("Too many filename conflicts")
                    print(f"[VideoCompressionWorker] Using alternative filename: {os.path.basename(final_output_path)}")
            
            # Rename compressed file to final name
            if self.task.output_path != final_output_path:
                os.rename(self.task.output_path, final_output_path)
                print(f"[VideoCompressionWorker] Renamed to: {os.path.basename(final_output_path)}")
            
            # Delete original file (only if we haven't already deleted it above)
            if os.path.abspath(final_output_path) != os.path.abspath(self.task.input_path) and os.path.exists(self.task.input_path):
                try:
                    os.remove(self.task.input_path)
                    print(f"[VideoCompressionWorker] Deleted original file: {self.task.original_filename}")
                except Exception as e:
                    print(f"[VideoCompressionWorker] Warning: Could not delete original file: {e}")
                    # Don't fail the entire operation if we can't delete the original
            
            return final_output_path
            
        except Exception as e:
            # Clean up compressed file on error
            if os.path.exists(self.task.output_path):
                try:
                    os.remove(self.task.output_path)
                except:
                    pass
            raise Exception(f"File operation failed: {e}")
    
    def _handle_cancellation(self):
        """Handle cancellation cleanup."""
        self.task.mark_cancelled()
        self.signals.worker_cancelled.emit(self.task.task_id)
        self._cleanup_temp_files()
    
    def _cleanup_temp_files(self):
        """Clean up temporary files."""
        if os.path.exists(self.task.output_path):
            try:
                os.remove(self.task.output_path)
                print(f"[VideoCompressionWorker] Cleaned up temp file: {self.task.output_path}")
            except Exception as e:
                print(f"[VideoCompressionWorker] Error cleaning up temp file: {e}") 