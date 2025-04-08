"""
Hotkey handler for the music player interface.

This module centralizes keyboard shortcuts for controlling the music player.
"""
from PyQt6.QtCore import Qt, QObject, QTimer
from PyQt6.QtGui import QKeyEvent
from qt_base_app.models.settings_manager import SettingsManager, SettingType
from .enums import STATE_PLAYING, STATE_PAUSED


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
            # Add more hotkeys as needed
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
        
        # Handle left/right seeking only in playing state
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            if self.main_player.app_state == STATE_PLAYING:
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
        volume = self.main_player.player_widget.volume_control.get_volume()
        new_volume = min(volume + 5, 200)  # Allow up to 200% volume
        self.main_player.set_volume(new_volume)
        
    def _volume_down(self):
        """Decrease volume by 5%"""
        volume = self.main_player.player_widget.volume_control.get_volume()
        new_volume = max(volume - 5, 0)
        self.main_player.set_volume(new_volume)
        
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