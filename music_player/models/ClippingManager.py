# music_player/models/ClippingManager.py
from PyQt6.QtCore import QObject, pyqtSignal
from typing import Optional, Tuple, List
import subprocess
import os
from pathlib import Path

class ClippingManager(QObject):
    """
    Manages the state of clipping markers (begin and end points) for media files,
    generates output filenames, and handles the ffmpeg process for clipping.
    This is a singleton class.
    """

    # Signals
    # Emits (media_path, begin_ms, end_ms) when markers or associated media change
    markers_updated = pyqtSignal(str, object, list) # pending_begin_ms (Optional[int]), segments (List[Tuple[int, int]])
    # Emits (original_path, clipped_path) on successful clip
    clip_successful = pyqtSignal(str, str)
    # Emits (original_path, error_message) on failed clip
    clip_failed = pyqtSignal(str, str)

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
        # self._begin_marker_ms: Optional[int] = None # OLD
        # self._end_marker_ms: Optional[int] = None   # OLD

        # --- NEW Data Structures for Multi-Segment ---
        self._pending_begin_marker_ms: Optional[int] = None
        self._segments: List[Tuple[int, int]] = [] # List of (start_ms, end_ms) tuples
        # ---------------------------------------------

        # Consider adding from qt_base_app.models.logger import Logger
        # self.logger = Logger.instance()

    def set_media(self, media_path: str):
        """
        Sets the current media file for clipping.
        - If the media path changes, existing markers are cleared.
        - Emits markers_updated(new_media_path_or_empty, None, None)
          for the new state (new media or no media).
        """
        # Normalize media_path: treat None as empty string for consistency
        effective_media_path = media_path if media_path is not None else ""

        if self._current_media_path != effective_media_path:
            # print(f"[ClippingManager] Media changing from '{self._current_media_path}' to '{effective_media_path}'")
            self._current_media_path = effective_media_path
            # self._begin_marker_ms = None # OLD
            # self._end_marker_ms = None   # OLD
            self._pending_begin_marker_ms = None # NEW
            self._segments = []                  # NEW
            
            # Always emit for the new state (new media or no media)
            # This ensures the UI is updated to reflect the (cleared) markers for the new context.
            # self.markers_updated.emit(self._current_media_path, self._begin_marker_ms, self._end_marker_ms) # OLD
            self.markers_updated.emit(self._current_media_path, self._pending_begin_marker_ms, self._segments) # NEW

    def mark_begin(self, timestamp_ms: int):
        """Sets the pending beginning marker for a new segment."""
        print(f"[ClippingManager DEBUG] mark_begin: _current_media_path='{self._current_media_path}', received timestamp_ms={timestamp_ms}") # DEBUG
        if not self._current_media_path:
            print("[ClippingManager] No media set, cannot mark pending begin.")
            return
        self._pending_begin_marker_ms = timestamp_ms
        if self._current_media_path:
            print(f"[ClippingManager DEBUG] mark_begin: Emitting markers_updated with pending_ms={self._pending_begin_marker_ms}") # DEBUG
            self.markers_updated.emit(self._current_media_path, self._pending_begin_marker_ms, self._segments)

    def mark_end(self, timestamp_ms: int):
        """Finalizes a segment using the pending begin marker and the given end timestamp."""
        print(f"[ClippingManager DEBUG] mark_end: _current_media_path='{self._current_media_path}', timestamp_ms={timestamp_ms}, _pending_begin_marker_ms BEFORE check = {self._pending_begin_marker_ms}") # DEBUG
        if not self._current_media_path:
            print("[ClippingManager] No media set, cannot mark end to define a segment.")
            return

        if self._pending_begin_marker_ms is None:
            print("[ClippingManager] No pending begin marker set. Press 'B' first to mark the start of a segment.")
            return

        if timestamp_ms <= self._pending_begin_marker_ms:
            print("[ClippingManager] End marker must be after pending begin marker.")
            return

        # Add the new segment
        new_segment = (self._pending_begin_marker_ms, timestamp_ms)
        self._segments.append(new_segment)
        self._pending_begin_marker_ms = None # Clear pending marker after defining a segment
        
        # Optional: Sort segments? Or sort only before clipping.
        # self._segments.sort(key=lambda x: x[0]) 

        # self.logger.debug(f"Segment {new_segment} added for {self._current_media_path}. Total segments: {len(self._segments)}")
        if self._current_media_path:
            print(f"[ClippingManager DEBUG] mark_end: Emitting markers_updated. Pending_ms is now {self._pending_begin_marker_ms}, segments: {self._segments}") # DEBUG
            self.markers_updated.emit(self._current_media_path, self._pending_begin_marker_ms, self._segments)

    # def clear_begin_marker(self): # OLD - Replaced by clear_pending_begin_marker
    #     """Clears the beginning marker."""
    #     if self._begin_marker_ms is not None:
    #         self._begin_marker_ms = None
    #         # self.logger.debug(f"Begin marker cleared for {self._current_media_path}")
    #         if self._current_media_path: # ensure media_path is not None
    #             self.markers_updated.emit(self._current_media_path, self._begin_marker_ms, self._end_marker_ms)

    # def clear_end_marker(self): # OLD - Not directly replaced, segment removal is different
    #     """Clears the end marker."""
    #     if self._end_marker_ms is not None:
    #         self._end_marker_ms = None
    #         # self.logger.debug(f"End marker cleared for {self._current_media_path}")
    #         if self._current_media_path: # ensure media_path is not None
    #             self.markers_updated.emit(self._current_media_path, self._begin_marker_ms, self._end_marker_ms)

    # def clear_all_markers(self): # OLD - Replaced by clear_all_segments
    #     """Clears both begin and end markers for the current active media, if any markers were set."""
    #     if not self._current_media_path: # Cannot clear markers if no media is active
    #         # print("[ClippingManager] No current media, cannot clear markers.")
    #         return
    #     # Check if markers were actually set before clearing and emitting
    #     if self._begin_marker_ms is not None or self._end_marker_ms is not None:
    #         self._begin_marker_ms = None
    #         self._end_marker_ms = None
    #         # print(f"[ClippingManager] All markers cleared for {self._current_media_path}")
    #         self.markers_updated.emit(self._current_media_path, self._begin_marker_ms, self._end_marker_ms)

    # --- NEW Methods for Multi-Segment Management ---
    def clear_pending_begin_marker(self):
        """Clears the currently pending begin marker."""
        if self._pending_begin_marker_ms is not None:
            self._pending_begin_marker_ms = None
            # print("[ClippingManager] Pending begin marker cleared.")
            if self._current_media_path:
                self.markers_updated.emit(self._current_media_path, self._pending_begin_marker_ms, self._segments)

    def clear_last_segment(self):
        """Removes the last added segment from the list."""
        if self._segments:
            removed_segment = self._segments.pop()
            # print(f"[ClippingManager] Last segment {removed_segment} removed.")
            if self._current_media_path:
                self.markers_updated.emit(self._current_media_path, self._pending_begin_marker_ms, self._segments)
        # else:
            # print("[ClippingManager] No segments to remove.")

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
            # print("[ClippingManager] All segments and pending markers cleared.")
            self.markers_updated.emit(self._current_media_path, self._pending_begin_marker_ms, self._segments)
        elif not self._current_media_path and changed: # Should not happen if logic is correct elsewhere
            # This case implies markers were cleared but no media path associated, potentially after media was set to None
            # To be safe, ensure UI gets an update for no media and no markers.
            self.markers_updated.emit("", None, [])
    # ----------------------------------------------

    def get_markers(self) -> Tuple[Optional[str], Optional[int], List[Tuple[int, int]]]: # Updated return type
        """Returns the current media path, pending begin marker, and list of segments."""
        # return self._current_media_path, self._begin_marker_ms, self._end_marker_ms # OLD
        return self._current_media_path, self._pending_begin_marker_ms, self._segments # NEW

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
        """Generates a unique filename for the clipped media."""
        if not self._current_media_path:
            # self.logger.error("ClippingManager: Cannot generate filename, no current media path.")
            return None

        original_path = Path(self._current_media_path)
        directory = original_path.parent
        stem = original_path.stem
        ext = original_path.suffix # Includes the dot, e.g., ".mp3"

        counter = 1
        while True:
            # Ensure stem doesn't accidentally create hidden files if it starts with "."
            # though original_path.stem usually handles this.
            clipped_filename = f"{stem}({counter}){ext}"
            potential_path = directory / clipped_filename
            if not potential_path.exists():
                # self.logger.info(f"Generated clipped filename: {potential_path}")
                return str(potential_path)
            counter += 1

    def perform_clip(self) -> Optional[str]:
        """
        Performs the clipping operation using ffmpeg based on the current_media_path and _segments.
        Segments are merged using ffmpeg's concat demuxer.
        Returns the path to the final clipped file on success, None otherwise.
        """
        media_path, pending_begin_ms, segments = self.get_markers()

        if not media_path:
            print("[ClippingManager] No media file specified for clipping.")
            self.clip_failed.emit("", "No media file specified for clipping.")
            return None

        if not segments:
            print("[ClippingManager] No segments defined for clipping.")
            self.clip_failed.emit(media_path, "No segments defined for clipping. Press 'B' then 'E' to define segments.")
            return None

        # 1. Sort Segments (and filter out any invalid ones that might have slipped through)
        valid_segments = sorted([s for s in segments if s[0] < s[1]], key=lambda x: x[0])
        if not valid_segments:
            print("[ClippingManager] No valid segments after sorting/filtering.")
            self.clip_failed.emit(media_path, "No valid segments to clip.")
            return None

        # 2. Merge Overlapping/Adjacent Segments
        merged_segments: List[Tuple[int, int]] = []
        if not valid_segments: # Should be caught above, but defensive check
            # This path should ideally not be reached if valid_segments check is robust
            self.clip_failed.emit(media_path, "No segments to process after initial validation.")
            return None

        current_start, current_end = valid_segments[0]
        for i in range(1, len(valid_segments)):
            next_start, next_end = valid_segments[i]
            if next_start <= current_end: # Overlap or adjacent
                current_end = max(current_end, next_end)
            else: # Gap, so finalize current_merged_segment and start a new one
                merged_segments.append((current_start, current_end))
                current_start, current_end = next_start, next_end
        merged_segments.append((current_start, current_end)) # Add the last processed segment
        
        # print(f"[ClippingManager] Original segments: {segments}")
        # print(f"[ClippingManager] Valid sorted segments: {valid_segments}")
        # print(f"[ClippingManager] Merged segments: {merged_segments}")

        if not merged_segments:
            # This case should not be reached if valid_segments had items
            self.clip_failed.emit(media_path, "Segment processing resulted in no segments.")
            return None

        output_path = self._generate_clipped_filename()
        if not output_path:
            print("[ClippingManager] Could not generate an output filename.")
            self.clip_failed.emit(media_path, "Could not generate an output filename for the clip.")
            return None

        temp_files: List[str] = []
        original_path_obj = Path(media_path)
        temp_dir = original_path_obj.parent / "temp_clip_segments"
        os.makedirs(temp_dir, exist_ok=True)
        list_file_path = temp_dir / "mylist.txt"

        try:
            # 3. Create Intermediate Clips for each merged segment
            for i, (start_ms, end_ms) in enumerate(merged_segments):
                segment_duration_ms = end_ms - start_ms
                if segment_duration_ms <= 0: continue # Should not happen after merge logic

                temp_output_filename = f"temp_segment_{i}{original_path_obj.suffix}"
                temp_output_path = str(temp_dir / temp_output_filename)
                temp_files.append(temp_output_path)

                ffmpeg_segment_cmd = [
                    "ffmpeg", "-y", "-hide_banner",
                    "-ss", self._ms_to_ffmpeg_time(start_ms),
                    "-i", media_path,
                    "-t", self._ms_to_ffmpeg_time(segment_duration_ms),
                    "-c", "copy",
                    # "-avoid_negative_ts", "make_zero", # May help with some concat issues
                    # "-fflags", "+genpts", # Generate new PTS if issues occur
                    temp_output_path
                ]
                # print(f"[ClippingManager] Executing segment command: {' '.join(ffmpeg_segment_cmd)}")
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                process = subprocess.Popen(ffmpeg_segment_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creationflags)
                stdout, stderr = process.communicate(timeout=120) # Timeout per segment
                if process.returncode != 0:
                    error_message = f"ffmpeg failed creating segment {i}. Error: {stderr.strip()}"
                    print(f"[ClippingManager] {error_message}")
                    self.clip_failed.emit(media_path, error_message)
                    return None # Early exit on segment creation failure

            # 4. Create list file for concat demuxer
            with open(list_file_path, 'w') as f:
                for temp_file in temp_files:
                    # FFmpeg concat demuxer needs relative paths from the list file, or absolute paths.
                    # Using absolute paths is safer if the list file isn't in the same dir as segments.
                    # However, if temp_dir is cwd for ffmpeg, relative is fine.
                    # For simplicity and robustness with _generate_clipped_filename, use cleaned absolute paths.
                    f.write(f"file '{Path(temp_file).as_posix()}'\n") # Use as_posix for cross-platform path compatibility in file list

            # 5. Concatenate intermediate clips
            ffmpeg_concat_cmd = [
                "ffmpeg", "-y", "-hide_banner",
                "-f", "concat",
                "-safe", "0", # Allow unsafe file paths (though we use absolute here)
                "-i", str(list_file_path),
                "-c", "copy",
                output_path
            ]
            # print(f"[ClippingManager] Executing concat command: {' '.join(ffmpeg_concat_cmd)}")
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.Popen(ffmpeg_concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creationflags)
            stdout, stderr = process.communicate(timeout=120) # Timeout for concat

            if process.returncode == 0:
                print(f"[ClippingManager] Multi-segment clipping successful: {output_path}")
                self.clip_successful.emit(media_path, output_path)
                return output_path
            else:
                error_message = f"ffmpeg failed concatenating segments. Error: {stderr.strip()}"
                print(f"[ClippingManager] {error_message}")
                self.clip_failed.emit(media_path, error_message)
                return None

        except subprocess.TimeoutExpired:
            # process might not be defined if timeout happened before first Popen
            # However, the logic ensures it will be if we reach here from inside try.
            if 'process' in locals() and hasattr(process, 'kill'): process.kill() # type: ignore
            error_message = f"ffmpeg command timed out. Error: {stderr.strip() if 'stderr' in locals() and stderr else 'No stderr'}" # type: ignore
            print(f"[ClippingManager] {error_message}")
            self.clip_failed.emit(media_path, error_message)
            return None
        except FileNotFoundError: # For ffmpeg itself
            error_message = "ffmpeg not found. Please ensure it's installed and in your system's PATH."
            print(f"[ClippingManager] {error_message}")
            self.clip_failed.emit(media_path, error_message)
            return None
        except Exception as e:
            error_message = f"An unexpected error occurred during multi-segment clipping: {str(e)}"
            print(f"[ClippingManager] {error_message}")
            self.clip_failed.emit(media_path, error_message)
            return None
        finally:
            # 6. Clean up temporary files and directory
            # print("[ClippingManager] Cleaning up temporary files...")
            if list_file_path.exists():
                try:
                    os.remove(list_file_path)
                except Exception as e:
                    print(f"[ClippingManager] Error removing list file {list_file_path}: {e}")
            for temp_file_path_str in temp_files:
                temp_file_p = Path(temp_file_path_str)
                if temp_file_p.exists():
                    try:
                        os.remove(temp_file_p)
                    except Exception as e:
                        print(f"[ClippingManager] Error removing temp segment file {temp_file_p}: {e}")
            if temp_dir.exists():
                try:
                    # Only remove if empty, as a safeguard
                    if not any(temp_dir.iterdir()): 
                        os.rmdir(temp_dir)
                    else:
                        print(f"[ClippingManager] Temp directory {temp_dir} not empty, not removing.")
                except Exception as e:
                    print(f"[ClippingManager] Error removing temp directory {temp_dir}: {e}")

    # OLD perform_clip content commented out or removed for brevity
    # ...

    # OLD perform_clip content commented out or removed for brevity
    # ... 