"""
Custom PlayButton component for the music player application.
Features a gradient background, inner circle, and play/pause icons.
"""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QLinearGradient, QPainterPath
from PyQt6.QtCore import Qt, QRectF, QSize, pyqtSignal, QPoint


class PlayButton(QWidget):
    """
    Custom play button component with gradient background and dynamic play/pause icon.
    """
    
    # Signal emitted when button is clicked
    clicked = pyqtSignal()
    
    def __init__(self, parent=None, size=40):
        super().__init__(parent)
        self.setFixedSize(size, size)
        
        # State
        self.is_playing = False
        self.is_hovered = False
        self.is_pressed = False
        
        # Colors
        self.gradient_start_color = QColor(255, 140, 0)  # Orange from timeline
        self.gradient_end_color = QColor('#6f2e84')      # Purple
        self.inner_circle_color = QColor('#2f2e2d')      # Dark gray
        self.inner_circle_hover_color = QColor('#3f3e3d') # Lighter gray for hover
        self.icon_color = QColor(255, 255, 255)          # White for the icon
        
        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
        
    def sizeHint(self):
        """Provide a size hint for the widget"""
        return QSize(40, 40)
        
    def paintEvent(self, event):
        """Paint the button with all three layers"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        size = min(self.width(), self.height())
        rect = QRectF(0, 0, size, size)
        
        # Draw outer circle with gradient
        self._draw_gradient_circle(painter, rect)
        
        # Draw inner circle
        inner_rect = rect.adjusted(size * 0.15, size * 0.15, -size * 0.15, -size * 0.15)
        self._draw_inner_circle(painter, inner_rect)
        
        # Draw play/pause icon
        icon_rect = inner_rect.adjusted(size * 0.12, size * 0.12, -size * 0.12, -size * 0.12)
        if self.is_playing:
            self._draw_pause_icon(painter, icon_rect)
        else:
            self._draw_play_icon(painter, icon_rect)
    
    def _draw_gradient_circle(self, painter, rect):
        """Draw the outer circle with gradient"""
        # Create gradient
        gradient = QLinearGradient(
            rect.topLeft(), 
            rect.bottomRight()
        )
        gradient.setColorAt(0, self.gradient_start_color)
        gradient.setColorAt(1, self.gradient_end_color)
        
        # Draw circle
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(rect)
    
    def _draw_inner_circle(self, painter, rect):
        """Draw the inner circle"""
        painter.setPen(Qt.PenStyle.NoPen)
        
        # Use a lighter color when hovered
        if self.is_hovered:
            painter.setBrush(QBrush(self.inner_circle_hover_color))
        else:
            painter.setBrush(QBrush(self.inner_circle_color))
            
        painter.drawEllipse(rect)
    
    def _draw_play_icon(self, painter, rect):
        """Draw the play triangle with rounded corners"""
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.icon_color))
        
        # Calculate center and dimensions
        center_x = rect.center().x()
        center_y = rect.center().y()
        width = rect.width()
        height = rect.height()
        
        # Make the triangle 20% smaller by scaling the rect
        scaled_rect = rect.adjusted(
            width * 0.1,   # Add 10% to left
            height * 0.1,  # Add 10% to top
            -width * 0.1,  # Subtract 10% from right
            -height * 0.1  # Subtract 10% from bottom
        )
        
        # Recalculate dimensions for the smaller area
        scaled_width = scaled_rect.width()
        scaled_height = scaled_rect.height()
        
        # Adjust placement for visual balance (play triangle looks better when shifted right slightly)
        offset_x = scaled_width * 0.05
        
        # Define pen for stroke-based rounded corners
        corner_radius = scaled_width * 0.15
        pen = QPen(self.icon_color, corner_radius * 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        
        # Create points for the triangle - classic play shape
        points = [
            QPoint(int(scaled_rect.left() + scaled_width * 0.25 + offset_x), int(scaled_rect.top() + scaled_height * 0.2)),  # Top point
            QPoint(int(scaled_rect.left() + scaled_width * 0.25 + offset_x), int(scaled_rect.top() + scaled_height * 0.8)),  # Bottom point
            QPoint(int(scaled_rect.right() - scaled_width * 0.15), int(center_y))                                           # Right point
        ]
        
        # Draw the triangle with the rounded corner pen
        painter.setPen(pen)
        painter.drawPolygon(points)
        
        # Fill the triangle (the stroke alone doesn't fill the shape)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(points)
    
    def _draw_pause_icon(self, painter, rect):
        """Draw two parallel bars for pause icon"""
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.icon_color))
        
        # Calculate dimensions for two bars
        bar_width = rect.width() * 0.25
        bar_spacing = rect.width() * 0.2
        bar_height = rect.height() * 0.7
        
        # Left bar
        left_bar = QRectF(
            rect.left() + (rect.width() - bar_width * 2 - bar_spacing) / 2,
            rect.top() + (rect.height() - bar_height) / 2,
            bar_width,
            bar_height
        )
        
        # Right bar
        right_bar = QRectF(
            left_bar.right() + bar_spacing,
            left_bar.top(),
            bar_width,
            bar_height
        )
        
        # Draw rounded rectangles for pause bars
        painter.drawRoundedRect(left_bar, bar_width * 0.3, bar_width * 0.3)
        painter.drawRoundedRect(right_bar, bar_width * 0.3, bar_width * 0.3)
    
    def mousePressEvent(self, event):
        """Handle mouse press event"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_pressed = True
            self.update()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release event"""
        if event.button() == Qt.MouseButton.LeftButton and self.is_pressed:
            self.is_pressed = False
            
            # Check if mouse is still inside the button
            if self.rect().contains(event.position().toPoint()):
                # Do NOT toggle state here - only emit the signal
                # Let the MainPlayer determine the appropriate state
                self.clicked.emit()
                
            self.update()
    
    def enterEvent(self, event):
        """Handle mouse enter event"""
        self.is_hovered = True
        self.update()
        
    def leaveEvent(self, event):
        """Handle mouse leave event"""
        self.is_hovered = False
        self.is_pressed = False
        self.update()
    
    def set_playing(self, is_playing):
        """Set the current state of the button"""
        if self.is_playing != is_playing:
            self.is_playing = is_playing
            self.update() 