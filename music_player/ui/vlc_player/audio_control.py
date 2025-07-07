"""
Audio control components for video playback.
"""
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QMenu
from PyQt6.QtCore import Qt, pyqtSignal
from typing import List, Dict, Any

from qt_base_app.theme.theme_manager import ThemeManager


class AudioLanguageLabel(QLabel):
    """
    Label displaying the current audio language code.
    Clicking opens a context menu with all available audio tracks.
    """
    
    audio_track_selected = pyqtSignal(int)  # Signal emitted when a language is selected from menu (track_id)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Initialize with no language
        self._language = ""
        self._has_multiple_tracks = False
        self._audio_tracks = []
        
        # Get theme manager
        self.theme_manager = ThemeManager.instance()
        
        # Set fixed size
        self.setFixedSize(30, 20)
        
        # Center text
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Style
        self.setStyleSheet("""
            background-color: #3c3c3c;
            color: white;
            border-radius: 3px;
            font-size: 10px;
            font-weight: bold;
            padding: 2px;
        """)
        
        # Set cursor
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Set tooltip
        self.setToolTip("Click to select audio track")
        
        # Hide initially
        self.hide()
        
    def set_language(self, language_code="", has_multiple_tracks=False):
        """
        Set the displayed language code and visibility.
        
        Args:
            language_code (str): Two-letter language code (e.g., "EN")
            has_multiple_tracks (bool): Whether multiple audio tracks are available
        """
        self._language = language_code.upper() if language_code else "AUD"
        self._has_multiple_tracks = has_multiple_tracks
        
        # Update text and visibility
        if self._has_multiple_tracks:
            self.setText(self._language)
            self.show()
        else:
            self.hide()
            
    def set_audio_tracks(self, tracks: List[Dict[str, Any]]):
        """Set the available audio tracks for the context menu."""
        self._audio_tracks = tracks
        
    def mousePressEvent(self, event):
        """Handle mouse press to show context menu with available audio tracks."""
        if event.button() == Qt.MouseButton.LeftButton and self._has_multiple_tracks:
            self._show_audio_menu(event.globalPosition().toPoint())
        super().mousePressEvent(event)
        
    def _extract_clean_track_name(self, track: Dict[str, Any]) -> str:
        """
        Extract a clean display name for the audio track.
        
        Args:
            track (dict): The audio track dictionary
            
        Returns:
            str: A clean display name for the menu
        """
        track_id = track.get('id', -1)
        name = track.get('name', f"Track {track_id}")

        if isinstance(name, bytes):
            try:
                name = name.decode('utf-8')
            except UnicodeDecodeError:
                name = name.decode('latin-1', errors='ignore')

        # Clean up common prefixes
        import re
        cleaned = re.sub(r'^(Track\s*\d+\s*-\s*)?', '', name, flags=re.IGNORECASE).strip()
        
        return cleaned if cleaned else f"Track {track_id}"
            
    def _show_audio_menu(self, position):
        """Show the context menu with all available audio tracks."""
        if not self._audio_tracks:
            return
            
        menu = QMenu(self)
        
        for track in self._audio_tracks:
            track_id = track.get('id', -1)
            if track_id < 0:
                continue

            display_name = self._extract_clean_track_name(track)
            action = menu.addAction(display_name)
            
            action.triggered.connect(lambda checked=False, tid=track_id: self.audio_track_selected.emit(tid))
        
        menu.exec(position)


class AudioControls(QWidget):
    """
    Widget combining audio language label and selection menu.
    """
    
    audio_track_selected = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.language_label = AudioLanguageLabel(self)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.language_label)
        
        self.language_label.audio_track_selected.connect(self.audio_track_selected)
        
        self.hide()
        
    def set_state(self, has_multiple_tracks: bool, current_language: str = "", tracks: List[Dict[str, Any]] = None):
        """
        Update the control's state.
        
        Args:
            has_multiple_tracks (bool): Whether multiple audio tracks are available
            current_language (str): Language code of current audio track
            tracks (list, optional): List of available audio tracks
        """
        self.language_label.set_language(current_language, has_multiple_tracks)
        
        if tracks is not None:
            self.language_label.set_audio_tracks(tracks)
        
        self.setVisible(has_multiple_tracks) 