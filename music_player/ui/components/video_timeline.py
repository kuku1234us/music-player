from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QRect

class VideoTimeline(QWidget):
    """
    A compact timeline component for video preview positioning.
    Displays a progress bar without a handle/playhead.
    Supports start/end markers for clipping.
    """
    position_changed = pyqtSignal(float) # Emits position in seconds
    marker_cleared = pyqtSignal(str)     # Emits "start" or "end" when marker is right-clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFixedHeight(24) # Compact height
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # State
        self._duration = 0.0
        self._position = 0.0
        self._is_dragging = False
        
        # Clipping state
        self._clip_start: float | None = None
        self._clip_end: float | None = None

        # Visual properties
        self.track_height = 6
        self.track_color = QColor("#606060")        # Active track color (Lighter gray for visibility)
        self.dimmed_color = QColor("#202020")       # Dimmed/Excluded track color (Almost black)
        self.progress_color = QColor(255, 140, 0)   # Orange
        self.dimmed_progress_color = QColor(100, 55, 0) # Dark/Dimmed Orange for clipped-away progress
        self.marker_color = QColor(255, 140, 0)     # Orange (Same as progress)
        self.marker_width = 4
        self.marker_hit_radius = 8                  # Pixel radius for hit testing

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

    def set_clip_start(self, val: float | None):
        if val != self._clip_start:
            self._clip_start = val
            self.update()

    def set_clip_end(self, val: float | None):
        if val != self._clip_end:
            self._clip_end = val
            self.update()

    def get_position(self) -> float:
        return self._position

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Calculate track geometry
        track_y = (self.height() - self.track_height) // 2
        width = self.width()
        
        if width <= 0 or self._duration <= 0:
            return
            
        has_start = self._clip_start is not None
        has_end = self._clip_end is not None

        start_sec = max(0.0, min(self._clip_start, self._duration)) if has_start else 0.0
        end_sec = max(0.0, min(self._clip_end, self._duration)) if has_end else self._duration
        if end_sec < start_sec: end_sec = start_sec # Safety

        start_x = int((start_sec / self._duration) * width)
        end_x = int((end_sec / self._duration) * width)

        # 1. Draw Background
        # Draw full dimmed background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.dimmed_color)
        bg_rect = QRect(0, track_y, width, self.track_height)
        painter.drawRoundedRect(bg_rect, self.track_height // 2, self.track_height // 2)
        
        # Draw active region on top if clips exist, or if no clips (full width)
        if end_x > start_x:
            active_rect = QRect(start_x, track_y, end_x - start_x, self.track_height)
            painter.setBrush(self.track_color)
            painter.drawRoundedRect(active_rect, self.track_height // 2, self.track_height // 2)

        # 2. Draw Progress (Orange)
        if self._position > 0:
            ratio = self._position / self._duration
            progress_width = int(width * ratio)
            
            if progress_width > 0:
                # We need to draw progress in potentially 3 segments: 
                # Before Start (Dimmed), Inside Active (Bright), After End (Dimmed)
                
                # Segment 1: 0 to min(progress_width, start_x) -> Dimmed
                if progress_width > 0:
                    w1 = min(progress_width, start_x)
                    if w1 > 0:
                         painter.setBrush(self.dimmed_progress_color)
                         r1 = QRect(0, track_y, w1, self.track_height)
                         painter.drawRoundedRect(r1, self.track_height // 2, self.track_height // 2)
                
                # Segment 2: start_x to min(progress_width, end_x) -> Bright
                if progress_width > start_x:
                    w2_end = min(progress_width, end_x)
                    w2 = w2_end - start_x
                    if w2 > 0:
                         painter.setBrush(self.progress_color)
                         r2 = QRect(start_x, track_y, w2, self.track_height)
                         # Note: RoundedRect might look weird if segments touch. 
                         # Ideally we'd use drawRect for inner joins, but let's stick to rounded for simplicity/style.
                         # Or just overdraw: Draw full dimmed first, then overwrite active part?
                         # Let's try overwriting strategy for cleaner code.
                         painter.drawRoundedRect(r2, self.track_height // 2, self.track_height // 2)

                # Segment 3: end_x to progress_width -> Dimmed
                if progress_width > end_x:
                    w3 = progress_width - end_x
                    if w3 > 0:
                         painter.setBrush(self.dimmed_progress_color)
                         r3 = QRect(end_x, track_y, w3, self.track_height)
                         painter.drawRoundedRect(r3, self.track_height // 2, self.track_height // 2)
                
                # Indicator line at end of progress (always white)
                painter.setBrush(Qt.GlobalColor.white)
                indicator_rect = QRect(progress_width - 2, track_y - 2, 4, self.track_height + 4)
                painter.drawRoundedRect(indicator_rect, 2, 2)

        # 3. Draw Markers (Orange)
        painter.setBrush(self.marker_color)
        
        if has_start:
            # Draw marker
            m_rect = QRect(start_x - 2, track_y - 4, 4, self.track_height + 8)
            painter.drawRoundedRect(m_rect, 2, 2)
            
        if has_end:
            m_rect = QRect(end_x - 2, track_y - 4, 4, self.track_height + 8)
            painter.drawRoundedRect(m_rect, 2, 2)

    def mousePressEvent(self, event):
        if self._duration <= 0:
            return

        x = event.position().x()
        width = self.width()

        if event.button() == Qt.MouseButton.RightButton:
            # Hit test for markers to clear them
            if self._check_marker_hit(x, self._clip_start):
                self.marker_cleared.emit("start")
                return
            if self._check_marker_hit(x, self._clip_end):
                self.marker_cleared.emit("end")
                return

        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._update_from_mouse(x)

    def _check_marker_hit(self, x: float, marker_sec: float | None) -> bool:
        if marker_sec is None:
            return False
        
        # Convert sec to pixels
        mx = (marker_sec / self._duration) * self.width()
        
        # Check distance
        return abs(x - mx) <= self.marker_hit_radius

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
