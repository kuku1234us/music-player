"""
Main player module that integrates the UI components with the VLC backend.
"""
import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot

from .player_widget import PlayerWidget
from .hotkey_handler import HotkeyHandler
from music_player.models.vlc_backend import VLCBackend
from music_player.models.settings_manager import SettingsManager, SettingType


class MainPlayer(QWidget):
    """
    Main player widget that combines the UI components with the VLC backend.
    This serves as the main interface between the UI and the media playback.
    """
    
    # Playback states
    STATE_PLAYING = "playing"
    STATE_PAUSED = "paused"
    STATE_STOPPED = "stopped"
    STATE_ENDED = "ended"
    STATE_ERROR = "error"
    
    # Signals
    track_changed = pyqtSignal(dict)  # Emits track metadata
    playback_state_changed = pyqtSignal(str)  # "playing", "paused", "stopped", "error"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("mainPlayer")
        
        # Enable background styling for the widget (needed for border visibility)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        # Get settings manager instance
        self.settings = SettingsManager.instance()
        
        # Internal state tracking
        self.app_state = self.STATE_STOPPED
        self.current_request_position = None
        
        # UI Components
        self.player_widget = PlayerWidget(self)
        
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
        """Set up the main player UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.player_widget)
        self.setLayout(layout)
        
        # Apply styling
        self.setStyleSheet("""
            QWidget#mainPlayer {
                background-color: #1e1e1e;
                border-radius: 8px;
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
        
        # Connect backend to UI
        self.backend.media_loaded.connect(self._on_media_loaded)
        self.backend.position_changed.connect(self.player_widget.set_position)
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
            self._set_app_state(self.STATE_PLAYING)
        elif state == "paused":
            self._set_app_state(self.STATE_PAUSED)
        elif state == "stopped":
            self._set_app_state(self.STATE_STOPPED)
        elif state == "error":
            self._set_app_state(self.STATE_ERROR)
        
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
            # Apply the position first if we have one pending
            position = self.current_request_position
            self.current_request_position = None
            
            # Was the player in ended state?
            if self.app_state == self.STATE_ENDED or not self.backend.is_playing:
                # Need to reset and restart playback
                self.backend.stop()
                self.backend.play()
                self.backend.seek(position)
            else:
                # Just seek and continue
                self.backend.seek(position)
        else:
            # Normal play
            self.backend.play()
            
        # Update app state
        self._set_app_state(self.STATE_PLAYING)
        
    def _on_pause_requested(self):
        """Handle pause requested from UI"""
        self.backend.pause()
        self._set_app_state(self.STATE_PAUSED)
        
    def _set_app_state(self, state):
        """
        Set the application playback state and update UI accordingly.
        
        Args:
            state (str): New state - one of the STATE_* constants
        """
        self.app_state = state
        
        # Update UI
        if state == self.STATE_PLAYING:
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
        self._set_app_state(self.STATE_ENDED)
        
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
        if self.app_state == self.STATE_ENDED:
            # For ended state: Only update UI state, no backend operations
            self.app_state = self.STATE_PAUSED
            self.player_widget.set_playing_state(False)
            self.player_widget.set_position(position_ms)
            self.playback_state_changed.emit(self.STATE_PAUSED)
        elif self.app_state == self.STATE_PLAYING:
            # Only perform backend operations if actually playing
            self.backend.seek(position_ms)
            if not self.backend.is_playing:
                self.backend.play()
        else:
            # For paused/stopped states: Just update UI position, no backend operations
            self.player_widget.set_position(position_ms)
        
    def play(self):
        """Start or resume playback"""
        result = self.backend.play()
        if result:
            self._set_app_state(self.STATE_PLAYING)
        return result
        
    def pause(self):
        """Pause playback"""
        result = self.backend.pause()
        if result:
            self._set_app_state(self.STATE_PAUSED)
        return result
        
    def stop(self):
        """Stop playback"""
        result = self.backend.stop()
        if result:
            self._set_app_state(self.STATE_STOPPED)
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
        return self.app_state == self.STATE_PLAYING
        
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
        Set the playback rate.
        
        Args:
            rate (float): New playback rate (e.g., 1.0 for normal, 1.5 for 50% faster)
            
        Returns:
            float: The actual rate that was set
        """
        # Clamp rate to reasonable bounds (0.25 to 2.0)
        clamped_rate = max(0.25, min(2.0, rate))
        
        # Update UI
        self.player_widget.set_rate(clamped_rate)
        
        # Update backend
        self.backend.set_rate(clamped_rate)
        
        return clamped_rate
        
    def get_rate(self):
        """
        Get the current playback rate.
        
        Returns:
            float: Current playback rate (1.0 is normal speed)
        """
        return self.backend.get_rate()
    
    def _apply_saved_volume(self):
        """Apply the saved volume setting"""
        volume = self.settings.get('player/volume', 100, SettingType.INT)
        self.player_widget.set_volume(volume)
        
        # Also set in backend (using capped value)
        backend_volume = min(100, volume)
        self.backend.set_volume(backend_volume) 