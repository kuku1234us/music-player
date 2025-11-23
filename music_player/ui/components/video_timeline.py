from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QRect

class VideoTimeline(QWidget):
    """
    A compact timeline component for video preview positioning.
    Displays a progress bar without a handle/playhead.
    """
    position_changed = pyqtSignal(float) # Emits position in seconds

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFixedHeight(24) # Compact height
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # State
        self._duration = 0.0
        self._position = 0.0
        self._is_dragging = False

        # Visual properties (matching CustomSlider style)
        self.track_height = 6
        self.track_color = QColor("#505050")
        self.progress_color = QColor(255, 140, 0) # Orange
        self.hover_color = QColor(255, 160, 50) # Lighter orange for hover

    def set_duration(self, duration: float):
        """Set total duration in seconds."""
        if duration != self._duration:
            self._duration = max(0.0, duration)
            self.update()

    def set_position(self, position: float):
        """Set current position in seconds."""
        pos = max(0.0, min(position, self._duration))
        if pos != self._position:
            self._position = pos
            self.update()

    def get_position(self) -> float:
        return self._position

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Calculate track geometry
        track_y = (self.height() - self.track_height) // 2
        width = self.width()
        
        # Draw background track
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.track_color)
        track_rect = QRect(0, track_y, width, self.track_height)
        painter.drawRoundedRect(track_rect, self.track_height // 2, self.track_height // 2)

        # Draw progress
        if self._duration > 0 and self._position > 0:
            ratio = self._position / self._duration
            progress_width = int(width * ratio)
            
            if progress_width > 0:
                painter.setBrush(self.progress_color)
                progress_rect = QRect(0, track_y, progress_width, self.track_height)
                painter.drawRoundedRect(progress_rect, self.track_height // 2, self.track_height // 2)
                
                # Optional: Draw a small indicator line at the end
                painter.setBrush(Qt.GlobalColor.white)
                indicator_rect = QRect(progress_width - 2, track_y - 2, 4, self.track_height + 4)
                painter.drawRoundedRect(indicator_rect, 2, 2)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._update_from_mouse(event.position().x())

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            self._update_from_mouse(event.position().x())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False

    def _update_from_mouse(self, x: float):
        if self._duration <= 0:
            return

        width = self.width()
        if width <= 0:
            return

        ratio = max(0.0, min(1.0, x / width))
        new_pos = ratio * self._duration
        
        if new_pos != self._position:
            self.set_position(new_pos)
            self.position_changed.emit(new_pos)

