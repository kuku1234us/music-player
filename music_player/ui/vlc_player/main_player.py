"""
Main player module that integrates the UI components with the VLC backend.
"""
import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QFileDialog
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
import vlc

from .player_widget import PlayerWidget
from .hotkey_handler import HotkeyHandler
from music_player.models.vlc_backend import VLCBackend
from qt_base_app.models.settings_manager import SettingsManager, SettingType

from .enums import STATE_PLAYING, STATE_PAUSED, STATE_STOPPED, STATE_ENDED, STATE_ERROR


class MainPlayer(QWidget):
    """
    Main player widget that combines the UI components with the VLC backend.
    This serves as the main interface between the UI and the media playback.
    """
    
    # Signals
    track_changed = pyqtSignal(dict)  # Emits track metadata
    playback_state_changed = pyqtSignal(str)  # "playing", "paused", "stopped", "error"
    media_changed = pyqtSignal(str, str, str, str)  # title, artist, album, artwork_path
    
    def __init__(self, parent=None, persistent_mode=False):
        super().__init__(parent)
        self.setObjectName("mainPlayer")
        
        # Enable background styling for the widget (needed for border visibility)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        # Store persistent mode flag
        self.persistent_mode = persistent_mode
        
        # Get settings manager instance
        self.settings = SettingsManager.instance()
        
        # Internal state tracking
        self.app_state = STATE_STOPPED
        self.current_request_position = None
        self.current_media = None
        self.block_position_updates = False  # Flag to temporarily block position updates
        self.last_metadata = None  # Store the last received metadata
        
        # UI Components
        self.player_widget = PlayerWidget(self, persistent=persistent_mode)
        
        # Backend
        self.backend = VLCBackend(self)
        
        # Hotkey handler
        self.hotkey_handler = HotkeyHandler(self)
        
        # Setup
        self._setup_ui()
        self._connect_signals()
        
        # Initialize volume
        self._apply_saved_volume()
        
        # Enable focus and keyboard tracking
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
    def _setup_ui(self):
        """Set up the main player UI layout using horizontal layout for persistent player"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)  # Reduced margins for compact display
        layout.addWidget(self.player_widget)
        self.setLayout(layout)
        
        # Apply styling
        self.setStyleSheet("""
            QWidget#mainPlayer {
                background-color: #1e1e1e;
                border-radius: 0px;
            }
        """)
        
    def _connect_signals(self):
        """Connect signals between UI and backend"""
        # Connect UI to backend
        self.player_widget.play_requested.connect(self._on_play_requested)
        self.player_widget.pause_requested.connect(self._on_pause_requested)
        self.player_widget.position_changed.connect(self._on_position_changed)
        self.player_widget.volume_changed.connect(self._on_volume_changed)
        self.player_widget.rate_changed.connect(self._on_rate_changed)
        self.player_widget.repeat_state_changed.connect(self._on_repeat_state_changed)
        
        # Connect backend to UI
        self.backend.media_loaded.connect(self.on_media_changed)
        self.backend.position_changed.connect(self._on_backend_position_changed)
        self.backend.duration_changed.connect(self.player_widget.set_duration)
        self.backend.state_changed.connect(self._on_backend_state_changed)
        self.backend.end_reached.connect(self._on_end_reached)
        self.backend.error_occurred.connect(self._show_error)

    def keyPressEvent(self, event):
        """
        Handle key press events for hotkeys.
        
        Args:
            event (QKeyEvent): The key event
        """
        # Let the hotkey handler process the event first
        if self.hotkey_handler.handle_key_press(event):
            # Event was handled by hotkey handler
            return
            
        # If not handled, pass to parent for default handling
        super().keyPressEvent(event)
        
    def showEvent(self, event):
        """
        Handle show events to ensure the player gets focus.
        
        Args:
            event: The show event
        """
        super().showEvent(event)
        # Set focus to this widget when shown
        self.setFocus()
        
    def _on_media_loaded(self, metadata):
        """
        Handle media loaded event from the backend.
        
        Args:
            metadata (dict): Media metadata
        """
        # Update UI with track info and artwork
        self.player_widget.update_track_info(
            metadata.get('title', 'Unknown Track'),
            metadata.get('artist', 'Unknown Artist'),
            metadata.get('album', 'Unknown Album'),
            metadata.get('artwork_path')  # Pass artwork path if available
        )
        
        # Set duration
        duration = metadata.get('duration', 0)
        self.player_widget.set_duration(duration)
        
        # Emit track changed signal
        self.track_changed.emit(metadata)
        
    def _on_backend_state_changed(self, state):
        """
        Handle state change events from the backend.
        Maps backend states to app states.
        
        Args:
            state (str): State from backend
        """
        # Map backend state to app state
        if state == "playing":
            self._set_app_state(STATE_PLAYING)
        elif state == "paused":
            self._set_app_state(STATE_PAUSED)
        elif state == "stopped":
            self._set_app_state(STATE_STOPPED)
        elif state == "error":
            self._set_app_state(STATE_ERROR)
        
    def _show_error(self, error_message):
        """
        Show an error message dialog.
        
        Args:
            error_message (str): Error message to display
        """
        QMessageBox.critical(self, "Playback Error", error_message)
        
    def _on_play_requested(self):
        """Handle play requested from UI"""
        # Check if we have a pending position request
        if self.current_request_position is not None:
            # Store the position
            position = self.current_request_position
            self.current_request_position = None
            
            # Block position updates during operations to prevent UI jitter
            self.block_position_updates = True
            
            try:
                # Was the player in ended state?
                if self.app_state == STATE_ENDED or not self.backend.is_playing:
                    # Need to reset and restart playback
                    self.backend.stop()
                    self.backend.play()
                    self.backend.seek(position)
                else:
                    # Just seek and continue
                    self.backend.seek(position)
                
                # Update UI position directly
                self.player_widget.set_position(position)
            finally:
                # Always unblock position updates when done
                self.block_position_updates = False
        else:
            # Normal play
            self.backend.play()
        
        # Set focus to this player to ensure hotkeys work
        self.setFocus()
            
        # Update app state
        self._set_app_state(STATE_PLAYING)
        
    def _on_pause_requested(self):
        """Handle pause requested from UI"""
        self.backend.pause()
        
        # Set focus to this player to ensure hotkeys work
        self.setFocus()
        
        self._set_app_state(STATE_PAUSED)
        
    def _set_app_state(self, state):
        """
        Set the application playback state and update UI accordingly.
        
        Args:
            state (str): New state - one of the STATE_* constants
        """
        self.app_state = state
        
        # Update UI
        if state == STATE_PLAYING:
            self.player_widget.set_playing_state(True)
        else:
            self.player_widget.set_playing_state(False)
            
        # Emit state changed signal
        self.playback_state_changed.emit(state)
        
    def _on_end_reached(self):
        """
        Handle end of media playback.
        Ensures the UI correctly reflects that playback has ended.
        """
        # Set app state to ended
        self._set_app_state(STATE_ENDED)
        
    def _on_position_changed(self, position_ms):
        """
        Handle position change from timeline.
        Only sends position changes to backend when in playing state,
        otherwise just updates UI and stores position for later.
        
        Args:
            position_ms (int): New position in milliseconds
        """
        # Store the position for all states
        self.current_request_position = position_ms
        
        # Different behavior based on current app state
        if self.app_state == STATE_ENDED:
            # For ended state: Only update UI state, no backend operations
            self.app_state = STATE_PAUSED
            self.player_widget.set_playing_state(False)
            self.player_widget.set_position(position_ms)
            self.playback_state_changed.emit(STATE_PAUSED)
        elif self.app_state == STATE_PLAYING:
            # Only perform backend operations if actually playing
            self.backend.seek(position_ms)
            if not self.backend.is_playing:
                self.backend.play()
        else:
            # For paused/stopped states: Just update UI position, no backend operations
            self.player_widget.set_position(position_ms)
        
    def play(self):
        """Start or resume playback"""
        # Check if we have a pending position request, similar to _on_play_requested
        if self.current_request_position is not None:
            # Store position before operations
            position = self.current_request_position
            self.current_request_position = None
            
            # Block position updates during operations to prevent UI jitter
            self.block_position_updates = True
            
            try:
                # Was the player in ended state?
                if self.app_state == STATE_ENDED or not self.backend.is_playing:
                    # Need to reset and restart playback
                    self.backend.stop()
                    result = self.backend.play()
                    self.backend.seek(position)
                else:
                    # Just seek and continue
                    self.backend.seek(position)
                    result = self.backend.play()
                    
                # Update UI position directly instead of relying on backend updates
                self.player_widget.set_position(position)
            finally:
                # Always unblock position updates when done
                self.block_position_updates = False
        else:
            # Normal play
            result = self.backend.play()
            
        if result:
            self._set_app_state(STATE_PLAYING)
        return result
        
    def pause(self):
        """Pause playback"""
        result = self.backend.pause()
        if result:
            self._set_app_state(STATE_PAUSED)
        return result
        
    def stop(self):
        """Stop playback"""
        result = self.backend.stop()
        if result:
            self._set_app_state(STATE_STOPPED)
        return result
        
    def set_volume(self, volume_percent):
        """
        Set playback volume
        
        Args:
            volume_percent (int): Volume percentage (0-200)
        """
        self.player_widget.set_volume(volume_percent)
        # The volume_changed signal will trigger _on_volume_changed
        
    def is_playing(self):
        """Check if application is in playing state"""
        return self.app_state == STATE_PLAYING
        
    def cleanup(self):
        """Clean up resources"""
        self.backend.cleanup()
        
    def closeEvent(self, event):
        """Handle widget close event"""
        self.cleanup()
        super().closeEvent(event)
        
    def _on_volume_changed(self, volume):
        """
        Handle volume change from UI.
        
        Args:
            volume (int): New volume level (0-100)
        """
        self.backend.set_volume(volume)
        # Save the new volume setting
        self.settings.set('player/volume', volume, SettingType.INT)
        
    def _on_rate_changed(self, rate):
        """
        Handle playback rate change from UI.
        
        Args:
            rate (float): New playback rate
        """
        # Update backend rate
        self.backend.set_rate(rate)
        
    def set_rate(self, rate):
        """
        Set the playback rate without affecting pitch.
        
        Args:
            rate (float): Playback rate (e.g., 1.0 for normal, 1.5 for 50% faster)
        """
        # Update UI
        self.player_widget.set_rate(rate)
        
        # Send to backend
        self.backend.set_rate(rate)
        
    def get_rate(self):
        """
        Get the current playback rate.
        
        Returns:
            float: Current playback rate (1.0 is normal speed)
        """
        return self.backend.get_rate()
        
    def seek_relative(self, seconds):
        """
        Seek the current track forward or backward by the specified number of seconds.
        
        Args:
            seconds (float): Number of seconds to seek (positive for forward, negative for backward)
        """
        current_position = self.backend.get_current_position()
        if current_position is not None:
            # Convert seconds to milliseconds
            seek_offset = int(seconds * 1000)
            new_position = max(0, current_position + seek_offset)
            self.backend.seek(new_position)
            
            # Update UI
            self.player_widget.set_position(new_position)
    
    def _apply_saved_volume(self):
        """Apply saved volume setting from settings manager"""
        volume = self.settings.get('player/volume', 100, SettingType.INT)
        self.set_volume(volume)
        # Update the UI to match
        if hasattr(self.player_widget, 'set_volume'):
            self.player_widget.set_volume(volume)
    
    def load_media(self):
        """Open a file dialog to select and load media"""
        # Get the last used directory from settings, or default to home directory
        last_dir = self.settings.get('player/last_directory', os.path.expanduser("~"), SettingType.STRING)
        
        # Open file dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Media File",
            last_dir,
            "Media Files (*.mp3 *.wav *.ogg *.flac *.aac *.m4a *.mp4 *.avi *.mkv *.mov *.webm *.m3u)"
        )
        
        if file_path:
            # Save the directory for next time
            self.settings.set('player/last_directory', os.path.dirname(file_path), SettingType.STRING)
            
            # Load the media file
            self.backend.load_media(file_path)
            
            # Set focus to this player to ensure hotkeys work
            self.setFocus()
            
            # Start playback automatically
            self.app_state = STATE_PLAYING
            
            return True
            
        return False

    def on_media_changed(self, media):
        """Handle media change event - receives metadata dict from backend"""
        if not media:
            return

        # Reset UI state
        self.player_widget.set_playing_state(False)
        
        # Get metadata from the dict
        title = media.get('title', os.path.basename(media.get('path', 'Unknown Track')))
        artist = media.get('artist', 'Unknown Artist')
        album = media.get('album', 'Unknown Album')
        artwork_path = media.get('artwork_path')
        
        # Update the player widget with track info
        self.player_widget.update_track_info(title, artist, album, artwork_path)
        
        # Emit signal for other components to update
        self.media_changed.emit(title, artist, album, artwork_path)
        
        # Set focus to this player to ensure hotkeys work
        self.setFocus()
        
        # Start playback automatically when media changes
        self.backend.play()
        self.app_state = STATE_PLAYING
        
        # Store the metadata
        self.last_metadata = media
        
        # Explicitly emit track_changed signal with metadata
        self.track_changed.emit(media)

    def _on_backend_position_changed(self, position_ms):
        """
        Handle position change events from the backend.
        Respects the blocking flag to prevent UI jitter during operations.
        
        Args:
            position_ms (int): Position in milliseconds
        """
        if not self.block_position_updates:
            self.player_widget.set_position(position_ms)

    def get_current_track_metadata(self):
        """
        Return the metadata of the currently loaded track.

        Returns:
            dict or None: The metadata dictionary or None if no track is loaded.
        """
        return self.last_metadata
        
    def get_current_artwork_path(self):
        """
        Return the artwork path of the currently loaded track.
        
        Returns:
            str or None: The artwork path or None if no artwork available
        """
        if self.last_metadata:
            return self.last_metadata.get('artwork_path')
        return None

    def _on_repeat_state_changed(self, state):
        """
        Handle repeat state changes from the UI.
        
        Args:
            state (str): Repeat state, "repeat_one" or "repeat_all"
        """
        # For now just log the state change, actual repeat functionality will be implemented later
        print(f"Repeat state changed to: {state}")
        # Will be connected to VLCBackend's repeat functionality when implemented