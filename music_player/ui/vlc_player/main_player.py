"""
Main player module that integrates the UI components with the VLC backend.
"""
import os
import sys # <-- Add sys import for platform check
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QFileDialog
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
import vlc
from typing import Optional

from .player_widget import PlayerWidget
from .hotkey_handler import HotkeyHandler
# Import VideoWidget for type hinting
from music_player.ui.components.player_components.video_widget import VideoWidget
from music_player.models.vlc_backend import VLCBackend
from qt_base_app.models.settings_manager import SettingsManager, SettingType
# Delay import to prevent circular dependency
# from music_player.models.playlist import Playlist # Import Playlist
# Import the player state module for playlist reference
from music_player.models import player_state
# Import the recently played model
from music_player.models.recently_played import RecentlyPlayedModel

# --- Add ClippingManager import ---
from music_player.models.ClippingManager import ClippingManager
# ---------------------------------

from .enums import STATE_PLAYING, STATE_PAUSED, STATE_ENDED, STATE_ERROR, REPEAT_ONE, REPEAT_ALL, REPEAT_RANDOM # REPEAT_NONE removed

# --- Add FullScreenManager import ---
from music_player.ui.components.player_components.full_screen_video import FullScreenManager
# ------------------------------------
# --- Add PlayerPage import for type hinting and method call ---
from music_player.ui.pages.player_page import PlayerPage 
# -----------------------------------------------------------

