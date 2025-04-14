"""
Main Player Widget that contains all playback related UI components.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSizePolicy, QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from .player_controls import PlayerControls
from .player_timeline import PlayerTimeline
from .album_art_display import AlbumArtDisplay
from .volume_control import VolumeControl
from .speed_overlay import SpeedOverlay
from .repeat_button import RepeatButton


class PlayerWidget(QWidget):
    """
    Main widget that contains all player UI components including
    controls, timeline, and album art display.
    """
    
    play_requested = pyqtSignal()
    pause_requested = pyqtSignal()
    next_requested = pyqtSignal()
    prev_requested = pyqtSignal()
    position_changed = pyqtSignal(int)
    volume_changed = pyqtSignal(int)
    rate_changed = pyqtSignal(float)
    repeat_state_changed = pyqtSignal(str)  # Signal for repeat mode changes
    
    def __init__(self, parent=None, persistent=False):
        super().__init__(parent)
        self.setObjectName("playerWidget")
        self.persistent = persistent
        
        # UI Components
        self.album_art = AlbumArtDisplay(self)
        self.controls = PlayerControls(self)
        self.timeline = PlayerTimeline(self)
        self.volume_control = VolumeControl(self)
        self.speed_overlay = SpeedOverlay(self)
        self.repeat_button = RepeatButton(self, size=29)  # Increased size to compensate for 20% growth inside the component
        
        # Track info components
        self.track_title = QLabel("No Track")
        self.track_artist = QLabel("No Artist")
        
        # Connect signals from UI components
        self._connect_signals()
        
        # Set up UI based on mode
        self._setup_ui()
        
    def _setup_ui(self):
        """Set up the player widget layout based on mode"""
        if self.persistent:
            self._setup_persistent_ui()
        else:
            self._setup_standard_ui()
    
    def _setup_persistent_ui(self):
        """Set up horizontal layout for persistent player bar"""
        # Create a vertical layout to hold track info (top), timeline (middle) and controls (bottom)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 5, 0, 5)  # Original padding
        main_layout.setSpacing(5)  # Original spacing
        
        # Add track info at top (song title and artist)
        track_info = QWidget()
        track_info_layout = QHBoxLayout(track_info)
        track_info_layout.setContentsMargins(10, 0, 10, 0)
        track_info_layout.setSpacing(5)
        
        # Style the track info labels (keep original styling)
        self.track_title.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        self.track_artist.setStyleSheet("color: #cccccc; font-size: 14px;")
        
        # Add track info to layout
        track_info_layout.addWidget(self.track_title, 1)  # Give track title stretch
        track_info_layout.addWidget(self.track_artist)
        
        # Add track info widget to main layout
        main_layout.addWidget(track_info)
        
        # Add timeline below track info
        main_layout.addWidget(self.timeline)
        
        # Create horizontal layout for controls row with three sections for proper centering
        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(10, 0, 10, 0)
        controls_row.setSpacing(10)
        
        # Set fixed size for thumbnail
        self.album_art.setFixedSize(40, 40)
        self.album_art.setMinimumSize(40, 40)
        self.album_art.image_label.setMinimumSize(40, 40)
        
        # Left section: Album art
        left_section = QHBoxLayout()
        left_section.addWidget(self.album_art)
        left_section.addStretch(1)  # Push art to the left
        
        # Center section: Playback controls in a centered container
        center_section = QHBoxLayout()
        center_section.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_section.addWidget(self.controls)
        
        # Right section: Repeat button and Volume control
        right_section = QHBoxLayout()
        right_section.addStretch(1)  # Push controls to the right
        right_section.addWidget(self.repeat_button)  # Add repeat button to the right section
        right_section.addWidget(self.volume_control)
        
        # Add the three sections to the controls row with equal weight
        controls_row.addLayout(left_section, 1)
        controls_row.addLayout(center_section, 1)
        controls_row.addLayout(right_section, 1)
        
        # Add the controls row to the main layout
        main_layout.addLayout(controls_row)
        
        # Set the main layout for this widget
        if self.layout():
            # Remove existing layout if any
            QWidget().setLayout(self.layout())
        self.setLayout(main_layout)
        
        # Hide the speed overlay initially, but position it centrally
        self.speed_overlay.hide()
        
        # Apply styling
        self.setStyleSheet("""
            QWidget#playerWidget {
                background-color: #1a1a1a;
                border-top: 1px solid #333333;
            }
        """)
    
    def _setup_standard_ui(self):
        """Set up the standard player widget layout (no longer used)"""
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
        
        # Create right section to hold repeat button and volume control
        right_section = QHBoxLayout()
        right_section.addWidget(self.repeat_button)
        right_section.addWidget(self.volume_control)
        
        # Create right widget to hold the right section
        right_widget = QWidget()
        right_widget.setLayout(right_section)
        bottom_layout.addWidget(right_widget)
        
        # Add components to main layout
        main_layout.addWidget(self.album_art, 1)
        main_layout.addWidget(self.timeline, 0, Qt.AlignmentFlag.AlignBottom)
        main_layout.addLayout(bottom_layout, 0)
        
        self.setLayout(main_layout)
        
        # Position the speed overlay centered at the top of the widget
        self.speed_overlay.setGeometry(
            (self.width() - 100) // 2, 20,  # X, Y - centered horizontally
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
        
        # Update the speed overlay position whether in persistent mode or not
        if self.persistent:
            # In persistent mode, position it at the track title level
            track_rect = self.track_title.geometry()
            self.speed_overlay.setGeometry(
                (self.width() - 100) // 2,  # X: centered horizontally
                track_rect.top(),  # Y: aligned with the track title
                100, 40  # Width, Height
            )
        else:
            # Position it centered at the top of the widget for standard mode
            self.speed_overlay.setGeometry(
                (self.width() - 100) // 2, 20,  # X, Y - centered horizontally
                100, 40  # Width, Height
            )
            
    def _connect_signals(self):
        """Connect internal signals.
        Connects button clicks and slider changes to appropriate slots or signals.
        """
        self.controls.play_clicked.connect(self.play_requested)
        self.controls.pause_clicked.connect(self.pause_requested)
        self.controls.next_clicked.connect(self.next_requested)
        self.controls.previous_clicked.connect(self.prev_requested)
        
        self.repeat_button.state_changed.connect(self.repeat_state_changed)
        
        self.volume_control.volume_changed.connect(self.volume_changed)
        
        self.timeline.position_changed.connect(self.position_changed)
        
    def update_track_info(self, title, artist, album, artwork_path=None):
        """Update displayed track information"""
        if artwork_path:
            self.album_art.set_image(artwork_path)
        else:
            # Explicitly set placeholder when no artwork is provided
            self.album_art._set_placeholder()
        
        # Update track info labels
        self.track_title.setText(title)
        self.track_artist.setText(artist)
        
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
        
        # Ensure the overlay is properly positioned when shown
        if self.persistent:
            # In persistent mode, position it at the track title level
            track_rect = self.track_title.geometry()
            self.speed_overlay.setGeometry(
                (self.width() - 100) // 2,  # X: centered horizontally
                track_rect.top(),  # Y: aligned with the track title
                100, 40  # Width, Height
            )
        else:
            # Standard positioning for non-persistent mode
            self.speed_overlay.setGeometry(
                (self.width() - 100) // 2, 20,  # X, Y - centered horizontally
                100, 40  # Width, Height
            )
        
        # Emit the rate changed signal for the backend
        self.rate_changed.emit(rate) 

    def set_next_prev_enabled(self, enabled: bool):
        """Enable or disable the Next and Previous buttons in the controls."""
        if hasattr(self.controls, 'set_next_enabled') and hasattr(self.controls, 'set_prev_enabled'):
            self.controls.set_next_enabled(enabled)
            self.controls.set_prev_enabled(enabled)
        else:
            # Fallback or warning if PlayerControls doesn't have the expected methods
            print("Warning: PlayerWidget cannot set next/prev state - PlayerControls lacks methods.")
            # You might need to access buttons directly if the methods don't exist:
            # if hasattr(self.controls, 'next_button') and hasattr(self.controls, 'prev_button'):
            #     self.controls.next_button.setEnabled(enabled)
            #     self.controls.prev_button.setEnabled(enabled) 