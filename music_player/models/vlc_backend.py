"""
VLC backend implementation for media playback functionality.
"""
import os
import time
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
import vlc


class VLCBackend(QObject):
    """
    Backend class that handles media playback using the VLC library.
    Emits signals for UI components to update based on playback state.
    """
    
    # Signals
    media_loaded = pyqtSignal(dict, bool)  # Emits media metadata AND is_video flag
    position_changed = pyqtSignal(int)  # Position in milliseconds
    duration_changed = pyqtSignal(int)  # Duration in milliseconds
    state_changed = pyqtSignal(str)  # "playing", "paused", "stopped", "error"
    end_reached = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Initialize VLC instance - Enable hardware acceleration for better performance
        vlc_args = [
            "--no-video-title-show",     # Don't show video title
            "--avcodec-hw=any",          # Enable hardware decoding (auto-detect best option)
            "--vout=directdraw",         # Use DirectDraw for Windows (hardware accelerated)
            "--avcodec-fast",            # Use fast decoding algorithms
            "--intf=dummy",              # No interface
            "--no-stats",                # Disable statistics for better performance
            "--network-caching=1000",    # Set network caching (1 second)
            "--file-caching=300",        # Set file caching (300ms)
            "--quiet"                    # Reduce verbose output
        ]
        print(f"[VLCBackend] Initializing VLC instance with hardware acceleration: {vlc_args}")
        
        try:
            self.vlc_instance = vlc.Instance(vlc_args)
            if self.vlc_instance is None:
                print("[VLCBackend] Warning: Hardware acceleration setup failed, trying fallback")
                # Fallback to basic hardware acceleration
                fallback_args = [
                    "--no-video-title-show",
                    "--avcodec-hw=auto",     # Auto-detect hardware decoding
                    "--intf=dummy",
                    "--quiet"
                ]
                self.vlc_instance = vlc.Instance(fallback_args)
                
            if self.vlc_instance is None:
                print("[VLCBackend] Warning: Fallback failed, trying minimal setup")
                # Final fallback to minimal VLC instance
                self.vlc_instance = vlc.Instance()
                
            if self.vlc_instance is None:
                raise RuntimeError("Failed to create VLC instance with any configuration")
                
            self.media_player = self.vlc_instance.media_player_new()
            if self.media_player is None:
                raise RuntimeError("Failed to create VLC media player")
                
            print("[VLCBackend] VLC instance and media player created successfully")
            
        except Exception as e:
            print(f"[VLCBackend] Error initializing VLC: {e}")
            # Try one more time with absolutely minimal setup
            try:
                print("[VLCBackend] Attempting minimal VLC initialization...")
                self.vlc_instance = vlc.Instance()
                self.media_player = self.vlc_instance.media_player_new()
                print("[VLCBackend] Minimal VLC initialization successful")
            except Exception as e2:
                print(f"[VLCBackend] Fatal: Cannot initialize VLC at all: {e2}")
                raise RuntimeError(f"VLC initialization failed: {e2}")
        
        # State tracking
        self.current_media = None
        self.is_playing = False
        self.current_position = 0
        self.current_duration = 0
        self._loading_media = False
        
        # Set up update timer for position tracking
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(500)  # Update every 500ms
        self.update_timer.timeout.connect(self._update_position)
        self.update_timer.start()
        
        # --- Add HWND storage --- 
        self._hwnd = None
        # ----------------------
        
    def load_media(self, media_path):
        """Load a media file, ensuring cleanup of previous state."""
        self._loading_media = True
        try:
            if not os.path.exists(media_path):
                self.error_occurred.emit(f"File not found: {media_path}")
                return False

            # 2. Stop the player
            print("[VLCBackend] Stopping player for media change.")
            self.media_player.stop()

            # --- Robust Reset (Using media_player) --- 
            # 1. Detach HWND first
            # if self._hwnd:
            #     print("[VLCBackend] Detaching HWND before stopping.")
            #     self.media_player.set_hwnd(0)

            # 3. Release previous media object
            if self.current_media:
                print("[VLCBackend] Releasing previous media object.")
                self.current_media.release()
                self.current_media = None
            # ---------------------------------------

            print(f"[VLCBackend] Creating new media for: {media_path}")
            new_media = self.vlc_instance.media_new(media_path)
            if not new_media:
                self.error_occurred.emit(f"Failed to create media object for: {media_path}")
                # Attempt to re-attach HWND even on failure?
                # if self._hwnd:
                #     self.media_player.set_hwnd(self._hwnd)
                return False
            
            self.current_media = new_media

            # 5. Set media directly on media_player
            print("[VLCBackend] Setting media on media_player.")
            self.media_player.set_media(self.current_media)

            # 6. Re-attach HWND immediately
            # if self._hwnd:
            #     print(f"[VLCBackend] Re-attaching HWND: {self._hwnd}")
            #     self.media_player.set_hwnd(self._hwnd)

            # 7. Register for parsing
            event_manager = self.current_media.event_manager()
            event_manager.event_attach(vlc.EventType.MediaParsedChanged, self._on_media_parsed)

            # 8. Parse media
            print("[VLCBackend] Starting media parse.")
            self.current_media.parse_with_options(vlc.MediaParseFlag.local, -1)

            return True
        finally:
            self._loading_media = False
        
    def _on_media_parsed(self, event):
        """
        Callback triggered when media parsing is complete
        
        Args:
            event: VLC event object
        """
        # DEBUG: Log entry and current parsed status
        if self.current_media:
            current_parsed_status_for_log = self.current_media.get_parsed_status()
            print(f"[VLCBackend DEBUG] _on_media_parsed entered. Current media parsed status: {current_parsed_status_for_log}, Event: {event}")
        else:
            print("[VLCBackend DEBUG] _on_media_parsed entered but self.current_media is None.")
            return

        if not self.current_media:
            return
            
        # Check parsing status
        status = self.current_media.get_parsed_status()
        
        if status == vlc.MediaParsedStatus.done:
            print("[VLCBackend] Media parsing completed successfully")
        elif status == vlc.MediaParsedStatus.failed:
            print("[VLCBackend] Media parsing failed, attempting to use available metadata")
        elif status == vlc.MediaParsedStatus.timeout:
            print("[VLCBackend] Media parsing timed out, using partial metadata")
        else:
            # If parsing is not done, failed, or timed out, we don't have enough info to proceed.
            print(f"[VLCBackend] Media parsing status: {status}. Not emitting media_loaded.")
            return

        # --- Streamlined Logic Start --- 
        # Determine if it's video *before* getting other metadata
        is_video = False
        try:
            # Ensure media_player is available
            if self.media_player:
                track_count = self.media_player.video_get_track_count()
                # Check if track_count is a valid number (not None) and greater than 0
                if track_count is not None and track_count > 0:
                    is_video = True
                print(f"[VLCBackend] Media type detection: video_get_track_count() = {track_count}. Is Video: {is_video}")
                
                # --- Check for subtitle tracks if it's a video ---
                if is_video:
                    spu_count = self.media_player.video_get_spu_count()
                    print(f"[VLCBackend] Subtitle tracks detected: {spu_count}")
                    if spu_count > 0:
                        # Auto-enable the first subtitle track (index 1, as 0 is often "Disable")
                        # We'll let MainPlayer handle when to actually call enable_subtitles
                        print("[VLCBackend] Subtitles available for auto-enabling")
            else:
                print("[VLCBackend] Warning: Backend media player not available for media type detection.")
        except Exception as e:
            print(f"[VLCBackend] Error during video track count detection: {e}. Assuming audio.")
            # is_video remains False
            
        # Get metadata
        mrl = self.current_media.get_mrl() or ""
        # Safely get basename, handle potential errors or empty MRL
        try:
            basename = os.path.basename(mrl) if mrl else "Unknown Track"
        except Exception:
            basename = "Unknown Track"
            
        metadata = {
            'title': self.current_media.get_meta(vlc.Meta.Title) or basename,
            'artist': self.current_media.get_meta(vlc.Meta.Artist) or "Unknown Artist",
            'album': self.current_media.get_meta(vlc.Meta.Album) or "Unknown Album",
            'duration': self.media_player.get_length() if self.media_player else 0 # Safely get length
        }
        
        # Extract album art (can be useful even for videos as a thumbnail)
        try:
            if mrl.startswith('file:///'):
                from urllib.parse import unquote
                file_path = unquote(mrl[8:])
                # Adjust for Windows paths starting with '/' after unquoting
                if os.name == 'nt' and file_path.startswith('/') and len(file_path) > 2 and file_path[2] == ':':
                    file_path = file_path[1:]
                
                artwork_extracted = self._extract_album_art(file_path)
                if artwork_extracted:
                    metadata['artwork_path'] = artwork_extracted
        except Exception as e:
            print(f"[VLCBackend] Error processing MRL for album art extraction: {e}")
        
        # Update duration internally and emit signal
        new_duration = metadata.get('duration', 0)
        if new_duration != self.current_duration:
            self.current_duration = new_duration
            print(f"[VLCBackend] Duration changed. Emitting duration_changed with: {self.current_duration} ms") # DEBUG
            self.duration_changed.emit(self.current_duration)
        
        # Emit media loaded signal with metadata and is_video flag
        print(f"[VLCBackend] Emitting media_loaded signal. is_video: {is_video}")
        self.media_loaded.emit(metadata, is_video)
        
        # Report hardware acceleration status if video
        if is_video:
            self._report_hardware_acceleration_status()
        # --- Streamlined Logic End --- 
        
    def _extract_album_art(self, file_path):
        """
        Extract album art from the media file and save to a temporary file.
        
        Args:
            file_path (str): Path to the media file
            
        Returns:
            str: Path to the extracted album art file, or None if extraction failed
        """
        try:
            # Create a temporary directory if it doesn't exist
            temp_dir = os.path.join(os.path.expanduser("~"), ".music_player_temp")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Create a unique file name based on the input file
            import hashlib
            file_hash = hashlib.md5(file_path.encode()).hexdigest()
            artwork_path = os.path.join(temp_dir, f"cover_{file_hash}.jpg")
            
            # Skip extraction if we already have this artwork
            if os.path.exists(artwork_path):
                return artwork_path
                
            # Try to get the artwork from the current_media object first
            # Since we've already parsed this media, it should have metadata
            artwork_data = self.current_media.get_meta(vlc.Meta.ArtworkURL)
            if artwork_data and artwork_data.startswith('file://'):
                # Convert file URL to path
                from urllib.parse import unquote
                art_path = unquote(artwork_data[7:])
                
                # For Windows paths
                if os.name == 'nt' and art_path.startswith('/'):
                    art_path = art_path[1:]
                    
                # Copy the artwork to our temporary location
                import shutil
                if os.path.exists(art_path):
                    shutil.copyfile(art_path, artwork_path)
                    return artwork_path
            
            # Alternative: Try to extract album art using mutagen
            try:
                import mutagen
                from mutagen.id3 import ID3, APIC
                from mutagen.mp3 import MP3
                from mutagen.flac import FLAC
                
                # Identify file format and extract artwork accordingly
                if file_path.lower().endswith('.mp3'):
                    audio = MP3(file_path)
                    if audio.tags:
                        for tag in audio.tags.values():
                            if isinstance(tag, APIC) and tag.data:
                                with open(artwork_path, 'wb') as img:
                                    img.write(tag.data)
                                return artwork_path
                                
                elif file_path.lower().endswith('.flac'):
                    audio = FLAC(file_path)
                    if audio.pictures:
                        with open(artwork_path, 'wb') as img:
                            img.write(audio.pictures[0].data)
                        return artwork_path
                        
            except ImportError:
                print("Mutagen library not available for alternative artwork extraction")
            except Exception as e:
                print(f"Error in mutagen extraction: {e}")
                
            return None
        except Exception as e:
            print(f"Error in _extract_album_art: {e}")
            return None
        
    def _update_position(self):
        """Update the current position and emit related signals"""
        if self._loading_media:
            return
        
        if not self.current_media:
            return
        
        # Check player state first to catch Ended state
        state = self.media_player.get_state()
        
        # Handle ended state
        if state == vlc.State.Ended:
            # Only emit end_reached if we haven't already marked playback as ended
            self.end_reached.emit()
            self.is_playing = False
            return
        elif state == vlc.State.Stopped:
            # Treat stopped state as end of playback, get ready for repeat
            self.end_reached.emit()
            self.is_playing = False
            return
        elif state == vlc.State.Error:
            self.state_changed.emit("error")
            self.error_occurred.emit("Playback error occurred")
            self.is_playing = False
            return
            
        # If not playing, don't continue with position updates
        if not self.media_player.is_playing():
            return
            
        # Get current position
        position = self.media_player.get_time()
        if position != -1 and position != self.current_position:
            self.current_position = position
            self.position_changed.emit(position)
            
        # Check for end of media by position (backup method)
        if self.current_duration > 0 and position >= self.current_duration:
            self.end_reached.emit()
            self.is_playing = False
        
    def play(self):
        """Start or resume playback"""
        if not self.current_media:
            return False

        play_result = self.media_player.play()
        if play_result == -1:
             print("[VLCBackend] Error starting playback.")
             self.is_playing = False
             self.state_changed.emit("error")
             return False
        new_state = self.media_player.get_state()
        
        self.is_playing = True
        self.state_changed.emit("playing")
        return True
        
    def pause(self):
        """Pause playback"""
        if not self.current_media or not self.media_player.is_playing():
            return False
            
        self.media_player.set_pause(1)
        self.is_playing = False
        self.state_changed.emit("paused")
        return True
        
    def stop(self):
        """Stop playback"""
        print("[VLCBackend] Stop command received via stop method.")
        stop_result = self.media_player.stop()
        print(f"[VLCBackend] media_player.stop() returned: {stop_result}")

        self.is_playing = False
        self.state_changed.emit("stopped")
        return True
        
    def seek(self, position_ms):
        """
        Seek to a specific position in the current media with verification for maximum accuracy.
        Uses retry logic to ensure the seek actually reaches the target position.
        
        Args:
            position_ms (int): Position in milliseconds
        """
        if not self.current_media:
            print("[VLCBackend] No media loaded, cannot seek")
            return False
            
        try:
            # Get current state
            current_state = self.media_player.get_state()
            print(f"[VLCBackend] Verification-based seeking to {position_ms}ms, current state: {current_state}")
            
            # Store the original playing state
            was_playing = (current_state == vlc.State.Playing)
            
            # Handle problematic states first
            if current_state == vlc.State.Ended:
                print("[VLCBackend] Ended state detected, resetting for seek")
                self.media_player.stop()
                self.media_player.play()
                self.media_player.pause()
                import time
                time.sleep(0.05)  # Reduced from 0.1s - 50ms for state stabilization
                current_state = vlc.State.Paused
                was_playing = False
            elif current_state == vlc.State.Error:
                print("[VLCBackend] Error state detected, attempting recovery")
                self.media_player.stop()
                self.media_player.play()
                self.media_player.pause()
                import time
                time.sleep(0.05)  # Reduced from 0.1s - 50ms for error recovery
                current_state = vlc.State.Paused
                was_playing = False
            
            # Ensure position is within valid range
            if self.current_duration > 0:
                position_ms = max(0, min(position_ms, self.current_duration))
            
            # Verification-based seeking with retry logic
            max_attempts = 3
            tolerance_ms = 50  # Accept within 50ms of target
            successful_seek = False
            
            for attempt in range(max_attempts):
                print(f"[VLCBackend] Seek attempt {attempt + 1}/{max_attempts}")
                
                # For paused state, briefly start playback to ensure frame decode/display
                if current_state == vlc.State.Paused:
                    self.media_player.play()
                    import time
                    time.sleep(0.005)  # Reduced from 0.01s - 5ms for playback start
                
                # Perform the seek operation
                seek_result = self.media_player.set_time(position_ms)
                if seek_result == -1:
                    # Try fallback to position-based seeking
                    if self.current_duration > 0:
                        relative_position = position_ms / self.current_duration
                        relative_position = max(0.0, min(1.0, relative_position))
                        seek_result = self.media_player.set_position(relative_position)
                        print(f"[VLCBackend] Using position-based seek: {relative_position:.3f}")
                
                if seek_result == -1:
                    print(f"[VLCBackend] Seek command failed on attempt {attempt + 1}")
                    continue
                
                # Wait for seek to be processed and frame to be decoded
                import time
                time.sleep(0.06)  # Increased from 0.04s to 0.06s - 60ms for seek processing and frame decode
                
                # Verify the actual position
                actual_position = self.media_player.get_time()
                if actual_position != -1:
                    position_error = abs(actual_position - position_ms)
                    print(f"[VLCBackend] Target: {position_ms}ms, Actual: {actual_position}ms, Error: {position_error}ms")
                    
                    if position_error <= tolerance_ms:
                        print(f"[VLCBackend] Seek accurate within tolerance ({position_error}ms <= {tolerance_ms}ms)")
                        successful_seek = True
                        # Update our position tracking with the actual position
                        self.current_position = actual_position
                        break
                    else:
                        print(f"[VLCBackend] Seek not accurate enough (error: {position_error}ms), retrying...")
                else:
                    print(f"[VLCBackend] Could not verify position, retrying...")
                
                # Brief pause before retry
                time.sleep(0.01)  # Reduced from 0.02s - 10ms between retries
            
            # Restore the original playing state
            if not was_playing and current_state != vlc.State.Ended:
                self.media_player.pause()
                # Wait for pause to take effect
                import time
                time.sleep(0.02)  # Reduced from 0.05s - 20ms for pause effect
                print("[VLCBackend] Restored paused state after verification-based seek")
            
            if successful_seek:
                print(f"[VLCBackend] Verification-based seek completed successfully")
                return True
            else:
                print(f"[VLCBackend] Failed to achieve accurate seek after {max_attempts} attempts")
                # Update position tracking even if not perfectly accurate
                final_position = self.media_player.get_time()
                if final_position != -1:
                    self.current_position = final_position
                    print(f"[VLCBackend] Using final position: {final_position}ms")
                else:
                    self.current_position = position_ms  # Fallback to requested position
                    print(f"[VLCBackend] Using requested position as fallback: {position_ms}ms")
                return False
            
        except Exception as e:
            print(f"[VLCBackend] Error during verification-based seek operation: {e}")
            return False
        
    def set_volume(self, volume):
        """
        Set the playback volume.
        
        Args:
            volume (int): Volume level (0-100)
        """
        self.media_player.audio_set_volume(volume)
        
    def get_volume(self):
        """Get the current volume level (0-100)"""
        return self.media_player.audio_get_volume()
        
    def is_media_loaded(self):
        """Check if media is currently loaded"""
        return self.current_media is not None
        
    def get_current_position(self):
        """Get the current playback position in milliseconds"""
        return self.current_position
        
    def get_duration(self):
        """Get the duration of the current media in milliseconds"""
        return self.current_duration
        
    def set_rate(self, rate):
        """
        Set the playback rate without affecting pitch.
        
        Args:
            rate (float): Playback rate (e.g., 1.0 for normal, 1.5 for 50% faster)
            
        Returns:
            bool: True if successful
        """
        if not self.media_player:
            return False
            
        # VLC native rate control automatically maintains normal pitch
        self.media_player.set_rate(rate)
        return True
        
    def get_rate(self):
        """
        Get the current playback rate.
        
        Returns:
            float: Current playback rate (1.0 is normal speed)
        """
        if not self.media_player:
            return 1.0
            
        return self.media_player.get_rate()
        
    def cleanup(self):
        """Clean up resources"""
        self.update_timer.stop()
        print("[VLCBackend Cleanup] Stopping media player.")
        self.stop()

        # Release resources
        print("[VLCBackend Cleanup] Releasing media player.")
        self.media_player.release()
        print("[VLCBackend Cleanup] Releasing VLC instance.")
        self.vlc_instance.release()
        print("[VLCBackend Cleanup] Cleanup finished.")
        
    def __del__(self):
        """Destructor to ensure cleanup"""
        self.cleanup()
        
    def get_current_media_path(self):
        """
        Get the path of the currently loaded media file.
        
        Returns:
            str: Normalized absolute path to the current media file, or None if no media is loaded
        """
        if not self.current_media:
            return None
            
        try:
            mrl = self.current_media.get_mrl()
            if mrl.startswith('file:///'):
                # Remove 'file:///' prefix and handle URL encoding
                from urllib.parse import unquote
                file_path = unquote(mrl[8:])
                
                # For Windows paths that start with a drive letter
                if os.name == 'nt' and file_path.startswith('/'):
                    file_path = file_path[1:]
                
                # Normalize the path to ensure consistency with position manager
                try:
                    normalized_path = os.path.abspath(file_path)
                    
                    # Handle network drive mappings for consistency
                    if os.name == 'nt':
                        normalized_path = self._resolve_network_path(normalized_path)
                    
                    return normalized_path
                except Exception as norm_error:
                    print(f"[VLCBackend] Warning: Failed to normalize path {file_path}: {norm_error}")
                    return file_path  # Return original if normalization fails
                    
        except Exception as e:
            print(f"[VLCBackend] Error getting media path: {e}")
            
        return None

    def _resolve_network_path(self, path: str) -> str:
        """
        Resolve mapped network drives to their UNC paths for consistent database storage.
        
        Args:
            path (str): File path that might use a mapped drive
            
        Returns:
            str: UNC path if it's a mapped network drive, otherwise the original path
        """
        if not path or len(path) < 3:
            return path
            
        # Check if it's a drive letter path (e.g., Z:\...)
        if path[1:3] == ':\\':
            drive_letter = path[0].upper()
            
            try:
                import subprocess
                # Use Windows NET USE command to get UNC path for the drive
                result = subprocess.run(
                    ['net', 'use', f'{drive_letter}:'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    # Parse the output to find the remote path
                    output_lines = result.stdout.strip().split('\n')
                    for line in output_lines:
                        if 'Remote name' in line or 'remote name' in line:
                            # Extract UNC path from "Remote name \\server\share"
                            parts = line.split()
                            if len(parts) >= 3 and parts[-1].startswith('\\\\'):
                                unc_root = parts[-1]
                                # Replace drive portion with UNC root
                                relative_path = path[3:]  # Remove "Z:\"
                                unc_path = os.path.join(unc_root, relative_path).replace('\\', '/')
                                unc_path = unc_path.replace('/', '\\')  # Ensure Windows separators
                                print(f"[VLCBackend] Resolved mapped drive: {path} -> {unc_path}")
                                return unc_path
                        
                        # Alternative parsing for different NET USE output formats
                        if '\\\\' in line and drive_letter in line:
                            # Find UNC path in the line
                            unc_start = line.find('\\\\')
                            if unc_start >= 0:
                                # Extract everything from \\ onwards, but stop at whitespace
                                unc_part = line[unc_start:].split()[0]
                                if unc_part.count('\\') >= 3:  # Valid UNC path \\server\share
                                    relative_path = path[3:]  # Remove "Z:\"
                                    unc_path = os.path.join(unc_part, relative_path).replace('\\', '/')
                                    unc_path = unc_path.replace('/', '\\')  # Ensure Windows separators
                                    print(f"[VLCBackend] Resolved mapped drive: {path} -> {unc_path}")
                                    return unc_path
                                    
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError) as e:
                print(f"[VLCBackend] Could not resolve network drive {drive_letter}: {e}")
            except Exception as e:
                print(f"[VLCBackend] Unexpected error resolving network drive {drive_letter}: {e}")
        
        # Return original path if not a mapped drive or resolution failed
        return path

    # --- Add method to set video output --- 
    def set_video_output(self, hwnd):
        """Set the window handle for video output."""
        self._hwnd = hwnd
        if self._hwnd:
            self.media_player.set_hwnd(self._hwnd)
            print(f"[VLCBackend] HWND set to: {self._hwnd}")
            # --- Disable VLC mouse input handling --- 
            try:
                self.media_player.video_set_mouse_input(False)
                print("[VLCBackend] Disabled VLC mouse input handling for HWND.")
                # --- Also disable VLC key input handling ---
                self.media_player.video_set_key_input(False)
                print("[VLCBackend] Disabled VLC key input handling for HWND.")
                # -----------------------------------------
            except Exception as e:
                print(f"[VLCBackend] Warning: Failed to set mouse/key input to False - {e}")
            # --------------------------------------
        else:
            # If hwnd is None, detach output (might not be strictly needed but good practice)
            self.media_player.set_hwnd(0)
            print("[VLCBackend] HWND detached.")
            # Optional: Re-enable mouse input if detaching?
            # try:
            #     self.media_player.video_set_mouse_input(True) 
            # except Exception as e:
            #     print(f"[VLCBackend] Warning: Failed to set mouse input to True on detach - {e}")
    # ------------------------------------- 

    # --- Add methods for subtitle handling ---
    def has_subtitle_tracks(self):
        """Check if the current media has any subtitle tracks."""
        if not self.media_player:
            return False
        try:
            track_count = self.media_player.video_get_spu_count()
            return track_count > 0
        except Exception as e:
            print(f"[VLCBackend] Error checking subtitle tracks: {e}")
            return False
    
    def enable_subtitles(self, track_id=0):
        """
        Enable subtitles at the specified track ID.
        If track_id is 0, it selects the default subtitle track.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.media_player:
            return False
        
        try:
            # Check if we have any subtitle tracks
            track_count = self.media_player.video_get_spu_count()
            if track_count <= 0:
                print("[VLCBackend] No subtitle tracks available")
                return False
                
            # Get current track (to avoid setting the same track again)
            current_track = self.media_player.video_get_spu()
            
            # If track_id is already active, no need to change
            if current_track == track_id:
                print(f"[VLCBackend] Subtitle track {track_id} already active")
                return True
                
            # Set the specified subtitle track
            result = self.media_player.video_set_spu(track_id)
            if result == 0:  # VLC returns 0 on success
                print(f"[VLCBackend] Enabled subtitle track {track_id}")
                return True
            else:
                print(f"[VLCBackend] Failed to enable subtitle track {track_id}")
                return False
                
        except Exception as e:
            print(f"[VLCBackend] Error enabling subtitles: {e}")
            return False
    
    def disable_subtitles(self):
        """
        Disable subtitles.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.media_player:
            return False
            
        try:
            # -1 disables subtitles in VLC
            result = self.media_player.video_set_spu(-1)
            if result == 0:  # VLC returns 0 on success
                print("[VLCBackend] Disabled subtitles")
                return True
            else:
                print("[VLCBackend] Failed to disable subtitles")
                return False
        except Exception as e:
            print(f"[VLCBackend] Error disabling subtitles: {e}")
            return False
    
    def get_subtitle_tracks(self):
        """
        Get a list of available subtitle tracks.
        
        Returns:
            list: List of dicts with id and name of each subtitle track
        """
        tracks = []
        if not self.media_player:
            return tracks
            
        try:
            # Get subtitle description (returns a list of dicts)
            spu_description = self.media_player.video_get_spu_description()
            if spu_description:
                for track in spu_description:
                    track_id = track[0]  # Track ID
                    track_name = track[1]  # Track name/description (might be bytes)
                    
                    # Try to decode track name if it's bytes
                    name_for_display = track_name
                    if isinstance(track_name, bytes):
                        try:
                            name_for_display = track_name.decode('utf-8')
                        except UnicodeDecodeError:
                            try:
                                name_for_display = track_name.decode('latin-1')
                            except Exception:
                                # Keep the bytes object if decoding fails
                                name_for_display = f"Track {track_id}"
                                print(f"[VLCBackend] Warning: Could not decode subtitle track name: {track_name}")
                    
                    # Try to get additional metadata if available
                    track_info = {
                        'id': track_id,
                        'name': track_name,  # Keep the original for compatibility
                        'display_name': name_for_display  # Add decoded version for display
                    }
                    
                    # If the player or media has a way to get language code directly, add it
                    # (This will depend on the VLC Python bindings version and capabilities)
                    try:
                        # Some versions of VLC might expose this information
                        if hasattr(self.media_player, 'video_get_spu_language') and callable(self.media_player.video_get_spu_language):
                            language = self.media_player.video_get_spu_language(track_id)
                            if language:
                                track_info['language'] = language
                    except Exception as e:
                        print(f"[VLCBackend] Could not get subtitle language directly: {e}")
                    
                    # Add the track info to our list
                    tracks.append(track_info)
            return tracks
        except Exception as e:
            print(f"[VLCBackend] Error getting subtitle tracks: {e}")
            return tracks
    # -----------------------------------

    def _report_hardware_acceleration_status(self):
        """
        Report hardware acceleration status for video playback.
        """
        try:
            # Try to get information about the current video codec and hardware acceleration
            if self.media_player and self.current_media:
                # Get video track information
                video_track_count = self.media_player.video_get_track_count()
                if video_track_count > 0:
                    print(f"[VLCBackend] Hardware Acceleration Status:")
                    print(f"[VLCBackend] - Video tracks detected: {video_track_count}")
                    
                    # Try to get current video track description
                    try:
                        video_tracks = self.media_player.video_get_track_description()
                        if video_tracks:
                            for track in video_tracks:
                                track_id = track[0]
                                track_name = track[1]
                                if isinstance(track_name, bytes):
                                    try:
                                        track_name = track_name.decode('utf-8', errors='ignore')
                                    except:
                                        track_name = str(track_name)
                                print(f"[VLCBackend] - Video track {track_id}: {track_name}")
                    except Exception as e:
                        print(f"[VLCBackend] - Could not get video track details: {e}")
                    
                    # Report that hardware acceleration is attempted
                    print(f"[VLCBackend] - Hardware acceleration: ENABLED (auto-detect)")
                    print(f"[VLCBackend] - Video output method: DirectDraw (hardware accelerated)")
                    
                else:
                    print(f"[VLCBackend] No video tracks found for hardware acceleration report")
        except Exception as e:
            print(f"[VLCBackend] Error reporting hardware acceleration status: {e}")