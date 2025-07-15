"""
Main player module that integrates the UI components with the VLC backend.
"""
import os
import sys # <-- Add sys import for platform check
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QFileDialog
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer
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

# --- Add Position Manager import ---
from music_player.models.position_manager import PlaybackPositionManager
# --------------------------------

# --- Add New Manager Imports ---
from music_player.models.subtitle_manager import SubtitleManager
from music_player.models.media_manager import MediaManager
from music_player.models.audio_manager import AudioManager
# ------------------------------

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
        
        # Playback Mode State
        self._playback_mode = 'single'  # 'single' or 'playlist'
        # Use string literal for type hint
        self._current_playlist: Optional['Playlist'] = None
        
        # --- Add FullScreenManager instance attribute ---
        self.full_screen_manager: Optional[FullScreenManager] = None
        # --- Add PlayerPage reference attribute ---
        self._player_page_ref: Optional[PlayerPage] = None
        # ----------------------------------------
        
        # --- Add Position Manager instance attribute ---
        self.position_manager = PlaybackPositionManager.instance()
        # --------------------------------------------
        
        # --- Add Subtitle Manager instance ---
        self.subtitle_manager = SubtitleManager()
        # ----------------------------------
        
        # --- Add Audio Manager instance ---
        self.audio_manager = AudioManager()
        # --------------------------------
        
        # --- Add Periodic Position Save Timer (Phase 3) ---
        self.position_save_timer = QTimer(self)
        self.position_save_timer.setInterval(10000)  # 10 seconds
        self.position_save_timer.timeout.connect(self._periodic_position_save)
        self.position_dirty = False  # Flag to track if position needs saving
        self.last_saved_position = 0  # Track last saved position to avoid redundant saves
        # ------------------------------------------------
        
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
        
        # Connect audio control signals
        self.player_widget.audio_track_selected.connect(self._select_audio_track)
        
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
        
        # --- Connect ClippingManager signals for post-clipping behavior ---
        self.clipping_manager.clip_successful.connect(self._on_clip_successful)
        self.clipping_manager.clip_failed.connect(self._on_clip_failed)
        # -----------------------------------------------------------------

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
        
    # --- Clipping Signal Handlers for Post-Clipping Behavior ---
    def _on_clip_successful(self, original_path: str, clipped_path: str):
        """
        Handle successful clipping operation with automatic mode switch and playback.
        
        Args:
            original_path (str): Path to the original media file that was clipped
            clipped_path (str): Path to the newly created clipped file
        """
        print(f"[MainPlayer] Clipping successful: '{original_path}' -> '{clipped_path}'")
        
        # Mode Switch: Set to single mode regardless of previous mode
        if self._playback_mode != 'single':
            print(f"[MainPlayer] Switching from {self._playback_mode} mode to single mode")
            self._playback_mode = 'single'
            self.playback_mode_changed.emit('single')
        
        # Clear Playlist Reference: Ensure clean single mode
        self._current_playlist = None
        
        # Update Current Path: Set to the new clipped file
        self.current_media_path = clipped_path
        
        # Update UI: Disable playlist controls for single mode
        self.player_widget.set_next_prev_enabled(False)
        
        # Clear Clipping State: Reset all markers and segments
        self.clipping_manager.clear_all_segments()
        
        # Notify timeline and clipping manager about the new media
        self.player_widget.timeline.set_current_media_path(self.current_media_path)
        self.clipping_manager.set_media(self.current_media_path)
        
        # Load New Media: Load the clipped file
        print(f"[MainPlayer] Loading clipped file: {clipped_path}")
        load_successful = self.backend.load_media(clipped_path)
        
        if load_successful:
            # Set state to playing for immediate playback
            self._set_app_state(STATE_PLAYING)
            
            # Start Playback: Start immediately from beginning
            self.backend.play()
            
            print("[MainPlayer] Post-clipping playback started successfully")
        else:
            print("[MainPlayer] Failed to load clipped file")
            self._show_error(f"Failed to load the clipped file: {clipped_path}")
        
        # Focus Management: Ensure hotkey functionality
        self.setFocus()
        
        # Add to recently played
        self.recently_played_model.add_item(item_type='file', name=os.path.basename(clipped_path), path=clipped_path)
        
    def _on_clip_failed(self, original_path: str, error_message: str):
        """
        Handle failed clipping operation with error display and state preservation.
        
        Args:
            original_path (str): Path to the original media file that failed to clip
            error_message (str): Error message describing the failure
        """
        print(f"[MainPlayer] Clipping failed for '{original_path}': {error_message}")
        
        # Error Display: Show error message to user
        QMessageBox.critical(self, "Clipping Failed", 
                           f"Failed to create clip from:\n{os.path.basename(original_path)}\n\nError: {error_message}")
        
        # State Preservation: Maintain current playback mode and loaded media
        # No changes to current state - user can continue working with original media
        
        # Focus Restoration: Restore hotkey functionality after error dialog
        self.setFocus()
        
        print("[MainPlayer] Clipping failure handled, original media state preserved")
    # -------------------------------------------------------------------
        
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
                # Use the existing method that properly handles unified loading
                self._load_and_play_path(next_track_path)
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
        
        # --- Manage Periodic Save Timer (Phase 3) ---
        if hasattr(self, 'position_save_timer'):
            if state == STATE_PLAYING:
                if not self.position_save_timer.isActive():
                    self.position_save_timer.start()
                    print("[MainPlayer] Started periodic position save timer")
            else:
                if self.position_save_timer.isActive():
                    self.position_save_timer.stop()
                    print(f"[MainPlayer] Stopped periodic position save timer (state: {state})")
        # ------------------------------------------
        
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
        
        # --- NEW: Save position 0 when media ends naturally (for repeat functionality) ---
        if self.current_media_path:
            current_duration = self.backend.get_duration()
            current_rate = self.backend.get_rate()
            
            subtitle_enabled, subtitle_track_id, subtitle_language = False, -1, ''
            if self._is_current_media_video:
                subtitle_enabled, subtitle_track_id, subtitle_language = self._get_current_subtitle_state()
            
            audio_track_id = self._get_current_audio_state()

            print(f"[MainPlayer] Saving position 0 for completed media: {os.path.basename(self.current_media_path)}")
            self.position_manager.save_position(self.current_media_path, 0, current_duration, current_rate,
                                                  subtitle_enabled, subtitle_track_id, subtitle_language,
                                                  audio_track_id)
        # ----------------------------------------------------------------------------------
        
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
        Always performs immediate seeking to VLC backend for accurate frame display,
        especially important for clipping marker placement accuracy.
        
        Args:
            position_ms (int): New position in milliseconds
        """
        # For accurate clipping, we always seek immediately regardless of play state
        if not self.current_media_path:
            print("[MainPlayer] No media loaded, cannot seek")
            return
        
        # Different behavior based on current app state
        if self.app_state == STATE_ENDED:
            # For ended state: Reset to paused and seek
            self.app_state = STATE_PAUSED
            self.player_widget.set_playing_state(False)
            self.playback_state_changed.emit(STATE_PAUSED)
            
        # Always perform immediate seeking for frame-accurate positioning
        # Set blocking flag to prevent position update loop
        self.block_position_updates = True
        seek_successful = False
        try:
            # Perform the seek operation
            seek_successful = self.backend.seek(position_ms)
            
            # If we're in playing state, ensure playback continues
            if self.app_state == STATE_PLAYING and not self.backend.is_playing:
                self.backend.play()
                
        finally:
            # Always unblock updates when done
            self.block_position_updates = False
            
        # Update UI timeline immediately after seek
        if seek_successful:
            self.player_widget.timeline.set_position(position_ms)
        else:
            print(f"[MainPlayer] Seek to {position_ms}ms failed")
            # Keep the UI in sync even if seek failed
            self.player_widget.timeline.set_position(position_ms)
        
    def play(self):
        """Start or resume playback"""
        # Since we now always seek immediately, no need for deferred position handling
        
        # Handle different app states
        if self.app_state == STATE_ENDED:
            # Need to reload media and start playback
            if self.current_media_path:
                # For ended state, just seek to beginning and play instead of reloading
                # This avoids unnecessary media reload and potential path normalization issues
                print(f"[MainPlayer] Restarting from ended state: {self.current_media_path}")
                self._set_app_state(STATE_PLAYING)
                
                # Seek to beginning and play
                self.backend.seek(0)
                result = self.backend.play()
            else:
                # No current media path to reload
                result = False
        else:
            # For paused or other states, just resume playback
            # Set UI state immediately for responsive UI
            if self.app_state == STATE_PAUSED:
                self._set_app_state(STATE_PLAYING)
            
            # Resume playback
            result = self.backend.play()
            
        return result
        
    def pause(self):
        """Pause playback"""
        # --- NEW: Save position and subtitle state when user manually pauses ---
        if self.current_media_path and self.backend.get_current_position():
            current_pos = self.backend.get_current_position()
            current_duration = self.backend.get_duration()
            current_rate = self.backend.get_rate()
            
            subtitle_enabled, subtitle_track_id, subtitle_language = False, -1, ''
            if self._is_current_media_video:
                subtitle_enabled, subtitle_track_id, subtitle_language = self._get_current_subtitle_state()
            
            audio_track_id = self._get_current_audio_state()

            # Use PositionManager to handle the business logic
            success, saved_position = self.position_manager.handle_manual_action_save(
                self.current_media_path, current_pos, current_duration, current_rate, "pause",
                subtitle_enabled, subtitle_track_id, subtitle_language, audio_track_id
            )
            if success:
                self.last_saved_position = saved_position
        # --------------------------------------------------------------------
        
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
        
        # --- Stop periodic save timer ---
        if hasattr(self, 'position_save_timer'):
            self.position_save_timer.stop()
        # ------------------------------
        
        # --- Call FullScreenManager cleanup ---
        if self.full_screen_manager:
            self.full_screen_manager.cleanup()
        # -------------------------------------
        
        # Stop playback and clean up
        self.backend.stop()
        
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
        
        # --- NEW: Save position and rate when rate changes ---
        if self.current_media_path and self.backend.get_current_position():
            current_pos = self.backend.get_current_position()
            current_duration = self.backend.get_duration()
            
            subtitle_enabled, subtitle_track_id, subtitle_language = False, -1, ''
            if self._is_current_media_video:
                subtitle_enabled, subtitle_track_id, subtitle_language = self._get_current_subtitle_state()
            
            audio_track_id = self._get_current_audio_state()

            print(f"[MainPlayer] Saving position {current_pos}ms at new rate {rate}x due to rate change")
            self.position_manager.save_position(self.current_media_path, current_pos, current_duration, rate,
                                                  subtitle_enabled, subtitle_track_id, subtitle_language,
                                                  audio_track_id)
            self.last_saved_position = current_pos
        # ----------------------------------------------------------------
        
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
    
    def load_media_unified(self, filepath: str, source_context: str = "unknown"):
        """
        Unified method for loading media files with comprehensive handling.
        This method ensures consistent behavior for position restoration, video widget state,
        and playback regardless of where the request originated.
        
        Args:
            filepath (str): The absolute path of the file to load
            source_context (str): Context of where the request came from (for logging)
        
        Returns:
            bool: True if loading was successful, False otherwise
        """
        print(f"[MainPlayer] Unified media loading from {source_context}: {filepath}")
        
        try:
            # Validate the file path
            if not filepath or not os.path.exists(filepath):
                print(f"[MainPlayer] Error: File does not exist: {filepath}")
                return False
            
            # Set mode to single and clear playlist reference
            self.set_playback_mode('single')
            self._current_playlist = None
            
            # Store video widget state for potential restoration
            video_widget_was_hidden = False
            if hasattr(self, '_video_widget') and self._video_widget:
                video_widget_was_hidden = not self._video_widget.isVisible()
                # Temporarily hide video widget to prevent flicker during loading
                self._video_widget.setVisible(False)
            
            # Add to recently played BEFORE loading (in case loading fails)
            try:
                self.recently_played_model.add_item(
                    item_type='file', 
                    name=os.path.basename(filepath), 
                    path=filepath
                )
            except Exception as e:
                print(f"[MainPlayer] Warning: Could not add to recently played: {e}")
            
            # Save current position before loading new media if different file
            if (self.current_media_path and 
                not MediaManager.compare_media_paths(self.current_media_path, filepath)):
                try:
                    current_pos = self.backend.get_current_position()
                    current_duration = self.backend.get_duration()
                    current_rate = self.backend.get_rate()
                    
                    if current_pos and current_duration:
                        subtitle_enabled, subtitle_track_id, subtitle_language = False, -1, ''
                        if self._is_current_media_video:
                            subtitle_enabled, subtitle_track_id, subtitle_language = self._get_current_subtitle_state()
                        
                        audio_track_id = self._get_current_audio_state()

                        success, saved_position = self.position_manager.handle_position_on_media_change(
                            self.current_media_path, filepath, current_pos, current_duration, current_rate,
                            subtitle_enabled, subtitle_track_id, subtitle_language, audio_track_id
                        )
                        if success:
                            self.last_saved_position = saved_position
                            print(f"[MainPlayer] Saved position {saved_position}ms at {current_rate}x for previous media")
                except Exception as e:
                    print(f"[MainPlayer] Warning: Could not save previous position: {e}")
            
            # Use MediaManager to validate and prepare the media file
            success, actual_path, file_info = MediaManager.prepare_media_for_loading(filepath)
            
            if not success:
                error_msg = file_info.get('error', f"Failed to prepare media: {actual_path}")
                print(f"[MainPlayer] Media preparation failed: {error_msg}")
                
                # Restore video widget state on error
                if hasattr(self, '_video_widget') and self._video_widget and not video_widget_was_hidden:
                    self._video_widget.setVisible(True)
                
                return False
            
            # Log any warnings from MediaManager
            if 'warning' in file_info:
                print(f"[MainPlayer] Warning from MediaManager: {file_info['warning']}")
            
            # Update current media path
            self.current_media_path = actual_path
            print(f"[MainPlayer] Media path set to: {actual_path}")
            
            # Notify timeline and clipping manager about new media
            self.player_widget.timeline.set_current_media_path(self.current_media_path)
            self.clipping_manager.set_media(self.current_media_path)
            
            # Set app state to playing for responsive UI
            self._set_app_state(STATE_PLAYING)
            
            # Load the media through backend
            load_successful = self.backend.load_media(actual_path)
            
            if load_successful:
                # Start playback
                self.backend.play()
                print(f"[MainPlayer] Successfully loaded and started playback from {source_context}")
                
                # The position and rate restoration will be handled automatically
                # in on_media_metadata_loaded when the backend signals media is ready
                
                # Ensure player has focus for hotkeys
                self.setFocus()
                
                return True
            else:
                print(f"[MainPlayer] Backend failed to load media: {actual_path}")
                self._set_app_state(STATE_PAUSED)
                
                # Restore video widget state on error  
                if hasattr(self, '_video_widget') and self._video_widget and not video_widget_was_hidden:
                    self._video_widget.setVisible(True)
                
                return False
                
        except Exception as e:
            print(f"[MainPlayer] Error in unified media loading: {e}")
            
            # Restore video widget state on error
            if hasattr(self, '_video_widget') and self._video_widget and not video_widget_was_hidden:
                self._video_widget.setVisible(True)
            
            return False
    
    def load_media(self):
        """Open a file dialog to select and load a SINGLE media file. Sets mode to 'single'."""
        # Store video widget state
        video_widget_was_hidden = False
        if hasattr(self, '_video_widget') and self._video_widget:
            video_widget_was_hidden = not self._video_widget.isVisible()
        self._video_widget.setVisible(False)

        last_dir = self.settings.get('player/last_directory', os.path.expanduser("~"), SettingType.STRING)
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Media File", last_dir,
            "Media Files (*.mp3 *.wav *.ogg *.flac *.aac *.m4a *.mp4 *.avi *.mkv *.mov *.webm *.m3u)"
        )
        
        if file_path:
            self.settings.set('player/last_directory', os.path.dirname(file_path), SettingType.STRING)
            
            # Use unified loading method
            success = self.load_media_unified(file_path, "file_dialog")
            
            if success:
                self.setFocus()
                return True
            else:
                # Restore video widget visibility if loading failed
                if hasattr(self, '_video_widget') and self._video_widget and not video_widget_was_hidden:
                    self._video_widget.setVisible(True)
                return False
        else:
            # Dialog was cancelled - restore video widget
            if hasattr(self, '_video_widget') and self._video_widget and not video_widget_was_hidden:
                self._video_widget.setVisible(True)
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
            self.subtitle_manager.reset_state()
            
            # Check if subtitles are available
            if self.backend.has_subtitle_tracks():
                print("[MainPlayer] Subtitles detected in video, processing tracks")
                
                # Get all tracks from backend
                backend_subtitle_tracks = self.backend.get_subtitle_tracks()
                print(f"[MainPlayer] Available subtitle tracks: {backend_subtitle_tracks}")
                
                # Process tracks using SubtitleManager to find best track
                suitable_track = self.subtitle_manager.process_subtitle_tracks(backend_subtitle_tracks)
                
                if suitable_track is not None:
                    print(f"[MainPlayer] Auto-enabling subtitle track {suitable_track['id']}")
                    if self.backend.enable_subtitles(suitable_track['id']):
                        # Update SubtitleManager state
                        self.subtitle_manager.update_subtitle_state(suitable_track['id'], True)
                        print(f"[MainPlayer] Successfully enabled subtitle track {suitable_track['id']}")
                    else:
                        print(f"[MainPlayer] Failed to enable subtitle track {suitable_track['id']}")
                else:
                    print("[MainPlayer] No suitable subtitle track found")
                        
                # Update subtitle controls in PlayerWidget
                self._update_subtitle_controls()
            else:
                # No subtitle tracks available for this video
                print("[MainPlayer] No subtitle tracks available for this video")
                # Update subtitle controls to hide them
                self._update_subtitle_controls()
        else:
            # Reset subtitle state for non-video files
            self.subtitle_manager.reset_state()
            self._update_subtitle_controls()
        # -------------------------------------------

        # --- NEW: Audio track handling ---
        self.audio_manager.reset_state()
        
        # Always get audio tracks to ensure at least one is active
        backend_audio_tracks = self.backend.get_audio_tracks()
        if backend_audio_tracks:
            # Process tracks to find the preferred one (or use the only one available)
            preferred_track = self.audio_manager.process_audio_tracks(backend_audio_tracks)
            
            if preferred_track:
                success = self.backend.set_audio_track(preferred_track['id'])
                if success:
                    self.audio_manager.update_audio_state(preferred_track['id'])
                    print(f"[MainPlayer] Set audio track to {preferred_track['id']} ({preferred_track.get('name', 'Unknown')})")
                else:
                    print(f"[MainPlayer] Failed to set audio track {preferred_track['id']}")
            else:
                # If no preferred track found but tracks exist, try to use the first valid track
                for track in backend_audio_tracks:
                    if track['id'] >= 0:  # Allow track 0, only skip truly disabled tracks (usually -1)
                        success = self.backend.set_audio_track(track['id'])
                        if success:
                            self.audio_manager.update_audio_state(track['id'])
                            print(f"[MainPlayer] Fallback: Set audio track to {track['id']} ({track.get('name', 'Unknown')})")
                            break
        else:
            print("[MainPlayer] No audio tracks available in media")

        self._update_audio_controls()
        # --- End Audio track handling ---

        # Update UI with track information
        self.player_widget.update_track_info(title, artist, album, artwork_path)
        self.setFocus()
        
        # --- NEW: Restore saved position, rate, and subtitle state if available ---
        if self.current_media_path:
            saved_position, saved_rate, saved_subtitle_enabled, saved_subtitle_track_id, saved_subtitle_language, saved_audio_track_id = self.position_manager.get_saved_position(self.current_media_path)
            if saved_position and self.backend.get_duration() > saved_position > 5000:
                print(f"[MainPlayer] Restoring saved position: {saved_position}ms at {saved_rate}x rate")
                # Use a small delay to ensure media is fully loaded before seeking, setting rate, and restoring subtitles
                QTimer.singleShot(100, lambda: self._restore_playback_state(
                    saved_position, saved_rate, saved_subtitle_enabled, saved_subtitle_track_id, saved_subtitle_language, saved_audio_track_id))
            elif saved_rate != 1.0 or saved_subtitle_enabled or saved_audio_track_id != -1:
                # Restore just the playback rate and/or subtitle state if no position to restore
                print(f"[MainPlayer] Restoring saved playback rate: {saved_rate}x and other settings")
                QTimer.singleShot(100, lambda: self._restore_settings(
                    saved_rate, saved_subtitle_enabled, saved_subtitle_track_id, saved_subtitle_language, saved_audio_track_id))
        # -------------------------------------------------------------------------
        
        # Emit the consolidated media_changed signal
        self.media_changed.emit(media, is_video)
        
    def _update_subtitle_controls(self):
        """Update the subtitle controls in the PlayerWidget using SubtitleManager state."""
        state_info = self.subtitle_manager.get_subtitle_state_info()
        self.player_widget.update_subtitle_state(
            state_info['has_subtitle_tracks'],
            state_info['subtitle_enabled'],
            state_info['current_subtitle_language'],
            state_info['subtitle_tracks']
        )
        
    def _restore_playback_state(self, position_ms: int, rate: float, 
                                           subtitle_enabled: bool, subtitle_track_id: int, subtitle_language: str,
                                           audio_track_id: int):
        """
        Helper method to restore position, playback rate, and subtitle state.
        
        Args:
            position_ms (int): Position to seek to in milliseconds
            rate (float): Playback rate to restore
            subtitle_enabled (bool): Whether subtitles should be enabled
            subtitle_track_id (int): ID of the subtitle track to restore
            subtitle_language (str): Language code of the subtitle track
            audio_track_id (int): ID of the audio track to restore
        """
        # First seek to the position
        self.backend.seek(position_ms)
        # Then restore other settings
        self._restore_settings(rate, subtitle_enabled, subtitle_track_id, subtitle_language, audio_track_id)
        
    def _restore_settings(self, rate: float, subtitle_enabled: bool, 
                                   subtitle_track_id: int, subtitle_language: str,
                                   audio_track_id: int):
        """
        Helper method to restore playback rate and subtitle state without seeking.
        
        Args:
            rate (float): Playback rate to restore
            subtitle_enabled (bool): Whether subtitles should be enabled
            subtitle_track_id (int): ID of the subtitle track to restore
            subtitle_language (str): Language code of the subtitle track
            audio_track_id (int): ID of the audio track to restore
        """
        # Set the playback rate
        self.backend.set_rate(rate)
        # Update UI to reflect the rate
        self.player_widget.set_rate(rate)
        # Restore subtitle state
        self._restore_subtitle_state(subtitle_enabled, subtitle_track_id, subtitle_language)
        # Restore audio track
        self._restore_audio_track_state(audio_track_id)
        
    def _restore_subtitle_state(self, subtitle_enabled: bool, subtitle_track_id: int, subtitle_language: str):
        """
        Helper method to restore subtitle state for video media.
        
        Args:
            subtitle_enabled (bool): Whether subtitles should be enabled
            subtitle_track_id (int): ID of the subtitle track to restore
            subtitle_language (str): Language code of the subtitle track
        """
        # Only restore subtitles for video media
        if not self._is_current_media_video or not subtitle_enabled:
            return
            
        # Check if the saved track still exists
        available_tracks = self.backend.get_subtitle_tracks() if self.backend.has_subtitle_tracks() else []
        
        # Try to find a matching track by ID or language
        matching_track = None
        for track in available_tracks:
            if track['id'] == subtitle_track_id:
                matching_track = track
                break
            # If no exact ID match, try to match by language as fallback
            elif subtitle_language and track.get('language', '').lower() == subtitle_language.lower():
                matching_track = track
        
        if matching_track:
            print(f"[MainPlayer] Restoring subtitle track {matching_track['id']} ({subtitle_language})")
            if self.backend.enable_subtitles(matching_track['id']):
                self.subtitle_manager.update_subtitle_state(matching_track['id'], True)
                self._update_subtitle_controls()
        else:
            print(f"[MainPlayer] Could not restore subtitle track {subtitle_track_id} ({subtitle_language}) - track not found")
    
    def _restore_audio_track_state(self, audio_track_id: int):
        """
        Helper method to restore audio track state.
        Falls back to default English track selection if saved track is not available.
        
        Args:
            audio_track_id (int): ID of the audio track to restore (-1 means no saved audio track)
        """
        available_tracks = self.backend.get_audio_tracks()
        
        if audio_track_id == -1 or not available_tracks:
            # No saved audio track or no tracks available - use default selection logic
            print(f"[MainPlayer] No saved audio track (ID: {audio_track_id}), using default selection")
            self._apply_default_audio_track_selection(available_tracks)
            return

        # Check if saved track still exists
        track_exists = any(track['id'] == audio_track_id for track in available_tracks)

        if track_exists:
            print(f"[MainPlayer] Restoring audio track {audio_track_id}")
            if self.backend.set_audio_track(audio_track_id):
                self.audio_manager.update_audio_state(audio_track_id)
                self._update_audio_controls()
            else:
                print(f"[MainPlayer] Failed to set saved audio track {audio_track_id}, falling back to default")
                self._apply_default_audio_track_selection(available_tracks)
        else:
            print(f"[MainPlayer] Saved audio track {audio_track_id} not found, falling back to default")
            self._apply_default_audio_track_selection(available_tracks)
    
    def _apply_default_audio_track_selection(self, available_tracks):
        """
        Apply default audio track selection logic (prefer English tracks).
        
        Args:
            available_tracks (list): List of available audio tracks
        """
        if not available_tracks:
            return
            
        # Use audio manager's logic to find the best track
        preferred_track = self.audio_manager.process_audio_tracks(available_tracks)
        
        if preferred_track:
            success = self.backend.set_audio_track(preferred_track['id'])
            if success:
                self.audio_manager.update_audio_state(preferred_track['id'])
                self._update_audio_controls()
                print(f"[MainPlayer] Applied default audio track: {preferred_track['id']} ({preferred_track.get('name', 'Unknown')})")
            else:
                print(f"[MainPlayer] Failed to set default audio track {preferred_track['id']}")
        else:
            # Fallback: try to use the first non-disabled track
            for track in available_tracks:
                if track['id'] >= 0:
                    success = self.backend.set_audio_track(track['id'])
                    if success:
                        self.audio_manager.update_audio_state(track['id'])
                        self._update_audio_controls()
                        print(f"[MainPlayer] Applied fallback audio track: {track['id']} ({track.get('name', 'Unknown')})")
                        break

    def _get_current_subtitle_state(self) -> tuple[bool, int, str]:
        """
        Get the current subtitle state for saving.
        
        Returns:
            tuple[bool, int, str]: (subtitle_enabled, subtitle_track_id, subtitle_language)
        """
        if not self._is_current_media_video:
            print(f"[MainPlayer._get_current_subtitle_state] Not video media, returning False, -1, ''")
            return False, -1, ''
        
        state_info = self.subtitle_manager.get_subtitle_state_info()
        result = (
            state_info.get('subtitle_enabled', False),
            self.subtitle_manager.current_subtitle_track,
            state_info.get('current_subtitle_language', '')
        )
        print(f"[MainPlayer._get_current_subtitle_state] Returning: {result}")
        print(f"[MainPlayer._get_current_subtitle_state] State info: {state_info}")
        return result
    
    def _get_current_audio_state(self) -> int:
        """
        Get the current audio track ID for saving.
        
        Returns:
            int: Current audio track ID
        """
        if not self.audio_manager.has_multiple_audio_tracks:
            return -1
        return self.audio_manager.current_audio_track

    def _restore_position_and_rate(self, position_ms: int, rate: float):
        """
        Legacy helper method - kept for backward compatibility.
        
        Args:
            position_ms (int): Position to seek to in milliseconds
            rate (float): Playback rate to restore
        """
        # Delegate to the new comprehensive method with no subtitle restoration
        self._restore_playback_state(position_ms, rate, False, -1, '', -1)
        
    def _toggle_subtitles(self):
        """Toggle subtitles on/off."""
        # Get current state from SubtitleManager
        state_info = self.subtitle_manager.get_subtitle_state_info()
        
        if not self._is_current_media_video or not state_info['has_subtitle_tracks']:
            return
            
        if state_info['subtitle_enabled']:
            # Disable subtitles
            if self.backend.disable_subtitles():
                self.subtitle_manager.update_subtitle_state(-1, False)
                print("[MainPlayer] Subtitles disabled")
        else:
            # Enable subtitles - get the next suitable track from SubtitleManager
            next_track = self.subtitle_manager.get_next_subtitle_track()
            if next_track and next_track['id'] >= 0:
                if self.backend.enable_subtitles(next_track['id']):
                    self.subtitle_manager.update_subtitle_state(next_track['id'], True)
                    print(f"[MainPlayer] Enabled subtitle track: {next_track['id']}")
            
        # Update UI
        self._update_subtitle_controls()
        
    def _cycle_subtitle_track(self):
        """Cycle to the next available subtitle track."""
        # Get current state from SubtitleManager
        state_info = self.subtitle_manager.get_subtitle_state_info()
        
        if not self._is_current_media_video or not state_info['has_subtitle_tracks']:
            return
            
        if not state_info['subtitle_tracks']:
            return
            
        # Get the next track from SubtitleManager
        next_track = self.subtitle_manager.get_next_subtitle_track()
            
        # Enable the new track if found
        if next_track:
            track_id = next_track['id']
            if self.backend.enable_subtitles(track_id):
                self.subtitle_manager.update_subtitle_state(track_id, True)
                track_name = next_track.get('display_name', next_track['name'])
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
        Internal helper that loads media and starts playback.
        Used by playlist navigation and other internal operations.
        
        Args:
            file_path (str): The absolute path to the media file.
        """
        print(f"[MainPlayer] Loading and playing path: {file_path}")
        self.load_media_unified(file_path, "internal_playlist_navigation")

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

        # Step 2c & 2d: Use unified loading system for consistent behavior
        print(f"[MainPlayer] Loading and playing selected track via unified system: {filepath}")
        # Set playback mode back to playlist after unified loading (which sets it to single)
        success = self.load_media_unified(filepath, "playlist_track_selection")
        if success:
            # Restore playlist mode since unified loading sets it to single
            self.set_playback_mode('playlist')
            self._current_playlist = current_ui_playlist
            print(f"[MainPlayer] Restored playlist mode after unified loading")
        
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
        
        # --- Set main player reference for drag and drop ---
        widget.set_main_player(self)
        # --------------------------------------------------
        
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
        
        # --- NEW: Save position and subtitle state when user manually stops ---
        if self.current_media_path and self.backend.get_current_position():
            current_pos = self.backend.get_current_position()
            current_duration = self.backend.get_duration()
            current_rate = self.backend.get_rate()
            
            subtitle_enabled, subtitle_track_id, subtitle_language = False, -1, ''
            if self._is_current_media_video:
                subtitle_enabled, subtitle_track_id, subtitle_language = self._get_current_subtitle_state()

            audio_track_id = self._get_current_audio_state()

            # Use PositionManager to handle the business logic
            success, saved_position = self.position_manager.handle_manual_action_save(
                self.current_media_path, current_pos, current_duration, current_rate, "stop",
                subtitle_enabled, subtitle_track_id, subtitle_language, audio_track_id
            )
            if success:
                self.last_saved_position = saved_position
        # -------------------------------------------------------------------
        
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
        
        # --- NEW: Reset subtitle state when stopping ---
        self.subtitle_manager.reset_state()
        self._update_subtitle_controls()
        # --------------------------------------------
        
        # --- NEW: Reset audio state when stopping ---
        self.audio_manager.reset_state()
        self._update_audio_controls()
        # --------------------------------------------

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
                self.subtitle_manager.update_subtitle_state(-1, False)
                print("[MainPlayer] Subtitles disabled via menu selection")
                self._update_subtitle_controls()
            return
            
        # Use SubtitleManager to find the track by ID
        selected_track = self.subtitle_manager.select_track_by_id(track_id)
        
        if selected_track and selected_track.get('action') != 'disable':
            # Enable the selected track
            if self.backend.enable_subtitles(track_id):
                self.subtitle_manager.update_subtitle_state(track_id, True)
                track_name = selected_track.get('display_name', selected_track['name'])
                print(f"[MainPlayer] Selected subtitle track: {track_id} ({track_name})")
                
                # Update UI
                self._update_subtitle_controls()

    def _select_audio_track(self, track_id: int):
        """
        Select a specific audio track by ID.
        
        Args:
            track_id (int): ID of the audio track to select.
        """
        if self.backend.set_audio_track(track_id):
            self.audio_manager.update_audio_state(track_id)
            self._update_audio_controls()
            print(f"[MainPlayer] Selected audio track: {track_id}")

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
            
            # --- NEW: Re-set the window handle after restoring the view, regardless of media type ---
            if self._video_widget:
                print("[MainPlayer] Re-setting VLC window handle after exiting full screen.")
                # Use a small delay to ensure the widget has been fully reparented and has a valid winId
                QTimer.singleShot(50, lambda: self._set_vlc_window_handle(self._video_widget))
            # -----------------------------------------------------------
        else:
            print("[MainPlayer] Warning: _player_page_ref not set or PlayerPage missing view methods. Cannot sync display.")
    # ---------------------------------------------------------

    # --- Method for PlayerPage to register itself (optional, alternative to parent search) ---
    def register_player_page(self, player_page: PlayerPage):
        """Allows PlayerPage to register itself with MainPlayer."""
        self._player_page_ref = player_page
        print("[MainPlayer] PlayerPage registered.")
    # ------------------------------------------------------------------------------------

    # --- Add Periodic Position Save Method (Phase 3) ---
    def _periodic_position_save(self):
        """
        Periodic position save method called every 10 seconds during playback.
        Uses PositionManager to encapsulate all business logic.
        """
        if not self.current_media_path or not self.is_playing():
            return
            
        current_pos = self.backend.get_current_position()
        current_duration = self.backend.get_duration()
        current_rate = self.backend.get_rate()
        
        # Get current subtitle state
        subtitle_enabled, subtitle_track_id, subtitle_language = False, -1, ''
        if self._is_current_media_video:
            subtitle_enabled, subtitle_track_id, subtitle_language = self._get_current_subtitle_state()
        
        audio_track_id = self._get_current_audio_state()

        # Delegate to PositionManager for all business logic
        success, new_last_saved = self.position_manager.handle_periodic_save(
            self.current_media_path, current_pos, current_duration, current_rate, self.last_saved_position,
            subtitle_enabled, subtitle_track_id, subtitle_language, audio_track_id
        )
        
        if success:
            self.last_saved_position = new_last_saved
            self.position_dirty = False
        # Note: PositionManager handles all logging and validation
    # -------------------------------------------------------

    def _update_audio_controls(self):
        """Update the audio controls in the PlayerWidget using AudioManager state."""
        state_info = self.audio_manager.get_audio_state_info()
        self.player_widget.update_audio_state(
            state_info['has_multiple_audio_tracks'],
            state_info['current_audio_language'],
            state_info['audio_tracks']
        )