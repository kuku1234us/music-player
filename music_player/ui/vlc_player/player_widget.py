"""
Main Player Widget that contains all playback related UI components.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal

from .player_controls import PlayerControls
from .player_timeline import PlayerTimeline
from .album_art_display import AlbumArtDisplay
from .volume_control import VolumeControl
from .speed_overlay import SpeedOverlay


class PlayerWidget(QWidget):
    """
    Main widget that contains all player UI components including
    controls, timeline, and album art display.
    """
    
    play_requested = pyqtSignal()
    pause_requested = pyqtSignal()
    next_requested = pyqtSignal()
    previous_requested = pyqtSignal()
    position_changed = pyqtSignal(int)
    volume_changed = pyqtSignal(int)
    rate_changed = pyqtSignal(float)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playerWidget")
        
        # UI Components
        self.album_art = AlbumArtDisplay(self)
        self.controls = PlayerControls(self)
        self.timeline = PlayerTimeline(self)
        self.volume_control = VolumeControl(self)
        self.speed_overlay = SpeedOverlay(self)
        
        # Connect signals from UI components
        self._connect_signals()
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Set up the player widget layout"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(10)
        
        # Create bottom area with three sections for proper centering
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)
        
        # Create left spacer section (same width as volume control)
        left_spacer = QWidget()
        left_spacer.setFixedWidth(180)  # Match width of volume control
        
        # Add the three sections to maintain proper centering
        bottom_layout.addWidget(left_spacer)
        bottom_layout.addWidget(self.controls, 1)  # Center section expands
        bottom_layout.addWidget(self.volume_control)
        
        # Add components to main layout
        main_layout.addWidget(self.album_art, 1)
        main_layout.addWidget(self.timeline, 0, Qt.AlignmentFlag.AlignBottom)
        main_layout.addLayout(bottom_layout, 0)
        
        self.setLayout(main_layout)
        
        # Position the speed overlay in the top-right corner with margins
        self.speed_overlay.setGeometry(
            self.width() - 120, 20,  # X, Y
            100, 40  # Width, Height
        )
        
        # Apply styling
        self.setStyleSheet("""
            QWidget#playerWidget {
                background-color: #1e1e1e;
                border-radius: 8px;
            }
        """)
        
    def resizeEvent(self, event):
        """Handle resize events to reposition the speed overlay"""
        super().resizeEvent(event)
        # Make sure the speed overlay stays in the top-right corner
        self.speed_overlay.setGeometry(
            self.width() - 120, 20,  # X, Y
            100, 40  # Width, Height
        )
        
    def _connect_signals(self):
        """Connect internal signals between UI components"""
        # Connect control signals to widget signals
        self.controls.play_clicked.connect(self.play_requested)
        self.controls.pause_clicked.connect(self.pause_requested)
        self.controls.next_clicked.connect(self.next_requested)
        self.controls.previous_clicked.connect(self.previous_requested)
        
        # Connect volume signals
        self.volume_control.volume_changed.connect(self.volume_changed)
        
        # Connect timeline signals
        self.timeline.position_changed.connect(self.position_changed)
        
    def update_track_info(self, title, artist, album, artwork_path=None):
        """Update displayed track information"""
        if artwork_path:
            self.album_art.set_image(artwork_path)
        
        # Update UI elements with track info
        self.timeline.set_track_info(title, artist)
        
    def set_duration(self, duration_ms):
        """Set the track duration in milliseconds"""
        self.timeline.set_duration(duration_ms)
        
    def set_position(self, position_ms):
        """Set the current playback position in milliseconds"""
        self.timeline.set_position(position_ms)
        
    def set_playing_state(self, is_playing):
        """Update UI to reflect playing/paused state"""
        self.controls.set_playing_state(is_playing)
        
    def set_volume(self, volume_percent):
        """Set the volume percentage (0-200)"""
        self.volume_control.set_volume(volume_percent)
        
    def get_volume(self):
        """Get the current volume percentage"""
        return self.volume_control.get_volume()
        
    def set_rate(self, rate):
        """
        Set the playback rate and update the UI.
        
        Args:
            rate (float): Playback rate (e.g., 1.0 for normal)
        """
        # Update the speed overlay
        self.speed_overlay.show_speed(rate)
        # Emit the rate changed signal for the backend
        self.rate_changed.emit(rate) 