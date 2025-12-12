# music_player/models/ClippingManager.py
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox
from typing import Optional, Tuple, List
import subprocess
import os
import json
from pathlib import Path

# Import Logger for proper logging
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from qt_base_app.models.logger import Logger
from music_player.ui.components.clipping_options_dialog import ClippingOptionsDialog

# Tolerance in seconds for snapping cut points to nearest keyframe for fast path
KEYFRAME_SNAP_TOLERANCE_SEC = 2.0

class ClippingManager(QObject):
    """
    Manages the state of clipping markers (begin and end points) for media files,
    generates output filenames, and handles the ffmpeg process for clipping.
    This is a singleton class.
    """

    # Signals
    markers_updated = pyqtSignal(str, object, list) # (media_path, pending_begin_ms, segments)
    clip_successful = pyqtSignal(str, str) # (original_path, clipped_path)
    clip_failed = pyqtSignal(str, str) # (original_path, error_message)

    _instance: Optional['ClippingManager'] = None

    @staticmethod
    def instance() -> 'ClippingManager':
        """Returns the singleton instance of ClippingManager."""
        if ClippingManager._instance is None:
            ClippingManager._instance = ClippingManager()
        return ClippingManager._instance

    def __init__(self):
        if ClippingManager._instance is not None:
            raise Exception("ClippingManager is a singleton, use instance() to get it.")
        super().__init__()
        self._current_media_path: Optional[str] = None
        self._pending_begin_marker_ms: Optional[int] = None
        self._segments: List[Tuple[int, int]] = [] # List of (start_ms, end_ms) tuples
        self._logger = Logger.instance()

    def set_media(self, media_path: str):
        """
        Sets the current media file for clipping.
        - If the media path changes, existing markers are cleared.
        - Emits markers_updated signal for the new state.
        """
        effective_media_path = media_path if media_path is not None else ""

        if self._current_media_path != effective_media_path:
            self._current_media_path = effective_media_path
            self._pending_begin_marker_ms = None
            self._segments = []
            
            # Always emit for the new state (new media or no media)
            self.markers_updated.emit(self._current_media_path, self._pending_begin_marker_ms, self._segments)

    def mark_begin(self, timestamp_ms: int):
        """Sets the pending beginning marker for a new segment."""
        if not self._current_media_path:
            self._logger.warning("ClippingManager", "No media set, cannot mark pending begin.")
            return
        self._pending_begin_marker_ms = timestamp_ms
        if self._current_media_path:
            self.markers_updated.emit(self._current_media_path, self._pending_begin_marker_ms, self._segments)

    def mark_end(self, timestamp_ms: int):
        """Finalizes a segment using the pending begin marker and the given end timestamp."""
        if not self._current_media_path:
            self._logger.warning("ClippingManager", "No media set, cannot mark end to define a segment.")
            return

        if self._pending_begin_marker_ms is None:
            self._logger.warning("ClippingManager", "No pending begin marker set. Press 'B' first to mark the start of a segment.")
            return

        if timestamp_ms <= self._pending_begin_marker_ms:
            self._logger.warning("ClippingManager", "End marker must be after pending begin marker.")
            return

        # Add the new segment
        new_segment = (self._pending_begin_marker_ms, timestamp_ms)
        self._segments.append(new_segment)
        self._pending_begin_marker_ms = None # Clear pending marker after defining a segment
        
        if self._current_media_path:
            self.markers_updated.emit(self._current_media_path, self._pending_begin_marker_ms, self._segments)

    def clear_pending_begin_marker(self):
        """Clears the currently pending begin marker."""
        if self._pending_begin_marker_ms is not None:
            self._pending_begin_marker_ms = None
            if self._current_media_path:
                self.markers_updated.emit(self._current_media_path, self._pending_begin_marker_ms, self._segments)

    def clear_last_segment(self):
        """Removes the last added segment from the list."""
        if self._segments:
            removed_segment = self._segments.pop()
            if self._current_media_path:
                self.markers_updated.emit(self._current_media_path, self._pending_begin_marker_ms, self._segments)

    def clear_all_segments(self):
        """Clears all defined segments and any pending begin marker."""
        changed = False
        if self._pending_begin_marker_ms is not None:
            self._pending_begin_marker_ms = None
            changed = True
        if self._segments:
            self._segments = []
            changed = True
        
        if changed and self._current_media_path:
            self.markers_updated.emit(self._current_media_path, self._pending_begin_marker_ms, self._segments)
        elif not self._current_media_path and changed:
            # Handle edge case: markers cleared but no media path
            self.markers_updated.emit("", None, [])

    def get_markers(self) -> Tuple[Optional[str], Optional[int], List[Tuple[int, int]]]:
        """Returns the current media path, pending begin marker, and list of segments."""
        return self._current_media_path, self._pending_begin_marker_ms, self._segments

    def _ms_to_ffmpeg_time(self, ms: Optional[int]) -> str:
        """Converts milliseconds to HH:MM:SS.mmm format for ffmpeg."""
        if ms is None or ms < 0: ms = 0 # Treat None or negative as 0
        seconds_total = ms // 1000
        milliseconds = ms % 1000
        minutes_total = seconds_total // 60
        seconds = seconds_total % 60
        hours = minutes_total // 60
        minutes = minutes_total % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

    def _generate_clipped_filename(self) -> Optional[str]:
        """Generates a unique filename for the clipped media using '_clipped' suffix."""
        if not self._current_media_path:
            return None

        original_path = Path(self._current_media_path)
        directory = original_path.parent
        stem = original_path.stem
        ext = original_path.suffix # Includes the dot, e.g., ".mp3"

        # Try base filename with '_clipped' suffix first
        base_clipped_filename = f"{stem}_clipped{ext}"
        potential_path = directory / base_clipped_filename
        if not potential_path.exists():
            return str(potential_path)

        # If base filename exists, try numbered variants
        counter = 1
        while True:
            clipped_filename = f"{stem}_clipped_{counter}{ext}"
            potential_path = directory / clipped_filename
            if not potential_path.exists():
                return str(potential_path)
            counter += 1

    def _format_concat_path(self, file_path: str) -> str:
        """Format paths for ffmpeg concat lists (use forward slashes on Windows/UNC)."""
        try:
            # Prefer plain forward slashes with unescaped drive colon: D:/path
            return Path(file_path).as_posix()
        except Exception:
            return file_path.replace('\\', '/')

    def _get_video_codec_info(self, video_path: str) -> Optional[dict]:
        """
        Extract comprehensive codec information from video file using ffprobe.
        """
        self._logger.info("ClippingManager", f"Analyzing codec: {video_path}")
        
        try:
            # Get detailed codec information using ffprobe with JSON output
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_streams',
                '-select_streams', 'v:0',  # Select first video stream
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            data = json.loads(result.stdout)
            
            if 'streams' in data and len(data['streams']) > 0:
                video_stream = data['streams'][0]
                
                codec_info = {
                    'codec_name': video_stream.get('codec_name', 'Unknown'),
                    'codec_long_name': video_stream.get('codec_long_name', 'Unknown'),
                    'profile': video_stream.get('profile', 'Unknown'),
                    'level': video_stream.get('level', 'Unknown'),
                    'pix_fmt': video_stream.get('pix_fmt', 'Unknown'),
                    'bit_rate': video_stream.get('bit_rate', 'Unknown'),
                    'width': video_stream.get('width', 'Unknown'),
                    'height': video_stream.get('height', 'Unknown')
                }
                
                self._logger.info("ClippingManager", f"Detected: {codec_info['codec_name']} {codec_info['profile']} Level {codec_info['level']}")
                return codec_info
            else:
                self._logger.info("ClippingManager", "No video streams found in file")
                return None
                
        except subprocess.CalledProcessError as e:
            self._logger.error("ClippingManager", f"ffprobe failed: {e}")
            return None
        except json.JSONDecodeError as e:
            self._logger.error("ClippingManager", f"JSON parsing failed: {e}")
            return None

    def _find_nearest_keyframe(self, video_path: str, target_time_seconds: float) -> Optional[dict]:
        """
        Find the nearest keyframe around the specified time (in seconds).
        """
        self._logger.info("ClippingManager", f"Finding keyframe around {target_time_seconds:.3f}s")
        
        try:
            # Search for keyframes in a window around the target time
            search_start = max(0, target_time_seconds - 10)  # 10 seconds before
            search_end = target_time_seconds + 10  # 10 seconds after
            
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_frames',
                '-select_streams', 'v:0',
                '-read_intervals', f'{search_start}%{search_end}',
                '-show_entries', 'frame=best_effort_timestamp_time,pkt_pts_time,key_frame',
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            data = json.loads(result.stdout)
            
            if 'frames' in data:
                keyframes = []
                for frame in data['frames']:
                    if frame.get('key_frame') == 1:
                        # Try multiple time fields as different versions of ffprobe may use different fields
                        frame_time = frame.get('best_effort_timestamp_time') or frame.get('pkt_pts_time')
                        if frame_time:
                            keyframes.append(float(frame_time))
                
                if keyframes:
                    # Find the nearest keyframe to target time
                    nearest_keyframe = min(keyframes, key=lambda x: abs(x - target_time_seconds))
                    distance = nearest_keyframe - target_time_seconds
                    adjustment_needed = abs(distance)
                    
                    self._logger.info("ClippingManager", f"Nearest keyframe: {nearest_keyframe:.3f}s (distance: {distance:.3f}s)")
                    
                    # Check if within our 0.4s threshold for keyframe snapping
                    within_threshold = adjustment_needed <= 0.4
                    if within_threshold:
                        self._logger.info("ClippingManager", "Within 0.4s threshold -> Option A (Keyframe Snapping)")
                    else:
                        self._logger.info("ClippingManager", "Beyond 0.4s threshold -> Option B (Minimal Re-encoding)")
                    
                    return {
                        'target_time': target_time_seconds,
                        'nearest_keyframe': nearest_keyframe,
                        'distance': distance,
                        'adjustment_needed': adjustment_needed,
                        'within_threshold': within_threshold,
                        'all_keyframes': sorted(keyframes)
                    }
                else:
                    self._logger.info("ClippingManager", "No keyframes found in search window")
                    return None
            else:
                self._logger.info("ClippingManager", "No frames data found")
                return None
                
        except subprocess.CalledProcessError as e:
            self._logger.error("ClippingManager", f"ffprobe keyframe detection failed: {e}")
            return None
        except json.JSONDecodeError as e:
            self._logger.error("ClippingManager", f"JSON parsing failed for keyframe data: {e}")
            return None

    def _compute_snap_plan_for_segments(self, media_path: str, merged_segments: list[tuple[int, int]], tolerance_sec: float):
        """
        Compute snapped start/end times for each segment based on nearest keyframes.

        Returns a tuple of (snapped_segments_seconds, out_of_tolerance_count).
        - snapped_segments_seconds: List of (snapped_start_sec, snapped_end_sec)
        - out_of_tolerance_count: Number of boundaries (start/end) that exceed tolerance
        """
        snapped_segments_seconds: list[tuple[float, float]] = []
        out_of_tolerance_boundaries = 0

        for start_ms, end_ms in merged_segments:
            original_start_sec = start_ms / 1000.0
            original_end_sec = end_ms / 1000.0

            # Find keyframes near start and end
            start_kf_info = self._find_nearest_keyframe(media_path, original_start_sec)
            end_kf_info = self._find_nearest_keyframe(media_path, original_end_sec)

            # Default snapped to original if no info available
            snapped_start_sec = original_start_sec
            snapped_end_sec = original_end_sec

            # Helper to get prev/next keyframe
            def get_prev_next(all_kf: list[float], t: float):
                prev = None
                nextv = None
                if all_kf:
                    prev_candidates = [kf for kf in all_kf if kf <= t]
                    next_candidates = [kf for kf in all_kf if kf >= t]
                    if prev_candidates:
                        prev = max(prev_candidates)
                    if next_candidates:
                        nextv = min(next_candidates)
                return prev, nextv

            # Decide snapped_start to previous keyframe if available
            if start_kf_info and 'all_keyframes' in start_kf_info and start_kf_info['all_keyframes']:
                prev_kf, _ = get_prev_next(start_kf_info['all_keyframes'], original_start_sec)
                if prev_kf is not None:
                    snapped_start_sec = prev_kf
                    if abs(original_start_sec - prev_kf) > tolerance_sec:
                        out_of_tolerance_boundaries += 1
                else:
                    # Fallback to nearest
                    nearest = start_kf_info.get('nearest_keyframe', original_start_sec)
                    snapped_start_sec = nearest
                    if abs(original_start_sec - nearest) > tolerance_sec:
                        out_of_tolerance_boundaries += 1
            else:
                # No keyframe info found -> treat as out-of-tolerance to force precise path
                out_of_tolerance_boundaries += 1

            # Decide snapped_end to next keyframe if available
            if end_kf_info and 'all_keyframes' in end_kf_info and end_kf_info['all_keyframes']:
                _, next_kf = get_prev_next(end_kf_info['all_keyframes'], original_end_sec)
                if next_kf is not None:
                    snapped_end_sec = next_kf
                    if abs(original_end_sec - next_kf) > tolerance_sec:
                        out_of_tolerance_boundaries += 1
                else:
                    nearest = end_kf_info.get('nearest_keyframe', original_end_sec)
                    snapped_end_sec = nearest
                    if abs(original_end_sec - nearest) > tolerance_sec:
                        out_of_tolerance_boundaries += 1
            else:
                out_of_tolerance_boundaries += 1

            # Ensure snapped_end after snapped_start minimally
            if snapped_end_sec <= snapped_start_sec:
                snapped_end_sec = snapped_start_sec + 0.04  # add small epsilon (40ms)

            snapped_segments_seconds.append((snapped_start_sec, snapped_end_sec))

        return snapped_segments_seconds, out_of_tolerance_boundaries

    def _prompt_strategy_choice(self, out_of_tolerance_count: int, tolerance_sec: float) -> str:
        """
        Prompt the user to choose fast (snap) or precise (exact) strategy.
        Returns 'fast' or 'precise'. Defaults to 'precise' on error.
        """
        try:
            message = (
                f"{out_of_tolerance_count} cut point(s) are more than {tolerance_sec:.1f}s away from a keyframe.\n\n"
                "Choose processing strategy:\n\n"
                "Fast (snap): Snap to nearest keyframes and stream-copy (very fast).\n"
                "Precise (exact): Re-encode for exact cut points (slower)."
            )
            box = QMessageBox()
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Clipping Strategy")
            box.setText(message)
            fast_btn = box.addButton("Fast (snap)", QMessageBox.ButtonRole.AcceptRole)
            precise_btn = box.addButton("Precise (exact)", QMessageBox.ButtonRole.DestructiveRole)
            box.setDefaultButton(precise_btn)
            box.exec()
            clicked = box.clickedButton()
            return 'fast' if clicked == fast_btn else 'precise'
        except Exception as e:
            self._logger.error("ClippingManager", f"Error prompting strategy choice: {e}")
            return 'precise'

    def _perform_video_clip_fast_path(self, media_path: str, snapped_segments_seconds: list[tuple[float, float]], codec_info: dict, output_path: str) -> Optional[str]:
        """
        Fast path: Snap to keyframes and stream-copy segments, then concatenate by copy.
        Uses safer settings per codec.
        """
        import shutil
        import time

        original_path_obj = Path(media_path)
        temp_dir = original_path_obj.parent / "temp_clip_segments"
        os.makedirs(temp_dir, exist_ok=True)
        self._logger.info("ClippingManager", f"Using temp directory: {temp_dir}")
        list_file_path = temp_dir / "mylist.txt"

        temp_files: list[str] = []

        detected_codec = (codec_info.get('codec_name') if codec_info else '') or 'unknown'
        detected_codec = detected_codec.lower()

        is_h26x = detected_codec in ['h264', 'hevc', 'h265']
        is_vpx = detected_codec in ['vp8', 'vp9']

        try:
            # Extract each segment
            for i, (snap_start_sec, snap_end_sec) in enumerate(snapped_segments_seconds):
                duration_sec = max(0.25, snap_end_sec - snap_start_sec)
                if is_h26x:
                    temp_out = str(temp_dir / f"temp_segment_{i}.ts")
                    bsf = 'h264_mp4toannexb' if detected_codec == 'h264' else 'hevc_mp4toannexb'
                    cmd = [
                        'ffmpeg', '-y', '-hide_banner',
                        '-ss', str(snap_start_sec),
                        '-i', media_path,
                        '-t', str(duration_sec),
                        '-map', '0:v:0', '-map', '0:a?', '-sn',
                        '-c', 'copy',
                        '-bsf:v', bsf,
                        '-muxpreload', '0', '-muxdelay', '0',
                        '-f', 'mpegts',
                        temp_out
                    ]
                elif is_vpx:
                    temp_out = str(temp_dir / f"temp_segment_{i}.webm")
                    cmd = [
                        'ffmpeg', '-y', '-hide_banner',
                        '-ss', str(snap_start_sec),
                        '-i', media_path,
                        '-t', str(duration_sec),
                        '-map', '0:v:0', '-map', '0:a?', '-sn',
                        '-c', 'copy',
                        temp_out
                    ]
                else:
                    temp_out = str(temp_dir / f"temp_segment_{i}.mkv")
                    cmd = [
                        'ffmpeg', '-y', '-hide_banner',
                        '-ss', str(snap_start_sec),
                        '-i', media_path,
                        '-t', str(duration_sec),
                        '-map', '0:v:0', '-map', '0:a?', '-sn',
                        '-c', 'copy',
                        temp_out
                    ]

                self._logger.info("ClippingManager", f"Fast path segment {i+1}: {' '.join(cmd)}")
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                process = subprocess.run(cmd, capture_output=True, text=True, creationflags=creationflags)
                if process.returncode != 0:
                    self._logger.error("ClippingManager", f"Fast path segment {i+1} failed: {process.stderr}")
                    return None
                # Ensure segment file exists and is non-empty (Windows I/O can lag)
                if not os.path.exists(temp_out):
                    self._logger.error("ClippingManager", f"Fast path segment {i+1} missing: {temp_out}")
                    return None
                for _ in range(3):
                    try:
                        if os.path.getsize(temp_out) > 0:
                            break
                    except Exception:
                        pass
                    time.sleep(0.05)
                try:
                    sz = os.path.getsize(temp_out)
                except Exception:
                    sz = 0
                if sz == 0:
                    # Fallback: minimal re-encode for this segment into TS
                    self._logger.error("ClippingManager", f"Fast path segment {i+1} is zero bytes, retrying with minimal re-encode")
                    re_cmd = [
                        'ffmpeg', '-y', '-hide_banner',
                        '-ss', str(snap_start_sec),
                        '-i', media_path,
                        '-t', str(duration_sec),
                        '-map', '0:v:0', '-map', '0:a?', '-sn',
                        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-b:a', '128k',
                        '-g', '60', '-sc_threshold', '0',
                        '-muxpreload', '0', '-muxdelay', '0',
                        '-f', 'mpegts',
                        temp_out
                    ]
                    re_proc = subprocess.run(re_cmd, capture_output=True, text=True, creationflags=creationflags)
                    if re_proc.returncode != 0 or not os.path.exists(temp_out) or os.path.getsize(temp_out) == 0:
                        self._logger.error("ClippingManager", f"Fallback re-encode failed for segment {i+1}: {re_proc.stderr}")
                        return None
                temp_files.append(temp_out)

            # Write file list for concat demuxer using absolute, ffmpeg-safe paths
            with open(list_file_path, 'w', encoding='utf-8') as f:
                for temp_file in temp_files:
                    safe_path = self._format_concat_path(temp_file)
                    f.write(f"file '{safe_path}'\n")

            # Final concat by copy
            cmd_concat = [
                'ffmpeg', '-y', '-hide_banner',
                '-f', 'concat', '-safe', '0',
                '-i', str(list_file_path),
                '-c', 'copy',
                '-fflags', '+genpts',
                '-movflags', '+faststart'
            ]
            if is_h26x:
                cmd_concat += ['-bsf:a', 'aac_adtstoasc']
            cmd_concat += [output_path]

            self._logger.info("ClippingManager", f"Fast path concat: {' '.join(cmd_concat)}")
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.run(cmd_concat, capture_output=True, text=True, creationflags=creationflags)
            if process.returncode != 0:
                self._logger.error("ClippingManager", f"Fast path concat failed: {process.stderr}")
                return None

            self._logger.info("ClippingManager", f"Video clipping successful (fast path): {output_path}")
            self.clip_successful.emit(media_path, output_path)
            return output_path

        finally:
            # Clean up temp files and directory
            try:
                if list_file_path.exists():
                    os.remove(list_file_path)
            except Exception:
                pass
            for p in temp_files:
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
            try:
                if temp_dir.exists() and not any(temp_dir.iterdir()):
                    os.rmdir(temp_dir)
            except Exception:
                pass

    def _perform_video_clip_precise_path(self, media_path: str, merged_segments: list[tuple[int, int]], output_path: str, resize_720p: bool = False) -> Optional[str]:
        """
        Precise path: Use filter_complex to trim and concat in one job, then re-encode once.
        """
        # Build filter graph
        v_labels = []
        a_labels = []
        filter_parts = []

        for i, (start_ms, end_ms) in enumerate(merged_segments):
            start_sec = max(0.0, start_ms / 1000.0)
            end_sec = max(start_sec + 0.01, end_ms / 1000.0)
            v_label = f"v{i}"
            a_label = f"a{i}"
            filter_parts.append(f"[0:v]trim=start={start_sec:.6f}:end={end_sec:.6f},setpts=PTS-STARTPTS[{v_label}]")
            filter_parts.append(f"[0:a]atrim=start={start_sec:.6f}:end={end_sec:.6f},asetpts=PTS-STARTPTS[{a_label}]")
            v_labels.append(f"[{v_label}]")
            a_labels.append(f"[{a_label}]")

        concat_part = ''.join(v_labels + a_labels) + f"concat=n={len(merged_segments)}:v=1:a=1[v][a]"
        filter_complex = ';'.join(filter_parts + [concat_part])

        v_filters = []
        if resize_720p:
            # Detect orientation by comparing width and height via ffprobe could be added; 
            # for simplicity, scale with adaptive aspect preservation using min dimension 720
            # Use scale filter that keeps aspect ratio by bounding max dimension to 720
            # For landscape: scale=-2:720; for portrait: scale=720:-2
            # We cannot know here without probing each segment, so set to scale='min(720,ih)'
            # Simpler: apply a generic scale to fit within 720p on the longer edge using force_original_aspect_ratio
            v_filters.append("scale='if(gt(a,1),-2,720)':'if(gt(a,1),720,-2)':force_original_aspect_ratio=decrease")
        v_filter_chain = ",".join(v_filters) if v_filters else None

        cmd = [
            'ffmpeg', '-y', '-hide_banner',
            '-i', media_path,
            '-filter_complex', filter_complex if not v_filter_chain else filter_complex + f";[v]" + v_filter_chain + "[v2]",
            '-map', '[v2]' if v_filter_chain else '[v]', '-map', '[a]',
            '-c:v', 'libx264', '-crf', '20', '-preset', 'medium', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
            output_path
        ]

        self._logger.info("ClippingManager", f"Precise path (single encode): {' '.join(cmd[:-1])} {output_path}")
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        process = subprocess.run(cmd, capture_output=True, text=True, creationflags=creationflags)
        if process.returncode != 0:
            self._logger.error("ClippingManager", f"Precise path failed: {process.stderr}")
            self.clip_failed.emit(media_path, process.stderr.strip())
            return None

        self._logger.info("ClippingManager", f"Video clipping successful (precise path): {output_path}")
        self.clip_successful.emit(media_path, output_path)
        return output_path

    def _check_codec_encoding_support(self, codec_info: dict) -> dict:
        """
        Check if ffmpeg can re-encode using the same codec as the source video.
        Uses CRF=23 approach for balanced quality and file size.
        """
        self._logger.info("ClippingManager", f"Testing re-encoding capability for {codec_info['codec_name']}")
        
        try:
            # Check available encoders
            cmd = ['ffmpeg', '-encoders']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            
            codec_name = codec_info['codec_name'].lower()
            
            # Map codec names to encoder names
            encoder_mapping = {
                'h264': 'libx264',
                'hevc': 'libx265', 
                'h265': 'libx265',
                'vp9': 'libvpx-vp9',
                'vp8': 'libvpx',
                'av1': 'libaom-av1'
            }
            
            expected_encoder = encoder_mapping.get(codec_name)
            
            if expected_encoder and expected_encoder in result.stdout:
                self._logger.info("ClippingManager", f"✓ Encoder '{expected_encoder}' is available")
                
                original_bitrate_bps = int(codec_info['bit_rate']) if codec_info['bit_rate'] != 'Unknown' else 1000000
                original_bitrate_kbps = original_bitrate_bps // 1000
                
                self._logger.info("ClippingManager", "Using CRF=23 approach for quality balance")
                
                # Build encoding parameters for CRF
                encoding_params = []
                
                if codec_name == 'h264':
                    encoding_params.extend(['-c:v', 'libx264'])
                    encoding_params.extend(['-crf', '23'])  # Good quality CRF
                    
                    if codec_info['profile'] != 'Unknown':
                        encoding_params.extend(['-profile:v', codec_info['profile'].lower()])
                    if codec_info['level'] != 'Unknown':
                        level_str = str(codec_info['level'])
                        if len(level_str) == 2:
                            level_formatted = f"{level_str[0]}.{level_str[1]}"
                            encoding_params.extend(['-level', level_formatted])
                    if codec_info['pix_fmt'] != 'Unknown':
                        encoding_params.extend(['-pix_fmt', codec_info['pix_fmt']])
                    
                    encoding_params.extend([
                        '-preset', 'slow',         # Better quality
                        '-tune', 'film',           # Optimize for film content
                    ])
                    
                    self._logger.info("ClippingManager", "Using CRF=23 mode for balanced quality/size")
                
                elif codec_name == 'vp9':
                    encoding_params.extend(['-c:v', 'libvpx-vp9'])
                    encoding_params.extend(['-crf', '23'])  # Good quality CRF for VP9
                    encoding_params.extend(['-b:v', '0'])   # Use CRF mode (0 bitrate = CRF)
                    
                    # VP9-specific optimizations
                    encoding_params.extend([
                        '-speed', '2',              # Good speed/quality balance
                        '-tile-columns', '2',       # Parallel encoding tiles
                        '-auto-alt-ref', '1',       # Alternative reference frames
                        '-lag-in-frames', '25',     # Look-ahead frames
                    ])
                    
                    if codec_info['pix_fmt'] != 'Unknown':
                        encoding_params.extend(['-pix_fmt', codec_info['pix_fmt']])
                    
                    self._logger.info("ClippingManager", "Using VP9 CRF=23 mode for balanced quality/size")
                
                elif codec_name in ['hevc', 'h265']:
                    encoding_params.extend(['-c:v', 'libx265'])
                    encoding_params.extend(['-crf', '23'])  # Good quality CRF for x265
                    
                    if codec_info['profile'] != 'Unknown':
                        encoding_params.extend(['-profile:v', codec_info['profile'].lower()])
                    if codec_info['pix_fmt'] != 'Unknown':
                        encoding_params.extend(['-pix_fmt', codec_info['pix_fmt']])
                    
                    encoding_params.extend([
                        '-preset', 'medium',        # Good speed/quality balance for x265
                    ])
                    
                    self._logger.info("ClippingManager", "Using H.265 CRF=23 mode for balanced quality/size")
                
                return {
                    'supported': True,
                    'encoder': expected_encoder,
                    'encoding_params': encoding_params,
                    'approach': 'crf',
                    'codec_name': codec_name
                }
                    
            else:
                self._logger.info("ClippingManager", f"✗ Encoder not available for {codec_name}")
                return {'supported': False, 'reason': f'Encoder not available'}
            
        except subprocess.CalledProcessError as e:
            self._logger.error("ClippingManager", f"Failed to check encoder support: {e}")
            return {'supported': False, 'reason': 'ffmpeg command failed'}

    def _detect_media_type(self, media_path: str) -> str:
        """
        Detect if the media file is audio, video, or unknown.
        Returns: 'audio', 'video', or 'unknown'
        """
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_streams',
                media_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            data = json.loads(result.stdout)
            
            if 'streams' in data:
                has_video = False
                has_audio = False
                
                for stream in data['streams']:
                    codec_type = stream.get('codec_type', '')
                    if codec_type == 'video':
                        has_video = True
                    elif codec_type == 'audio':
                        has_audio = True
                
                if has_video:
                    return 'video'
                elif has_audio:
                    return 'audio'
                else:
                    return 'unknown'
            else:
                return 'unknown'
                
        except Exception as e:
            self._logger.error("ClippingManager", f"Media type detection error: {e}")
            return 'unknown'

    def _get_audio_codec_info(self, audio_path: str) -> dict:
        """
        Extract comprehensive codec information from audio file using ffprobe.
        """
        self._logger.info("ClippingManager", f"Analyzing audio codec: {audio_path}")
        
        try:
            # Get detailed codec information using ffprobe with JSON output
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_streams',
                '-select_streams', 'a:0',  # Select first audio stream
                audio_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            data = json.loads(result.stdout)
            
            if 'streams' in data and len(data['streams']) > 0:
                audio_stream = data['streams'][0]
                
                codec_info = {
                    'codec_name': audio_stream.get('codec_name', 'Unknown'),
                    'codec_long_name': audio_stream.get('codec_long_name', 'Unknown'),
                    'bit_rate': audio_stream.get('bit_rate', 'Unknown'),
                    'sample_rate': audio_stream.get('sample_rate', 'Unknown'),
                    'channels': audio_stream.get('channels', 'Unknown'),
                    'channel_layout': audio_stream.get('channel_layout', 'Unknown'),
                    'duration': audio_stream.get('duration', 'Unknown')
                }
                
                self._logger.info("ClippingManager", f"Detected audio: {codec_info['codec_name']} {codec_info['sample_rate']}Hz {codec_info['channels']}ch")
                return codec_info
            else:
                self._logger.info("ClippingManager", "No audio streams found in file")
                return {}
                
        except subprocess.CalledProcessError as e:
            self._logger.error("ClippingManager", f"ffprobe failed for audio: {e}")
            return {}
        except json.JSONDecodeError as e:
            self._logger.error("ClippingManager", f"JSON parsing failed for audio: {e}")
            return {}

    def _check_audio_codec_encoding_support(self, codec_info: dict) -> dict:
        """
        Check if ffmpeg can re-encode using the same codec as the source audio.
        """
        self._logger.info("ClippingManager", f"Testing audio re-encoding capability for {codec_info.get('codec_name', 'Unknown')}")
        
        try:
            # Check available encoders
            cmd = ['ffmpeg', '-encoders']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            
            codec_name = codec_info.get('codec_name', '').lower()
            
            # Map audio codec names to encoder names
            audio_encoder_mapping = {
                'mp3': 'libmp3lame',
                'aac': 'aac',
                'opus': 'libopus',
                'vorbis': 'libvorbis',
                'flac': 'flac',
                'pcm_s16le': 'pcm_s16le',
                'pcm_s24le': 'pcm_s24le',
                'alac': 'alac'
            }
            
            expected_encoder = audio_encoder_mapping.get(codec_name)
            
            if expected_encoder and expected_encoder in result.stdout:
                self._logger.info("ClippingManager", f"✓ Audio encoder '{expected_encoder}' is available")
                
                # Build encoding parameters for audio
                encoding_params = []
                
                if codec_name == 'mp3':
                    encoding_params.extend(['-c:a', 'libmp3lame'])
                    # Use VBR quality mode for MP3
                    encoding_params.extend(['-q:a', '2'])  # VBR quality 2 (high quality)
                    
                elif codec_name == 'aac':
                    encoding_params.extend(['-c:a', 'aac'])
                    encoding_params.extend(['-b:a', '128k'])  # Standard AAC bitrate
                    
                elif codec_name == 'opus':
                    encoding_params.extend(['-c:a', 'libopus'])
                    encoding_params.extend(['-b:a', '128k'])  # Standard Opus bitrate
                    
                elif codec_name == 'vorbis':
                    encoding_params.extend(['-c:a', 'libvorbis'])
                    encoding_params.extend(['-q:a', '5'])  # Vorbis quality 5 (good quality)
                    
                elif codec_name == 'flac':
                    encoding_params.extend(['-c:a', 'flac'])
                    # FLAC is lossless, no quality settings needed
                    
                elif codec_name.startswith('pcm_'):
                    encoding_params.extend(['-c:a', codec_name])
                    # PCM is uncompressed, no quality settings needed
                    
                elif codec_name == 'alac':
                    encoding_params.extend(['-c:a', 'alac'])
                    # ALAC is lossless, no quality settings needed
                
                # Preserve sample rate and channels if available
                if codec_info.get('sample_rate') != 'Unknown':
                    encoding_params.extend(['-ar', str(codec_info['sample_rate'])])
                if codec_info.get('channels') != 'Unknown':
                    encoding_params.extend(['-ac', str(codec_info['channels'])])
                
                self._logger.info("ClippingManager", f"Using audio encoding parameters: {' '.join(encoding_params)}")
                
                return {
                    'supported': True,
                    'encoder': expected_encoder,
                    'encoding_params': encoding_params,
                    'approach': 'audio_optimized',
                    'codec_name': codec_name
                }
                    
            else:
                self._logger.info("ClippingManager", f"✗ Audio encoder not available for {codec_name}")
                return {'supported': False, 'reason': f'Audio encoder not available'}
            
        except subprocess.CalledProcessError as e:
            self._logger.error("ClippingManager", f"Failed to check audio encoder support: {e}")
            return {'supported': False, 'reason': 'ffmpeg command failed'}

    def _perform_audio_clip(self, media_path: str, merged_segments: List[Tuple[int, int]], codec_info: dict, encoder_support: dict) -> Optional[str]:
        """
        Perform audio clipping using audio-optimized approach.
        Audio doesn't have keyframes, so we use sample-accurate cutting.
        """
        self._logger.info("ClippingManager", f"Processing {len(merged_segments)} audio segment(s)")
        
        # Generate output filename
        output_path = self._generate_clipped_filename()
        if not output_path:
            return None
            
        original_path_obj = Path(media_path)
        temp_files: List[str] = []
        temp_dir = original_path_obj.parent / "temp_clip_segments"
        os.makedirs(temp_dir, exist_ok=True)
        list_file_path = temp_dir / "mylist.txt"
        
        try:
            for i, (start_ms, end_ms) in enumerate(merged_segments):
                segment_duration_ms = end_ms - start_ms
                if segment_duration_ms <= 0: 
                    continue
                
                start_time_seconds = start_ms / 1000.0
                duration_seconds = segment_duration_ms / 1000.0
                
                self._logger.info("ClippingManager", f"=== Audio Segment {i+1}/{len(merged_segments)} ===")
                self._logger.info("ClippingManager", f"Segment timing: {start_time_seconds:.3f}s to {(start_ms + segment_duration_ms)/1000.0:.3f}s")
                
                temp_output_filename = f"temp_segment_{i}{original_path_obj.suffix}"
                temp_output_path = str(temp_dir / temp_output_filename)
                temp_files.append(temp_output_path)
                
                # Audio processing strategy
                if encoder_support['supported']:
                    self._logger.info("ClippingManager", f"Using audio-optimized encoding with {encoder_support['encoder']}")
                    
                    # High-quality audio re-encoding for sample accuracy
                    ffmpeg_cmd = [
                        "ffmpeg", "-y", "-hide_banner",
                        "-ss", str(start_time_seconds),
                        "-i", media_path,
                        "-t", str(duration_seconds)
                    ] + encoder_support['encoding_params'] + [
                        temp_output_path
                    ]
                    
                else:
                    self._logger.info("ClippingManager", "Using stream copy fallback for audio")
                    
                    # Stream copy fallback (should work for most audio formats)
                    ffmpeg_cmd = [
                        "ffmpeg", "-y", "-hide_banner",
                        "-ss", str(start_time_seconds),
                        "-i", media_path,
                        "-t", str(duration_seconds),
                        "-c", "copy",
                        "-avoid_negative_ts", "make_zero",
                        temp_output_path
                    ]
                
                self._logger.info("ClippingManager", f"Audio processing: {' '.join(ffmpeg_cmd)}")
                
                # Execute ffmpeg command
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                process = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, creationflags=creationflags)
                
                if process.returncode != 0:
                    error_message = f"Audio ffmpeg failed for segment {i}. Error: {process.stderr.strip()}"
                    self._logger.error("ClippingManager", error_message)
                    return None
                else:
                    self._logger.info("ClippingManager", f"Audio segment {i+1} processed successfully")
            
            # Concatenate all audio segments
            self._logger.info("ClippingManager", f"Concatenating {len(temp_files)} audio segments")
            
            with open(list_file_path, 'w') as f:
                for temp_file in temp_files:
                    safe_path = self._format_concat_path(os.path.abspath(temp_file))
                    f.write(f"file '{safe_path}'\n")
            
            ffmpeg_concat_cmd = [
                "ffmpeg", "-y", "-hide_banner",
                "-f", "concat", "-safe", "0",
                "-i", str(list_file_path),
                "-c", "copy",
                "-movflags", "+faststart",
                output_path
            ]
            
            self._logger.info("ClippingManager", f"Final audio concatenation: {' '.join(ffmpeg_concat_cmd)}")
            
            process = subprocess.run(ffmpeg_concat_cmd, capture_output=True, text=True, creationflags=creationflags)
            
            if process.returncode == 0:
                self._logger.info("ClippingManager", f"Audio clipping successful: {output_path}")
                self.clip_successful.emit(media_path, output_path)
                return output_path
            else:
                error_message = f"Audio concatenation failed. Error: {process.stderr.strip()}"
                self._logger.error("ClippingManager", error_message)
                self.clip_failed.emit(media_path, error_message)
                return None
                
        except Exception as e:
            error_message = f"Audio clipping failed: {str(e)}"
            self._logger.error("ClippingManager", error_message)
            return None
        finally:
            # Clean up temporary files
            self._cleanup_temp_files(temp_dir, temp_files, list_file_path)

    def perform_clip(self) -> Optional[str]:
        """
        Performs adaptive clipping operation using ffmpeg.
        Automatically detects media type and uses appropriate processing:
        - Video: Keyframe-aware processing (Option A/B/C) for efficiency and precision
        - Audio: Sample-accurate processing optimized for audio files
        
        Returns the path to the final clipped file on success, None otherwise.
        """
        media_path, pending_begin_ms, segments = self.get_markers()

        if not media_path:
            self._logger.warning("ClippingManager", "No media file specified for clipping.")
            self.clip_failed.emit("", "No media file specified for clipping.")
            return None

        if not segments:
            self._logger.warning("ClippingManager", "No segments defined for clipping.")
            self.clip_failed.emit(media_path, "No segments defined for clipping. Press 'B' then 'E' to define segments.")
            return None

        # 1. Sort Segments and filter out invalid ones
        valid_segments = sorted([s for s in segments if s[0] < s[1]], key=lambda x: x[0])
        if not valid_segments:
            self._logger.warning("ClippingManager", "No valid segments after sorting/filtering.")
            self.clip_failed.emit(media_path, "No valid segments to clip.")
            return None

        # 2. Merge Overlapping/Adjacent Segments
        merged_segments: List[Tuple[int, int]] = []
        current_start, current_end = valid_segments[0]
        for i in range(1, len(valid_segments)):
            next_start, next_end = valid_segments[i]
            if next_start <= current_end: # Overlap or adjacent
                current_end = max(current_end, next_end)
            else: # Gap, so finalize current segment and start a new one
                merged_segments.append((current_start, current_end))
                current_start, current_end = next_start, next_end
        merged_segments.append((current_start, current_end)) # Add the last processed segment

        if not merged_segments:
            self.clip_failed.emit(media_path, "Segment processing resulted in no segments.")
            return None

        # 3. Prompt user for options (Snap Keyframe, Resize 720p)
        snap_keyframe = False
        resize_720p = False
        try:
            # Parent will be the main window; QDialog will center itself reasonably
            dlg = ClippingOptionsDialog()
            if dlg.exec():
                opts = dlg.get_options()
                snap_keyframe = bool(opts.get('snap_keyframe', False))
                resize_720p = bool(opts.get('resize_720p', False))
        except Exception as e:
            self._logger.error("ClippingManager", f"Failed to show clipping options dialog: {e}")

        # 4. Detect media type to choose processing approach
        media_type = self._detect_media_type(media_path)
        self._logger.info("ClippingManager", f"Detected media type: {media_type}")

        try:
            if media_type == 'audio':
                # Audio processing path - sample-accurate clipping
                self._logger.info("ClippingManager", "Using audio processing pipeline")
                
                # Analyze audio codec
                audio_codec_info = self._get_audio_codec_info(media_path)
                if not audio_codec_info:
                    self._logger.info("ClippingManager", "Could not analyze audio codec, using stream copy")
                    audio_codec_info = {'codec_name': 'unknown'}
                
                # Check audio encoder support
                audio_encoder_support = self._check_audio_codec_encoding_support(audio_codec_info)
                
                # Perform audio clipping
                result_path = self._perform_audio_clip(media_path, merged_segments, audio_codec_info, audio_encoder_support)
                
                if result_path:
                    self._logger.info("ClippingManager", f"Audio clipping successful: {result_path}")
                    self.clip_successful.emit(media_path, result_path)
                    return result_path
                else:
                    self._logger.error("ClippingManager", "Audio clipping failed")
                    self.clip_failed.emit(media_path, "Audio clipping failed")
                    return None
                    
            elif media_type == 'video':
                # Video processing path - dual strategy selection
                self._logger.info("ClippingManager", "Analyzing keyframes for fast/precise strategy selection")

                # Determine codec info once
                codec_info = self._get_video_codec_info(media_path)

                # Compute snap plan and count out-of-tolerance boundaries
                snapped_segments_seconds, out_of_tol = self._compute_snap_plan_for_segments(
                    media_path, merged_segments, KEYFRAME_SNAP_TOLERANCE_SEC
                )

                output_path = self._generate_clipped_filename()
                if not output_path:
                    self._logger.error("ClippingManager", "Could not generate an output filename.")
                    self.clip_failed.emit(media_path, "Could not generate an output filename for the clip.")
                    return None

                # New option: Force Snap Keyframe (stream copy only) if requested
                if snap_keyframe and not resize_720p:
                    self._logger.info("ClippingManager", "Force Snap Keyframe enabled -> using stream copy regardless of tolerance")
                    return self._perform_video_clip_fast_path(media_path, snapped_segments_seconds, codec_info, output_path)

                # If resizing to 720p is requested, we must re-encode with scaling filter
                if resize_720p:
                    self._logger.info("ClippingManager", "Resize to 720p enabled -> using precise path with scaling")
                    return self._perform_video_clip_precise_path(media_path, merged_segments, output_path, resize_720p=True)

                # Default decision tree (no explicit options selected)
                if out_of_tol == 0:
                    self._logger.info("ClippingManager", "All cut points within tolerance -> using fast stream-copy path")
                    return self._perform_video_clip_fast_path(media_path, snapped_segments_seconds, codec_info, output_path)
                else:
                    strategy = self._prompt_strategy_choice(out_of_tol, KEYFRAME_SNAP_TOLERANCE_SEC)
                    if strategy == 'fast':
                        self._logger.info("ClippingManager", "User selected Fast (snap) -> using fast stream-copy path")
                        return self._perform_video_clip_fast_path(media_path, snapped_segments_seconds, codec_info, output_path)
                    else:
                        self._logger.info("ClippingManager", "User selected Precise (exact) -> re-encoding via concat filter")
                        return self._perform_video_clip_precise_path(media_path, merged_segments, output_path)
                
            else:
                # Unknown media type - try basic processing
                self._logger.warning("ClippingManager", f"Unknown media type '{media_type}', attempting basic processing")
                return self._perform_basic_clip(media_path, merged_segments)
                
        except Exception as e:
            error_message = f"Clipping failed: {str(e)}"
            self._logger.error("ClippingManager", error_message)
            self.clip_failed.emit(media_path, error_message)
            return None

    def _perform_video_clip(self, media_path: str, merged_segments: List[Tuple[int, int]]) -> Optional[str]:
        """
        Perform video clipping using keyframe-aware adaptive processing.
        This is the original video processing logic extracted into a separate method.
        """
        # 3. Analyze original video codec (once for all segments)
        self._logger.info("ClippingManager", f"Analyzing original video for adaptive processing")
        codec_info = self._get_video_codec_info(media_path)
        if not codec_info:
            self._logger.info("ClippingManager", "Could not analyze video codec, using basic encoding")
            # Fallback to basic encoding if codec analysis fails
            return self._perform_basic_clip(media_path, merged_segments)
        
        # 4. Check codec encoding support
        encoder_support = self._check_codec_encoding_support(codec_info)

        output_path = self._generate_clipped_filename()
        if not output_path:
            self._logger.error("ClippingManager", "Could not generate an output filename.")
            self.clip_failed.emit(media_path, "Could not generate an output filename for the clip.")
            return None

        # 5. Process each segment with adaptive algorithm
        temp_files: List[str] = []
        original_path_obj = Path(media_path)
        temp_dir = original_path_obj.parent / "temp_clip_segments"
        os.makedirs(temp_dir, exist_ok=True)
        list_file_path = temp_dir / "mylist.txt"

        try:
            self._logger.info("ClippingManager", f"Processing {len(merged_segments)} segment(s) with adaptive algorithm")
            
            for i, (start_ms, end_ms) in enumerate(merged_segments):
                segment_duration_ms = end_ms - start_ms
                if segment_duration_ms <= 0: continue
                
                start_time_seconds = start_ms / 1000.0
                end_time_seconds = end_ms / 1000.0
                
                self._logger.info("ClippingManager", f"\n=== Segment {i+1}/{len(merged_segments)} ===")
                self._logger.info("ClippingManager", f"Segment timing: {start_time_seconds:.3f}s to {end_time_seconds:.3f}s")
                
                # Analyze keyframes around the start time
                keyframe_info = self._find_nearest_keyframe(media_path, start_time_seconds)

                temp_output_filename = f"temp_segment_{i}{original_path_obj.suffix}"
                temp_output_path = str(temp_dir / temp_output_filename)
                temp_files.append(temp_output_path)

                # Adaptive processing decision
                if keyframe_info and keyframe_info['within_threshold']:
                    # Option A: Keyframe Snapping (≤ 0.4s threshold)
                    self._logger.info("ClippingManager", "Using Option A: Keyframe Snapping")
                    snapped_start_time = keyframe_info['nearest_keyframe']
                    adjustment = keyframe_info['distance']
                    
                    self._logger.info("ClippingManager", f"Snapping from {start_time_seconds:.3f}s to {snapped_start_time:.3f}s")
                    self._logger.info("ClippingManager", f"Time adjustment: {abs(adjustment):.3f}s {'forward' if adjustment > 0 else 'backward'}")
                    
                    # Adjust end time relative to the snapped start time
                    adjusted_duration = (end_ms - start_ms) / 1000.0
                    
                    # Use pure stream copy for maximum efficiency
                    ffmpeg_cmd = [
                        "ffmpeg", "-y", "-hide_banner",
                        "-ss", str(snapped_start_time),
                        "-i", media_path,
                        "-t", str(adjusted_duration),
                        "-c", "copy",  # Pure stream copy
                        "-avoid_negative_ts", "make_zero",
                        temp_output_path
                    ]
                    
                    self._logger.info("ClippingManager", f"Keyframe snapping (stream copy): {' '.join(ffmpeg_cmd)}")
                    
                else:
                    # Option B: Minimal Re-encoding (> 0.4s threshold) or Option C: Unsupported codec fallback
                    if not encoder_support['supported']:
                        # Option C: Enhanced keyframe snapping for unsupported codecs
                        self._logger.info("ClippingManager", "Using Option C: Enhanced Keyframe Snapping (unsupported codec)")
                        
                        if keyframe_info:
                            # Find nearest keyframe with backward preference
                            all_keyframes = keyframe_info['all_keyframes']
                            backward_keyframes = [kf for kf in all_keyframes if kf <= start_time_seconds]
                            
                            if backward_keyframes:
                                snapped_start_time = max(backward_keyframes)  # Nearest before
                                self._logger.info("ClippingManager", f"Enhanced snapping: {start_time_seconds:.3f}s -> {snapped_start_time:.3f}s (backward preference)")
                            else:
                                # Fall back to forward keyframe if no backward available
                                forward_keyframes = [kf for kf in all_keyframes if kf > start_time_seconds]
                                if forward_keyframes:
                                    snapped_start_time = min(forward_keyframes)
                                    self._logger.info("ClippingManager", f"Enhanced snapping: {start_time_seconds:.3f}s -> {snapped_start_time:.3f}s (forward fallback)")
                                else:
                                    snapped_start_time = start_time_seconds
                                    self._logger.info("ClippingManager", "No keyframes found, using original time")
                            
                            adjusted_duration = (end_ms - start_ms) / 1000.0
                            
                            # Use pure stream copy
                            ffmpeg_cmd = [
                                "ffmpeg", "-y", "-hide_banner",
                                "-ss", str(snapped_start_time),
                                "-i", media_path,
                                "-t", str(adjusted_duration),
                                "-c", "copy",  # Pure stream copy
                                "-avoid_negative_ts", "make_zero",
                                temp_output_path
                            ]
                            
                            self._logger.info("ClippingManager", f"Enhanced keyframe snapping: {' '.join(ffmpeg_cmd)}")
                        else:
                            self._logger.info("ClippingManager", "No keyframe data, falling back to basic re-encoding")
                            return self._perform_basic_clip(media_path, merged_segments)
                            
                    else:
                        # Option B: Minimal Re-encoding for precision
                        self._logger.info("ClippingManager", "Using Option B: Minimal Re-encoding")
                        
                        if keyframe_info:
                            # Find first keyframe at or after start time
                            first_keyframe_after = None
                            for kf_time in keyframe_info['all_keyframes']:
                                if kf_time >= start_time_seconds:
                                    first_keyframe_after = kf_time
                                    break
                            
                            if first_keyframe_after:
                                reencoding_duration = first_keyframe_after - start_time_seconds
                                self._logger.info("ClippingManager", f"Re-encoding {reencoding_duration:.3f}s from {start_time_seconds:.3f}s to {first_keyframe_after:.3f}s")
                                
                                # Phase 1: Re-encode from start to first keyframe
                                # Use consistent output format based on original codec
                                original_extension = original_path_obj.suffix
                                temp_extension = original_extension  # Keep same container format
                                
                                # Override for certain codecs that need specific containers
                                detected_codec = encoder_support.get('codec_name', 'unknown')
                                if detected_codec == 'vp9':
                                    temp_extension = '.webm'  # VP9 should use WebM container
                                elif detected_codec in ['h264', 'hevc', 'h265']:
                                    temp_extension = '.mp4'   # H.264/H.265 should use MP4 container
                                
                                temp_reencoded = str(temp_dir / f"reencoded_{i}{temp_extension}")
                                
                                ffmpeg_reencode_cmd = [
                                    "ffmpeg", "-y", "-hide_banner",
                                    "-ss", str(start_time_seconds),
                                    "-i", media_path,
                                    "-t", str(reencoding_duration),
                                    "-force_key_frames", "expr:gte(t,0)"
                                ] + encoder_support['encoding_params'] + [
                                    "-c:a", "libopus" if detected_codec == 'vp9' else "aac", 
                                    "-b:a", "128k",
                                    temp_reencoded
                                ]
                                
                                self._logger.info("ClippingManager", f"Phase 1 (re-encode): {' '.join(ffmpeg_reencode_cmd)}")
                                
                                creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                                process = subprocess.run(ffmpeg_reencode_cmd, capture_output=True, text=True, creationflags=creationflags)
                                
                                if process.returncode != 0:
                                    self._logger.error("ClippingManager", f"Phase 1 failed: {process.stderr}")
                                    return None
                                
                                # Phase 2: Stream copy from first keyframe to end
                                temp_streamcopy = str(temp_dir / f"streamcopy_{i}{temp_extension}")
                                remaining_duration = end_time_seconds - first_keyframe_after
                                
                                if remaining_duration > 0:
                                    ffmpeg_streamcopy_cmd = [
                                        "ffmpeg", "-y", "-hide_banner",
                                        "-ss", str(first_keyframe_after),
                                        "-i", media_path,
                                        "-t", str(remaining_duration),
                                        "-c", "copy",
                                        temp_streamcopy
                                    ]
                                    
                                    self._logger.info("ClippingManager", f"Phase 2 (stream copy): {' '.join(ffmpeg_streamcopy_cmd)}")
                                    
                                    process = subprocess.run(ffmpeg_streamcopy_cmd, capture_output=True, text=True, creationflags=creationflags)
                                    
                                    if process.returncode != 0:
                                        self._logger.error("ClippingManager", f"Phase 2 failed: {process.stderr}")
                                        return None
                                    
                                    # Phase 3: Concatenate the two parts
                                    concat_list = str(temp_dir / f"concat_{i}.txt")
                                    with open(concat_list, 'w') as f:
                                        reencoded_name = os.path.basename(temp_reencoded)
                                        streamcopy_name = os.path.basename(temp_streamcopy)
                                        f.write(f"file '{reencoded_name}'\n")
                                        f.write(f"file '{streamcopy_name}'\n")
                                    
                                    # Use consistent output format for final segment
                                    temp_final_segment = str(temp_dir / f"temp_segment_{i}{temp_extension}")
                                    
                                    ffmpeg_concat_cmd = [
                                        "ffmpeg", "-y", "-hide_banner",
                                        "-f", "concat", "-safe", "0",
                                        "-i", concat_list,
                                        "-c", "copy",
                                        temp_final_segment
                                    ]
                                    
                                    self._logger.info("ClippingManager", f"Phase 3 (concat): {' '.join(ffmpeg_concat_cmd)}")
                                    
                                    process = subprocess.run(ffmpeg_concat_cmd, capture_output=True, text=True, creationflags=creationflags, cwd=str(temp_dir))
                                    
                                    if process.returncode != 0:
                                        self._logger.error("ClippingManager", f"Phase 3 failed: {process.stderr}")
                                        
                                        # Check if it's a codec/container mismatch issue
                                        error_output = process.stderr.lower()
                                        if any(keyword in error_output for keyword in ['incorrect codec parameters', 'only vp8 or vp9', 'only h264']):
                                            self._logger.info("ClippingManager", "Codec/container mismatch detected, falling back to enhanced keyframe snapping")
                                            
                                            # Fallback to enhanced keyframe snapping (Option C approach)
                                            if keyframe_info:
                                                all_keyframes = keyframe_info['all_keyframes']
                                                backward_keyframes = [kf for kf in all_keyframes if kf <= start_time_seconds]
                                                
                                                if backward_keyframes:
                                                    fallback_start_time = max(backward_keyframes)
                                                    self._logger.info("ClippingManager", f"Fallback snapping: {start_time_seconds:.3f}s -> {fallback_start_time:.3f}s")
                                                else:
                                                    forward_keyframes = [kf for kf in all_keyframes if kf > start_time_seconds]
                                                    if forward_keyframes:
                                                        fallback_start_time = min(forward_keyframes)
                                                        self._logger.info("ClippingManager", f"Fallback snapping: {start_time_seconds:.3f}s -> {fallback_start_time:.3f}s")
                                                    else:
                                                        fallback_start_time = start_time_seconds
                                                
                                                fallback_duration = (end_ms - start_ms) / 1000.0
                                                
                                                # Use simple stream copy with fallback timing
                                                fallback_cmd = [
                    "ffmpeg", "-y", "-hide_banner",
                                                    "-ss", str(fallback_start_time),
                    "-i", media_path,
                                                    "-t", str(fallback_duration),
                    "-c", "copy",
                                                    "-avoid_negative_ts", "make_zero",
                                                    temp_output_path
                                                ]
                                                
                                                self._logger.info("ClippingManager", f"Fallback stream copy: {' '.join(fallback_cmd)}")
                                                
                                                fallback_process = subprocess.run(fallback_cmd, capture_output=True, text=True, creationflags=creationflags)
                                                
                                                if fallback_process.returncode != 0:
                                                    self._logger.error("ClippingManager", f"Fallback also failed: {fallback_process.stderr}")
                                                    return None
                                                else:
                                                    self._logger.info("ClippingManager", f"Segment {i+1} processed successfully with fallback")
                                                    continue  # Skip to next segment
                                            else:
                                                return None
                                        else:
                                            return None
                                    else:
                                        # Phase 3 succeeded - move the concatenated segment to expected location
                                        import shutil
                                        shutil.move(temp_final_segment, temp_output_path)
                                        self._logger.info("ClippingManager", f"Segment {i+1} processed successfully (minimal re-encoding)")
                                else:
                                    # Only re-encoded portion needed (no stream copy part)
                                    import shutil
                                    shutil.move(temp_reencoded, temp_output_path)
                                    self._logger.info("ClippingManager", f"Segment {i+1} processed successfully (re-encode only)")
                            else:
                                self._logger.info("ClippingManager", "No keyframe found after start time, using full re-encoding")
                                # Fall back to single-phase re-encoding
                                ffmpeg_cmd = [
                                    "ffmpeg", "-y", "-hide_banner",
                                    "-ss", str(start_time_seconds),
                                    "-i", media_path,
                                    "-t", str((end_ms - start_ms) / 1000.0),
                                    "-force_key_frames", "expr:gte(t,0)"
                                ] + encoder_support['encoding_params'] + [
                                    "-c:a", "libopus" if encoder_support.get('codec_name') == 'vp9' else "aac", 
                                    "-b:a", "128k",
                    temp_output_path
                ]
                
                                # Execute the chosen ffmpeg command (for Options A, C, and basic re-encoding)
                                if 'ffmpeg_cmd' in locals():
                                    creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                                    process = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, creationflags=creationflags)
                                    if process.returncode != 0:
                                        error_message = f"ffmpeg failed for segment {i}. Error: {process.stderr.strip()}"
                                        self._logger.error("ClippingManager", error_message)
                                        self.clip_failed.emit(media_path, error_message)
                                        return None
                                    else:
                                        self._logger.info("ClippingManager", f"Segment {i+1} processed successfully")

            # 6. Concatenate all processed segments into final output
            self._logger.info("ClippingManager", f"\nConcatenating {len(temp_files)} processed segments")
            
            with open(list_file_path, 'w') as f:
                for temp_file in temp_files:
                    rel_name = os.path.basename(temp_file)
                    f.write(f"file '{rel_name}'\n")

            ffmpeg_final_concat_cmd = [
                "ffmpeg", "-y", "-hide_banner",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_file_path),
                "-c", "copy",
                "-movflags", "+faststart",
                output_path
            ]
            
            self._logger.info("ClippingManager", f"Final concatenation: {' '.join(ffmpeg_final_concat_cmd)}")
            
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.run(ffmpeg_final_concat_cmd, capture_output=True, text=True, creationflags=creationflags, cwd=str(temp_dir))

            if process.returncode == 0:
                self._logger.info("ClippingManager", f"Video clipping successful: {output_path}")
                self.clip_successful.emit(media_path, output_path)
                return output_path
            else:
                error_message = f"ffmpeg failed concatenating segments. Error: {process.stderr.strip()}"
                self._logger.error("ClippingManager", error_message)
                self.clip_failed.emit(media_path, error_message)
                return None

        except subprocess.TimeoutExpired:
            if 'process' in locals() and hasattr(process, 'kill'): process.kill() # type: ignore
            error_message = "ffmpeg command timed out during adaptive processing"
            self._logger.error("ClippingManager", error_message)
            self.clip_failed.emit(media_path, error_message)
            return None
        except FileNotFoundError:
            error_message = "ffmpeg not found. Please ensure it's installed and in your system's PATH."
            self._logger.error("ClippingManager", error_message)
            self.clip_failed.emit(media_path, error_message)
            return None
        except Exception as e:
            error_message = f"An unexpected error occurred during video clipping: {str(e)}"
            self._logger.error("ClippingManager", error_message)
            self.clip_failed.emit(media_path, error_message)
            return None
        finally:
            # Clean up temporary files
            self._cleanup_temp_files(temp_dir, temp_files, list_file_path)

    def _perform_basic_clip(self, media_path: str, merged_segments: List[Tuple[int, int]]) -> Optional[str]:
        """
        Fallback method using basic encoding when codec analysis fails.
        """
        self._logger.info("ClippingManager", "Using basic clipping fallback")
        
        output_path = self._generate_clipped_filename()
        if not output_path:
            return None
            
        temp_files: List[str] = []
        original_path_obj = Path(media_path)
        temp_dir = original_path_obj.parent / "temp_clip_segments"
        os.makedirs(temp_dir, exist_ok=True)
        list_file_path = temp_dir / "mylist.txt"

        try:
            for i, (start_ms, end_ms) in enumerate(merged_segments):
                segment_duration_ms = end_ms - start_ms
                if segment_duration_ms <= 0: continue

                temp_output_filename = f"temp_segment_{i}{original_path_obj.suffix}"
                temp_output_path = str(temp_dir / temp_output_filename)
                temp_files.append(temp_output_path)

                start_time_str = self._ms_to_ffmpeg_time(start_ms)
                duration_str = self._ms_to_ffmpeg_time(segment_duration_ms)
                
                # Basic encoding with CRF=23
                ffmpeg_cmd = [
                    "ffmpeg", "-y", "-hide_banner",
                    "-ss", start_time_str,
                    "-i", media_path,
                    "-t", duration_str,
                    "-c:v", "libx264",
                    "-crf", "23",
                    "-preset", "fast",
                    "-force_key_frames", "expr:gte(t,0)",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-avoid_negative_ts", "make_zero",
                    temp_output_path
                ]
                
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                process = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, creationflags=creationflags)
                
                if process.returncode != 0:
                    error_message = f"Basic encoding failed for segment {i}. Error: {process.stderr.strip()}"
                    self._logger.error("ClippingManager", error_message)
                    self.clip_failed.emit(media_path, error_message)
                    return None

            # Concatenate segments
            with open(list_file_path, 'w') as f:
                for temp_file in temp_files:
                    rel_name = os.path.basename(temp_file)
                    f.write(f"file '{rel_name}'\n")

            ffmpeg_concat_cmd = [
                "ffmpeg", "-y", "-hide_banner",
                "-f", "concat", "-safe", "0",
                "-i", str(list_file_path),
                "-c", "copy",
                "-movflags", "+faststart",
                output_path
            ]
            
            process = subprocess.run(ffmpeg_concat_cmd, capture_output=True, text=True, creationflags=creationflags)

            if process.returncode == 0:
                self._logger.info("ClippingManager", f"Basic clipping successful: {output_path}")
                self.clip_successful.emit(media_path, output_path)
                return output_path
            else:
                error_message = f"Basic concatenation failed. Error: {process.stderr.strip()}"
                self._logger.error("ClippingManager", error_message)
                self.clip_failed.emit(media_path, error_message)
                return None
                
        except Exception as e:
            error_message = f"Basic clipping failed: {str(e)}"
            self._logger.error("ClippingManager", error_message)
            self.clip_failed.emit(media_path, error_message)
            return None
        finally:
            self._cleanup_temp_files(temp_dir, temp_files, list_file_path)

    def _cleanup_temp_files(self, temp_dir: Path, temp_files: List[str], list_file_path: Path):
        """Clean up temporary files and directory."""
        if list_file_path.exists():
            try:
                os.remove(list_file_path)
            except Exception as e:
                self._logger.error("ClippingManager", f"Error removing list file: {e}")
        
        for temp_file_path_str in temp_files:
            temp_file_p = Path(temp_file_path_str)
            if temp_file_p.exists():
                try:
                    os.remove(temp_file_p)
                except Exception as e:
                    self._logger.error("ClippingManager", f"Error removing temp file: {e}")
        
        # Clean up additional temporary files (from minimal re-encoding)
        if temp_dir.exists():
            try:
                for temp_item in temp_dir.glob("*"):
                    if temp_item.is_file():
                        os.remove(temp_item)
                
                if not any(temp_dir.iterdir()): 
                    os.rmdir(temp_dir)
            except Exception as e:
                self._logger.error("ClippingManager", f"Error cleaning temp directory: {e}")