class MainPlayer(QWidget):
    """
    Main player widget that combines the UI components with the VLC backend.
    This serves as the main interface between the UI and the media playback.
    Supports both single file and playlist playback modes.
    """
    
    # Signals
    # track_changed = pyqtSignal(dict)  # Emits track metadata <- REMOVED
    playback_state_changed = pyqtSignal(str)  # "playing", "paused", "ended", "error"
    # media_changed = pyqtSignal(str, str, str, str)  # title, artist, album, artwork_path <- OLD SIGNATURE
    media_changed = pyqtSignal(dict, bool) # Emits metadata dict and is_video flag <- NEW SIGNATURE
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
        # Get recently played model instance
        self.recently_played_model = RecentlyPlayedModel.instance()
        
        # Internal state tracking
        self.app_state = STATE_PAUSED
        self.current_request_position = None
        self.current_media_path: Optional[str] = None # Store path of current single media or track
        self.block_position_updates = False  # Flag to temporarily block position updates
        self.last_metadata = None  # Store the last received metadata
        self._current_repeat_mode = REPEAT_ALL # Default repeat mode stored internally
        self._is_current_media_video = False # <-- NEW: Flag to track media type
        # Use VideoWidget for type hint as it's more specific, though QWidget is also valid
        self._video_widget: Optional[VideoWidget] = None # <-- NEW: Reference to video output widget
        
        # --- Get ClippingManager instance ---
        self.clipping_manager = ClippingManager.instance()
        # ----------------------------------
        
        # Subtitle state tracking
        self._has_subtitle_tracks = False
        self._subtitle_enabled = False
        self._current_subtitle_track = -1
        self._subtitle_tracks = []
        self._current_subtitle_language = ""
        
        # Playback Mode State
        self._playback_mode = 'single'  # 'single' or 'playlist'
        # Use string literal for type hint
        self._current_playlist: Optional['Playlist'] = None
        
        # --- Add FullScreenManager instance attribute ---
        self.full_screen_manager: Optional[FullScreenManager] = None
        # --- Add PlayerPage reference attribute ---
        self._player_page_ref: Optional[PlayerPage] = None
        # ----------------------------------------
        
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
        
        # Connect subtitle control signals
        self.player_widget.toggle_subtitles.connect(self._toggle_subtitles)
        self.player_widget.next_subtitle.connect(self._cycle_subtitle_track)  # Legacy support
        self.player_widget.subtitle_selected.connect(self._select_subtitle_track)  # New menu selection
        
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

            # # --- NEW: Try setting HWND when playback starts for video ---
            # if self._is_current_media_video and self._video_widget:
            #     print("[MainPlayer] State is PLAYING and media is video, setting HWND.")
            #     self._set_vlc_window_handle(self._video_widget)
            # # -----------------------------------------------------------

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
        
        # --- Call FullScreenManager cleanup ---
        if self.full_screen_manager:
            self.full_screen_manager.cleanup()
        # -------------------------------------
        
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

        # --- HIDE VIDEO WIDGET before opening file dialog ---
        self._video_widget.setVisible(False)
        video_was_hidden = True
        # -----------------------

        last_dir = self.settings.get('player/last_directory', os.path.expanduser("~"), SettingType.STRING)
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Media File", last_dir,
            "Media Files (*.mp3 *.wav *.ogg *.flac *.aac *.m4a *.mp4 *.avi *.mkv *.mov *.webm *.m3u)"
        )
        
        if file_path:
            self.settings.set('player/last_directory', os.path.dirname(file_path), SettingType.STRING)
            
            self.set_playback_mode('single')
            self._current_playlist = None
            
            self.recently_played_model.add_item(item_type='file', name=os.path.basename(file_path), path=file_path)
            
            # Hiding is done before dialog, no need here
            
            try:
                self._load_and_play_path(file_path)
            finally:
                # --- KEEP THIS RESTORE LOGIC ---
                # This is needed because the media type isn't known until AFTER loading.
                if self._video_widget: # <-- We need to remove the 'video_was_hidden' check here
                     if self._is_current_media_video:
                         print("[MainPlayer] New media is video, restoring video widget visibility.")
                         self._video_widget.setVisible(True)
                     else:
                         print("[MainPlayer] New media is audio, keeping video widget hidden.")
                # -------------------------------
                # --- NEW: Notify PlayerTimeline and ClippingManager about media change ---
                self.player_widget.timeline.set_current_media_path(self.current_media_path)
                self.clipping_manager.set_media(self.current_media_path if self.current_media_path else "")
                # ---------------------------------------------------------------------

            self.setFocus()
            return True
        else:
            # --- KEEP THIS RESTORE LOGIC TOO ---
            # Restore if dialog was cancelled
            if self._video_widget: # <-- And remove 'video_was_hidden' here
                 print("[MainPlayer] File dialog cancelled, restoring video widget visibility.")
                 self._video_widget.setVisible(True)
            # --------------------------------
            # --- NEW: Notify PlayerTimeline and ClippingManager if dialog cancelled (media path becomes None effectively) ---
            # self.player_widget.timeline.set_current_media_path(None) # self.current_media_path would be None
            # self.clipping_manager.set_media("") # No specific media path was set
            # Decided against this here, as current_media_path wouldn't have changed to a *new* valid path.
            # The existing media (if any) remains, so markers for it should persist.
            # Clearing happens when a *new* media is successfully loaded or explicitly stopped.
            # -----------------------------------------------------------------------------------------------------------
            return False

    def on_media_metadata_loaded(self, media: dict, is_video: bool):
        """
        Handle media loaded event - receives metadata dict AND is_video flag from backend.
        Updates metadata, UI elements, and stores media type.
        """
        if not media:
            print("[MainPlayer] on_media_metadata_loaded received empty media.")
            # Try advancing if in playlist mode
            if self._playback_mode == 'playlist':
                print("[MainPlayer] Attempting next track due to empty media.")
                self.play_next_track(force_advance=True)
            return

        self.last_metadata = media # Store metadata regardless of UI update
        
        title = media.get('title', os.path.basename(self.current_media_path or 'Unknown Track'))
        artist = media.get('artist', 'Unknown Artist')
        album = media.get('album', 'Unknown Album')
        artwork_path = media.get('artwork_path')
        
        # --- Store media type internally using received value --- 
        self._is_current_media_video = is_video
        print(f"[MainPlayer] Media loaded. is_video = {self._is_current_media_video}")
        # --------------------------------------------------------
        
        # --- Check and enable subtitles for videos ---
        if self._is_current_media_video:
            # Reset subtitle state
            self._reset_subtitle_state()
            
            # Check if subtitles are available
            if self.backend.has_subtitle_tracks():
                print("[MainPlayer] Subtitles detected in video, auto-enabling first track")
                self._has_subtitle_tracks = True
                
                # Get all tracks
                self._subtitle_tracks = self.backend.get_subtitle_tracks()
                print(f"[MainPlayer] Available subtitle tracks: {self._subtitle_tracks}")
                
                # Find the first non-disabled track (usually ID 1, as 0 is often "Disabled")
                suitable_track = None
                for track in self._subtitle_tracks:
                    # Skip track 0 which is usually "Disabled"
                    if track['id'] > 0:
                        suitable_track = track
                        # Prefer to use display_name if available
                        track_name = track.get('display_name', track['name'])
                        # Check if language is available directly or extract from name
                        self._current_subtitle_language = track.get('language') or self._extract_language_code(track_name)
                        break
                
                # If we found a suitable track, enable it
                if suitable_track is not None:
                    print(f"[MainPlayer] Auto-enabling subtitle track {suitable_track['id']}")
                    if self.backend.enable_subtitles(suitable_track['id']):
                        self._subtitle_enabled = True
                        self._current_subtitle_track = suitable_track['id']
                else:
                    # If only track 0 exists, try it anyway
                    if self._subtitle_tracks and self.backend.enable_subtitles(0):
                        self._subtitle_enabled = True
                        self._current_subtitle_track = 0
                        # Use the name of track 0 as well
                        if self._subtitle_tracks[0]:
                            track_name = self._subtitle_tracks[0].get('display_name', self._subtitle_tracks[0]['name'])
                            self._current_subtitle_language = (self._subtitle_tracks[0].get('language') or 
                                                              self._extract_language_code(track_name))
                        
                # Update subtitle controls in PlayerWidget
                self._update_subtitle_controls()
        else:
            # Reset subtitle state for non-video files
            self._reset_subtitle_state()
            self._update_subtitle_controls()
        # -------------------------------------------

        # Update UI with track information
        self.player_widget.update_track_info(title, artist, album, artwork_path)
        self.setFocus()
        
        # Emit the consolidated media_changed signal
        self.media_changed.emit(media, is_video)
        
    def _reset_subtitle_state(self):
        """Reset internal subtitle state tracking."""
        self._has_subtitle_tracks = False
        self._subtitle_enabled = False
        self._current_subtitle_track = -1
        self._subtitle_tracks = []
        self._current_subtitle_language = ""
        
    def _update_subtitle_controls(self):
        """Update the subtitle controls in the PlayerWidget based on current state."""
        self.player_widget.update_subtitle_state(
            self._has_subtitle_tracks,
            self._subtitle_enabled,
            self._current_subtitle_language,
            self._subtitle_tracks  # Pass the full list of subtitle tracks for the menu
        )
        
    def _extract_language_code(self, track_name):
        """
        Extract a 2-3 letter language code from a subtitle track name.
        
        Args:
            track_name (str or bytes): Full name of the subtitle track
            
        Returns:
            str: Extracted language code or "SUB" if not found
        """
        # If track_name is bytes, decode it to a string
        if isinstance(track_name, bytes):
            try:
                track_name = track_name.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    # Try another common encoding if utf-8 fails
                    track_name = track_name.decode('latin-1')
                except Exception:
                    # If all decoding fails, return default
                    print(f"[MainPlayer] Warning: Could not decode subtitle track name: {track_name}")
                    return "SUB"
        
        # If the track name is empty, return default value
        if not track_name:
            return "SUB"
            
        # Try to extract any 2-3 letter code in square brackets or parentheses
        import re
        match = re.search(r'[\[\(]([a-z]{2,3})[\]\)]', track_name.lower())
        if match:
            return match.group(1).upper()
            
        # Try to find common language identifiers in the track name
        track_lower = track_name.lower()
        
        # Look for language name patterns like "English" or "en"
        language_patterns = [
            # Match standalone 2-letter codes
            (r'\b(en|fr|es|de|it|ru|ja|zh|ko|ar|nl|pt|sv|pl|tr|he|vi|th)\b', 0),
            # Match standalone 3-letter codes
            (r'\b(eng|fre|spa|ger|ita|rus|jpn|chi|kor)\b', 0),
            # Extract from language names (capture first 2 chars)
            (r'\b(english|french|spanish|german|italian|russian|japanese|chinese|korean|arabic|dutch|portuguese|swedish|polish|turkish|hebrew|vietnamese|thai)\b', 2)
        ]
        
        for pattern, length in language_patterns:
            match = re.search(pattern, track_lower)
            if match:
                code = match.group(1)
                # If it's a full language name, take first 2 characters
                if length > 0:
                    code = code[:length]
                return code.upper()
                
        # If track name includes "subtitles" or similar terms, extract nearby text
        subtitle_match = re.search(r'(subtitle|caption)s?\s*[:\-]?\s*([a-z]{2,3}|[A-Za-z]+)', track_lower)
        if subtitle_match:
            code = subtitle_match.group(2)
            # If it's a language name rather than code, take first 2 chars
            if len(code) > 3:
                code = code[:2]
            return code.upper()
                
        # Default to "SUB" if no language code found
        return "SUB"
        
    def _toggle_subtitles(self):
        """Toggle subtitles on/off."""
        if not self._is_current_media_video or not self._has_subtitle_tracks:
            return
            
        if self._subtitle_enabled:
            # Disable subtitles
            if self.backend.disable_subtitles():
                self._subtitle_enabled = False
                print("[MainPlayer] Subtitles disabled")
        else:
            # Enable subtitles (use last track, or first available)
            track_id = self._current_subtitle_track
            if track_id <= 0 and self._subtitle_tracks:
                # Find first valid track
                for track in self._subtitle_tracks:
                    if track['id'] > 0:
                        track_id = track['id']
                        # Use display_name if available
                        track_name = track.get('display_name', track['name'])
                        # Get language directly or extract it
                        self._current_subtitle_language = track.get('language') or self._extract_language_code(track_name)
                        break
                        
            if track_id > 0:
                if self.backend.enable_subtitles(track_id):
                    self._subtitle_enabled = True
                    self._current_subtitle_track = track_id
                    print(f"[MainPlayer] Enabled subtitle track: {track_id}")
            
        # Update UI
        self._update_subtitle_controls()
        
    def _cycle_subtitle_track(self):
        """Cycle to the next available subtitle track."""
        if not self._is_current_media_video or not self._has_subtitle_tracks:
            return
            
        if not self._subtitle_tracks:
            return
            
        # Find the next track after the current one
        current_track = self._current_subtitle_track
        next_track = None
        found_current = False
        
        # First pass: find a track after the current one
        for track in self._subtitle_tracks:
            if found_current and track['id'] > 0:  # Skip disabled tracks (usually id=0)
                next_track = track
                break
            if track['id'] == current_track:
                found_current = True
                
        # If we didn't find a next track, loop back to the first one
        if next_track is None:
            for track in self._subtitle_tracks:
                if track['id'] > 0:  # Skip disabled tracks
                    next_track = track
                    break
                    
        # If we still don't have a track, try to enable track 0 as a fallback
        if next_track is None and self._subtitle_tracks:
            next_track = self._subtitle_tracks[0]
            
        # Enable the new track if found
        if next_track:
            track_id = next_track['id']
            if self.backend.enable_subtitles(track_id):
                self._subtitle_enabled = True
                self._current_subtitle_track = track_id
                # Use display_name if available
                track_name = next_track.get('display_name', next_track['name'])
                # Get language directly or extract it
                self._current_subtitle_language = next_track.get('language') or self._extract_language_code(track_name)
                print(f"[MainPlayer] Switched to subtitle track: {track_id} ({track_name})")
                
        # Update UI
        self._update_subtitle_controls()
        
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

    # Use object type hint for the slot to avoid import issues
    @pyqtSlot(object) 
    def load_playlist(self, playlist: Optional[object]):
        """ 
        Sets the player to use the provided Playlist object. 
        The player will directly reference the global current_playing_playlist,
        so any changes made to the playlist elsewhere will be immediately available.
        
        Checks if the requested playlist is already playing and ignores the request if so.
        """
        print(f"[MainPlayer] load_playlist called with: {playlist}")
        
        # --- Add check: If this playlist is already playing, do nothing --- 
        # Note: Comparison should still work with object references
        if self._playback_mode == 'playlist' and self._current_playlist == playlist and self.is_playing():
            # We might need to add an isinstance check here if the playlist object isn't directly comparable
            # For now, assume reference comparison works. Add if runtime errors occur.
            # from music_player.models.playlist import Playlist
            # if isinstance(playlist, Playlist):
            #     print(f"[MainPlayer] Playlist '{playlist.name}' is already playing. Ignoring load request.")
            print(f"[MainPlayer] Playlist is already playing. Ignoring load request.") # Generic message
            return
        # --- End check ---
        
        # Need Playlist type for adding to recently played, import locally
        from music_player.models.playlist import Playlist
        if not isinstance(playlist, Playlist):
             # Handle the case where a non-playlist object was somehow passed
             print(f"[MainPlayer] Error: load_playlist called with non-Playlist object: {type(playlist)}")
             return
             
        # --- If checks passed, proceed to load --- 
        
        # Update the global player state *first*
        player_state.set_current_playlist(playlist)
        
        # Update the internal reference *second*
        self._current_playlist = playlist
        # NOTE: We could potentially just rely on player_state.get_current_playlist() 
        #       instead of self._current_playlist, but having a local reference 
        #       can sometimes be cleaner. For now, keep both synced.
 
        # Store a reference to the global current_playing_playlist
        # This ensures we always use the most up-to-date playlist state
        # self._current_playlist = player_state.get_current_playlist() # Redundant now
        
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
            
        # Get the first file path directly from the playlist method
        first_track_path = self._current_playlist.get_first_file()
        # --- DEBUG --- 
        print(f"[MainPlayer] load_playlist: Received first_track_path: {repr(first_track_path)}")
        # ------------- 

        # Add playlist to recently played WHEN it starts playing
        if first_track_path: # Only add if we have something to play
            # Ensure playlist has a valid filepath before adding
            if playlist.filepath:
                self.recently_played_model.add_item(item_type='playlist', name=playlist.name, path=playlist.filepath)
            else:
                print(f"[MainPlayer] Warning: Cannot add playlist '{playlist.name}' to recently played, missing filepath.")
        
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
        # Ensure file_path is a string before checking existence or showing error
        actual_path = file_path
        if isinstance(file_path, dict):
            actual_path = file_path.get('path', '') # Extract path if it's a dict
            print(f"[MainPlayer] Warning: _load_and_play_path received dict, extracted path: {actual_path}")

        if not actual_path or not os.path.exists(actual_path):
            # Display the extracted path in the error message
            error_display_path = actual_path if actual_path else "(Empty Path)"
            self._show_error(f"Media file not found: {error_display_path}")
            # --- NEW: If load fails, ensure timeline and clipping manager know there's effectively no *new* media ---
            # This assumes current_media_path might have been optimistically set before this check.
            # If _load_and_play_path is only called with confirmed paths, this might be redundant.
            # However, it's safer to ensure state is consistent if an error occurs mid-load.
            if self.current_media_path != actual_path or not actual_path: # If intended path failed
                self.player_widget.timeline.set_current_media_path(None) # Or previous valid path if applicable
                self.clipping_manager.set_media("")
            # -------------------------------------------------------------------------------------------------
            if self._playback_mode == 'playlist':
                # If loading fails in playlist mode, try to advance
                self.play_next_track(force_advance=True)
            return # Exit early on error
            
        # Use the extracted actual_path from now on
        self.current_media_path = actual_path
        print(f"[MainPlayer] Backend loading: {actual_path}")
        
        # --- NEW: Notify PlayerTimeline and ClippingManager about new media path BEFORE loading ---
        self.player_widget.timeline.set_current_media_path(self.current_media_path)
        self.clipping_manager.set_media(self.current_media_path)
        # ------------------------------------------------------------------------------------
        
        # Always set the app state to playing BEFORE loading media for responsive UI
        self._set_app_state(STATE_PLAYING)
        
        # Load the media (this will trigger on_media_changed but won't start playback)
        load_successful = self.backend.load_media(actual_path)

        if load_successful:
            # Explicitly start playback after media is loaded
            self.backend.play()
        else:
            print("[MainPlayer] Backend load_media failed, playback not started.")
            self._set_app_state(STATE_PAUSED) # Revert to paused if load failed

    def play_next_track(self, force_advance=False):
        """
        Plays the next track in the playlist based on the current state and repeat mode.
        Args:
            force_advance (bool): If True, forces advancing even if logic might otherwise prevent it.
                                 (Currently unused in this method's logic but added for compatibility)
        """
        print(f"[MainPlayer] play_next_track called (force_advance={force_advance})")
        if self._playback_mode == 'playlist' and self._current_playlist:
            # Get the next file path directly
            next_track_path = self._current_playlist.get_next_file()
            # --- DEBUG --- 
            # print(f"[MainPlayer] play_next_track: Received next_track_path: {repr(next_track_path)}")
            # ------------- 

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
            # Get the previous file path directly
            prev_track_path = self._current_playlist.get_previous_file()
            # --- DEBUG --- 
            # print(f"[MainPlayer] play_previous_track: Received prev_track_path: {repr(prev_track_path)}")
            # ------------- 

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
        
        # Add the specific track to recently played
        self.recently_played_model.add_item(item_type='file', name=os.path.basename(filepath), path=filepath)
        
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
        
        # Add to recently played BEFORE loading
        self.recently_played_model.add_item(item_type='file', name=os.path.basename(filepath), path=filepath)
        
        # Load and play the track
        self._load_and_play_path(filepath)
        self.setFocus() # Ensure player retains focus

    def increase_volume(self, amount=5):
        """Increase volume by a specified amount (default 5%)."""
        # Use player_widget.volume_control to get volume, respecting the control's range
        if hasattr(self.player_widget, 'volume_control') and hasattr(self.player_widget.volume_control, 'get_volume'):
            volume = self.player_widget.volume_control.get_volume()
            # Ensure the range matches the volume control's capability (assuming 0-200 based on hotkey handler)
            new_volume = min(volume + amount, 200) 
            self.set_volume(new_volume)
        else:
            print("[MainPlayer] Warning: Could not access volume control to increase volume.")
            
    def decrease_volume(self, amount=5):
        """Decrease volume by a specified amount (default 5%)."""
        if hasattr(self.player_widget, 'volume_control') and hasattr(self.player_widget.volume_control, 'get_volume'):
            volume = self.player_widget.volume_control.get_volume()
            new_volume = max(volume - amount, 0)
            self.set_volume(new_volume)
        else:
            print("[MainPlayer] Warning: Could not access volume control to decrease volume.")
            
    def wheelEvent(self, event):
        """Handle mouse wheel events for volume control."""
        delta = event.angleDelta().y()
        if delta > 0:  # Wheel up
            self.increase_volume()
            event.accept()
        elif delta < 0:  # Wheel down
            self.decrease_volume()
            event.accept()
        else:
            super().wheelEvent(event) # Pass event up if not handled

    def set_video_widget(self, widget: VideoWidget): # <-- NEW METHOD (Use VideoWidget type)
        """
        Sets the VideoWidget to be used for video output.

        Args:
            widget (VideoWidget): The widget where video should be rendered.
        """
        print(f"[MainPlayer] Setting video output widget: {widget}")
        self._video_widget = widget
        self._set_vlc_window_handle(widget) # Use helper to set the handle

        # --- Instantiate and connect FullScreenManager ---
        if self._video_widget:
            # If a previous manager exists, clean it up
            if self.full_screen_manager:
                self.full_screen_manager.cleanup()
            
            self.full_screen_manager = FullScreenManager(
                video_widget=self._video_widget, 
                main_player=self, 
                parent=self # QObject parent for auto-cleanup if MainPlayer is deleted
            )
            if hasattr(self._video_widget, 'fullScreenRequested'):
                self._video_widget.fullScreenRequested.connect(self._handle_full_screen_request)
            else:
                print("[MainPlayer] Warning: VideoWidget does not have fullScreenRequested signal.")
            # --- Connect to FullScreenManager's exit_requested_via_escape signal ---
            if hasattr(self.full_screen_manager, 'exit_requested_via_escape'):
                self.full_screen_manager.exit_requested_via_escape.connect(self._handle_exit_request_from_escape)
            else:
                print("[MainPlayer] Warning: FullScreenManager does not have exit_requested_via_escape signal.")
            # --- Connect to FullScreenManager's did_exit_full_screen signal ---
            if hasattr(self.full_screen_manager, 'did_exit_full_screen'):
                self.full_screen_manager.did_exit_full_screen.connect(self._sync_player_page_display)
            else:
                print("[MainPlayer] Warning: FullScreenManager does not have did_exit_full_screen signal.")
            # -------------------------------------------------------------------
        # -------------------------------------------------

    def _set_vlc_window_handle(self, widget: Optional[VideoWidget]):
        """Internal helper to set the VLC window handle via the backend."""
        if not widget:
            print("[MainPlayer] Clearing VLC window handle via backend.")
            # Call backend method with None to detach
            if self.backend:
                self.backend.set_video_output(None)
            return

        # Call the backend's method to set the handle
        if self.backend and hasattr(self.backend, 'set_video_output'):
            try:
                win_id_int = int(widget.winId())
                print(f"[MainPlayer] Setting VLC window handle via backend: {win_id_int}")
                # Call the backend's setter method
                self.backend.set_video_output(win_id_int)
            except Exception as e:
                print(f"[MainPlayer] Error getting winId or calling backend.set_video_output: {e}")
        else:
            print("[MainPlayer] Warning: Backend not available or missing set_video_output method.")

    # --- Add Stop Method --- 
    def stop(self):
        """Stop playback immediately."""
        print("[MainPlayer] stop() method called. Calling backend.stop()")
        # Set internal state first?
        # self._set_app_state(STATE_STOPPED) # If we add a stopped state
        # Or just let backend state signal handle it?
        # For now, just delegate and rely on backend signal if state needs update.
        self.backend._loading_media=True # This seems like an internal flag for VLCBackend
        self.backend.media_player.stop() # Direct call to VLC instance player

        # --- NEW: When stopping, clear media context for timeline and clipping ---
        # This effectively signals that no media is active for clipping.
        self.current_media_path = None # Explicitly clear path
        self.player_widget.timeline.set_current_media_path(None)
        self.clipping_manager.set_media("") # Pass empty string to denote no media
        # Optionally, reset timeline display if desired (e.g., clear duration/position labels)
        self.player_widget.timeline.set_duration(0)
        self.player_widget.timeline.set_position(0)
        self.player_widget.update_track_info("No Media", "", "", None)
        self._set_app_state(STATE_PAUSED) # Or a new STATE_STOPPED if defined
        # -----------------------------------------------------------------------
    # -----------------------

    # --- Add methods for subtitle control ---
    def get_subtitle_tracks(self):
        """
        Get a list of available subtitle tracks.
        
        Returns:
            list: List of dicts with id and name of each subtitle track
        """
        return self.backend.get_subtitle_tracks()
        
    def enable_subtitles(self, track_id=0):
        """
        Enable subtitles at the specified track ID.
        
        Args:
            track_id (int): The subtitle track ID to enable (default: 0)
            
        Returns:
            bool: True if successful, False otherwise
        """
        return self.backend.enable_subtitles(track_id)
        
    def disable_subtitles(self):
        """
        Disable subtitles.
        
        Returns:
            bool: True if successful, False otherwise
        """
        return self.backend.disable_subtitles()
        
    def has_subtitle_tracks(self):
        """
        Check if the current media has any subtitle tracks.
        
        Returns:
            bool: True if subtitle tracks are available, False otherwise
        """
        return self.backend.has_subtitle_tracks()
    # ------------------------------------

    def _select_subtitle_track(self, track_id):
        """
        Select a specific subtitle track by ID.
        
        Args:
            track_id (int): ID of the subtitle track to select, or -1 to disable subtitles
        """
        if not self._is_current_media_video:
            return
            
        if track_id < 0:
            # Disable subtitles
            if self.backend.disable_subtitles():
                self._subtitle_enabled = False
                print("[MainPlayer] Subtitles disabled via menu selection")
                self._update_subtitle_controls()
            return
            
        # Find the track with the given ID
        selected_track = None
        for track in self._subtitle_tracks:
            if track['id'] == track_id:
                selected_track = track
                break
                
        if selected_track:
            # Enable the selected track
            if self.backend.enable_subtitles(track_id):
                self._subtitle_enabled = True
                self._current_subtitle_track = track_id
                
                # Get the track name for language code extraction
                track_name = selected_track.get('display_name', selected_track['name'])
                
                # Update language code
                self._current_subtitle_language = selected_track.get('language') or self._extract_language_code(track_name)
                
                print(f"[MainPlayer] Selected subtitle track: {track_id} ({track_name})")
                
                # Update UI
                self._update_subtitle_controls()

    # --- Add slot for full screen request ---
    @pyqtSlot()
    def _handle_full_screen_request(self):
        """Handles the request to toggle full-screen mode."""
        if self.full_screen_manager:
            print("[MainPlayer] Toggling full screen via FullScreenManager.")
            self.full_screen_manager.toggle_full_screen()
            # --- Sync player page display after toggle ---
            # if not self.full_screen_manager.is_full_screen: # If exited full screen # REMOVED - Handled by did_exit_full_screen signal
            #     self._sync_player_page_display()
            # --------------------------------------------
        else:
            print("[MainPlayer] Warning: FullScreenManager not initialized. Cannot toggle full screen.")
    # --------------------------------------

    # --- Add method to be called by HotkeyHandler for F12 ---
    def request_toggle_full_screen(self):
        """Public method to request toggling full-screen mode, typically called by HotkeyHandler."""
        if self.full_screen_manager:
            print("[MainPlayer] F12 pressed, toggling full screen via FullScreenManager.")
            self.full_screen_manager.toggle_full_screen()
            # --- Sync player page display after toggle ---
            # if not self.full_screen_manager.is_full_screen: # If exited full screen # REMOVED - Handled by did_exit_full_screen signal
            #     self._sync_player_page_display()
            # --------------------------------------------
        else:
            print("[MainPlayer] Warning: FullScreenManager not initialized. F12 action ignored.")
    # ------------------------------------------------------

    # --- Add new slot for ESC exit from FullScreenManager ---
    @pyqtSlot()
    def _handle_exit_request_from_escape(self):
        """Handles the explicit exit request from FullScreenManager (due to ESC)."""
        if self.full_screen_manager and self.full_screen_manager.is_full_screen:
            print("[MainPlayer] ESC pressed in full screen, triggering manager to exit.")
            self.full_screen_manager.exit_full_screen() # Manager handles the exit mechanics and will emit did_exit_full_screen
            # self._sync_player_page_display() # MainPlayer syncs its own UI view # REMOVED - Handled by did_exit_full_screen signal
        else:
            print("[MainPlayer] Warning: FullScreenManager not init or not in full screen for ESC exit.")
    # ---------------------------------------------------------

    # --- Add method to synchronize PlayerPage display state ---
    def _sync_player_page_display(self):
        """Ensures the PlayerPage displays the correct view (video or album art)."""
        print(f"[MainPlayer._sync_player_page_display] Called. Current media is video: {self._is_current_media_video}")
        if not self._player_page_ref: # Check if player_page_ref is set
            # Try to find PlayerPage if not set (e.g., if MainPlayer is child of Dashboard)
            # This is a fallback, ideally _player_page_ref is set explicitly.
            parent_widget = self.parentWidget()
            while parent_widget:
                if hasattr(parent_widget, 'player_page') and isinstance(parent_widget.player_page, PlayerPage):
                    self._player_page_ref = parent_widget.player_page
                    break
                parent_widget = parent_widget.parentWidget()

        if self._player_page_ref and hasattr(self._player_page_ref, 'show_video_view') and hasattr(self._player_page_ref, 'show_album_art_view'):
            if self._is_current_media_video:
                print("[MainPlayer] Syncing PlayerPage to show video view.")
                self._player_page_ref.show_video_view()
            else:
                print("[MainPlayer] Syncing PlayerPage to show album art view.")
                self._player_page_ref.show_album_art_view()
        else:
            print("[MainPlayer] Warning: _player_page_ref not set or PlayerPage missing view methods. Cannot sync display.")
    # ---------------------------------------------------------

    # --- Method for PlayerPage to register itself (optional, alternative to parent search) ---
    def register_player_page(self, player_page: PlayerPage):
        """Allows PlayerPage to register itself with MainPlayer."""
        self._player_page_ref = player_page
        print("[MainPlayer] PlayerPage registered.")
    # ------------------------------------------------------------------------------------