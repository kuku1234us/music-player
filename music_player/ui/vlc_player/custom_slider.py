"""
CustomSlider component for the music player application.
Can be used for timeline and volume controls.
"""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QPoint, QRect
from typing import Optional, List, Tuple

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
    
    # --- NEW Signals for clipping markers ---
    begin_marker_clicked = pyqtSignal()
    end_marker_clicked = pyqtSignal()
    # ------------------------------------
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True) # Enable mouse tracking for hover effects
        
        # Create play head widget
        self.play_head = PlayHead(self)
        
        # Slider properties
        self.minimum = 0
        self.maximum = 100
        self.current_value = 0
        self.pressed = False
        
        # Track visual properties
        self.track_height = 6
        self.track_color = QColor("#505050")
        self.progress_color = QColor(255, 140, 0) # Original Orange
        self.setMinimumHeight(20)
        
        # --- NEW Properties for clipping markers ---
        # For single begin/end markers (visual representation)
        self.begin_marker_percent: Optional[float] = None
        self.end_marker_percent: Optional[float] = None # This will be None for multi-segment logic
        self.begin_marker_x: Optional[int] = None
        self.end_marker_x: Optional[int] = None
        self.begin_marker_rect: Optional[QRect] = None
        self.end_marker_rect: Optional[QRect] = None
        
        # For multi-segment markers
        self.pending_begin_marker_percent: Optional[float] = None
        self.segments_percent: List[Tuple[float, float]] = []

        self.marker_badge_width = 8 # Pixel width of the marker badge
        self.marker_badge_height = 16 # Pixel height of the marker badge
        self.begin_marker_color = QColor(255, 165, 0) # Lighter Orange
        self.end_marker_color = QColor(204, 102, 0)   # Darker Orange
        self.excluded_region_color = QColor(0, 0, 0, 80) # Semi-transparent black
        # -----------------------------------------
        
        # Set focus policy to allow keyboard control
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Ensure playhead is raised above other elements
        self.play_head.raise_()
    
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

        # --- NEW: Draw clipping markers and shaded regions ---
        self._update_marker_pixel_positions() # Ensure positions are current

        # Draw shaded excluded regions
        if self.begin_marker_x is not None:
            painter.setBrush(self.excluded_region_color)
            painter.setPen(Qt.PenStyle.NoPen)
            excluded_before_rect = QRect(0, 0, self.begin_marker_x, self.height())
            painter.drawRect(excluded_before_rect)

        if self.end_marker_x is not None:
            painter.setBrush(self.excluded_region_color)
            painter.setPen(Qt.PenStyle.NoPen)
            excluded_after_rect = QRect(self.end_marker_x, 0, self.width() - self.end_marker_x, self.height())
            painter.drawRect(excluded_after_rect)

        # Draw marker badges
        badge_y = (self.height() - self.marker_badge_height) // 2
        if self.begin_marker_x is not None and self.begin_marker_rect is not None:
            painter.setBrush(self.begin_marker_color)
            painter.setPen(Qt.PenStyle.NoPen) # No border for badges
            painter.drawRect(self.begin_marker_rect)

        if self.end_marker_x is not None and self.end_marker_rect is not None:
            painter.setBrush(self.end_marker_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(self.end_marker_rect)
        # --------------------------------------------------

        # Draw actual segments
        for start_percent, end_percent in self.segments_percent:
            if start_percent is not None and end_percent is not None:
                start_x_center = int(start_percent * self.width())
                end_x_center = int(end_percent * self.width())

                # Highlight included segment region
                # Ensure start_draw_x is not greater than end_draw_x for the highlight
                highlight_start_x = max(0, start_x_center) # Highlight from the marker's effective start
                highlight_end_x = min(self.width(), end_x_center) # Highlight to the marker's effective end
                if highlight_end_x > highlight_start_x:
                    segment_highlight_color = self.progress_color.lighter(130) # A lighter shade of orange
                    painter.setBrush(segment_highlight_color)
                    segment_rect = QRect(highlight_start_x, track_y, highlight_end_x - highlight_start_x, self.track_height)
                    painter.drawRect(segment_rect) # Use simple rect for segments for now

                badge_y = (self.height() - self.marker_badge_height) // 2
                
                # Draw segment start marker (green badge)
                seg_begin_badge_left_x = max(0, start_x_center - self.marker_badge_width // 2)
                seg_begin_marker_rect = QRect(seg_begin_badge_left_x, badge_y, self.marker_badge_width, self.marker_badge_height)
                painter.setBrush(self.begin_marker_color)
                painter.drawRect(seg_begin_marker_rect)

                # Draw segment end marker (red badge)
                seg_end_badge_left_x = max(0, end_x_center - self.marker_badge_width // 2)
                # Ensure end marker doesn't overdraw start marker if too close
                if seg_end_badge_left_x < seg_begin_badge_left_x + self.marker_badge_width:
                    seg_end_badge_left_x = seg_begin_badge_left_x + self.marker_badge_width 
                seg_end_marker_rect = QRect(seg_end_badge_left_x, badge_y, self.marker_badge_width, self.marker_badge_height)
                painter.setBrush(self.end_marker_color)
                painter.drawRect(seg_end_marker_rect)

        # Draw pending begin marker (if any)
        if self.pending_begin_marker_percent is not None:
            pending_x_center = int(self.pending_begin_marker_percent * self.width())
            badge_y = (self.height() - self.marker_badge_height) // 2
            
            pending_badge_left_x = max(0, pending_x_center - self.marker_badge_width // 2)
            pending_marker_rect = QRect(pending_badge_left_x, badge_y, self.marker_badge_width, self.marker_badge_height)
            
            pending_color = QColor(255, 190, 70) # Very light orange
            painter.setBrush(pending_color)
            painter.drawRect(pending_marker_rect)

    def resizeEvent(self, event):
        """Handle resize events to update playhead position"""
        super().resizeEvent(event)
        self.updatePlayheadPosition()
        self._update_marker_pixel_positions() # NEW: Update marker positions on resize
        
    def mousePressEvent(self, event):
        """Handle mouse press events"""
        if event.button() == Qt.MouseButton.LeftButton:
            # --- NEW: Check for marker clicks first ---
            click_pos = event.position().toPoint()
            if self.begin_marker_rect and self.begin_marker_rect.contains(click_pos):
                self.begin_marker_clicked.emit()
                event.accept()
                return
            if self.end_marker_rect and self.end_marker_rect.contains(click_pos):
                self.end_marker_clicked.emit()
                event.accept()
                return
            # -----------------------------------------
            
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
        # --- MODIFIED: Use a simpler calculation for value from x, independent of playhead width for this part ---
        # playhead_half_width = self.play_head.width() // 2 
        # adjusted_width = self.width() - playhead_half_width * 2
        # adjusted_x = x - playhead_half_width
        
        # Calculate new value based on the full width of the slider bar
        if self.width() <=1: # Avoid division by zero or negative
            new_value = self.minimum
        else:
            new_value = int(self.minimum + (x / (self.width()-1)) * (self.maximum - self.minimum))
        # ----------------------------------------------------------------------------------------------------
            
        # Bound value to range
        new_value = max(self.minimum, min(new_value, self.maximum))
        
        # Set value if changed
        if new_value != self.current_value:
            self.setValue(new_value)
    
    def sizeHint(self):
        """Provide a size hint for the widget"""
        return QSize(200, 20) 

    # --- NEW Methods for clipping markers ---
    def _update_marker_pixel_positions(self):
        """Internal method to calculate and update pixel positions and rects of markers."""
        # This method might need more significant changes for multi-segment.
        # For now, ensure it doesn't crash with the new data types.
        # The actual drawing of multiple segments will be handled in paintEvent.
        # This method can be simplified or repurposed if single begin/end markers are no longer primary.

        slider_width = self.width()
        if slider_width <= 0:
            # Clear all old single-marker-related pixel data
            self.begin_marker_x = None
            self.end_marker_x = None
            self.begin_marker_rect = None
            self.end_marker_rect = None
            return

        # For multi-segment, individual segment marker positions are calculated directly in paintEvent.
        # The old self.begin_marker_x/rect and self.end_marker_x/rect might not be directly applicable
        # unless we want to represent an "overall" start/end of all segments, or if they are
        # repurposed for the "pending_begin_marker_percent".

        # Update for pending_begin_marker_percent (if we want a clickable rect for it)
        if self.pending_begin_marker_percent is not None:
            # This part is more about creating clickable regions if needed, less about drawing.
            # Drawing is now handled in paintEvent.
            # For now, let's keep it simple and not create clickable rects for pending markers here.
            pass
        
        # Clear old single marker visual state if segments are active
        if self.segments_percent:
            self.begin_marker_percent = None # Old single marker
            self.end_marker_percent = None   # Old single marker
            self.begin_marker_x = None
            self.end_marker_x = None
            self.begin_marker_rect = None
            self.end_marker_rect = None

        # If not using segments, and old single markers are somehow set (e.g. legacy call)
        # this is where the error occurred.
        # Ensure self.end_marker_percent is a number if used.
        # However, the main logic should now use self.segments_percent and self.pending_begin_marker_percent.

        # Simplified: this method won't set up self.begin_marker_x etc. for multi-segments for now.
        # paintEvent will handle it.
        
        self.update() # Trigger repaint if positions changed

    def set_clipping_markers(self, pending_begin_percent: Optional[float], segments_percent: List[Tuple[float, float]]):
        """
        Sets the visual clipping markers on the slider for multi-segment display.
        Args:
            pending_begin_percent (Optional[float]): Position of the pending begin marker (0.0 to 1.0), or None.
            segments_percent (List[Tuple[float, float]]): List of (start_percent, end_percent) tuples for defined segments.
        """
        changed = False
        if self.pending_begin_marker_percent != pending_begin_percent:
            self.pending_begin_marker_percent = pending_begin_percent
            changed = True
        
        # Make a copy for comparison if segments_percent can be mutated externally
        if self.segments_percent != list(segments_percent): # Ensure to compare with a list copy
            self.segments_percent = list(segments_percent) # Store a copy
            changed = True

        # Clear old single marker attributes as they are not used with multi-segment display
        if changed:
            self.begin_marker_percent = None
            self.end_marker_percent = None # Explicitly set to None to avoid type errors
            self._update_marker_pixel_positions()
            # self.update() # update is called by _update_marker_pixel_positions if needed
    # ------------------------------------ 