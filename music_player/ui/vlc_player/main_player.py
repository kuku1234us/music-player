"""
Main player module that integrates the UI components with the VLC backend.
"""
import os
import sys 
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QFileDialog
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer
import vlc
from typing import Optional, TYPE_CHECKING
from qt_base_app.models.logger import Logger

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

from .enums import STATE_PLAYING, STATE_PAUSED, STATE_ENDED, STATE_ERROR, REPEAT_ONE, REPEAT_ALL, REPEAT_RANDOM 

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

if TYPE_CHECKING:
    from music_player.models.playlist import Playlist

class MainPlayer(QWidget):
    """
    Main player widget that combines the UI components with the VLC backend.
    """
    
    # Signals
    playback_state_changed = pyqtSignal(str) 
    media_changed = pyqtSignal(dict, bool) 
    playback_mode_changed = pyqtSignal(str)
    
    # --- New Navigation Signals ---
    browser_nav_request = pyqtSignal(str) # 'next' or 'prev'
    browser_delete_request = pyqtSignal(str) # filepath
    # ------------------------------
    
    def __init__(self, parent=None, persistent_mode=False):
        super().__init__(parent)
        self.setObjectName("mainPlayer")
        
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.persistent_mode = persistent_mode
        self.settings = SettingsManager.instance()
        self.recently_played_model = RecentlyPlayedModel.instance()
        
        # Internal state tracking
        self.app_state = STATE_PAUSED
        self.current_media_path: Optional[str] = None 
        self.block_position_updates = False  
        self.last_metadata = None  
        self._current_repeat_mode = REPEAT_ALL 
        self._is_current_media_video = False 
        self._video_widget: Optional[VideoWidget] = None 
        
        # Playback Source Context
        self.playback_source = 'single' # 'single', 'playlist', 'browser'

        self.clipping_manager = ClippingManager.instance()
        self._playback_mode = 'single'  
        self._current_playlist: Optional['Playlist'] = None
        
        self.full_screen_manager: Optional[FullScreenManager] = None
        self._player_page_ref: Optional[PlayerPage] = None
        
        self.position_manager = PlaybackPositionManager.instance()
        self.subtitle_manager = SubtitleManager()
        self.audio_manager = AudioManager()
        
        self.position_save_timer = QTimer(self)
        self.position_save_timer.setInterval(10000) 
        self.position_save_timer.timeout.connect(self._periodic_position_save)
        self.position_dirty = False  
        self.last_saved_position = 0  
        
        # UI Components
        self.player_widget = PlayerWidget(self, persistent=persistent_mode)
        
        # Backend
        self.backend = VLCBackend(self)
        
        # Hotkey handler
        self.hotkey_handler = HotkeyHandler(self)
        
        # Setup
        self._setup_ui()
        self._connect_signals()
        
        self._apply_saved_volume()
        self._apply_saved_repeat_mode() 
        
        self.player_widget.set_next_prev_enabled(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5) 
        layout.addWidget(self.player_widget)
        self.setLayout(layout)
        
        self.setStyleSheet("""
            QWidget#mainPlayer {
                background-color: #1e1e1e;
                border-radius: 0px;
            }
        """)
        
    def _connect_signals(self):
        self.player_widget.play_requested.connect(self._on_play_requested)
        self.player_widget.pause_requested.connect(self._on_pause_requested)
        self.player_widget.position_changed.connect(self._on_position_changed)
        self.player_widget.volume_changed.connect(self._on_volume_changed)
        self.player_widget.rate_changed.connect(self._on_rate_changed)
        self.player_widget.repeat_state_changed.connect(self._on_repeat_state_changed)
        self.player_widget.next_requested.connect(self.play_next_track) 
        self.player_widget.prev_requested.connect(self.play_previous_track) 
        
        self.player_widget.toggle_subtitles.connect(self._toggle_subtitles)
        self.player_widget.next_subtitle.connect(self._cycle_subtitle_track)  
        self.player_widget.subtitle_selected.connect(self._select_subtitle_track)  
        
        self.player_widget.audio_track_selected.connect(self._select_audio_track)
        
        self.backend.media_loaded.connect(self.on_media_metadata_loaded) 
        self.backend.position_changed.connect(self._handle_backend_position_change)
        self.backend.duration_changed.connect(self.player_widget.timeline.set_duration)
        self.backend.state_changed.connect(self._handle_backend_error_states) 
        self.backend.end_reached.connect(self._on_end_reached)
        self.backend.error_occurred.connect(self._show_error)
        # When an old VLC worker finishes, delete its old video surface to prevent HWND reuse bugs.
        if hasattr(self.backend, "surface_released"):
            self.backend.surface_released.connect(self._on_backend_surface_released)
        
        self.clipping_manager.clip_successful.connect(self._on_clip_successful)
        self.clipping_manager.clip_failed.connect(self._on_clip_failed)

    def _handle_backend_position_change(self, position_ms):
        if not self.block_position_updates:
            self.player_widget.timeline.set_position(position_ms)
        
    def keyPressEvent(self, event):
        if self.hotkey_handler.handle_key_press(event):
            return
        super().keyPressEvent(event)
        
    def showEvent(self, event):
        super().showEvent(event)
        self.setFocus()
        
    def _show_error(self, error_message):
        QMessageBox.critical(self, "Playback Error", error_message)
        
    # --- New Hotkey Request Handlers ---
    def on_next_media_request(self):
        """Handler for PageDown (Next) request."""
        if self.playback_source == 'playlist' or self._playback_mode == 'playlist':
            self.play_next_track()
        elif self.playback_source == 'browser':
            self.browser_nav_request.emit('next')
            
    def on_prev_media_request(self):
        """Handler for PageUp (Prev) request."""
        if self.playback_source == 'playlist' or self._playback_mode == 'playlist':
            self.play_previous_track()
        elif self.playback_source == 'browser':
            self.browser_nav_request.emit('prev')
            
    def on_delete_media_request(self):
        """Handler for Delete key request."""
        if self.playback_source == 'browser' and self.current_media_path:
            self.browser_delete_request.emit(self.current_media_path)
    # -----------------------------------

    # ... [Keep existing clipping handlers] ...
    def _on_clip_successful(self, original_path: str, clipped_path: str):
        Logger.instance().debug(caller="MainPlayer", msg=f"[MainPlayer] Clipping successful: '{original_path}' -> '{clipped_path}'")
        if self._playback_mode != 'single':
            self._playback_mode = 'single'
            self.playback_mode_changed.emit('single')
        self._current_playlist = None
        self.current_media_path = clipped_path
        self.player_widget.set_next_prev_enabled(False)
        self.clipping_manager.clear_all_segments()
        self.player_widget.timeline.set_current_media_path(self.current_media_path)
        self.clipping_manager.set_media(self.current_media_path)
        load_successful = self.backend.load_media(clipped_path)
        if load_successful:
            self._set_app_state(STATE_PLAYING)
            self.backend.play()
        else:
            self._show_error(f"Failed to load the clipped file: {clipped_path}")
        self.setFocus()
        self.recently_played_model.add_item(item_type='file', name=os.path.basename(clipped_path), path=clipped_path)
        
    def _on_clip_failed(self, original_path: str, error_message: str):
        Logger.instance().error(caller="MainPlayer", msg=f"[MainPlayer] Clipping failed for '{original_path}': {error_message}")
        QMessageBox.critical(self, "Clipping Failed", f"Failed to create clip from:\n{os.path.basename(original_path)}\n\nError: {error_message}")
        self.setFocus()

    # ... [Keep play/pause/set_app_state methods] ...
    def _on_play_requested(self):
        if self.app_state == STATE_PLAYING: return
        if self._playback_mode == 'playlist':
            if not self._current_playlist or len(self._current_playlist) == 0: return
        elif not self.current_media_path: return

        if self.app_state == STATE_PAUSED:
            self._set_app_state(STATE_PLAYING)
            self.play()
            return

        if self.app_state == STATE_ENDED:
            if self._playback_mode == 'playlist':
                next_track_path = self._current_playlist.get_next_file() or self._current_playlist.get_first_file()
                self._load_and_play_path(next_track_path)
            else:
                self._set_app_state(STATE_PLAYING)
                self.backend.seek(0)
                self.backend.play()
            self.setFocus()
            return
            
        if self._playback_mode == 'playlist' and self._current_playlist:
            first_track = self._current_playlist.get_first_file()
            if first_track:
                self._set_app_state(STATE_PLAYING)
                self._load_and_play_path(first_track)
        elif self.current_media_path:
            self._set_app_state(STATE_PLAYING)
            self.backend.seek(0)
            self.backend.play()
        self.setFocus()
        
    def _on_pause_requested(self):
        self._set_app_state(STATE_PAUSED)
        self.backend.pause()
        self.setFocus()
        
    def _set_app_state(self, state):
        self.app_state = state
        if hasattr(self, 'position_save_timer'):
            if state == STATE_PLAYING:
                if not self.position_save_timer.isActive(): self.position_save_timer.start()
            else:
                if self.position_save_timer.isActive(): self.position_save_timer.stop()
        if state == STATE_PLAYING:
            self.player_widget.set_playing_state(True)
        else:
            self.player_widget.set_playing_state(False)
        self.playback_state_changed.emit(state)
        
    def _handle_backend_error_states(self, state):
        if state == "error":
            Logger.instance().error(caller="MainPlayer", msg=f"[MainPlayer] Backend reported error state.")
            self._set_app_state(STATE_ERROR)
        elif state == "playing" and self.app_state != STATE_PLAYING:
            self._set_app_state(STATE_PLAYING)
        elif state == "paused" and self.app_state != STATE_PAUSED:
            self._set_app_state(STATE_PAUSED)

    def _on_end_reached(self):
        Logger.instance().debug(caller="MainPlayer", msg="[MainPlayer] End reached signal received.")
        if self.current_media_path:
            try:
                # Save position 0 (reset) logic via centralized helper would save current pos (end), 
                # but we want to force save 0. So we use position_manager directly or specific args.
                # Actually, duplicate logic just for "0" is fine, or we update helper to accept override.
                # Let's use the manual call for this specific "reset to 0" case to be explicit.
                sub_state = self.subtitle_manager.get_subtitle_state_info()
                audio_state = self.audio_manager.get_audio_state_info()
                
                self.position_manager.save_position(
                    self.current_media_path, 
                    0, 
                    self.backend.get_duration(), 
                    self.backend.get_rate(),
                    sub_state['subtitle_enabled'], 
                    self.subtitle_manager.current_subtitle_track, 
                    sub_state['current_subtitle_language'], 
                    audio_state['current_audio_track']
                )
            except Exception as e:
                Logger.instance().error(caller="MainPlayer", msg=f"Error saving position on end: {e}")
        
        if self._playback_mode == 'single':
            self.backend.seek(0)
            self.backend.play()
        elif self._playback_mode == 'playlist' and self._current_playlist:
            next_track_path = self._current_playlist.get_next_file()
            if next_track_path:
                self._load_and_play_path(next_track_path)
            else:
                self.backend.stop()
                self.player_widget.set_playing_state(False)

    def _on_position_changed(self, position_ms):
        if not self.current_media_path: return
        if self.app_state == STATE_ENDED:
            self.app_state = STATE_PAUSED
            self.player_widget.set_playing_state(False)
            self.playback_state_changed.emit(STATE_PAUSED)
            
        self.block_position_updates = True
        try:
            self.backend.seek(position_ms)
            if self.app_state == STATE_PLAYING: # removed "and not self.backend.is_playing" check as is_playing is now a method/property
                self.backend.play()
                
            # --- Save Position on Timeline Seek ---
            self._save_current_playback_state("seek_timeline", position_override_ms=position_ms)
            # --------------------------------------
            
        finally:
            self.block_position_updates = False
        self.player_widget.timeline.set_position(position_ms)
        
    def play(self):
        if self.app_state == STATE_ENDED and self.current_media_path:
            self._set_app_state(STATE_PLAYING)
            self.backend.seek(0)
            self.backend.play()
        else:
            if self.app_state == STATE_PAUSED: self._set_app_state(STATE_PLAYING)
            self.backend.play()
        return True
        
    def pause(self):
        self._save_current_playback_state("pause")
        self._set_app_state(STATE_PAUSED)
        self.backend.pause()
        return True
        
    def set_volume(self, volume_percent):
        self.player_widget.set_volume(volume_percent)
        
    def is_playing(self):
        return self.app_state == STATE_PLAYING
        
    def cleanup(self):
        self.backend.cleanup()
        if hasattr(self, 'position_save_timer'): self.position_save_timer.stop()
        if self.full_screen_manager: self.full_screen_manager.cleanup()
        self.backend.stop()
        
    def _on_volume_changed(self, volume):
        self.backend.set_volume(volume)
        self.settings.set('player/volume', volume, SettingType.INT)
        
    def _on_rate_changed(self, rate):
        self.backend.set_rate(rate)
        
    def set_rate(self, rate):
        self.player_widget.set_rate(rate)
        self.backend.set_rate(rate)
        self._save_current_playback_state("rate_change")
        
    def get_rate(self):
        return self.backend.get_rate()
        
    def seek_relative(self, seconds):
        current_position = self.backend.get_current_position()
        if current_position is not None:
            new_position = max(0, current_position + int(seconds * 1000))
            self.backend.seek(new_position)
            self.player_widget.set_position(new_position)
            
            # --- Save Position on Relative Seek (Arrow Keys) ---
            self._save_current_playback_state("seek_relative", position_override_ms=new_position)
            # ---------------------------------------------------
    
    def _apply_saved_volume(self):
        volume = self.settings.get('player/volume', 100, SettingType.INT)
        self.set_volume(volume)
    
    # --- UPDATED: Unified Media Loading with Surface Swapping ---
    # --- Helper for Centralized State Saving ---
    def _save_current_playback_state(self, action_reason="manual", position_override_ms: Optional[int] = None):
        """
        Centralized helper to save current playback state (position, tracks, rate).
        """
        if not self.current_media_path: return

        sub_state = self.subtitle_manager.get_subtitle_state_info()
        audio_state = self.audio_manager.get_audio_state_info()
        
        # Get current position (default to 0 if None)
        pos = int(position_override_ms) if position_override_ms is not None else (self.backend.get_current_position() or 0)
        dur = self.backend.get_duration()
        if not dur or dur <= 0:
            # Fall back to UI timeline duration when backend duration is not yet available.
            try:
                dur = self.player_widget.timeline.get_duration()
            except Exception:
                dur = 0
        rate = self.backend.get_rate()
        
        self.position_manager.handle_manual_action_save(
            self.current_media_path,
            pos,
            dur,
            rate,
            action_reason,
            sub_state['subtitle_enabled'],
            self.subtitle_manager.current_subtitle_track,
            sub_state['current_subtitle_language'],
            audio_state['current_audio_track']
        )
    # -------------------------------------------

    def load_media_unified(self, filepath: str, source_context: str = "unknown"):
        Logger.instance().debug(caller="MainPlayer", msg=f"[MainPlayer] Unified media loading from {source_context}: {filepath}")
        
        # --- Save Position of Current Media Before Switching ---
        if self.current_media_path:
             self._save_current_playback_state("media_switch")
        # -----------------------------------------------------
        
        # --- Update Context & Source ---
        if source_context == "browser_files":
            self.playback_source = 'browser'
        elif source_context in ["playlist_track_selection", "internal_playlist_navigation"]:
            self.playback_source = 'playlist'
        else:
            self.playback_source = 'single'
        # -------------------------------

        try:
            if not filepath or not os.path.exists(filepath):
                Logger.instance().error(caller="MainPlayer", msg=f"[MainPlayer] Error: File does not exist: {filepath}")
                return False
            
            self.set_playback_mode('single')
            self._current_playlist = None
            
            # --- Swap Video Surface & Get HWND ---
            if self._player_page_ref:
                # 1. Ask PlayerPage to switch to the NEXT surface
                self._player_page_ref.swap_video_surface()
                
                # 2. Get the new widget
                new_widget = self._player_page_ref.get_current_video_widget()
                
                # 3. Register it with MainPlayer (sets up hotkeys, drag-drop, FullScreenManager)
                # This calls backend.set_video_output(hwnd) internally, updating backend's stored HWND
                self.set_video_widget(new_widget)
            # -------------------------------------
            
            try:
                self.recently_played_model.add_item(item_type='file', name=os.path.basename(filepath), path=filepath)
            except Exception: pass
            
            # Use MediaManager
            success, actual_path, file_info = MediaManager.prepare_media_for_loading(filepath)
            if not success:
                return False
            
            self.current_media_path = actual_path
            self.player_widget.timeline.set_current_media_path(self.current_media_path)
            self.clipping_manager.set_media(self.current_media_path)
            self._set_app_state(STATE_PLAYING)
            
            # Load with stored HWND (already updated by set_video_widget)
            load_successful = self.backend.load_media(actual_path)
            
            if load_successful:
                self.backend.play()
                self.setFocus()
                return True
            else:
                self._set_app_state(STATE_PAUSED)
                return False
                
        except Exception as e:
            Logger.instance().error(caller="MainPlayer", msg=f"[MainPlayer] Error in unified media loading: {e}")
            return False
    # ------------------------------------------------------------
    
    def load_media(self):
        last_dir = self.settings.get('player/last_directory', os.path.expanduser("~"), SettingType.STRING)
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Media File", last_dir, "Media Files (*.mp3 *.wav *.ogg *.flac *.aac *.m4a *.mp4 *.avi *.mkv *.mov *.webm *.m3u)")
        if file_path:
            self.settings.set('player/last_directory', os.path.dirname(file_path), SettingType.STRING)
            success = self.load_media_unified(file_path, "file_dialog")
            if success: self.setFocus()
            return True
        return False

    def on_media_metadata_loaded(self, media: dict, is_video: bool):
        if not media:
            if self._playback_mode == 'playlist': self.play_next_track(force_advance=True)
            return

        self.last_metadata = media 
        title = media.get('title', os.path.basename(self.current_media_path or 'Unknown Track'))
        artist = media.get('artist', 'Unknown Artist')
        album = media.get('album', 'Unknown Album')
        artwork_path = media.get('artwork_path')
        self._is_current_media_video = is_video
        
        # Track Updates (Using cached getters from backend)
        self.subtitle_manager.reset_state()
        if self._is_current_media_video and self.backend.has_subtitle_tracks():
             tracks = self.backend.get_subtitle_tracks()
             suitable = self.subtitle_manager.process_subtitle_tracks(tracks)
             if suitable: self.backend.enable_subtitles(suitable['id'])
        self._update_subtitle_controls()

        self.audio_manager.reset_state()
        a_tracks = self.backend.get_audio_tracks()
        if a_tracks:
            pref = self.audio_manager.process_audio_tracks(a_tracks)
            if pref: self.backend.set_audio_track(pref['id'])
            else:
                # Defensive: never select the "Disable" track (commonly id = -1).
                for t in a_tracks:
                    try:
                        if int(t.get('id', -1)) >= 0:
                            self.backend.set_audio_track(t['id'])
                            break
                    except Exception:
                        continue
        self._update_audio_controls()

        self.player_widget.update_track_info(title, artist, album, artwork_path)
        self.setFocus()
        self.media_changed.emit(media, is_video)
        
        # Position restoration logic
        if self.current_media_path:
             saved_position, saved_rate, saved_subtitle_enabled, saved_subtitle_track_id, saved_subtitle_language, saved_audio_track_id = self.position_manager.get_saved_position(self.current_media_path)
             
             if saved_position is not None and saved_position > 5000:
                 # NOTE: PlaybackPositionManager.get_saved_position() already validates saved_position
                 # against the DB-stored duration, so we should not gate restoration on
                 # VLCBackend.get_duration() (which can be stale during media switching).
                 Logger.instance().debug(caller="MainPlayer", msg=f"Restoring position {saved_position}ms")
                 # Restore with a slight delay to ensure backend is ready
                 QTimer.singleShot(200, lambda: self._restore_playback_state(saved_position, saved_rate, saved_subtitle_enabled, saved_subtitle_track_id, saved_subtitle_language, saved_audio_track_id))
                 
             elif saved_rate != 1.0:
                 self.set_rate(saved_rate)

    def _update_subtitle_controls(self):
        state_info = self.subtitle_manager.get_subtitle_state_info()
        self.player_widget.update_subtitle_state(state_info['has_subtitle_tracks'], state_info['subtitle_enabled'], state_info['current_subtitle_language'], state_info['subtitle_tracks'])
        
    def _restore_playback_state(self, position_ms, rate, sub_enabled, sub_id, sub_lang, aud_id):
        self.backend.seek(position_ms)
        self._restore_settings(rate, sub_enabled, sub_id, sub_lang, aud_id)
        
    def _restore_settings(self, rate, sub_enabled, sub_id, sub_lang, aud_id):
        # Restore rate
        self.backend.set_rate(rate)
        self.player_widget.set_rate(rate)
        
        # Restore subtitles
        if self._is_current_media_video and self.backend.has_subtitle_tracks():
            if sub_enabled and sub_id >= 0:
                self.backend.enable_subtitles(sub_id)
                self.subtitle_manager.update_subtitle_state(sub_id, True)
            else:
                self.backend.disable_subtitles()
                self.subtitle_manager.update_subtitle_state(-1, False)
            self._update_subtitle_controls()
            
        # Restore audio track
        if aud_id >= 0:
            if self.backend.set_audio_track(aud_id):
                self.audio_manager.update_audio_state(aud_id)
                self._update_audio_controls()

    def _toggle_subtitles(self):
        state_info = self.subtitle_manager.get_subtitle_state_info()
        if not self._is_current_media_video or not state_info['has_subtitle_tracks']: return
        if state_info['subtitle_enabled']:
            self.backend.disable_subtitles()
            self.subtitle_manager.update_subtitle_state(-1, False)
        else:
            next_track = self.subtitle_manager.get_next_subtitle_track()
            if next_track:
                self.backend.enable_subtitles(next_track['id'])
                self.subtitle_manager.update_subtitle_state(next_track['id'], True)
        self._update_subtitle_controls()
        
    def _cycle_subtitle_track(self):
        state_info = self.subtitle_manager.get_subtitle_state_info()
        if not self._is_current_media_video or not state_info['has_subtitle_tracks']: return
        next_track = self.subtitle_manager.get_next_subtitle_track()
        if next_track:
            self.backend.enable_subtitles(next_track['id'])
            self.subtitle_manager.update_subtitle_state(next_track['id'], True)
        self._update_subtitle_controls()
        
    def get_current_track_metadata(self): return self.last_metadata
    def get_current_artwork_path(self): return self.last_metadata.get('artwork_path') if self.last_metadata else None
    def get_current_media_path(self): return self.current_media_path

    def _apply_saved_repeat_mode(self):
        repeat_mode = self.settings.get('player/repeat_mode', REPEAT_ALL, SettingType.STRING)
        self._current_repeat_mode = repeat_mode
        if self._playback_mode == 'playlist' and self._current_playlist: self._current_playlist.set_repeat_mode(self._current_repeat_mode)
        self.player_widget.set_repeat_state(self._current_repeat_mode)

    def _on_repeat_state_changed(self, state):
        if state != self._current_repeat_mode:
            self._current_repeat_mode = state
            if self._playback_mode == 'playlist' and self._current_playlist: self._current_playlist.set_repeat_mode(self._current_repeat_mode)
            self.settings.set('player/repeat_mode', self._current_repeat_mode, SettingType.STRING)

    def set_playback_mode(self, mode: str):
        if self._playback_mode != mode:
            self._playback_mode = mode
            self.player_widget.set_next_prev_enabled(mode == 'playlist')
            self.playback_mode_changed.emit(mode)

    @pyqtSlot(object) 
    def load_playlist(self, playlist: Optional[object]):
        if self._playback_mode == 'playlist' and self._current_playlist == playlist and self.is_playing(): return
        player_state.set_current_playlist(playlist)
        self._current_playlist = playlist
        if self._current_playlist: self._current_playlist.set_repeat_mode(self._current_repeat_mode)
        self.set_playback_mode('playlist')
        if len(self._current_playlist) == 0:
            self.player_widget.update_track_info("No Tracks", f"Playlist: {self._current_playlist.name}", "", None)
            return
        first_track = self._current_playlist.get_first_file()
        if playlist.filepath: self.recently_played_model.add_item(item_type='playlist', name=playlist.name, path=playlist.filepath)
        if first_track: self._load_and_play_path(first_track)

    def _load_and_play_path(self, file_path: str):
        self.load_media_unified(file_path, "internal_playlist_navigation")

    def play_next_track(self, force_advance=False):
        if self._playback_mode == 'playlist' and self._current_playlist:
            next_track = self._current_playlist.get_next_file()
            if next_track: self._load_and_play_path(next_track)

    def play_previous_track(self):
        if self._playback_mode == 'playlist' and self._current_playlist:
            prev_track = self._current_playlist.get_previous_file()
            if prev_track: self._load_and_play_path(prev_track)

    @pyqtSlot(str)
    def play_track_from_playlist(self, filepath: str):
        current_ui_playlist = player_state.get_current_playlist() 
        if not current_ui_playlist: return
        self.set_playback_mode('playlist')
        self._current_playlist = current_ui_playlist
        if self._current_playlist: self._current_playlist.set_repeat_mode(self._current_repeat_mode)
        if not self._current_playlist.select_track_by_filepath(filepath): return
        success = self.load_media_unified(filepath, "playlist_track_selection")
        if success:
            self.set_playback_mode('playlist')
            self._current_playlist = current_ui_playlist
        self.setFocus()

    def increase_volume(self, amount=5):
        vol = self.backend.get_volume()
        self.set_volume(min(vol + amount, 200))
    def decrease_volume(self, amount=5):
        vol = self.backend.get_volume()
        self.set_volume(max(vol - amount, 0))
    def wheelEvent(self, event):
        if event.angleDelta().y() > 0: self.increase_volume()
        else: self.decrease_volume()
        event.accept()

    def set_video_widget(self, widget: VideoWidget):
        self._video_widget = widget
        widget.set_main_player(self)
        self._set_vlc_window_handle(widget)
        if self._video_widget:
            if self.full_screen_manager: self.full_screen_manager.cleanup()
            self.full_screen_manager = FullScreenManager(video_widget=self._video_widget, main_player=self, parent=self)
            if hasattr(self._video_widget, 'fullScreenRequested'): self._video_widget.fullScreenRequested.connect(self._handle_full_screen_request)
            if hasattr(self.full_screen_manager, 'exit_requested_via_escape'): self.full_screen_manager.exit_requested_via_escape.connect(self._handle_exit_request_from_escape)
            if hasattr(self.full_screen_manager, 'did_exit_full_screen'): self.full_screen_manager.did_exit_full_screen.connect(self._sync_player_page_display)

    def _set_vlc_window_handle(self, widget: Optional[VideoWidget]):
        if not widget:
            if self.backend: self.backend.set_video_output(None)
            return
        if self.backend:
            try:
                self.backend.set_video_output(int(widget.winId()))
            except Exception: pass

    def stop(self):
        if self.current_media_path:
            self._save_current_playback_state("stop")
            
        self.backend.stop()
        self.current_media_path = None
        self.player_widget.timeline.set_current_media_path(None)
        self.clipping_manager.set_media("")
        self.subtitle_manager.reset_state()
        self._update_subtitle_controls()
        self.audio_manager.reset_state()
        self._update_audio_controls()
        self._set_app_state(STATE_PAUSED)

    def get_subtitle_tracks(self): return self.backend.get_subtitle_tracks()
    def enable_subtitles(self, track_id=0): return self.backend.enable_subtitles(track_id)
    def disable_subtitles(self): return self.backend.disable_subtitles()
    def has_subtitle_tracks(self): return self.backend.has_subtitle_tracks()

    def _select_subtitle_track(self, track_id):
        if not self._is_current_media_video: return
        if track_id < 0:
            self.backend.disable_subtitles()
            self.subtitle_manager.update_subtitle_state(-1, False)
        else:
            self.backend.enable_subtitles(track_id)
            self.subtitle_manager.update_subtitle_state(track_id, True)
        self._update_subtitle_controls()

    def _select_audio_track(self, track_id):
        if self.backend.set_audio_track(track_id):
            self.audio_manager.update_audio_state(track_id)
            self._update_audio_controls()

    @pyqtSlot()
    def _handle_full_screen_request(self):
        if self.full_screen_manager: self.full_screen_manager.toggle_full_screen()

    def request_toggle_full_screen(self):
        if self.full_screen_manager: self.full_screen_manager.toggle_full_screen()

    @pyqtSlot()
    def _handle_exit_request_from_escape(self):
        if self.full_screen_manager and self.full_screen_manager.is_full_screen:
            self.full_screen_manager.exit_full_screen()

    def _sync_player_page_display(self):
        if not self._player_page_ref:
            p = self.parentWidget()
            while p:
                if hasattr(p, 'player_page') and isinstance(p.player_page, PlayerPage):
                    self._player_page_ref = p.player_page
                    break
                p = p.parentWidget()
        if self._player_page_ref:
            if self._is_current_media_video: self._player_page_ref.show_video_view()
            else: self._player_page_ref.show_album_art_view()
            if self._video_widget: QTimer.singleShot(50, lambda: self._set_vlc_window_handle(self._video_widget))

    def register_player_page(self, player_page: PlayerPage):
        self._player_page_ref = player_page

    @pyqtSlot(int)
    def _on_backend_surface_released(self, hwnd: int):
        if self._player_page_ref and hasattr(self._player_page_ref, "release_video_surface"):
            self._player_page_ref.release_video_surface(hwnd)

    def _periodic_position_save(self):
        if not self.current_media_path or not self.is_playing(): return
        
        sub_state = self.subtitle_manager.get_subtitle_state_info()
        audio_state = self.audio_manager.get_audio_state_info()
        
        success, new_last_pos = self.position_manager.handle_periodic_save(
            self.current_media_path,
            self.backend.get_current_position() or 0,
            self.backend.get_duration(),
            self.backend.get_rate(),
            self.last_saved_position,
            sub_state['subtitle_enabled'],
            self.subtitle_manager.current_subtitle_track,
            sub_state['current_subtitle_language'],
            audio_state['current_audio_track']
        )
        
        if success:
            self.last_saved_position = new_last_pos
            
        self.position_dirty = False

    def _update_audio_controls(self):
        state_info = self.audio_manager.get_audio_state_info()
        self.player_widget.update_audio_state(state_info['has_multiple_audio_tracks'], state_info['current_audio_language'], state_info['audio_tracks'])
