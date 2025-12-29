import os
import subprocess
import json
import logging
import threading
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple, Dict
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool, QSize, QRect, QStandardPaths

from music_player.models.vid_proc_model import VidProcItem

class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(str, float) # filename, percent
    result = pyqtSignal(object)

class ProbeWorker(QRunnable):
    def __init__(self, file_path: Path, signals: WorkerSignals):
        super().__init__()
        self.file_path = file_path
        self.signals = signals

    def run(self):
        try:
            cmd = [
                "ffprobe", "-v", "error", 
                "-select_streams", "v:0", 
                "-show_entries", "stream=width,height,avg_frame_rate,codec_name",
                "-show_entries", "format=duration",
                "-of", "json",
                str(self.file_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            
            stream = data['streams'][0]
            fmt = data['format']
            
            w = int(stream.get('width', 0))
            h = int(stream.get('height', 0))
            
            fps_str = stream.get('avg_frame_rate', '30/1')
            if '/' in fps_str:
                num, den = map(int, fps_str.split('/'))
                fps = num / den if den != 0 else 0
            else:
                fps = float(fps_str)
                
            duration = float(fmt.get('duration', 0))
            
            info = {
                'path': self.file_path,
                'size': QSize(w, h),
                'fps': fps,
                'duration': duration,
                'codec_v': stream.get('codec_name', 'unknown'),
            }
            self.signals.result.emit(info)
            self.signals.finished.emit()
            
        except Exception as e:
            self.signals.error.emit(str(e))

class EncodeWorker(QRunnable):
    def __init__(self, item: VidProcItem, out_dir: Path, signals: WorkerSignals, target_height: int = 1920):
        super().__init__()
        self.item = item
        self.out_dir = out_dir
        self.signals = signals
        self.target_height = target_height
        self._is_cancelled = False
        self.process = None # Keep reference to process

    def cancel(self):
        self._is_cancelled = True
        if self.process:
            try:
                self.process.terminate()
                # Maybe wait or kill if needed, but terminate usually works for ffmpeg
            except:
                pass

    def run(self):
        if self._is_cancelled:
            return

        try:
            file_path = self.item['path']
            crop_rect = self.item['crop_rect']
            
            # Output filename
            out_name = f"{file_path.stem}.mp4"
            out_path = self.out_dir / out_name
            
            crop_filter = f"crop={crop_rect.width()}:{crop_rect.height()}:{crop_rect.x()}:{crop_rect.y()}"
            
            scale_filter = ""
            pad_filter = ""
            
            if self.target_height > 0:
                target_w = int(self.target_height * 9 / 16)
                target_h = self.target_height
                scale_filter = f",scale={target_w}:{target_h}:force_original_aspect_ratio=decrease"
                pad_filter = f",pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2"
            else:
                scale_filter = ",scale=trunc(iw/2)*2:trunc(ih/2)*2"
                pad_filter = ""

            vf = f"{crop_filter}{scale_filter}{pad_filter},setsar=1,format=yuv420p"
            
            # Clipping logic
            clip_start = self.item.get('clip_start')
            clip_end = self.item.get('clip_end')
            
            # Start time (-ss before input for fast seek)
            start_args = []
            start_sec = 0.0
            if clip_start is not None and clip_start > 0:
                start_args = ["-ss", str(clip_start)]
                start_sec = clip_start
            
            # Duration/End args (after input)
            duration_args = []
            if clip_end is not None:
                if clip_start is not None and clip_start > 0:
                     # Calculate duration
                     duration = clip_end - clip_start
                     if duration > 0:
                         duration_args = ["-t", str(duration)]
                else:
                     # Start is 0, so just stop at end
                     duration_args = ["-to", str(clip_end)]
            
            cmd = [
                "ffmpeg", "-y"] + start_args + [
                "-i", str(file_path),
                "-vf", vf,
                "-r", "30",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"] + duration_args + [
                str(out_path)
            ]
            
            self.process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            stdout, stderr = self.process.communicate()
            
            if self._is_cancelled:
                return # Don't emit result if cancelled

            if self.process.returncode != 0:
                raise Exception(f"FFmpeg failed: {stderr[-200:]}") 
                
            self.signals.result.emit({
                'path': file_path,
                'out_path': out_path,
                'success': True
            })
            self.signals.finished.emit()
            
        except Exception as e:
            if not self._is_cancelled:
                self.signals.error.emit(str(e))

class MergeWorker(QRunnable):
    def __init__(self, files: List[Path], out_path: Path, signals: WorkerSignals):
        super().__init__()
        self.files = files
        self.out_path = out_path
        self.signals = signals
        self._is_cancelled = False
        self.process = None

    def cancel(self):
        self._is_cancelled = True
        if self.process:
            try:
                self.process.terminate()
            except:
                pass

    def run(self):
        if self._is_cancelled:
            return

        list_path = None
        try:
            # Create concat list file
            list_path = self.out_path.parent / "concat_list.txt"
            with open(list_path, 'w', encoding='utf-8') as f:
                for p in self.files:
                    safe_path = str(p).replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")
            
            # FFMpeg concat command
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_path),
                "-c", "copy",
                str(self.out_path)
            ]
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            stdout, stderr = self.process.communicate()
            
            if self._is_cancelled:
                return

            if self.process.returncode != 0:
                raise Exception(f"Merge failed: {stderr[-200:]}")

            self.signals.result.emit({
                'out_path': self.out_path,
                'success': True
            })
            self.signals.finished.emit()

        except Exception as e:
            if not self._is_cancelled:
                self.signals.error.emit(str(e))
        finally:
            if list_path and list_path.exists():
                try:
                    list_path.unlink()
                except:
                    pass

