from PyQt6.QtCore import QObject, pyqtSignal, QThread, QSemaphore
from typing import List
import subprocess
import os
import re
from pathlib import Path
import uuid
from music_player.models.ffmpeg_utils import get_video_duration, parse_ffmpeg_progress

# Global semaphore to limit concurrent re-encoding processes
# For Intel i7 + RTX 3050 Ti: 2-3 concurrent processes recommended
MAX_CONCURRENT_REENCODING = 3
encoding_semaphore = QSemaphore(MAX_CONCURRENT_REENCODING)

class DouyinMergeWorker(QThread):
    progress = pyqtSignal(float)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, video_files, output_directory, parent=None):
        super().__init__(parent)
        self.video_files = video_files
        self.output_directory = output_directory

    def run(self):
        try:
            # Generate output filename
            output_filename = self._generate_output_filename()
            output_path = os.path.join(self.output_directory, output_filename)
            
            # Create filelist.txt for FFmpeg concat
            filelist_path = os.path.join(self.output_directory, "filelist.txt")
            with open(filelist_path, 'w', encoding='utf-8') as f:
                for video_file in self.video_files:
                    f.write(f"file '{video_file}'\n")
            
            # FFmpeg concat command using stream copy for pre-encoded files
            # Since trimming stage re-encodes with consistent settings, we can use copy
            cmd = [
                'ffmpeg', '-f', 'concat', '-safe', '0', '-i', filelist_path,
                '-c', 'copy',  # Stream copy - no re-encoding needed
                '-movflags', '+faststart',  # Web optimization
                '-y',  # Overwrite output
                output_path
            ]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
            
            # Monitor progress - stream copy is much faster than re-encoding
            total_duration = 0
            current_time = 0
            
            # Calculate total duration of all input files for progress estimation
            try:
                for video_file in self.video_files:
                    duration = get_video_duration(video_file)
                    if duration:
                        total_duration += duration
            except:
                total_duration = len(self.video_files) * 10  # Fallback estimate
            
            while process.poll() is None:
                line = process.stderr.readline()
                if line:
                    # Parse time progress for stream copy
                    time_match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
                    if time_match:
                        hours, minutes, seconds = time_match.groups()
                        current_time = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                        if total_duration > 0:
                            progress = min(current_time / total_duration, 1.0)
                            self.progress.emit(progress)
            
            if process.returncode == 0:
                # Clean up filelist
                os.remove(filelist_path)
                self.completed.emit(output_path)
            else:
                stderr_output = process.stderr.read()
                self.failed.emit(f"FFmpeg merge error: {stderr_output}")
        except Exception as e:
            self.failed.emit(str(e))

    def _generate_output_filename(self):
        """Generate output filename like output00.mp4, output01.mp4, etc."""
        counter = 0
        while True:
            filename = f"output{counter:02d}.mp4"
            if not os.path.exists(os.path.join(self.output_directory, filename)):
                return filename
            counter += 1

