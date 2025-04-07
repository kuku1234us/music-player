"""
CustomSlider component for the music player application.
Can be used for timeline and volume controls.
"""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QPoint, QRect

from music_player.ui.vlc_player.play_head import PlayHead


class CustomSlider(QWidget):
    """
    Custom slider implementation with PlayHead component.
    Implements similar API to QSlider for easy integration.
    """
    
    # Signals similar to QSlider
    valueChanged = pyqtSignal(int)
    sliderPressed = pyqtSignal()
    sliderReleased = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Create play head widget
        self.play_head = PlayHead(self)
        
        # Slider properties
        self.minimum = 0
        self.maximum = 100
        self.current_value = 0
        self.pressed = False
        
        # Track visual properties
        self.track_height = 4
        self.track_color = QColor(50, 50, 50)  # Dark gray
        self.progress_color = QColor(255, 140, 0)  # Orange
        self.setMinimumHeight(20)
        
        # Set focus policy to allow keyboard control
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def setMinimum(self, value):
        """Set minimum value of the slider"""
        self.minimum = value
        self.updatePlayheadPosition()
        
    def setMaximum(self, value):
        """Set maximum value of the slider"""
        self.maximum = value
        self.updatePlayheadPosition()
        
    def setRange(self, minimum, maximum):
        """Set range of the slider"""
        self.minimum = minimum
        self.maximum = maximum
        self.updatePlayheadPosition()
        
    def setValue(self, value):
        """Set current value of the slider"""
        if self.minimum <= value <= self.maximum and value != self.current_value:
            self.current_value = value
            self.updatePlayheadPosition()
            self.valueChanged.emit(value)
            self.update()
            
    def value(self):
        """Get the current value of the slider"""
        return self.current_value
            
    def updatePlayheadPosition(self):
        """Update position of the play head based on current value"""
        if self.maximum == self.minimum:
            position = 0
        else:
            range_width = self.width() - self.play_head.width()
            position = int(((self.current_value - self.minimum) / (self.maximum - self.minimum)) * range_width)
        
        # Center the playhead vertically on the track
        vertical_position = (self.height() - self.play_head.height()) // 2
        self.play_head.move(position, vertical_position)
        
    def paintEvent(self, event):
        """Paint the slider track and progress"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate track position
        track_y = (self.height() - self.track_height) // 2
        
        # Draw track background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.track_color)
        track_rect = QRect(
            0, 
            track_y, 
            self.width(), 
            self.track_height
        )
        painter.drawRoundedRect(track_rect, self.track_height // 2, self.track_height // 2)
        
        # Draw progress (filled part)
        if self.current_value > self.minimum:
            progress_width = 0
            if self.maximum > self.minimum:
                playhead_center = self.play_head.x() + self.play_head.width() // 2
                progress_width = playhead_center
            
            if progress_width > 0:
                painter.setBrush(self.progress_color)
                progress_rect = QRect(0, track_y, progress_width, self.track_height)
                painter.drawRoundedRect(progress_rect, self.track_height // 2, self.track_height // 2)
    
    def resizeEvent(self, event):
        """Handle resize events to update playhead position"""
        super().resizeEvent(event)
        self.updatePlayheadPosition()
        
    def mousePressEvent(self, event):
        """Handle mouse press events"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.pressed = True
            self.sliderPressed.emit()
            self.updateValueFromPosition(event.position().toPoint())
            
    def mouseMoveEvent(self, event):
        """Handle mouse move events"""
        if self.pressed:
            self.updateValueFromPosition(event.position().toPoint())
            
    def mouseReleaseEvent(self, event):
        """Handle mouse release events"""
        if event.button() == Qt.MouseButton.LeftButton and self.pressed:
            self.pressed = False
            self.sliderReleased.emit()
            
    def updateValueFromPosition(self, position):
        """Update slider value based on mouse position"""
        if self.width() == 0:
            return
            
        # Calculate click position adjusting for playhead width
        x = max(0, min(position.x(), self.width() - 1))
        playhead_half_width = self.play_head.width() // 2
        adjusted_width = self.width() - playhead_half_width * 2
        adjusted_x = x - playhead_half_width
        
        # Calculate new value
        if adjusted_width <= 0:
            new_value = self.minimum
        else:
            new_value = int(self.minimum + (adjusted_x / adjusted_width) * (self.maximum - self.minimum))
            
        # Bound value to range
        new_value = max(self.minimum, min(new_value, self.maximum))
        
        # Set value if changed
        if new_value != self.current_value:
            self.setValue(new_value)
    
    def sizeHint(self):
        """Provide a size hint for the widget"""
        return QSize(200, 20) 