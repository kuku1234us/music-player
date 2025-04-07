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
    media_loaded = pyqtSignal(dict)  # Emits media metadata
    position_changed = pyqtSignal(int)  # Position in milliseconds
    duration_changed = pyqtSignal(int)  # Duration in milliseconds
    state_changed = pyqtSignal(str)  # "playing", "paused", "stopped", "error"
    end_reached = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Initialize VLC instance
        self.instance = vlc.Instance('--no-video')
        self.media_player = self.instance.media_player_new()
        self.media_list = self.instance.media_list_new()
        self.list_player = self.instance.media_list_player_new()
        
        # Connect list player to media player
        self.list_player.set_media_player(self.media_player)
        self.list_player.set_media_list(self.media_list)
        
        # State tracking
        self.current_media = None
        self.is_playing = False
        self.current_position = 0
        self.current_duration = 0
        
        # Set up update timer for position tracking
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(500)  # Update every 500ms
        self.update_timer.timeout.connect(self._update_position)
        
        # Event handling
        self._setup_events()
        
    def _setup_events(self):
        """Set up VLC event handling"""
        # We use polling with QTimer instead of VLC events for better compatibility
        
        # Start the update timer
        self.update_timer.start()
        
    def load_media(self, media_path):
        """
        Load a media file from the specified path.
        
        Args:
            media_path (str): Path to the media file
        """
        if not os.path.exists(media_path):
            self.error_occurred.emit(f"File not found: {media_path}")
            return False
            
        # Create a new media object
        self.current_media = self.instance.media_new(media_path)
        
        # Create a new media list instead of trying to clear the existing one
        self.list_player.stop()
        self.media_list = self.instance.media_list_new()
        self.media_list.add_media(self.current_media)
        self.list_player.set_media_list(self.media_list)
        
        # Parse the media to extract metadata
        self.current_media.parse()
        
        # Wait a bit for parsing (non-blocking)
        QTimer.singleShot(500, self._emit_media_loaded)
        
        # Play the media
        self.list_player.play_item(self.current_media)
        self.pause()  # Start in paused state
        
        return True
        
    def _emit_media_loaded(self):
        """Emit media loaded signal with metadata after parsing"""
        if not self.current_media:
            return
            
        # Get metadata
        metadata = {
            'title': self.current_media.get_meta(vlc.Meta.Title) or os.path.basename(self.current_media.get_mrl()),
            'artist': self.current_media.get_meta(vlc.Meta.Artist) or "Unknown Artist",
            'album': self.current_media.get_meta(vlc.Meta.Album) or "Unknown Album",
            'duration': self.media_player.get_length()
        }
        
        # Extract album art from media file
        try:
            # Get the file path from the MRL (Media Resource Locator)
            mrl = self.current_media.get_mrl()
            if mrl.startswith('file:///'):
                # Remove 'file:///' prefix and handle URL encoding
                from urllib.parse import unquote
                file_path = unquote(mrl[8:])
                
                # For Windows paths that start with a drive letter
                if os.name == 'nt' and file_path.startswith('/'):
                    file_path = file_path[1:]
                
                # Extract album art to a temporary file
                artwork_extracted = self._extract_album_art(file_path)
                if artwork_extracted:
                    metadata['artwork_path'] = artwork_extracted
        except Exception as e:
            print(f"Error extracting album art: {e}")
        
        # Update duration
        self.current_duration = metadata['duration']
        self.duration_changed.emit(self.current_duration)
        
        # Emit media loaded signal
        self.media_loaded.emit(metadata)
    
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
                
            # Use VLC's internal methods to extract artwork
            # Create a new media object specifically for parsing
            media = self.instance.media_new(file_path)
            media.parse()
            
            # Wait for parsing to complete (non-blocking but with timeout)
            # This is important to ensure metadata is available
            parse_timeout = 3  # seconds
            start_time = time.time()
            while time.time() - start_time < parse_timeout:
                # In some VLC versions, get_parsed_status() might not exist or work differently
                # So just wait a bit for parsing to complete
                time.sleep(0.2)
                
                # Try to get artwork data
                artwork_data = media.get_meta(vlc.Meta.ArtworkURL)
                if artwork_data and artwork_data.startswith('file://'):
                    break
            
            # Try to get the artwork
            artwork_data = media.get_meta(vlc.Meta.ArtworkURL)
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
        if not self.current_media:
            return
        
        # Check player state first to catch Ended state
        state = self.media_player.get_state()
        
        # Handle ended state
        if state == vlc.State.Ended:
            # Only emit end_reached if we haven't already marked playback as stopped
            if self.is_playing:
                self.end_reached.emit()
                self.state_changed.emit("stopped")
                self.is_playing = False
            return
        elif state == vlc.State.Stopped:
            self.state_changed.emit("stopped")
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
            
        self.list_player.play()
        self.is_playing = True
        self.state_changed.emit("playing")
        return True
        
    def pause(self):
        """Pause playback"""
        if not self.current_media:
            return False
            
        self.list_player.pause()
        self.is_playing = False
        self.state_changed.emit("paused")
        return True
        
    def stop(self):
        """Stop playback"""
        if not self.current_media:
            return False
            
        self.list_player.stop()
        self.is_playing = False
        self.state_changed.emit("stopped")
        return True
        
    def seek(self, position_ms):
        """
        Seek to a specific position in the current media.
        
        Args:
            position_ms (int): Position in milliseconds
        """
        if not self.current_media:
            return False
            
        # Check if we're in an ended state
        current_state = self.media_player.get_state()
        if current_state == vlc.State.Ended:
            # When seeking after end of media, we need to reset
            # the player state to ensure seeking works correctly
            self.list_player.stop()
            self.list_player.play()
            self.list_player.pause()
        
        # Now perform the seek
        self.media_player.set_time(position_ms)
        self.current_position = position_ms
        return True
        
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
        self.stop()
        
        # Release resources
        self.media_player.release()
        self.list_player.release()
        self.media_list.release()
        self.instance.release()
        
    def __del__(self):
        """Destructor to ensure cleanup"""
        self.cleanup() 