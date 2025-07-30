from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPalette, QColor, QPainter, QPen, QBrush

class CustomToolTip(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # WA_StyledBackground is no longer needed as we are custom painting
        
        # Set padding, which will be used in paintEvent and sizeHint
        self.setContentsMargins(6, 6, 6, 6)

    def paintEvent(self, event):
        """Override paint event to draw a custom rounded rectangle background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Define colors and border properties
        background_color = QColor("#1a1a1a")
        border_color = QColor("#525252")
        border_width = 1
        border_radius = 8

        # Define the rectangle for drawing
        rect = self.rect()
        
        # Create a path for the rounded rectangle background
        path = painter.clipPath()
        path.addRoundedRect(QRectF(rect), border_radius, border_radius)
        
        # Fill the background
        painter.fillPath(path, QBrush(background_color))

        # Draw the border
        pen = QPen(border_color, border_width)
        painter.setPen(pen)
        painter.drawPath(path)
        
        # Now call the base class paintEvent to draw the text, which will respect the margins
        super().paintEvent(event)

    def show_tooltip(self, pos, text):
        self.setText(text)
        self.adjustSize() # adjustSize will now correctly account for margins
        self.move(pos)
        self.show() 