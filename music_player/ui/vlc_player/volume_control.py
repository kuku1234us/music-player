"""
Volume control component for the music player application.
"""
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon

from music_player.ui.vlc_player.custom_slider import CustomSlider


class VolumeControl(QWidget):
    """
    Widget for controlling playback volume with a slider and numeric display.
    Displays volume from 0% to 200%.
    """
    
    volume_changed = pyqtSignal(int)  # Volume as percentage (0-200)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("volumeControl")
        
        # UI Components
        self.volume_slider = CustomSlider(self)
        self.volume_label = QLabel("100%", self)
        self.speaker_icon = QLabel(self)
        
        # Set volume range (0-200%)
        self.volume_slider.setRange(0, 200)
        self.volume_slider.setValue(100)  # Default to 100%
        
        # Set fixed width for the entire component
        self.setFixedWidth(180)
        
        self._setup_ui()
        self._connect_signals()
        
    def _setup_ui(self):
        """Set up the volume control UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(5)
        
        # Configure volume label
        font = QFont()
        font.setPointSize(10)
        self.volume_label.setFont(font)
        self.volume_label.setMinimumWidth(50)
        self.volume_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        # Configure speaker icon
        self.speaker_icon.setText("🔊")  # Using emoji as placeholder, replace with proper icon
        self.speaker_icon.setFont(QFont("", 14))
        self.speaker_icon.setMinimumWidth(30)
        self.speaker_icon.setFixedWidth(30)
        self.speaker_icon.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        # Configure slider
        self.volume_slider.setMinimumWidth(80)
        self.volume_slider.setMaximumWidth(120)
        
        # Custom styling for volume slider
        # We can customize the track color or other properties if needed
        
        # Add widgets to layout
        layout.addWidget(self.volume_label)
        layout.addWidget(self.volume_slider)
        layout.addWidget(self.speaker_icon)
        
        self.setLayout(layout)
        
        # Set styles
        self.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
            }
        """)
        
    def _connect_signals(self):
        """Connect slider signals to slots"""
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        
    def _on_volume_changed(self, value):
        """Handle volume slider value changes"""
        # Update volume label
        self.volume_label.setText(f"{value}%")
        
        # Update icon based on volume level
        if value == 0:
            self.speaker_icon.setText("🔇")  # Muted
        elif value < 50:
            self.speaker_icon.setText("🔈")  # Low volume
        elif value < 150:
            self.speaker_icon.setText("🔉")  # Medium volume
        else:
            self.speaker_icon.setText("🔊")  # High volume
            
        # Emit signal
        self.volume_changed.emit(value)
        
    def set_volume(self, volume):
        """Set volume percentage (0-200)"""
        # Ensure volume is within range
        volume = max(0, min(200, volume))
        
        # Update slider (will trigger valueChanged signal)
        self.volume_slider.setValue(volume)
        
    def get_volume(self):
        """Get current volume percentage"""
        return self.volume_slider.value()
        
    def mute(self):
        """Mute the volume (set to 0%)"""
        self.set_volume(0) 