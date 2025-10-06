from PyQt6.QtCore import QObject, pyqtSignal, QThread, QSemaphore
from typing import List
import json
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

    def __init__(self, video_files, output_directory, ts_first=False, audio_fix=False, parent=None):
        super().__init__(parent)
        self.video_files = video_files
        self.output_directory = output_directory
        self.ts_first = ts_first
        self.audio_fix = audio_fix

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
            
            if self.ts_first:
                # Skip MP4 concat and go directly to TS concat path
                ok = self._attempt_ts_concat_fallback(output_path)
                if ok:
                    # Optional one-pass audio encode after successful TS concat
                    if self.audio_fix:
                        if not self._audio_one_pass_fix(output_path):
                            self.failed.emit("Final audio encode failed after TS concat.")
                            return
                    try:
                        os.remove(filelist_path)
                    except Exception:
                        pass
                    self.completed.emit(output_path)
                    return
                else:
                    self.failed.emit("TS-first concat failed")
                    return
            else:
                # MP4 concat (copy-only)
                cmd = [
                    'ffmpeg', '-f', 'concat', '-safe', '0', '-i', filelist_path,
                    '-c', 'copy',
                    '-fflags', '+genpts',
                    '-movflags', '+faststart',
                    '-y',
                    output_path
                ]
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
            
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
            
            if not self.ts_first:
                if process.returncode == 0:
                    # Validate merged output; if errors, try TS fallback
                    validated = self._validate_output(output_path)
                    if not validated:
                        fallback_ok = self._attempt_ts_concat_fallback(output_path)
                        if not fallback_ok:
                            stderr_output = process.stderr.read()
                            self.failed.emit(f"FFmpeg merge validation failed and fallback failed: {stderr_output}")
                            return
                    # Optional one-pass audio encode for mixed sets
                    if self.audio_fix:
                        if not self._audio_one_pass_fix(output_path):
                            self.failed.emit("Final audio encode failed after merge.")
                            return
                    try:
                        os.remove(filelist_path)
                    except Exception:
                        pass
                    self.completed.emit(output_path)
                else:
                    stderr_output = (process.stderr.read() or '').lower()
                    # Attempt fallback TS concat for H.264 streams (stream copy, no re-encode)
                    fallback_ok = self._attempt_ts_concat_fallback(output_path)
                    if fallback_ok:
                        # Optional one-pass audio encode after TS fallback
                        if self.audio_fix:
                            if not self._audio_one_pass_fix(output_path):
                                self.failed.emit("Final audio encode failed after TS fallback.")
                                return
                        try:
                            os.remove(filelist_path)
                        except Exception:
                            pass
                        self.completed.emit(output_path)
                    else:
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

    def _attempt_ts_concat_fallback(self, output_path: str) -> bool:
        """Fallback concat via MPEG-TS (copy only). Returns True on success."""
        try:
            temp_ts_files = []
            # Create TS segments
            for i, src in enumerate(self.video_files):
                ts_path = os.path.join(self.output_directory, f"concat_fallback_{i}.ts")
                # Per-clip: copy video, re-encode audio to uniform AAC config, then TS remux
                cmd = [
                    'ffmpeg', '-y', '-hide_banner',
                    '-i', src,
                    '-map', '0:v:0', '-map', '0:a?',
                    '-c:v', 'copy',
                    '-c:a', 'aac', '-profile:a', 'aac_low', '-ar', '48000', '-ac', '2', '-b:a', '192k',
                    '-bsf:v', 'h264_mp4toannexb',
                    '-f', 'mpegts',
                    ts_path
                ]
                p = subprocess.run(cmd, capture_output=True, text=True, creationflags=(subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
                if p.returncode != 0:
                    # Cleanup and abort
                    for t in temp_ts_files:
                        try: os.remove(t)
                        except Exception: pass
                    return False
                temp_ts_files.append(ts_path)

            # Write concat demuxer list
            list_path = os.path.join(self.output_directory, 'ts_concat_list.txt')
            try:
                with open(list_path, 'w', encoding='utf-8') as lf:
                    for t in temp_ts_files:
                        lf.write(f"file '{os.path.abspath(t)}'\n")
            except Exception:
                # Cleanup and abort
                for t in temp_ts_files:
                    try: os.remove(t)
                    except Exception: pass
                return False

            # Concat TS segments via demuxer and remux back to MP4 (copy, no re-encode)
            cmd2 = [
                'ffmpeg', '-y', '-hide_banner',
                '-f', 'concat', '-safe', '0', '-i', list_path,
                '-map', '0:v:0', '-map', '0:a?',
                '-c', 'copy',
                '-fflags', '+genpts',
                '-bsf:a', 'aac_adtstoasc',
                '-movflags', '+faststart',
                '-muxpreload', '0', '-muxdelay', '0',
                output_path
            ]
            p2 = subprocess.run(cmd2, capture_output=True, text=True, creationflags=(subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
            success = (p2.returncode == 0)
            # Cleanup TS files
            for t in temp_ts_files:
                try: os.remove(t)
                except Exception: pass
            try:
                os.remove(list_path)
            except Exception:
                pass
            return success
        except Exception:
            return False

    def _validate_output(self, output_path: str) -> bool:
        """Decode output to null to catch hard errors; returns True if OK."""
        try:
            cmd = ['ffmpeg', '-v', 'error', '-i', output_path, '-f', 'null', '-']
            p = subprocess.run(cmd, capture_output=True, text=True, creationflags=(subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
            # Treat any stderr content or non-zero return as failure
            return p.returncode == 0 and not (p.stderr and p.stderr.strip())
        except Exception:
            return False

    def _audio_one_pass_fix(self, output_path: str) -> bool:
        """One-pass audio encode on final merged file; video copy-only."""
        try:
            base = os.path.splitext(output_path)[0]
            temp_out = base + "_audiofix.mp4"
            cmd = [
                'ffmpeg', '-y', '-hide_banner',
                '-i', output_path,
                '-map', '0:v:0', '-map', '0:a?',
                '-c:v', 'copy',
                '-af', 'aresample=async=1:min_hard_comp=0.100:first_pts=0',
                '-c:a', 'aac', '-profile:a', 'aac_low', '-ar', '44100', '-ac', '2', '-b:a', '192k',
                '-fflags', '+genpts',
                '-movflags', '+faststart',
                '-muxpreload', '0', '-muxdelay', '0',
                temp_out
            ]
            p = subprocess.run(cmd, capture_output=True, text=True, creationflags=(subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
            if p.returncode != 0:
                return False
            try:
                os.remove(output_path)
            except Exception:
                pass
            os.replace(temp_out, output_path)
            return True
        except Exception:
            return False

    # Removed audio-only remux per current policy (avoid re-encoding audio in final merge)

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
            if duration is None or duration <= 3.03:
                self.failed.emit(self.task_id, "Video too short or invalid")
                return
            
            trim_duration = duration - 3.03
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
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
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
    normalize_started = pyqtSignal(int)
    normalize_file_started = pyqtSignal(str, str, int, int)
    normalize_file_progress = pyqtSignal(str, float)
    normalize_file_completed = pyqtSignal(str, str)
    normalize_file_failed = pyqtSignal(str, str, str)

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
        else:  # No trimming
            if do_merge:
                # Normalize to majority format, then merge via stream copy
                self._start_normalize_then_merge(video_files)

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
        self.merge_worker = DouyinMergeWorker(
            files_to_merge,
            self.output_directory,
            ts_first=getattr(self, '_mixed_merge', False),
            audio_fix=False
        )
        self.merge_worker.progress.connect(self.merge_progress.emit)
        self.merge_worker.completed.connect(self.merge_completed.emit)
        self.merge_worker.failed.connect(self.merge_failed.emit)
        self.merge_worker.finished.connect(self.process_finished.emit)
        self.merge_worker.start()

    # --- New: Normalize then merge for merge-only mode ---
    def _start_normalize_then_merge(self, files_to_merge: List[str]):
        try:
            if not files_to_merge:
                self.merge_failed.emit("No files to merge.")
                self.process_finished.emit()
                return
            # Analyze with ffprobe
            signatures = []
            for f in files_to_merge:
                sig = self._probe_signature(f)
                if sig:
                    signatures.append((f, sig))
            if not signatures:
                self.merge_failed.emit("Could not analyze inputs.")
                self.process_finished.emit()
                return
            # Reset mixed flags for this run
            self._mixed_merge = False
            # Determine if audio is heterogeneous across inputs
            audio_keys = set()
            for _, s in signatures:
                audio_keys.add((s.get('acodec'), s.get('sample_rate'), s.get('channels'), s.get('channel_layout')))
            self._mixed_audio = len(audio_keys) > 1
            # Pick majority signature
            from collections import Counter
            sig_list = [json.dumps(s, sort_keys=True) for _, s in signatures]
            common_sig_json, _ = Counter(sig_list).most_common(1)[0]
            common_sig = json.loads(common_sig_json)

            # Plan normalization
            to_copy = []
            to_encode = []
            for f, sig in signatures:
                if self._signatures_match(sig, common_sig):
                    to_copy.append(f)
                else:
                    to_encode.append(f)

            # Track whether the final merge will mix originals with normalized outputs
            self._mixed_merge = bool(to_copy and to_encode)

            # If all match, just merge
            if not to_encode:
                self._start_merging(files_to_merge)
                return

            # Normalize outliers concurrently with semaphore
            self.normalize_started.emit(len(to_encode))
            self.workers = []
            self._temp_normalized_files = []
            self.completed_count = 0
            self.total_files = len(to_encode)
            self._merge_input_order = list(files_to_merge)
            self._task_to_original = {}
            self._normalized_map = {}
            for index, f in enumerate(to_encode):
                task_id = str(uuid.uuid4())
                self.normalize_file_started.emit(task_id, f, index + 1, len(to_encode))
                worker = _NormalizeWorker(task_id, f, common_sig)
                worker.progress.connect(self.normalize_file_progress.emit)
                worker.completed.connect(self._on_normalize_completed)
                worker.failed.connect(self.normalize_file_failed.emit)
                worker.finished.connect(self._on_worker_finished_normalize)
                self.workers.append(worker)
                self._task_to_original[task_id] = f
                worker.start()
            # Keep to_copy for later
            self._files_to_copy_after_normalize = to_copy
        except Exception as e:
            self.merge_failed.emit(str(e))
            self.process_finished.emit()

    def _on_worker_finished_normalize(self):
        self.workers = [w for w in self.workers if not w.isFinished()]
        if not self.workers:
            # Build ordered list following original input order
            ordered = []
            for orig in self._merge_input_order:
                mapped = self._normalized_map.get(orig, orig)
                ordered.append(mapped)
            # Start merge, then cleanup temp normalized files after completion
            self._start_merging(ordered)

    def _on_normalize_completed(self, task_id, file_path):
        # Map original to normalized path and track for cleanup
        orig = self._task_to_original.get(task_id)
        if orig:
            self._normalized_map[orig] = file_path
        self._temp_normalized_files.append(file_path)
        self.completed_count += 1
        self.normalize_file_completed.emit(task_id, file_path)

    def _probe_signature(self, filepath: str):
        try:
            cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', '-select_streams', 'v:0', filepath]
            p = subprocess.run(cmd, capture_output=True, text=True, check=True)
            v = json.loads(p.stdout)['streams'][0]
            acmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', '-select_streams', 'a:0', filepath]
            ap = subprocess.run(acmd, capture_output=True, text=True)
            a = None
            if ap.returncode == 0:
                data = json.loads(ap.stdout)
                if data.get('streams'):
                    a = data['streams'][0]
            return {
                'vcodec': v.get('codec_name'),
                'vprofile': v.get('profile'),
                'vlevel': v.get('level'),
                'width': v.get('width'),
                'height': v.get('height'),
                'pix_fmt': v.get('pix_fmt'),
                'r_frame_rate': v.get('r_frame_rate'),
                'avg_frame_rate': v.get('avg_frame_rate'),
                'acodec': (a or {}).get('codec_name'),
                'sample_rate': (a or {}).get('sample_rate'),
                'channels': (a or {}).get('channels'),
                'channel_layout': (a or {}).get('channel_layout'),
            }
        except Exception:
            return None

    def _signatures_match(self, a: dict, b: dict) -> bool:
        keys = ['vcodec','vprofile','vlevel','width','height','pix_fmt','avg_frame_rate','acodec','sample_rate','channels','channel_layout']
        return all(str(a.get(k)) == str(b.get(k)) for k in keys)


class _NormalizeWorker(QThread):
    progress = pyqtSignal(str, float)
    completed = pyqtSignal(str, str)
    failed = pyqtSignal(str, str, str)

    def __init__(self, task_id: str, input_path: str, target_sig: dict, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self.input_path = input_path
        self.target_sig = target_sig

    def run(self):
        encoding_semaphore.acquire()
        try:
            # Determine target parameters
            width = int(self.target_sig.get('width') or 720)
            height = int(self.target_sig.get('height') or 1280)
            fps_expr = (self.target_sig.get('avg_frame_rate') or '30/1')
            try:
                num, den = fps_expr.split('/')
                fps = str(round(float(num)/float(den)))
            except Exception:
                fps = '30'
            # We normalize to H.264 for compatibility
            vcodec = 'libx264'
            acodec = 'aac'
            # Match profile/level to majority signature if present
            vprofile = self.target_sig.get('vprofile')
            vlevel = self.target_sig.get('vlevel')
            level_arg: list[str] = []
            profile_arg: list[str] = []
            if vprofile and isinstance(vprofile, str):
                profile_arg = ['-profile:v', vprofile.lower()]
            # ffprobe level often returns integers like 50 -> use 5.0
            if vlevel not in (None, 'Unknown'):
                try:
                    lvl_str = str(vlevel)
                    if lvl_str.isdigit() and len(lvl_str) == 2:
                        lvl_str = f"{lvl_str[0]}.{lvl_str[1]}"
                    level_arg = ['-level', lvl_str]
                except Exception:
                    level_arg = []

            # Fixed GOP length (~2 seconds) and disable scene cut for stable cadence
            try:
                g_frames = str(int(round(float(fps))) * 2)
            except Exception:
                g_frames = '60'

            input_dir = Path(self.input_path).parent
            temp_output = str(input_dir / f'normalized_{self.task_id}.mp4')
            duration = get_video_duration(self.input_path) or 0
            # Audio normalization targets from majority signature
            target_sample_rate = self.target_sig.get('sample_rate') or '44100'
            target_channels = self.target_sig.get('channels') or 2
            try:
                target_channels = int(str(target_channels))
            except Exception:
                target_channels = 2

            cmd = [
                'ffmpeg','-i', self.input_path,
                '-vf', f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                '-c:v', vcodec, '-crf', '20', '-preset', 'medium', '-pix_fmt', 'yuv420p',
                '-r', fps,
                '-vsync', 'cfr',
                '-video_track_timescale', '90000',
                '-g', g_frames, '-sc_threshold', '0',
                # No -force_key_frames to avoid cadence distortion
            ] + profile_arg + level_arg + [
                '-c:a', acodec, '-profile:a', 'aac_low', '-b:a', '128k',
                '-ar', str(target_sample_rate), '-ac', str(target_channels),
                '-avoid_negative_ts', 'make_zero',
                '-movflags', '+faststart',
                '-y', temp_output
            ]
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            while process.poll() is None:
                line = process.stderr.readline()
                if line:
                    progress_val = parse_ffmpeg_progress(line, duration)
                    if progress_val is not None:
                        self.progress.emit(self.task_id, progress_val)
            if process.returncode == 0:
                # Do not overwrite original in merge-only mode; return new path
                self.completed.emit(self.task_id, temp_output)
            else:
                stderr_output = process.stderr.read()
                self.failed.emit(self.task_id, self.input_path, f"FFmpeg error: {stderr_output}")
        except Exception as e:
            self.failed.emit(self.task_id, self.input_path, str(e))
        finally:
            encoding_semaphore.release()

    def cancel_all_trimming(self):
        self._is_cancelled = True
        print(f"[DouyinProcessor] Cancelling {len(self.workers)} active workers...")
        for worker in self.workers:
            if worker.isRunning():
                worker.terminate()
                worker.wait() 