class DouyinTrimWorker(QThread):
    progress = pyqtSignal(str, float)
    completed = pyqtSignal(str, str)
    failed = pyqtSignal(str, str)

    def __init__(self, task_id, input_path, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self.input_path = input_path

    def run(self):
        # Acquire semaphore to limit concurrent re-encoding
        print(f"[DouyinTrimWorker] Task {self.task_id}: Waiting for encoding slot...")
        encoding_semaphore.acquire()
        
        try:
            print(f"[DouyinTrimWorker] Task {self.task_id}: Starting re-encoding (slot acquired)")
            self._perform_trimming()
        finally:
            # Always release the semaphore, even if an error occurs
            encoding_semaphore.release()
            print(f"[DouyinTrimWorker] Task {self.task_id}: Encoding slot released")
    
    def _perform_trimming(self):
        """Perform the actual trimming operation."""
        try:
            duration = get_video_duration(self.input_path)
            if duration is None or duration <= 3.02:
                self.failed.emit(self.task_id, "Video too short or invalid")
                return
            
            trim_duration = duration - 3.02
            input_dir = Path(self.input_path).parent
            temp_output = str(input_dir / f'temp_{self.task_id}.mp4')
            
            # Re-encode during trimming to ensure proper keyframes and sync
            # This prevents video/audio desync issues from imprecise cuts
            cmd = [
                'ffmpeg', '-i', self.input_path, 
                '-t', str(trim_duration),
                '-vf', 'scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2',  # Scale to 720p maintaining aspect ratio
                '-c:v', 'libx264', '-crf', '20', '-preset', 'medium',  # Re-encode video with high quality
                '-r', '30',  # Force 30fps for consistency
                '-force_key_frames', '0',  # Ensure first frame is keyframe
                '-c:a', 'aac', '-b:a', '128k',  # Re-encode audio
                '-pix_fmt', 'yuv420p',  # Ensure compatibility
                '-avoid_negative_ts', 'make_zero',  # Fix timestamp issues
                '-threads', '2',  # Limit FFmpeg threads per process
                '-y',
                temp_output
            ]
            
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
            
            while process.poll() is None:
                line = process.stderr.readline()
                if line:
                    progress_val = parse_ffmpeg_progress(line, duration)
                    if progress_val is not None:
                        self.progress.emit(self.task_id, progress_val)
            
            if process.returncode == 0:
                os.remove(self.input_path)
                os.rename(temp_output, self.input_path)
                self.completed.emit(self.task_id, self.input_path)
            else:
                stderr_output = process.stderr.read()
                self.failed.emit(self.task_id, f"FFmpeg error: {stderr_output}")
        except Exception as e:
            self.failed.emit(self.task_id, str(e))

class DouyinProcessor(QObject):
    trim_batch_started = pyqtSignal(int)
    trim_file_started = pyqtSignal(str, str, int, int)
    trim_file_progress = pyqtSignal(str, float)
    trim_file_completed = pyqtSignal(str, str)
    trim_file_failed = pyqtSignal(str, str, str)
    trim_batch_finished = pyqtSignal()
    merge_started = pyqtSignal()
    merge_progress = pyqtSignal(float)
    merge_completed = pyqtSignal(str)
    merge_failed = pyqtSignal(str)
    process_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.workers = []
        self.trimmed_files = []
        self._is_cancelled = False
        self.should_merge_after_trim = False
        self.completed_count = 0
        self.total_files = 0

    @staticmethod
    def set_max_concurrent_encoding(max_concurrent: int):
        """
        Adjust the maximum number of concurrent encoding processes.
        Recommended values:
        - Intel i3/i5: 1-2
        - Intel i7/i9: 2-4  
        - AMD Ryzen 5: 2-3
        - AMD Ryzen 7/9: 3-5
        """
        global encoding_semaphore, MAX_CONCURRENT_REENCODING
        if max_concurrent < 1:
            max_concurrent = 1
        if max_concurrent > 8:  # Safety limit
            max_concurrent = 8
            
        print(f"[DouyinProcessor] Updating max concurrent encoding from {MAX_CONCURRENT_REENCODING} to {max_concurrent}")
        MAX_CONCURRENT_REENCODING = max_concurrent
        encoding_semaphore = QSemaphore(max_concurrent)

    def start_processing(self, video_files: List[str], output_directory: str, do_trim: bool, do_merge: bool):
        # Reset state for new operation to fix bug of merging old files
        self.trimmed_files = []
        self.workers = []
        self._is_cancelled = False
        self.should_merge_after_trim = do_merge
        self.output_directory = output_directory
        self.completed_count = 0
        self.total_files = len(video_files) if do_trim else 0

        if not do_trim and not do_merge:
            self.process_finished.emit()
            return
        
        if do_trim:
            print(f"[DouyinProcessor] Starting batch processing of {len(video_files)} files with max {MAX_CONCURRENT_REENCODING} concurrent encoders")
            self.trim_batch_started.emit(len(video_files))
            for index, file_path in enumerate(video_files):
                task_id = str(uuid.uuid4())
                self.trim_file_started.emit(task_id, file_path, index + 1, len(video_files))
                worker = DouyinTrimWorker(task_id, file_path)
                worker.progress.connect(self.trim_file_progress.emit)
                worker.completed.connect(self._on_trim_completed)
                worker.failed.connect(self.trim_file_failed.emit)
                worker.finished.connect(self._on_worker_finished)
                self.workers.append(worker)
                worker.start()  # All workers start immediately, but semaphore controls actual encoding
        else:  # No trimming, but merging is requested
            if do_merge:
                self._start_merging(video_files)

    def _on_trim_completed(self, task_id, file_path):
        self.trimmed_files.append(file_path)
        self.completed_count += 1
        self.trim_file_completed.emit(task_id, file_path)
        
        print(f"[DouyinProcessor] Completed {self.completed_count}/{self.total_files} files")

    def _on_worker_finished(self):
        self.workers = [w for w in self.workers if not w.isFinished()]
        if not self.workers:
            print(f"[DouyinProcessor] All trimming workers finished. Processed {len(self.trimmed_files)} files successfully")
            self.trim_batch_finished.emit()
            # Start merging after trimming is complete
            if self.trimmed_files and self.should_merge_after_trim:
                self._start_merging(self.trimmed_files)
            else: # Trim only, no merge
                self.process_finished.emit()

    def _start_merging(self, files_to_merge: List[str]):
        if not files_to_merge:
            self.merge_failed.emit("No files to merge.")
            self.process_finished.emit()
            return
            
        print(f"[DouyinProcessor] Starting merge of {len(files_to_merge)} files")
        self.merge_started.emit()
        self.merge_worker = DouyinMergeWorker(files_to_merge, self.output_directory)
        self.merge_worker.progress.connect(self.merge_progress.emit)
        self.merge_worker.completed.connect(self.merge_completed.emit)
        self.merge_worker.failed.connect(self.merge_failed.emit)
        self.merge_worker.finished.connect(self.process_finished.emit)
        self.merge_worker.start()

    def cancel_all_trimming(self):
        self._is_cancelled = True
        print(f"[DouyinProcessor] Cancelling {len(self.workers)} active workers...")
        for worker in self.workers:
            if worker.isRunning():
                worker.terminate()
                worker.wait() 