"""
PlayHead component for displaying the current position in the timeline.
"""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from PyQt6.QtCore import Qt, QSize


class PlayHead(QWidget):
    """
    Custom widget that displays two concentric circles representing the playback head.
    The outer circle is gray and the inner circle is orange.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Set fixed size for the play head
        self.setFixedSize(20, 20)
        
        # Colors for the circles
        self.outer_color = QColor(110, 110, 110, 230)  # Gray with high opacity
        self.inner_color = QColor(255, 140, 0)  # Orange (#FF8C00)
        
        # Sizes for the circles
        self.outer_size = 18  # Diameter of outer circle
        self.inner_size = 8   # Diameter of inner circle
        
    def sizeHint(self):
        """Provide a size hint for the widget"""
        return QSize(20, 20)
        
    def paintEvent(self, event):
        """Paint the concentric circles"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate center point of the widget
        center_x = self.width() / 2
        center_y = self.height() / 2
        
        # Draw outer circle (gray)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.outer_color))
        painter.drawEllipse(
            int(center_x - self.outer_size / 2),
            int(center_y - self.outer_size / 2),
            int(self.outer_size),
            int(self.outer_size)
        )
        
        # Draw inner circle (orange)
        painter.setBrush(QBrush(self.inner_color))
        painter.drawEllipse(
            int(center_x - self.inner_size / 2),
            int(center_y - self.inner_size / 2),
            int(self.inner_size),
            int(self.inner_size)
        ) 