"""
Data structure for video compression tasks.
"""
import os
import uuid
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from enum import Enum

class CompressionStatus(Enum):
    """Status enum for compression tasks."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class VideoCompressionTask:
    """
    Data structure representing a single video compression task.
    
    This class contains all the information needed to track and execute
    a video compression operation, including input/output paths, progress,
    and status information.
    """
    
    # Core task information
    task_id: str
    input_path: str
    output_path: str
    file_index: int
    total_files: int
    
    # Status and progress tracking
    status: CompressionStatus = CompressionStatus.PENDING
    progress: float = 0.0
    error_message: str = ""
    
    # File information
    original_filename: str = ""
    original_size_bytes: int = 0
    compressed_size_bytes: int = 0
    
    # Timing information
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    def __post_init__(self):
        """Initialize computed fields after dataclass creation."""
        if not self.original_filename:
            self.original_filename = os.path.basename(self.input_path)
        
        # Get original file size if file exists
        if not self.original_size_bytes and os.path.exists(self.input_path):
            try:
                self.original_size_bytes = os.path.getsize(self.input_path)
            except (OSError, IOError):
                self.original_size_bytes = 0
    
    @classmethod
    def create(cls, input_path: str, output_directory: str, file_index: int, total_files: int):
        """
        Create a new VideoCompressionTask.
        
        Args:
            input_path: Path to the input video file
            output_directory: Base output directory (not used, preserved for compatibility)
            file_index: Index of this file in the batch (0-based)
            total_files: Total number of files in the batch
            
        Returns:
            VideoCompressionTask: New task instance
        """
        task_id = str(uuid.uuid4())
        
        # Use the same directory as the input file to preserve directory structure
        input_path_obj = Path(input_path)
        input_directory = input_path_obj.parent
        temp_output_filename = f"temp_{task_id}.mp4"
        output_path = str(input_directory / temp_output_filename)
        
        return cls(
            task_id=task_id,
            input_path=input_path,
            output_path=output_path,
            file_index=file_index,
            total_files=total_files
        )
    
    def get_final_output_path(self) -> str:
        """
        Get the final output path using the original filename stem.
        
        Returns:
            str: Final output path with original filename
        """
        output_dir = os.path.dirname(self.output_path)
        original_stem = Path(self.input_path).stem
        return os.path.join(output_dir, f"{original_stem}.mp4")
    
    def get_progress_percentage(self) -> int:
        """
        Get progress as an integer percentage (0-100).
        
        Returns:
            int: Progress percentage
        """
        return int(self.progress * 100)
    
    def get_compression_ratio(self) -> Optional[float]:
        """
        Calculate compression ratio if both file sizes are available.
        
        Returns:
            Optional[float]: Compression ratio (compressed_size / original_size) or None
        """
        if self.original_size_bytes > 0 and self.compressed_size_bytes > 0:
            return self.compressed_size_bytes / self.original_size_bytes
        return None
    
    def get_size_reduction_percentage(self) -> Optional[float]:
        """
        Calculate size reduction percentage.
        
        Returns:
            Optional[float]: Size reduction percentage or None
        """
        ratio = self.get_compression_ratio()
        if ratio is not None:
            return (1.0 - ratio) * 100
        return None
    
    def get_duration_seconds(self) -> Optional[float]:
        """
        Get task duration in seconds.
        
        Returns:
            Optional[float]: Duration in seconds or None if not completed
        """
        if self.start_time is not None and self.end_time is not None:
            return self.end_time - self.start_time
        return None
    
    def mark_started(self):
        """Mark the task as started and record start time."""
        import time
        self.status = CompressionStatus.PROCESSING
        self.start_time = time.time()
    
    def mark_completed(self, compressed_size_bytes: int = 0):
        """
        Mark the task as completed and record end time.
        
        Args:
            compressed_size_bytes: Size of the compressed file in bytes
        """
        import time
        self.status = CompressionStatus.COMPLETED
        self.progress = 1.0
        self.end_time = time.time()
        self.compressed_size_bytes = compressed_size_bytes
    
    def mark_failed(self, error_message: str):
        """
        Mark the task as failed with an error message.
        
        Args:
            error_message: Description of the error that occurred
        """
        import time
        self.status = CompressionStatus.FAILED
        self.error_message = error_message
        self.end_time = time.time()
    
    def mark_cancelled(self):
        """Mark the task as cancelled."""
        import time
        self.status = CompressionStatus.CANCELLED
        self.end_time = time.time()
    
    def update_progress(self, progress: float):
        """
        Update the task progress.
        
        Args:
            progress: Progress value between 0.0 and 1.0
        """
        self.progress = max(0.0, min(1.0, progress))
    
    def is_finished(self) -> bool:
        """
        Check if the task is in a finished state.
        
        Returns:
            bool: True if task is completed, failed, or cancelled
        """
        return self.status in [CompressionStatus.COMPLETED, CompressionStatus.FAILED, CompressionStatus.CANCELLED]
    
    def __str__(self) -> str:
        """String representation of the task."""
        return f"VideoCompressionTask(id={self.task_id[:8]}..., file={self.original_filename}, status={self.status.value})" 