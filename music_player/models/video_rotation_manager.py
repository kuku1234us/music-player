"""
Manager and worker for rotating videos with ffmpeg, with progress reporting.
"""
import os
import subprocess
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool

from .ffmpeg_utils import (
    get_video_duration,
    parse_ffmpeg_progress,
    build_rotation_copy_command,
    build_rotation_reencode_command,
)


class VideoRotationWorkerSignals(QObject):
    file_started = pyqtSignal(str, int, int)              # filename, index, total
    file_progress = pyqtSignal(str, float)                # task_id, progress (0.0-1.0)
    file_completed = pyqtSignal(str)                      # filename
    file_failed = pyqtSignal(str, str)                    # filename, error
    file_finished = pyqtSignal()                          # lifecycle end


class VideoRotationWorker(QRunnable):
    """
    QRunnable worker that rotates a single video file.
    Emits progress for re-encode paths; metadata rotation is reported as instant.
    """

    def __init__(self, file_path: str, index: int, total: int, direction: str, ffmpeg_path: str = "ffmpeg"):
        super().__init__()
        self.file_path = file_path
        self.index = index
        self.total = total
        self.direction = direction  # 'cw' or 'ccw'
        self.ffmpeg_path = ffmpeg_path
        self.signals = VideoRotationWorkerSignals()

        self._temp_output: Optional[str] = None
        self._duration: Optional[float] = None

    def run(self):
        filename = os.path.basename(self.file_path)
        self.signals.file_started.emit(filename, self.index, self.total)

        try:
            ext = Path(self.file_path).suffix.lower()
            # Containers that commonly respect metadata rotation
            metadata_rotate_exts = {'.mp4', '.mov', '.m4v', '.3gp'}

            import uuid
            self._temp_output = os.path.join(os.path.dirname(self.file_path), f".__rotate_tmp__{uuid.uuid4().hex}{ext}")

            if ext in metadata_rotate_exts:
                cmd = build_rotation_copy_command(self.file_path, self._temp_output, self.direction, self.ffmpeg_path)
                # Run quickly without detailed progress
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags)
                if proc.returncode != 0:
                    last_line = proc.stderr.splitlines()[-1] if proc.stderr else "ffmpeg error"
                    raise Exception(last_line)
                # Replace original
                os.replace(self._temp_output, self.file_path)
                if os.path.exists(self._temp_output):
                    try: os.remove(self._temp_output)
                    except: pass
                # Emit completion
                self.signals.file_progress.emit(filename, 1.0)
                self.signals.file_completed.emit(filename)
                return

            # Fallback: re-encode with transpose filter and progress reporting
            self._duration = get_video_duration(self.file_path, self.ffmpeg_path)
            cmd = build_rotation_reencode_command(self.file_path, self._temp_output, self.direction, self.ffmpeg_path)

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )

            # Monitor progress from stderr
            try:
                while True:
                    line = process.stderr.readline()
                    if not line:
                        break
                    prog = parse_ffmpeg_progress(line, self._duration)
                    if prog is not None:
                        self.signals.file_progress.emit(filename, prog)
            except Exception:
                # Ignore parsing errors; rely on final status
                pass

            stdout, stderr = process.communicate()
            if process.returncode != 0:
                last_line = (stderr or '').splitlines()[-1] if stderr else "ffmpeg error"
                raise Exception(last_line)

            # Replace original atomically
            os.replace(self._temp_output, self.file_path)
            if os.path.exists(self._temp_output):
                try: os.remove(self._temp_output)
                except: pass

            self.signals.file_progress.emit(filename, 1.0)
            self.signals.file_completed.emit(filename)

        except Exception as e:
            # Cleanup temp on error
            if self._temp_output and os.path.exists(self._temp_output):
                try: os.remove(self._temp_output)
                except: pass
            self.signals.file_failed.emit(filename, str(e))
        finally:
            self.signals.file_finished.emit()


class VideoRotationManager(QObject):
    """
    Coordinates batch rotation of videos with a single concurrent worker.
    """

    rotation_batch_started = pyqtSignal(int)                # total_files
    rotation_batch_finished = pyqtSignal()
    rotation_file_started = pyqtSignal(str, int, int)       # filename, index, total
    rotation_file_progress = pyqtSignal(str, float)         # filename, progress
    rotation_file_completed = pyqtSignal(str)               # filename
    rotation_file_failed = pyqtSignal(str, str)             # filename, error

    def __init__(self, parent=None, ffmpeg_path: str = "ffmpeg"):
        super().__init__(parent)
        self._ffmpeg_path = ffmpeg_path
        self._thread_pool = QThreadPool.globalInstance()
        self._files: List[str] = []
        self._direction: Optional[str] = None
        self._current_index = 0

    def start_rotations(self, video_files: List[str], direction: str):
        if not video_files:
            return
        self._files = list(video_files)
        self._direction = direction
        self._current_index = 0
        self.rotation_batch_started.emit(len(self._files))
        self._start_next()

    def _start_next(self):
        if self._current_index >= len(self._files):
            self.rotation_batch_finished.emit()
            return

        file_path = self._files[self._current_index]
        worker = VideoRotationWorker(
            file_path=file_path,
            index=self._current_index + 1,
            total=len(self._files),
            direction=self._direction or 'cw',
            ffmpeg_path=self._ffmpeg_path,
        )

        worker.signals.file_started.connect(self.rotation_file_started)
        worker.signals.file_progress.connect(self.rotation_file_progress)
        worker.signals.file_completed.connect(self.rotation_file_completed)
        worker.signals.file_failed.connect(self.rotation_file_failed)
        worker.signals.file_finished.connect(self._on_worker_finished)

        self._thread_pool.start(worker)

    def _on_worker_finished(self):
        self._current_index += 1
        self._start_next()


