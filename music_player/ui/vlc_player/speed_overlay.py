"""
Speed overlay widget that shows current playback speed.

This overlay appears briefly when playback speed is changed.
"""
from PyQt6.QtWidgets import QLabel, QGraphicsOpacityEffect
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation
from PyQt6.QtGui import QFont


class SpeedOverlay(QLabel):
    """
    Overlay that displays the current playback speed.
    Automatically fades out after a specified duration.
    """
    
    def __init__(self, parent=None):
        """
        Initialize the speed overlay.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        
        # Set initial value
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("1.00×")
        
        # Style the overlay
        self.setStyleSheet("""
            background-color: rgba(40, 40, 40, 0.8);
            color: #ffffff;
            border-radius: 4px;
            padding: 6px 10px;
        """)
        
        # Use a larger, bold font
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        self.setFont(font)
        
        # Setup opacity effect for fade animation
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self.opacity_effect)
        
        # Create fade animation
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(500)  # 500ms fade
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.finished.connect(self.hide)
        
        # Timer for auto-hiding
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._start_fade)
        
        # Initially hide the overlay
        self.hide()
        
    def show_speed(self, speed):
        """
        Show the speed overlay with the given speed value.
        
        Args:
            speed (float): Current playback speed
        """
        # Format the speed text
        self.setText(f"{speed:.2f}×")
        
        # Reset opacity to fully visible
        self.opacity_effect.setOpacity(1.0)
        self.fade_animation.stop()
        
        # Show the overlay
        self.show()
        self.raise_()
        
        # Restart the hide timer
        self.hide_timer.start(2000)  # 2 seconds before fading
        
    def _start_fade(self):
        """Start the fade-out animation"""
        self.fade_animation.start() 