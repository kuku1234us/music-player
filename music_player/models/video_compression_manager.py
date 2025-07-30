"""
Manager class for video compression operations.
"""
import os
import shutil
import subprocess
from typing import List, Dict, Optional
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal, QThreadPool

from .video_compression_task import VideoCompressionTask, CompressionStatus
from .video_compression_worker import VideoCompressionWorker
from .video_file_utils import discover_video_files, validate_video_files, get_video_file_info
from .ffmpeg_utils import get_video_resolution

class VideoCompressionManager(QObject):
    """
    Manager class for coordinating video compression operations.
    
    This class handles:
    - File discovery and validation
    - Task creation and management
    - Worker thread coordination
    - Progress tracking and reporting
    - Cancellation handling
    """
    
    # Batch-level signals
    compression_batch_started = pyqtSignal(int)  # total_files
    compression_batch_finished = pyqtSignal()
    compression_batch_cancelled = pyqtSignal()
    
    # File-level signals
    compression_file_started = pyqtSignal(str, str, int, int)  # task_id, filename, index, total
    compression_file_progress = pyqtSignal(str, float)  # task_id, progress (0.0-1.0)
    compression_file_completed = pyqtSignal(str, str, str)  # task_id, original_filename, compressed_filename
    compression_file_failed = pyqtSignal(str, str, str)  # task_id, filename, error_message
    compression_file_cancelled = pyqtSignal(str, str)  # task_id, filename
    
    # Status signals
    status_message = pyqtSignal(str)  # status_message
    error_message = pyqtSignal(str)  # error_message
    
    def __init__(self, parent=None):
        """
        Initialize the VideoCompressionManager.
        
        Args:
            parent: Parent QObject
        """
        super().__init__(parent)
        
        # Task management
        self.tasks: Dict[str, VideoCompressionTask] = {}
        self.active_workers: Dict[str, VideoCompressionWorker] = {}
        self.current_batch_size = 0
        self.completed_tasks = 0
        self.failed_tasks = 0
        self.cancelled_tasks = 0
        
        # Thread pool for workers
        self.thread_pool = QThreadPool.globalInstance()
        
        # Configuration - simplified since FFmpeg is assumed to be in PATH
        self.ffmpeg_path = "ffmpeg"  # Use system PATH
        self.max_concurrent_workers = 1  # Process one file at a time to avoid overwhelming system
        
        # State
        self.is_batch_active = False
        self.batch_cancelled = False
        
        # Validate FFmpeg availability on initialization
        self._validate_ffmpeg_availability()
        
    def _validate_ffmpeg_availability(self):
        """
        Validate that FFmpeg is available in the system PATH.
        Since we assume it's installed, this is a simple check.
        """
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            if result.returncode == 0:
                print("[VideoCompressionManager] FFmpeg is available and ready")
                # Extract version for logging
                version_match = result.stdout.split('\n')[0]
                print(f"[VideoCompressionManager] {version_match}")
            else:
                print(f"[VideoCompressionManager] Warning: FFmpeg returned non-zero exit code: {result.returncode}")
        except FileNotFoundError:
            print("[VideoCompressionManager] Warning: FFmpeg not found in PATH")
        except subprocess.TimeoutExpired:
            print("[VideoCompressionManager] Warning: FFmpeg validation timed out")
        except Exception as e:
            print(f"[VideoCompressionManager] Warning: FFmpeg validation error: {e}")
    
    def start_compressions(self, selected_objects: List[Dict], output_directory: str):
        """
        Start compression process for selected items.
        
        Args:
            selected_objects: List of selected file/directory objects from browser
            output_directory: Directory where compressed files will be saved
        """
        if self.is_batch_active:
            self.error_message.emit("Compression batch is already active")
            return
        
        try:
            # Reset state
            self._reset_batch_state()
            
            # Validate output directory
            if not os.path.exists(output_directory):
                os.makedirs(output_directory, exist_ok=True)
            
            if not os.path.isdir(output_directory):
                self.error_message.emit(f"Invalid output directory: {output_directory}")
                return
            
            # Check write permissions
            if not os.access(output_directory, os.W_OK):
                self.error_message.emit(f"No write permission for output directory: {output_directory}")
                return
            
            # Extract file paths from selected objects
            selected_paths = self._extract_paths_from_objects(selected_objects)
            
            if not selected_paths:
                self.error_message.emit("No valid files or directories selected")
                return
            
            # Discover video files
            print(f"[VideoCompressionManager] Discovering video files in {len(selected_paths)} selected items")
            video_files = discover_video_files(selected_paths)
            
            if not video_files:
                self.error_message.emit("No video files found in the selected items")
                return
            
            # Validate video files
            valid_video_files = validate_video_files(video_files)
            
            if not valid_video_files:
                self.error_message.emit("No valid video files found")
                return
            
            # Filter out videos that do not need compression
            files_to_compress = self._filter_videos_for_compression(valid_video_files)

            if not files_to_compress:
                self.error_message.emit("No videos found that require compression (already 720p or smaller).")
                return

            # Check available disk space
            try:
                from .video_file_utils import format_file_size
                
                if output_directory:
                    stat = shutil.disk_usage(output_directory)
                    free_bytes = stat.free
                    
                    # Calculate total input file size
                    total_input_size = sum(task.original_size_bytes for task in self.tasks.values())
                    
                    # Estimate required space (assume compression might not reduce size significantly)
                    # Add 20% buffer for safety
                    required_space = int(total_input_size * 1.2)
                    
                    if free_bytes < required_space:
                        raise Exception(
                            f"Insufficient disk space. Required: {format_file_size(required_space)}, "
                            f"Available: {format_file_size(free_bytes)}"
                        )
                    
                    print(f"[VideoCompressionManager] Disk space check passed. Available: {format_file_size(free_bytes)}")
                
            except Exception as e:
                print(f"[VideoCompressionManager] Disk space check warning: {e}")
            
            # Create tasks
            tasks = self._create_tasks(files_to_compress, output_directory)
            
            if not tasks:
                self.error_message.emit("Failed to create compression tasks")
                return
            
            # Start batch processing
            self._start_batch_processing(tasks)
            
        except Exception as e:
            error_msg = f"Failed to start compression: {str(e)}"
            print(f"[VideoCompressionManager] {error_msg}")
            self.error_message.emit(error_msg)
    
    def cancel_all_compressions(self):
        """Cancel all ongoing compressions."""
        if not self.is_batch_active:
            return
        
        print("[VideoCompressionManager] Cancelling all compressions")
        self.batch_cancelled = True
        
        # Cancel all active workers
        for worker in self.active_workers.values():
            worker.cancel()
        
        # Mark all pending tasks as cancelled
        for task in self.tasks.values():
            if task.status == CompressionStatus.PENDING:
                task.mark_cancelled()
        
        self.compression_batch_cancelled.emit()
    
    def get_compression_status(self) -> Dict:
        """
        Get current compression status.
        
        Returns:
            Dict: Status information
        """
        return {
            'is_active': self.is_batch_active,
            'total_tasks': self.current_batch_size,
            'completed': self.completed_tasks,
            'failed': self.failed_tasks,
            'cancelled': self.cancelled_tasks,
            'active_workers': len(self.active_workers),
            'pending_tasks': len([t for t in self.tasks.values() if t.status == CompressionStatus.PENDING])
        }
    
    def set_ffmpeg_path(self, ffmpeg_path: str):
        """
        Set the path to the FFmpeg executable.
        
        Args:
            ffmpeg_path: Path to FFmpeg executable
        """
        self.ffmpeg_path = ffmpeg_path
        print(f"[VideoCompressionManager] FFmpeg path set to: {ffmpeg_path}")
        # Re-validate FFmpeg with new path
        self._validate_ffmpeg_availability()
    
    def set_max_concurrent_workers(self, max_workers: int):
        """
        Set the maximum number of concurrent compression workers.
        
        Args:
            max_workers: Maximum number of concurrent workers
        """
        self.max_concurrent_workers = max(1, max_workers)
        print(f"[VideoCompressionManager] Max concurrent workers set to: {self.max_concurrent_workers}")
    
    def get_estimated_time_remaining(self) -> Optional[float]:
        """
        Get estimated time remaining for the current batch.
        
        Returns:
            Optional[float]: Estimated seconds remaining, or None if not available
        """
        if not self.is_batch_active or self.completed_tasks == 0:
            return None
        
        # Calculate average time per completed task
        total_time = 0
        completed_count = 0
        
        for task in self.tasks.values():
            if task.status == CompressionStatus.COMPLETED:
                duration = task.get_duration_seconds()
                if duration:
                    total_time += duration
                    completed_count += 1
        
        if completed_count == 0:
            return None
        
        avg_time_per_task = total_time / completed_count
        remaining_tasks = self.current_batch_size - self.completed_tasks - self.failed_tasks
        
        return avg_time_per_task * remaining_tasks
    
    def _filter_videos_for_compression(self, video_files: List[str]) -> List[str]:
        """Filter list of videos to only include those that need compression."""
        files_to_compress = []
        for video_file in video_files:
            resolution = get_video_resolution(video_file, self.ffmpeg_path)
            if resolution:
                width, height = resolution
                # Compress if larger than 720p in any dimension
                if width > 720 or height > 720:
                    files_to_compress.append(video_file)
                else:
                    print(f"[VideoCompressionManager] Skipping already small video: {os.path.basename(video_file)} ({width}x{height})")
            else:
                # If resolution can't be determined, include it for processing by default
                print(f"[VideoCompressionManager] Could not determine resolution for {os.path.basename(video_file)}, including for compression.")
                files_to_compress.append(video_file)
        return files_to_compress

    def _reset_batch_state(self):
        """Reset state for a new batch."""
        self.tasks.clear()
        self.active_workers.clear()
        self.current_batch_size = 0
        self.completed_tasks = 0
        self.failed_tasks = 0
        self.cancelled_tasks = 0
        self.is_batch_active = False
        self.batch_cancelled = False
    
    def _extract_paths_from_objects(self, selected_objects: List[Dict]) -> List[str]:
        """
        Extract file paths from selected browser objects.
        
        Args:
            selected_objects: List of selected objects from browser table
            
        Returns:
            List[str]: List of file paths
        """
        paths = []
        
        for obj in selected_objects:
            if isinstance(obj, dict):
                path = obj.get('path')
                if path and os.path.exists(path):
                    paths.append(path)
            elif hasattr(obj, 'path'):
                path = getattr(obj, 'path')
                if path and os.path.exists(path):
                    paths.append(path)
        
        return paths
    
    def _create_tasks(self, video_files: List[str], output_directory: str) -> List[VideoCompressionTask]:
        """
        Create compression tasks for video files.
        
        Args:
            video_files: List of video file paths
            output_directory: Output directory for compressed files
            
        Returns:
            List[VideoCompressionTask]: List of created tasks
        """
        tasks = []
        total_files = len(video_files)
        
        for index, video_file in enumerate(video_files):
            try:
                task = VideoCompressionTask.create(
                    input_path=video_file,
                    output_directory=output_directory,
                    file_index=index,
                    total_files=total_files
                )
                tasks.append(task)
                self.tasks[task.task_id] = task
                
                print(f"[VideoCompressionManager] Created task {index + 1}/{total_files}: {task.original_filename}")
                
            except Exception as e:
                print(f"[VideoCompressionManager] Failed to create task for {video_file}: {e}")
        
        return tasks
    
    def _start_batch_processing(self, tasks: List[VideoCompressionTask]):
        """
        Start batch processing of compression tasks.
        
        Args:
            tasks: List of tasks to process
        """
        if not tasks:
            return
        
        self.current_batch_size = len(tasks)
        self.is_batch_active = True
        
        print(f"[VideoCompressionManager] Starting batch processing of {self.current_batch_size} files")
        
        # Emit batch started signal
        self.compression_batch_started.emit(self.current_batch_size)
        
        # Start processing tasks (respecting max concurrent workers)
        self._process_next_tasks()
    
    def _process_next_tasks(self):
        """Process the next available tasks up to the maximum concurrent limit."""
        if self.batch_cancelled:
            return
        
        # Find pending tasks
        pending_tasks = [task for task in self.tasks.values() if task.status == CompressionStatus.PENDING]
        
        # Start workers up to the concurrent limit
        while (len(self.active_workers) < self.max_concurrent_workers and 
               pending_tasks and 
               not self.batch_cancelled):
            
            task = pending_tasks.pop(0)
            self._start_worker_for_task(task)
    
    def _start_worker_for_task(self, task: VideoCompressionTask):
        """
        Start a worker for a specific task.
        
        Args:
            task: Task to process
        """
        try:
            worker = VideoCompressionWorker(task, self.ffmpeg_path)
            
            # Connect worker signals
            worker.signals.worker_started.connect(self._on_worker_started)
            worker.signals.worker_finished.connect(self._on_worker_finished)
            worker.signals.worker_failed.connect(self._on_worker_failed)
            worker.signals.worker_cancelled.connect(self._on_worker_cancelled)
            worker.signals.progress_updated.connect(self._on_progress_updated)
            worker.signals.compression_started.connect(self._on_compression_started)
            worker.signals.compression_completed.connect(self._on_compression_completed)
            
            # Add to active workers
            self.active_workers[task.task_id] = worker
            
            # Start the worker
            self.thread_pool.start(worker)
            
            print(f"[VideoCompressionManager] Started worker for task: {task.task_id}")
            
        except Exception as e:
            error_msg = f"Failed to start worker for {task.original_filename}: {str(e)}"
            print(f"[VideoCompressionManager] {error_msg}")
            task.mark_failed(error_msg)
            self.compression_file_failed.emit(task.task_id, task.original_filename, error_msg)
    
    def _on_worker_started(self, task_id: str):
        """Handle worker started signal."""
        task = self.tasks.get(task_id)
        if task:
            print(f"[VideoCompressionManager] Worker started for: {task.original_filename}")
    
    def _on_worker_finished(self, task_id: str):
        """Handle worker finished signal."""
        # Remove from active workers
        if task_id in self.active_workers:
            del self.active_workers[task_id]
        
        # Check if batch is complete
        self._check_batch_completion()
        
        # Start next task if available
        if not self.batch_cancelled:
            self._process_next_tasks()
    
    def _on_worker_failed(self, task_id: str, error_message: str):
        """Handle worker failed signal."""
        task = self.tasks.get(task_id)
        if task:
            self.failed_tasks += 1
            self.compression_file_failed.emit(task_id, task.original_filename, error_message)
            print(f"[VideoCompressionManager] Compression failed: {task.original_filename} - {error_message}")
    
    def _on_worker_cancelled(self, task_id: str):
        """Handle worker cancelled signal."""
        task = self.tasks.get(task_id)
        if task:
            self.cancelled_tasks += 1
            self.compression_file_cancelled.emit(task_id, task.original_filename)
            print(f"[VideoCompressionManager] Compression cancelled: {task.original_filename}")
    
    def _on_progress_updated(self, task_id: str, progress: float):
        """Handle progress update signal."""
        self.compression_file_progress.emit(task_id, progress)
    
    def _on_compression_started(self, task_id: str, filename: str):
        """Handle compression started signal."""
        task = self.tasks.get(task_id)
        if task:
            self.compression_file_started.emit(
                task_id, 
                filename, 
                task.file_index, 
                task.total_files
            )
    
    def _on_compression_completed(self, task_id: str, original_filename: str, compressed_filename: str):
        """Handle compression completed signal."""
        task = self.tasks.get(task_id)
        if task:
            self.completed_tasks += 1
            self.compression_file_completed.emit(task_id, original_filename, compressed_filename)
            
            # Log compression statistics
            if task.original_size_bytes > 0 and task.compressed_size_bytes > 0:
                reduction = task.get_size_reduction_percentage()
                duration = task.get_duration_seconds()
                from .video_file_utils import format_file_size
                
                stats = f"Size: {format_file_size(task.original_size_bytes)} -> {format_file_size(task.compressed_size_bytes)}"
                if reduction:
                    stats += f" ({reduction:.1f}% reduction)"
                if duration:
                    stats += f", Time: {duration:.1f}s"
                
                print(f"[VideoCompressionManager] Compression completed: {original_filename} -> {compressed_filename} ({stats})")
            else:
                print(f"[VideoCompressionManager] Compression completed: {original_filename} -> {compressed_filename}")
    
    def _check_batch_completion(self):
        """Check if the batch is complete and emit appropriate signals."""
        if not self.is_batch_active:
            return
        
        # Check if all tasks are finished
        finished_tasks = [task for task in self.tasks.values() if task.is_finished()]
        
        if len(finished_tasks) == self.current_batch_size:
            self.is_batch_active = False
            
            if self.batch_cancelled:
                print("[VideoCompressionManager] Batch cancelled")
                self.compression_batch_cancelled.emit()
            else:
                print(f"[VideoCompressionManager] Batch completed - {self.completed_tasks} completed, {self.failed_tasks} failed")
                self.compression_batch_finished.emit()
    
    def __del__(self):
        """Cleanup when manager is destroyed."""
        if hasattr(self, 'active_workers'):
            for worker in self.active_workers.values():
                worker.cancel() 