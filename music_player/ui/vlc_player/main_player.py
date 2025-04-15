"""
Main player module that integrates the UI components with the VLC backend.
"""
import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QFileDialog
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
import vlc
from typing import Optional

from .player_widget import PlayerWidget
from .hotkey_handler import HotkeyHandler
from music_player.models.vlc_backend import VLCBackend
from qt_base_app.models.settings_manager import SettingsManager, SettingType
from music_player.models.playlist import Playlist # Import Playlist
# Import the player state module for playlist reference
from music_player.models import player_state

from .enums import STATE_PLAYING, STATE_PAUSED, STATE_ENDED, STATE_ERROR, REPEAT_ONE, REPEAT_ALL, REPEAT_RANDOM # REPEAT_NONE removed


class MainPlayer(QWidget):
    """
    Main player widget that combines the UI components with the VLC backend.
    This serves as the main interface between the UI and the media playback.
    Supports both single file and playlist playback modes.
    """
    
    # Signals
    track_changed = pyqtSignal(dict)  # Emits track metadata
    playback_state_changed = pyqtSignal(str)  # "playing", "paused", "ended", "error"
    media_changed = pyqtSignal(str, str, str, str)  # title, artist, album, artwork_path
    playback_mode_changed = pyqtSignal(str) # Emits 'single' or 'playlist'
    
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
        self.app_state = STATE_PAUSED
        self.current_request_position = None
        self.current_media_path: Optional[str] = None # Store path of current single media or track
        self.block_position_updates = False  # Flag to temporarily block position updates
        self.last_metadata = None  # Store the last received metadata
        self._current_repeat_mode = REPEAT_ALL # Default repeat mode stored internally
        
        # Playback Mode State
        self._playback_mode = 'single'  # 'single' or 'playlist'
        self._current_playlist: Optional[Playlist] = None
        
        # UI Components
        self.player_widget = PlayerWidget(self, persistent=persistent_mode)
        
        # Backend
        self.backend = VLCBackend(self)
        
        # Hotkey handler
        self.hotkey_handler = HotkeyHandler(self)
        
        # Setup
        self._setup_ui()
        self._connect_signals()
        
        # Initialize volume and repeat state
        self._apply_saved_volume()
        self._apply_saved_repeat_mode() # Load repeat mode on init
        
        # Disable next/prev buttons initially (until playlist is loaded)
        self.player_widget.set_next_prev_enabled(False)
        
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
        # Connect UI to backend/player logic
        self.player_widget.play_requested.connect(self._on_play_requested)
        self.player_widget.pause_requested.connect(self._on_pause_requested)
        self.player_widget.position_changed.connect(self._on_position_changed)
        self.player_widget.volume_changed.connect(self._on_volume_changed)
        self.player_widget.rate_changed.connect(self._on_rate_changed)
        self.player_widget.repeat_state_changed.connect(self._on_repeat_state_changed)
        self.player_widget.next_requested.connect(self.play_next_track) # Connect Next button
        self.player_widget.prev_requested.connect(self.play_previous_track) # Connect Prev button
        
        # Connect backend to UI/player logic
        self.backend.media_loaded.connect(self.on_media_metadata_loaded) # Connect to the renamed slot
        
        # Direct connection between backend position and timeline, but with flag check first
        self.backend.position_changed.connect(self._handle_backend_position_change)
        
        # Connect duration updates directly to the timeline
        self.backend.duration_changed.connect(self.player_widget.timeline.set_duration)
        
        # Connect for UI state control - PlayButton is controlled by MainPlayer
        self.backend.state_changed.connect(self._handle_backend_error_states) 
        self.backend.end_reached.connect(self._on_end_reached)
        self.backend.error_occurred.connect(self._show_error)

    def _handle_backend_position_change(self, position_ms):
        """
        Handle position updates from backend to timeline, respecting the blocking flag.
        
        Args:
            position_ms (int): Position in milliseconds from backend
        """
        if not self.block_position_updates:
            self.player_widget.timeline.set_position(position_ms)
        
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
        
    def _show_error(self, error_message):
        """
        Show an error message dialog.
        
        Args:
            error_message (str): Error message to display
        """
        QMessageBox.critical(self, "Playback Error", error_message)
        
    def _on_play_requested(self):
        """Handle play requested from UI"""
        # Handle the simplest cases first
        if self.app_state == STATE_PLAYING:
            print("[MainPlayer] Play requested while already playing - ignoring")
            return
            
        # Check if we have media to play
        if self._playback_mode == 'playlist':
            if not self._current_playlist or len(self._current_playlist) == 0:
                print("[MainPlayer] Play requested but playlist is empty")
                return
        elif not self.current_media_path:
            print("[MainPlayer] No media to play in single mode")
            return

        # After this point, something should start to play unless there are errors

        # If player is currently paused, just resume play
        if self.app_state == STATE_PAUSED:
            # Set UI state first for responsive UI (play() will also do this, but good for immediate feedback)
            self._set_app_state(STATE_PLAYING)
            # Call self.play() instead of self.backend.play() to handle potential seek requests
            self.play()
            return

        # If the player is in the ENDED state, we need to restart
        if self.app_state == STATE_ENDED:
            # Handle playlist mode
            if self._playback_mode == 'playlist':
                # Get the next track
                next_track_path = self._current_playlist.get_next_file()
                if not next_track_path:
                    # If we're at the end and no next track (shouldn't happen with repeat), use first track
                    print("[MainPlayer] No next track available, using first track in playlist")
                    next_track_path = self._current_playlist.get_first_file()
                    
                print(f"[MainPlayer] Loading track from playlist: {next_track_path}")
                self.current_request_position = 0  # Start from beginning of track
                # Set state to playing BEFORE loading media for responsive UI
                self._set_app_state(STATE_PLAYING)
                self.backend.load_media(next_track_path)
            else:
                # Single file mode with an existing media file loaded
                print(f"[MainPlayer] Restarting track: {self.current_media_path}")
                # Set state to playing first for responsive UI
                self._set_app_state(STATE_PLAYING)
                self.backend.seek(0)  # Rewind to beginning
                self.backend.play()
            
            self.setFocus()
            return
            
        # At this point, we're in an unexpected state (possibly initial state)
        # Just attempt to start playback with what we have
        print(f"[MainPlayer] Play requested in state {self.app_state}, attempting to play")
        
        if self._playback_mode == 'playlist' and self._current_playlist:
            first_track = self._current_playlist.get_first_file()
            if first_track:
                # Set state to playing BEFORE loading media for responsive UI
                self._set_app_state(STATE_PLAYING)
                self._load_and_play_path(first_track)
        elif self.current_media_path:
            # Set state to playing first for responsive UI
            self._set_app_state(STATE_PLAYING)
            self.backend.seek(0)
            self.backend.play()
            
        self.setFocus()
        
    def _on_pause_requested(self):
        """Handle pause requested from UI"""
        # Set app state to paused FIRST for responsive UI
        self._set_app_state(STATE_PAUSED)
        
        # Then tell the backend to pause
        self.backend.pause()
        
        # Set focus to this player to ensure hotkeys work
        self.setFocus()
        
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
        
    def _handle_backend_error_states(self, state):
        """
        Handle backend state change events.
        This now primarily focuses on the 'error' state, as 'ended' is handled by _on_end_reached.
        
        Args:
            state (str): State from backend ("playing", "paused", "stopped", "error")
        """
        # Map backend state to app state
        if state == "error":
            print(f"[MainPlayer] Backend reported error state.")
            self._set_app_state(STATE_ERROR)
            # Optionally show an error message or take other recovery steps
            # self._show_error("An unknown playback error occurred.")
        elif state == "ended":
            # This case should now be fully handled by _on_end_reached directly.
            # We might still log it here if needed for debugging.
            print("[MainPlayer] Backend state changed to 'ended' (handled by _on_end_reached).")
            # No action needed here anymore.
            pass 
        elif state == "playing":
            # If the backend spontaneously reports 'playing', ensure our state matches.
            # This might happen after certain operations or recovery.
            if self.app_state != STATE_PLAYING:
                print("[MainPlayer] Backend state changed to 'playing', syncing app state.")
                self._set_app_state(STATE_PLAYING)
        elif state == "paused":
            # If the backend spontaneously reports 'paused', ensure our state matches.
            if self.app_state != STATE_PAUSED:
                print("[MainPlayer] Backend state changed to 'paused', syncing app state.")
                self._set_app_state(STATE_PAUSED)
        # Note: We don't explicitly handle "stopped" as our app doesn't use it.

    def _on_end_reached(self):
        """
        Handler for the media end event.
        Decides what to do when a track finishes playing based on playback mode and repeat settings.
        """
        print(f"[MainPlayer] _on_end_reached called with mode {self._playback_mode}")
        if self._playback_mode == 'single':
            # Always repeat in single mode
            self.backend.seek(0)
            self.backend.play()
        elif self._playback_mode == 'playlist' and self._current_playlist:
            # In playlist mode, get the next track from the playlist
            # The playlist now handles repeat logic internally based on its own repeat mode
            next_track_path = self._current_playlist.get_next_file()
            
            if next_track_path:
                print(f"[MainPlayer] Playing next track: {next_track_path}")
                self._load_and_play_path(next_track_path)
            else:
                # If there's no next track, stop playback
                print("[MainPlayer] No more tracks in playlist, stopping playback")
                self.backend.stop()
                self.player_widget.set_playing_state(False)

    def _on_position_changed(self, position_ms):
        """
        Handle position change from timeline.
        Only sends position changes to backend when in playing state,
        otherwise just updates UI and stores position for later.
        
        Args:
            position_ms (int): New position in milliseconds
        """
        # Store the position for all states initially
        self.current_request_position = position_ms
        
        # Different behavior based on current app state
        if self.app_state == STATE_ENDED:
            # For ended state: Only update UI state, no backend operations
            # Keep current_request_position set for the next play() call
            self.app_state = STATE_PAUSED
            self.player_widget.set_playing_state(False)
            self.playback_state_changed.emit(STATE_PAUSED)
            # Update UI timeline immediately
            self.player_widget.timeline.set_position(position_ms)
        elif self.app_state == STATE_PLAYING:
            # Only perform backend operations if actually playing
            # Set blocking flag to prevent position update loop
            self.block_position_updates = True
            seek_successful = False
            try:
                self.backend.seek(position_ms)
                # Optional: Check if backend is still playing, restart if stopped unexpectedly
                if not self.backend.is_playing:
                    self.backend.play()
                seek_successful = True # Assume seek was sent
            finally:
                # Always unblock updates when done
                self.block_position_updates = False
                
            # If seek was successfully initiated while playing, clear the request
            if seek_successful:
                self.current_request_position = None
                # Update UI timeline immediately after successful seek during playback
                self.player_widget.timeline.set_position(position_ms)

        else: # STATE_PAUSED or other non-playing states
            # For paused states: Just update timeline manually, keep current_request_position
            self.player_widget.timeline.set_position(position_ms)
        
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
                if self.app_state == STATE_ENDED:
                    # Need to reload media and start playback
                    if self.current_media_path:
                        # Set UI state immediately for responsive UI
                        self._set_app_state(STATE_PLAYING)
                        
                        # Load the media first (this triggers on_media_changed for metadata)
                        self.backend.load_media(self.current_media_path)
                        
                        # Explicitly start playback and seek to requested position
                        result = self.backend.play()
                        self.backend.seek(position)
                    else:
                        # No current media path to reload
                        result = False
                else:
                    # For already playing or paused state, update UI immediately for responsiveness
                    self._set_app_state(STATE_PLAYING)
                    # Just seek and continue
                    self.backend.seek(position)
                    result = self.backend.play()
                    
                # Update timeline directly
                self.player_widget.timeline.set_position(position)
            finally:
                # Always unblock updates when done
                self.block_position_updates = False
        else:
            # For direct play request with no position change, update UI immediately
            if self.app_state == STATE_PAUSED or self.app_state == STATE_ENDED:
                self._set_app_state(STATE_PLAYING)
            # Normal play
            result = self.backend.play()
            
        return result
        
    def pause(self):
        """Pause playback"""
        # Set app state to paused FIRST for responsive UI
        self._set_app_state(STATE_PAUSED)
        
        # Then tell the backend to pause
        result = self.backend.pause()
        
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
        """
        Clean up resources when the main player is closed.
        """
        # Unregister from player_state - REMOVED
        # player_state.unregister_track_play_requested_callback(self._on_track_play_requested)
        
        # Stop playback and clean up
        self.backend.stop()
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
        """Open a file dialog to select and load a SINGLE media file. Sets mode to 'single'."""
        last_dir = self.settings.get('player/last_directory', os.path.expanduser("~"), SettingType.STRING)
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Media File", last_dir,
            "Media Files (*.mp3 *.wav *.ogg *.flac *.aac *.m4a *.mp4 *.avi *.mkv *.mov *.webm *.m3u)"
        )
        
        if file_path:
            self.settings.set('player/last_directory', os.path.dirname(file_path), SettingType.STRING)
            
            # Update playback mode without stopping current playback
            self.set_playback_mode('single')
            self._current_playlist = None
            
            self._load_and_play_path(file_path)
            self.setFocus()
            return True
        return False
        
    def on_media_metadata_loaded(self, media):
        """
        Handle media metadata loaded event - receives metadata dict from backend.
        Only updates metadata and UI elements, does not affect playback state.
        """
        if not media:
            # This might happen if loading failed internally in backend
            # If in playlist mode, try advancing?
            if self._playback_mode == 'playlist':
                print("[MainPlayer] on_media_metadata_loaded received empty media, attempting next track.")
                self.play_next_track(force_advance=True)
            return

        self.last_metadata = media # Store metadata regardless of UI update
        
        title = media.get('title', os.path.basename(self.current_media_path or 'Unknown Track'))
        artist = media.get('artist', 'Unknown Artist')
        album = media.get('album', 'Unknown Album')
        artwork_path = media.get('artwork_path')
        
        # Update UI with track information
        self.player_widget.update_track_info(title, artist, album, artwork_path)
        self.media_changed.emit(title, artist, album, artwork_path)
        self.setFocus()
        
        # Emit track changed signal with complete metadata
        self.track_changed.emit(media)
        
    def get_current_track_metadata(self):
        """ Returns metadata of the currently playing track. """
        return self.last_metadata
        
    def get_current_artwork_path(self):
        """ Returns artwork path of the currently playing track. """
        if self.last_metadata:
            return self.last_metadata.get('artwork_path')
        return None
        
    def get_current_media_path(self) -> Optional[str]:
        """ Returns the path of the currently loaded media file or track. """
        return self.current_media_path

    def _apply_saved_repeat_mode(self):
        """ Load repeat mode from settings, validate, store internally, and update UI. """
        # Default to REPEAT_ALL if saved value is invalid
        repeat_mode = self.settings.get('player/repeat_mode', REPEAT_ALL, SettingType.STRING)
        
        # Validate it's one of the allowed modes, default to REPEAT_ALL if not
        if repeat_mode not in [REPEAT_ONE, REPEAT_ALL, REPEAT_RANDOM]:
            print(f"Warning: Invalid or deprecated repeat mode '{repeat_mode}' found in settings, defaulting to REPEAT_ALL.")
            repeat_mode = REPEAT_ALL
            # Optionally re-save the setting to clean it up
            # self.settings.set('player/repeat_mode', repeat_mode, SettingType.STRING)
        
        # Store validated mode internally
        self._current_repeat_mode = repeat_mode
        print(f"[MainPlayer] Applied repeat mode from settings: {self._current_repeat_mode}")
        
        # Update the playlist's repeat mode if we're in playlist mode
        if self._playback_mode == 'playlist' and self._current_playlist:
            self._current_playlist.set_repeat_mode(self._current_repeat_mode)
        
        # Update the UI button state
        self.player_widget.set_repeat_state(self._current_repeat_mode)

    def _on_repeat_state_changed(self, state):
        """
        Handle repeat state change from UI, validate, store internally, and save setting.
        Args:
            state (str): Repeat state (REPEAT_ONE, REPEAT_ALL, REPEAT_RANDOM) from PlayerWidget
        """
        # Validate the state received from the UI
        if state not in [REPEAT_ONE, REPEAT_ALL, REPEAT_RANDOM]:
            print(f"Warning: Received invalid repeat state '{state}' from UI. Resetting UI.")
            # Reset UI to match internal state if invalid state received
            self.player_widget.set_repeat_state(self._current_repeat_mode)
            self._current_repeat_mode = REPEAT_ALL
            return
            
        # Update internal state if changed
        if state != self._current_repeat_mode:
            self._current_repeat_mode = state
            print(f"[MainPlayer] Internal repeat mode changed to: {self._current_repeat_mode}")
            
            # Update playlist's repeat mode if we're in playlist mode
            if self._playback_mode == 'playlist' and self._current_playlist:
                self._current_playlist.set_repeat_mode(self._current_repeat_mode)
                
            # Save the new state to settings
            self.settings.set('player/repeat_mode', self._current_repeat_mode, SettingType.STRING)

    def set_playback_mode(self, mode: str):
        """ Sets the playback mode and updates UI elements accordingly. """
        if mode not in ['single', 'playlist']:
            print(f"Warning: Invalid playback mode requested: {mode}")
            return
            
        if self._playback_mode != mode:
            self._playback_mode = mode
            print(f"[MainPlayer] Playback mode set to: {self._playback_mode}")
            # Enable/disable Next/Prev buttons based on mode
            is_playlist_mode = (self._playback_mode == 'playlist')
            self.player_widget.set_next_prev_enabled(is_playlist_mode)
            self.playback_mode_changed.emit(self._playback_mode)

    @pyqtSlot(Playlist)
    def load_playlist(self, playlist: Optional[Playlist]):
        """ 
        Sets the player to use the provided Playlist object. 
        The player will directly reference the global current_playing_playlist,
        so any changes made to the playlist elsewhere will be immediately available.
        
        Checks if the requested playlist is already playing and ignores the request if so.
        """
        print(f"[MainPlayer] load_playlist called with: {playlist}")
        
        # --- Add check: If this playlist is already playing, do nothing --- 
        if self._playback_mode == 'playlist' and self._current_playlist == playlist and self.is_playing():
            print(f"[MainPlayer] Playlist '{playlist.name if playlist else 'None'}' is already playing. Ignoring load request.")
            return
        # --- End check ---
        
        if not playlist:
            # Only show warning if playlist is None, not if it's just empty
            self.set_playback_mode('single')
            # Use direct reference to global variable rather than keeping a copy
            self._current_playlist = None
            self.player_widget.update_track_info("No Track", "", "", None)
            self.player_widget.timeline.set_duration(0)
            self.player_widget.timeline.set_position(0)
            return

        # Store a reference to the global current_playing_playlist
        # This ensures we always use the most up-to-date playlist state
        self._current_playlist = player_state.get_current_playlist()
        
        # Set the playlist's repeat mode to match the player's mode
        # This is one of the appropriate times to set the repeat mode
        if self._current_playlist:
            self._current_playlist.set_repeat_mode(self._current_repeat_mode)
        
        self.set_playback_mode('playlist')
        
        # If playlist is empty, just clean the UI and wait - no error
        if len(self._current_playlist) == 0:
            print(f"[MainPlayer] Playlist '{self._current_playlist.name}' is empty, waiting for tracks to be added.")
            self.player_widget.update_track_info("No Tracks", f"Playlist: {self._current_playlist.name}", "", None)
            self.player_widget.timeline.set_duration(0)
            self.player_widget.timeline.set_position(0)
            return
            
        # Get the first file path from the playlist
        first_track_path = self._current_playlist.get_first_file()
        
        if first_track_path:
            print(f"[MainPlayer] Loading first track from playlist: {first_track_path}")
            # Use load_and_play_path which now explicitly handles state updates and playback
            self._load_and_play_path(first_track_path)
        else:
            # This should only happen if there's a technical error retrieving a track
            # that we know exists (since we checked len > 0 above)
            self._show_error("Could not retrieve first track from playlist.")

    def _load_and_play_path(self, file_path: str):
        """
        Internal helper to load a specific file path and start playback.
        Args:
            file_path (str): The absolute path to the media file.
        """
        if not file_path or not os.path.exists(file_path):
            self._show_error(f"Media file not found: {file_path}")
            if self._playback_mode == 'playlist':
                # If loading fails in playlist mode, try to advance
                self.play_next_track(force_advance=True) # Pass force_advance if needed
            # No longer stopping here - let current playback continue if any
            return
             
        self.current_media_path = file_path
        print(f"[MainPlayer] Backend loading: {file_path}")
        
        # Always set the app state to playing BEFORE loading media for responsive UI
        self._set_app_state(STATE_PLAYING)
        
        # Load the media (this will trigger on_media_changed but won't start playback)
        self.backend.load_media(file_path)
        
        # Explicitly start playback after media is loaded
        self.backend.play()

    def play_next_track(self):
        """
        Plays the next track in the playlist based on the current state and repeat mode.
        """
        print("[MainPlayer] play_next_track called")
        if self._playback_mode == 'playlist' and self._current_playlist:
            next_track_path = self._current_playlist.get_next_file()
            
            if next_track_path:
                print(f"[MainPlayer] Playing next track: {next_track_path}")
                self._load_and_play_path(next_track_path)
            else:
                print("[MainPlayer] No next track available in playlist")
        else:
            print("[MainPlayer] Cannot play next track - not in playlist mode or no playlist")

    def play_previous_track(self):
        """
        Plays the previous track in the playlist based on the current state and repeat mode.
        """
        print("[MainPlayer] play_previous_track called")
        if self._playback_mode == 'playlist' and self._current_playlist:
            prev_track_path = self._current_playlist.get_previous_file()
            
            if prev_track_path:
                print(f"[MainPlayer] Playing previous track: {prev_track_path}")
                self._load_and_play_path(prev_track_path)
            else:
                print("[MainPlayer] No previous track available in playlist")
        else:
            print("[MainPlayer] Cannot play previous track - not in playlist mode or no playlist")

    @pyqtSlot(str)
    def play_track_from_playlist(self, filepath: str):
        """
        Slot to handle playback requests originating from the playlist UI.

        Args:
            filepath (str): The absolute path of the track selected in the playlist UI.
        """
        print(f"[MainPlayer] Received request to play track: {filepath}")
        
        # Step 2a: Ensure we are in playlist mode and have the correct playlist
        current_ui_playlist = player_state.get_current_playlist() # Get the playlist currently shown in UI
        
        if not current_ui_playlist:
            print("[MainPlayer] Error: No current playlist set in player_state. Cannot play track.")
            return
            
        if self._playback_mode != 'playlist' or self._current_playlist != current_ui_playlist:
            print(f"[MainPlayer] Switching to playlist mode for playlist: {current_ui_playlist.name}")
            self.set_playback_mode('playlist')
            # Set internal player playlist reference to the one from the UI
            self._current_playlist = current_ui_playlist
            # Sync the repeat mode from player to the newly assigned playlist
            if self._current_playlist:
                 self._current_playlist.set_repeat_mode(self._current_repeat_mode)
            
        if not self._current_playlist:
             print("[MainPlayer] Error: Could not set the current playlist reference.")
             return
             
        # Step 2b: Select the track in the playlist model
        if not self._current_playlist.select_track_by_filepath(filepath):
            print(f"[MainPlayer] Error: Track '{filepath}' not found in current playlist '{self._current_playlist.name}'.")
            return # Stop if track couldn't be selected

        # Step 2c & 2d: Load, set state, seek, and play
        print(f"[MainPlayer] Loading and playing selected track: {filepath}")
        self.current_media_path = filepath # Update current media path
        self.backend.load_media(filepath)
        self._set_app_state(STATE_PLAYING)
        # self.backend.seek(0) # seek(0) might not be needed as load_media often starts from beginning
        self.backend.play()
        self.setFocus() # Ensure player retains focus

    @pyqtSlot(str)
    def play_single_file(self, filepath: str):
        """
        Slot to handle requests to play a single file directly.
        Sets the playback mode to 'single'.

        Args:
            filepath (str): The absolute path of the file to play.
        """
        print(f"[MainPlayer] Received request to play single file: {filepath}")
        
        # Set mode to single and clear playlist reference
        self.set_playback_mode('single') 
        self._current_playlist = None
        
        # Load and play the track
        self._load_and_play_path(filepath)
        self.setFocus() # Ensure player retains focus