class VidProcManager(QObject):
    # Signals
    item_probed = pyqtSignal(dict)
    scan_started = pyqtSignal(int)
    scan_progress = pyqtSignal(int, int)
    scan_finished = pyqtSignal()
    preview_ready = pyqtSignal(Path, str, int)
    process_progress = pyqtSignal(str, float)
    process_finished = pyqtSignal(str, bool, str)
    merge_finished = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread_pool = QThreadPool()
        self.process_pool = QThreadPool()
        self.process_pool.setMaxThreadCount(1)
        self.logger = logging.getLogger(__name__)
        
        self._scan_total = 0
        self._scan_current = 0
        self._preview_versions: Dict[Path, int] = {}
        self._active_workers = [] # Track active workers for cancellation
        
        # IMPORTANT: do NOT base temp paths on os.getcwd(). When the app is launched
        # via a Windows protocol handler (e.g. from Chrome), the working directory
        # may be C:\Windows\System32, which is not writable for normal users.
        #
        # Use an OS-provided, user-writable temp directory instead.
        temp_root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation) or tempfile.gettempdir()
        self.temp_dir = Path(temp_root) / "MusicPlayer" / "vidproc"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def scan_folder(self, folder_path: Path):
        """Scan folder for videos and start probing."""
        extensions = {'.mp4', '.mov', '.mkv', '.webm'}
        files_to_probe = []
        try:
            for f in folder_path.iterdir():
                if f.is_file() and f.suffix.lower() in extensions:
                    files_to_probe.append(f)
            
            self._scan_total = len(files_to_probe)
            self._scan_current = 0
            self.scan_started.emit(self._scan_total)
            
            if self._scan_total == 0:
                self.scan_finished.emit()
                return

            for f in files_to_probe:
                self._probe_file(f)
                
        except Exception as e:
            self.logger.error(f"Error scanning folder: {e}")
            self.scan_finished.emit()

    def _probe_file(self, file_path: Path):
        signals = WorkerSignals()
        signals.result.connect(self._on_probe_result)
        signals.finished.connect(self._on_probe_finished)
        signals.error.connect(lambda e: self._on_probe_finished()) 
        
        worker = ProbeWorker(file_path, signals)
        self.thread_pool.start(worker)

    def _on_probe_finished(self):
        self._scan_current += 1
        self.scan_progress.emit(self._scan_current, self._scan_total)
        if self._scan_current >= self._scan_total:
            self.scan_finished.emit()

    def _on_probe_result(self, info):
        self.item_probed.emit(info)
        self.generate_thumb_in(info['path'], min(5.0, info['duration'] * 0.2))

    def generate_thumb_in(self, file_path: Path, timestamp: float):
        out_path = self.temp_dir / f"{file_path.stem}_in.jpg"
        cmd = [
            "ffmpeg", "-y", "-ss", str(timestamp), 
            "-i", str(file_path), 
            "-frames:v", "1", 
            "-vf", "scale=360:-2", 
            str(out_path)
        ]
        t = threading.Thread(target=self._run_ffmpeg_thumb, args=(cmd, file_path, 'in', 0))
        t.start()

    def generate_preview(self, item: VidProcItem):
        if not item: return
        file_path = item['path']
        crop_rect = item['crop_rect']
        out_path = self.temp_dir / f"{file_path.stem}_out.jpg"
        
        if item.get('preview_time') is not None:
             ts = float(item['preview_time'])
        else:
             ts = min(5.0, item['duration'] * 0.2)
        
        self.generate_thumb_in(file_path, ts)

        crop_filter = f"crop={crop_rect.width()}:{crop_rect.height()}:{crop_rect.x()}:{crop_rect.y()}"
        vf = f"{crop_filter},scale=360:-2"
        
        cmd = [
            "ffmpeg", "-y", "-ss", str(ts),
            "-i", str(file_path),
            "-frames:v", "1",
            "-vf", vf,
            str(out_path)
        ]

        current_version = self._preview_versions.get(file_path, 0) + 1
        self._preview_versions[file_path] = current_version
        
        t = threading.Thread(target=self._run_ffmpeg_thumb, args=(cmd, file_path, 'out', current_version))
        t.start()
    
    def _run_ffmpeg_thumb(self, cmd, file_path, type_, version):
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.preview_ready.emit(file_path, type_, version)
        except Exception as e:
            self.logger.error(f"Thumb gen failed: {e}")

    def get_preview_version(self, file_path: Path) -> int:
        return self._preview_versions.get(file_path, 0)

    def cancel_all_processing(self):
        """Cancel all active and queued processing tasks."""
        self.process_pool.clear() # Remove queued tasks
        for worker in self._active_workers:
            worker.cancel()
        self._active_workers.clear()

    def process_items(self, items: List[VidProcItem], out_dir: Path, target_height: int = 1920):
        """Start batch processing."""
        self._active_workers.clear() # Should be empty but safety first
        
        for item in items:
            if item['included'] and item['status'] != 'ok':
                signals = WorkerSignals()
                signals.result.connect(self._on_process_result)
                signals.error.connect(lambda err, p=item['path']: self.process_finished.emit(str(p), False, err))
                
                worker = EncodeWorker(item, out_dir, signals, target_height=target_height)
                
                # Manage active workers list
                self._active_workers.append(worker)
                # We need to remove from list when finished to avoid leaks or double cancel
                # But signals.finished can be called on separate thread.
                # For simplicity in this architecture, we just clear list on cancel or start.
                # Since process_pool is sequential (1 thread), we know they run one by one.
                # But wait, if we have multiple items, they are all queued.
                # If we want to cancel *all*, we need the list.
                
                self.process_pool.start(worker)

    def _on_process_result(self, result):
        self.process_finished.emit(str(result['path']), True, str(result['out_path']))

    def merge_videos(self, output_files: List[Path], out_path: Path):
        """Merge multiple processed videos into one."""
        signals = WorkerSignals()
        signals.result.connect(lambda res: self.merge_finished.emit(True, str(res['out_path'])))
        signals.error.connect(lambda err: self.merge_finished.emit(False, err))
        
        worker = MergeWorker(output_files, out_path, signals)
        self._active_workers.append(worker)
        self.process_pool.start(worker)
