"""
Player timeline component for showing track progress and time information.
"""
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from qt_base_app.models.logger import Logger

from .custom_slider import CustomSlider
from music_player.models.ClippingManager import ClippingManager
from typing import Optional, List, Tuple


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
        self._current_media_path: Optional[str] = None
        
        # UI Components
        self.position_slider = CustomSlider(self)
        self.current_time_label = QLabel("00:00:00", self)
        self.total_time_label = QLabel("00:00:00", self)
        
        self._setup_ui()
        self._connect_signals()
        
    def _setup_ui(self):
        """Set up the timeline UI layout and styling"""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 0, 10, 0)
        main_layout.setSpacing(10)
        
        # Configure time labels
        time_font = QFont()
        time_font.setPointSize(9)

        self.current_time_label.setFont(time_font)
        self.total_time_label.setFont(time_font)
        
        # Position slider
        self.position_slider.setRange(0, 1000)
        
        # Add widgets to layout
        main_layout.addWidget(self.current_time_label)
        main_layout.addWidget(self.position_slider, 1)
        main_layout.addWidget(self.total_time_label)
        
        self.setLayout(main_layout)
        
        # Set styles
        self.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
            }
        """)
        
        # Connect to ClippingManager and CustomSlider marker clicks
        self.clipping_manager = ClippingManager.instance()
        self.clipping_manager.markers_updated.connect(self._on_clipping_markers_updated)
        self.position_slider.begin_marker_clicked.connect(self._on_begin_marker_badge_clicked)
        self.position_slider.end_marker_clicked.connect(self._on_end_marker_badge_clicked)
        
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
        Logger.instance().debug(caller="PlayerTimeline", msg=f"[PlayerTimeline] set_duration called with: {duration_ms} ms")
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

    # Methods for handling clipping marker updates and interactions
    def set_current_media_path(self, media_path: Optional[str]):
        """
        Sets the path of the media currently loaded in the player.
        This is used to ensure markers are only shown for the relevant media.
        """
        if self._current_media_path != media_path:
            self._current_media_path = media_path
            # When media path changes, clear visual markers from the slider immediately
            # The ClippingManager.markers_updated signal will also fire soon after
            # its set_media is called, which will provide the definitive state.
            self.position_slider.set_clipping_markers(None, [])

    def _on_clipping_markers_updated(self, media_path: str, pending_begin_ms: Optional[int], segments_ms_list: List[Tuple[int, int]]):
        """
        Slot for markers_updated signal from ClippingManager.
        Updates the visual markers on the CustomSlider for multi-segment display.
        """
        if self._current_media_path == media_path and self._current_media_path != "": # Ensure it's for the active media
            pending_begin_percent: Optional[float] = None
            segments_percent_list: List[Tuple[float, float]] = []

            if self.duration_ms > 0:
                if pending_begin_ms is not None:
                    pending_begin_percent = pending_begin_ms / self.duration_ms
                
                for start_ms, end_ms in segments_ms_list:
                    start_percent = start_ms / self.duration_ms
                    end_percent = end_ms / self.duration_ms
                    segments_percent_list.append((start_percent, end_percent))
            
            Logger.instance().debug(caller="player_timeline", msg=f"[PlayerTimeline DEBUG] _on_clipping_markers_updated: Calling set_clipping_markers with pending_percent={pending_begin_percent}, segments_percent={segments_percent_list}")
            self.position_slider.set_clipping_markers(pending_begin_percent, segments_percent_list)
        elif media_path == "" and (self._current_media_path == "" or self._current_media_path is None) : # Case where media was cleared globally
            Logger.instance().debug(caller="player_timeline", msg=f"[PlayerTimeline DEBUG] _on_clipping_markers_updated: Clearing markers (media_path empty, current_media_path empty/None)")
            self.position_slider.set_clipping_markers(None, []) # Clear with empty list
        elif self._current_media_path != media_path:
            # If the update is for a different media path (e.g. stale signal) or 
            # if current media path is now empty but update is for an old one, clear markers.
            Logger.instance().debug(caller="player_timeline", msg=f"[PlayerTimeline DEBUG] _on_clipping_markers_updated: Clearing markers (media_path mismatch or stale)")
            self.position_slider.set_clipping_markers(None, []) # Clear with empty list

    def _on_begin_marker_badge_clicked(self):
        """Handles click on the begin marker badge.
        NOTE: For multi-segment, direct removal of individual segment start points
        via timeline click is currently deferred. Use Shift+B / Shift+E / Shift+Del hotkeys.
        """
        # self.clipping_manager.clear_pending_begin_marker() # Example if it were to clear pending
        pass

    def _on_end_marker_badge_clicked(self):
        """Handles click on the end marker badge.
        NOTE: For multi-segment, direct removal of individual segment end points
        via timeline click is currently deferred. Use Shift+B / Shift+E / Shift+Del hotkeys.
        """
        # self.clipping_manager.clear_last_segment() # Example if it were to clear last segment
        pass 