"""
Hotkey handler for the music player interface.

This module centralizes keyboard shortcuts for controlling the music player.
"""
from PyQt6.QtCore import Qt, QObject, QTimer
from PyQt6.QtGui import QKeyEvent
from qt_base_app.models.settings_manager import SettingsManager, SettingType
from .enums import STATE_PLAYING, STATE_PAUSED
from music_player.models.ClippingManager import ClippingManager


class HotkeyHandler(QObject):
    """
    Handles keyboard shortcuts for the music player.
    
    This class processes keyboard events and translates them into
    player actions like play/pause, next track, etc.
    """
    
    def __init__(self, main_player):
        """
        Initialize the hotkey handler.
        
        Args:
            main_player: The MainPlayer instance to control
        """
        super().__init__(parent=main_player)
        self.main_player = main_player
        self.settings = SettingsManager.instance()
        self.clipping_manager = ClippingManager.instance()
        
        # Buffered seek management
        self.seek_accumulator = 0
        self.seek_timer = QTimer(self)
        self.seek_timer.setSingleShot(True)
        self.seek_timer.timeout.connect(self._apply_accumulated_seek)
        self.seek_debounce_time = 100  # ms to wait before applying accumulated seeks
        
        # Define hotkeys and their actions
        self.hotkeys = {
            Qt.Key.Key_Space: self._toggle_play_pause,
            Qt.Key.Key_MediaPlay: self._play,
            Qt.Key.Key_MediaPause: self._pause,
            Qt.Key.Key_MediaStop: self._stop,
            Qt.Key.Key_Left: self._seek_backward,
            Qt.Key.Key_Right: self._seek_forward,
            Qt.Key.Key_Up: self._volume_up,
            Qt.Key.Key_Down: self._volume_down,
            Qt.Key.Key_Plus: self._volume_up,     # Add + key for volume up
            Qt.Key.Key_Minus: self._volume_down,  # Add - key for volume down
            Qt.Key.Key_BracketLeft: self._decrease_playback_speed,  # [ key to decrease speed
            Qt.Key.Key_BracketRight: self._increase_playback_speed, # ] key to increase speed
            Qt.Key.Key_0: self._reset_playback_speed,  # 0 key to reset speed to normal
            Qt.Key.Key_F12: self._request_toggle_full_screen,
            Qt.Key.Key_B: self._mark_clip_begin,
            Qt.Key.Key_E: self._mark_clip_end,
            Qt.Key.Key_C: self._perform_clip,
            # Add more hotkeys as needed
            # Note: Shift + Key combinations will be handled separately in handle_key_press
        }
        
    def handle_key_press(self, event: QKeyEvent) -> bool:
        """
        Handle a key press event.
        
        Args:
            event: The key event to handle
            
        Returns:
            bool: True if the event was handled, False otherwise
        """
        key = event.key()
        modifiers = event.modifiers()

        # --- NEW: Handle Shift + Key combinations for clipping controls ---
        if modifiers == Qt.KeyboardModifier.ShiftModifier:
            if key == Qt.Key.Key_B:
                self._clear_pending_begin_marker()
                return True
            elif key == Qt.Key.Key_E:
                self._clear_last_segment()
                return True
            elif key == Qt.Key.Key_Delete or key == Qt.Key.Key_Backspace: # Allow Shift+Del or Shift+Backspace
                self._clear_all_segments()
                return True
        # -----------------------------------------------------------------
        
        # Handle left/right seeking in both playing and paused states (for clipping accuracy)
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            if self.main_player.app_state in [STATE_PLAYING, STATE_PAUSED]:
                action = self.hotkeys.get(key)
                if action:
                    action()
                    return True
        # Handle other hotkeys regardless of state
        elif key in self.hotkeys:
            action = self.hotkeys.get(key)
            if action:
                action()
                return True
        
        return False
        
    def _toggle_play_pause(self):
        """Toggle between play and pause"""
        if self.main_player.app_state == STATE_PLAYING:
            self.main_player.pause()
        else:
            self.main_player.play()
            
    def _play(self):
        """Play the current track"""
        self.main_player.play()
        
    def _pause(self):
        """Pause the current track"""
        self.main_player.pause()
        
    def _stop(self):
        """Stop playback"""
        self.main_player.stop()
        
    def _seek_backward(self):
        """Seek backward by 5 seconds"""
        self.main_player.seek_relative(-5)
        
    def _seek_forward(self):
        """Seek forward by 5 seconds"""
        self.main_player.seek_relative(5)
        
    def _volume_up(self):
        """Increase volume by 5%"""
        self.main_player.increase_volume(5)
        
    def _volume_down(self):
        """Decrease volume by 5%"""
        self.main_player.decrease_volume(5)
        
    def _schedule_seek(self):
        """Schedule a seek operation after accumulating multiple seek requests"""
        if not self.seek_timer.isActive():
            self.seek_timer.start(self.seek_debounce_time)
            
    def _apply_accumulated_seek(self):
        """Apply the accumulated seek operations"""
        if self.seek_accumulator != 0:
            self.main_player.seek_relative(self.seek_accumulator)
            self.seek_accumulator = 0
        
    def _increase_playback_speed(self):
        """Increase playback speed by 0.10"""
        current_rate = self.main_player.get_rate()
        new_rate = current_rate + 0.10
        self.main_player.set_rate(new_rate)
        
    def _decrease_playback_speed(self):
        """Decrease playback speed by 0.10"""
        current_rate = self.main_player.get_rate()
        new_rate = current_rate - 0.10
        self.main_player.set_rate(new_rate)
        
    def _reset_playback_speed(self):
        """Reset playback speed to normal (1.0)"""
        self.main_player.set_rate(1.0)
        
    def _request_toggle_full_screen(self):
        """Requests the main player to toggle full-screen mode."""
        if hasattr(self.main_player, 'request_toggle_full_screen'):
            self.main_player.request_toggle_full_screen()
        else:
            print("[HotkeyHandler] MainPlayer does not have request_toggle_full_screen method.")
        
    def _increase_volume(self):
        """Increase volume by 10%"""
        current_volume = self.main_player.player_widget.get_volume()
        new_volume = min(current_volume + 10, 200)  # Ensure we don't exceed 200%
        self.main_player.set_volume(new_volume)
        
    def _decrease_volume(self):
        """Decrease volume by 10%"""
        current_volume = self.main_player.player_widget.get_volume()
        new_volume = max(current_volume - 10, 0)  # Ensure we don't go below 0%
        self.main_player.set_volume(new_volume)

    def _mark_clip_begin(self):
        """Marks the beginning of the clip at the current playback position."""
        print(f"[HotkeyHandler DEBUG] _mark_clip_begin: current_media_path='{self.main_player.current_media_path}', app_state='{self.main_player.app_state}'") # DEBUG
        if self.main_player.current_media_path and self.main_player.app_state in [STATE_PLAYING, STATE_PAUSED]:
            current_time_ms = self.main_player.backend.get_current_position()
            print(f"[HotkeyHandler DEBUG] _mark_clip_begin: current_time_ms={current_time_ms}") # DEBUG
            if current_time_ms is not None:
                self.clipping_manager.mark_begin(current_time_ms)
            else: 
                print(f"[HotkeyHandler DEBUG] _mark_clip_begin: current_time_ms is None, not calling clipping_manager.mark_begin") # DEBUG
        else:
            print(f"[HotkeyHandler DEBUG] _mark_clip_begin: Conditions not met.") # DEBUG

    def _mark_clip_end(self):
        """Marks the end of the clip at the current playback position."""
        if self.main_player.current_media_path and self.main_player.app_state in [STATE_PLAYING, STATE_PAUSED]:
            current_time_ms = self.main_player.backend.get_current_position()
            if current_time_ms is not None:
                # print(f"[HotkeyHandler] Mark end at {current_time_ms}ms") # For debugging
                self.clipping_manager.mark_end(current_time_ms)
            # else: # For debugging
                # print(f"[HotkeyHandler] Could not get current position to mark end.")

    def _perform_clip(self):
        """Initiates the clipping process using the currently set markers."""
        if self.main_player.current_media_path: # Basic check: media must be loaded
            # print(f"[HotkeyHandler] Perform clip requested.") # For debugging
            self.clipping_manager.perform_clip()
        # else: # For debugging
            # print(f"[HotkeyHandler] Cannot perform clip: No media loaded.") 

    # --- NEW Hotkey Methods for Multi-Segment ---
    def _clear_pending_begin_marker(self):
        """Clears the current pending begin marker."""
        if self.main_player.current_media_path:
            self.clipping_manager.clear_pending_begin_marker()
            # print("[HotkeyHandler] Clear pending begin marker requested.")

    def _clear_last_segment(self):
        """Clears the last added segment."""
        if self.main_player.current_media_path:
            self.clipping_manager.clear_last_segment()
            # print("[HotkeyHandler] Clear last segment requested.")

    def _clear_all_segments(self):
        """Clears all defined segments and any pending begin marker."""
        if self.main_player.current_media_path:
            self.clipping_manager.clear_all_segments()
            # print("[HotkeyHandler] Clear all segments requested.")
    # ------------------------------------------ 