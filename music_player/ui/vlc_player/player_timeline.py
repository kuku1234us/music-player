"""
Player timeline component for showing track progress and time information.
"""
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from .custom_slider import CustomSlider


class PlayerTimeline(QWidget):
    """
    Widget for displaying and controlling the playback position with
    time labels and a progress slider.
    """
    
    position_changed = pyqtSignal(int)  # Position in milliseconds
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playerTimeline")
        
        # State
        self.duration_ms = 0
        self.current_position_ms = 0
        self.is_seeking = False
        
        # UI Components
        self.position_slider = CustomSlider(self)
        self.current_time_label = QLabel("00:00:00", self)
        self.total_time_label = QLabel("00:00:00", self)
        self.track_title_label = QLabel("No track playing", self)
        self.track_artist_label = QLabel("", self)
        
        self._setup_ui()
        self._connect_signals()
        
    def _setup_ui(self):
        """Set up the timeline UI layout and styling"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 0, 10, 0)
        main_layout.setSpacing(5)
        
        # Track info layout
        track_info_layout = QHBoxLayout()
        
        # Configure track info labels
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        self.track_title_label.setFont(title_font)
        
        artist_font = QFont()
        artist_font.setPointSize(10)
        self.track_artist_label.setFont(artist_font)
        
        # Add track info to layout
        track_info_layout.addWidget(self.track_title_label, 1)
        track_info_layout.addStretch(1)
        track_info_layout.addWidget(self.track_artist_label)
        
        # Timeline layout
        timeline_layout = QHBoxLayout()
        timeline_layout.setSpacing(10)
        
        # Configure time labels
        time_font = QFont()
        time_font.setPointSize(9)
        time_font.setFamily("Monospace")
        self.current_time_label.setFont(time_font)
        self.total_time_label.setFont(time_font)
        
        # Position slider is now a CustomSlider
        self.position_slider.setRange(0, 1000)
        
        # Add widgets to timeline layout
        timeline_layout.addWidget(self.current_time_label)
        timeline_layout.addWidget(self.position_slider, 1)
        timeline_layout.addWidget(self.total_time_label)
        
        # Add layouts to main layout
        main_layout.addLayout(track_info_layout)
        main_layout.addLayout(timeline_layout)
        
        self.setLayout(main_layout)
        
        # Set styles
        self.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
            }
        """)
        
    def _connect_signals(self):
        """Connect slider signals to corresponding slots"""
        self.position_slider.sliderPressed.connect(self._on_slider_pressed)
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        self.position_slider.valueChanged.connect(self._on_slider_value_changed)
        
    def _on_slider_pressed(self):
        """Handle slider press to start seeking"""
        self.is_seeking = True
        
    def _on_slider_released(self):
        """Handle slider release to finish seeking"""
        self.is_seeking = False
        position_ms = int(self.position_slider.value() * self.duration_ms / 1000)
        self.position_changed.emit(position_ms)
        
    def _on_slider_value_changed(self, value):
        """Handle slider value change during seeking"""
        if self.is_seeking and self.duration_ms > 0:
            position_ms = int(value * self.duration_ms / 1000)
            self._update_time_labels(position_ms, self.duration_ms)
            
    def set_duration(self, duration_ms):
        """Set the total duration of the current track"""
        self.duration_ms = duration_ms
        self._update_time_labels()
            
    def set_position(self, position_ms):
        """Update the current playback position"""
        if not self.is_seeking:
            self.current_position_ms = position_ms
            if self.duration_ms > 0:
                slider_value = int(position_ms * 1000 / self.duration_ms)
                # Block signals to avoid feedback loop
                self.position_slider.blockSignals(True)
                self.position_slider.setValue(slider_value)
                self.position_slider.blockSignals(False)
            self._update_time_labels()
            
    def set_track_info(self, title, artist):
        """Set the track title and artist"""
        self.track_title_label.setText(title)
        self.track_artist_label.setText(artist)
            
    def _update_time_labels(self, position_ms=None, duration_ms=None):
        """Update the time labels with current time and total time"""
        if position_ms is None:
            position_ms = self.current_position_ms
        if duration_ms is None:
            duration_ms = self.duration_ms
            
        self.current_time_label.setText(self._format_time(position_ms))
        self.total_time_label.setText(self._format_time(duration_ms))
    
    @staticmethod
    def _format_time(ms):
        """Format milliseconds to HH:MM:SS time format"""
        total_seconds = ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def get_position(self):
        """Get the current playback position in milliseconds"""
        return self.current_position_ms
        
    def get_duration(self):
        """Get the total duration of the current track in milliseconds"""
        return self.duration_ms 