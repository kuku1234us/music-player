"""
Hotkey handler for the music player interface.

This module centralizes keyboard shortcuts for controlling the music player.
"""
from PyQt6.QtCore import Qt, QObject, QTimer
from PyQt6.QtGui import QKeyEvent
from qt_base_app.models.settings_manager import SettingsManager, SettingType


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
        
    def handle_key_press(self, event: QKeyEvent) -> bool:
        """
        Handle a key press event.
        
        Args:
            event: The key event to handle
            
        Returns:
            bool: True if the event was handled, False otherwise
        """
        if event.key() == Qt.Key.Key_Space:
            # Toggle play/pause
            if self.main_player.app_state == self.main_player.STATE_PLAYING:
                self.main_player.pause()
            else:
                self.main_player.play()
            return True
            
        elif event.key() == Qt.Key.Key_Left:
            # Seek backward
            seek_interval = self.settings.get('preferences/seek_interval', 3, SettingType.INT)
            self.seek_accumulator -= seek_interval
            self._schedule_seek()
            return True
            
        elif event.key() == Qt.Key.Key_Right:
            # Seek forward
            seek_interval = self.settings.get('preferences/seek_interval', 3, SettingType.INT)
            self.seek_accumulator += seek_interval
            self._schedule_seek()
            return True
            
        # Up arrow key to increase volume
        elif event.key() == Qt.Key.Key_Up:
            self._increase_volume()
            return True
            
        # Down arrow key to decrease volume
        elif event.key() == Qt.Key.Key_Down:
            self._decrease_volume()
            return True
            
        # "+" key to increase volume
        elif event.key() == Qt.Key.Key_Plus:
            self._increase_volume()
            return True
            
        # "-" key to decrease volume
        elif event.key() == Qt.Key.Key_Minus:
            self._decrease_volume()
            return True
            
        # ']' key to increase playback speed
        elif event.key() == Qt.Key.Key_BracketRight:
            self._increase_playback_speed()
            return True
            
        # '[' key to decrease playback speed
        elif event.key() == Qt.Key.Key_BracketLeft:
            self._decrease_playback_speed()
            return True
            
        # '0' key to reset playback speed
        elif event.key() == Qt.Key.Key_0:
            self._reset_playback_speed()
            return True
        
        return False
        
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
        new_volume = min(200, current_volume + 10)  # Ensure we don't exceed 200%
        self.main_player.player_widget.set_volume(new_volume)
        self.main_player._on_volume_changed(new_volume)
        
    def _decrease_volume(self):
        """Decrease volume by 10%"""
        current_volume = self.main_player.player_widget.get_volume()
        new_volume = max(0, current_volume - 10)  # Ensure we don't go below 0%
        self.main_player.player_widget.set_volume(new_volume)
        self.main_player._on_volume_changed(new_volume) 