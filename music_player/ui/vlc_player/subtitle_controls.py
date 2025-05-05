"""
Subtitle control components for video playback.
"""
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QMenu
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtSvg import QSvgRenderer
from io import BytesIO

from qt_base_app.theme.theme_manager import ThemeManager


class SubtitleToggleButton(QPushButton):
    """
    Button to toggle subtitles on/off with eye icon.
    """
    
    clicked = pyqtSignal()  # Signal emitted when button is clicked
    
    # SVG for eye icon (visible)
    EYE_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"></path><circle cx="12" cy="12" r="3"></circle></svg>"""
    
    # SVG for eye-off icon (hidden)
    EYE_OFF_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#52525b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"></path><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"></path><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"></path><line x1="2" x2="22" y1="2" y2="22"></line></svg>"""
    
    def __init__(self, parent=None, size=24):
        super().__init__(parent)
        self.size = size
        
        # Whether subtitles are currently enabled
        self._subtitles_enabled = False
        
        # Create SVG renderers for the icons
        self.eye_renderer = QSvgRenderer(bytes(self.EYE_ICON_SVG, encoding='utf-8'))
        self.eye_off_renderer = QSvgRenderer(bytes(self.EYE_OFF_ICON_SVG, encoding='utf-8'))
        
        # Set button properties
        self.setFixedSize(size, size)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Initialize with subtitles disabled
        self.update_icon()
        
        # Set tooltip
        self.setToolTip("Toggle Subtitles")
        
        # Set stylesheet to ensure proper background
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
            }
        """)
        
    def set_enabled_state(self, enabled):
        """Set the button state (whether subtitles are currently enabled)."""
        if self._subtitles_enabled != enabled:
            self._subtitles_enabled = enabled
            self.update_icon()
            
    def update_icon(self):
        """Update the button icon based on current state."""
        # Create a pixmap to render the SVG
        pixmap = QPixmap(self.size, self.size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        # Get the right renderer based on state
        renderer = self.eye_renderer if self._subtitles_enabled else self.eye_off_renderer
        
        # Set up a painter for the pixmap
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Use renderer directly without setting color in the painter
        # The SVG already has stroke defined
        renderer.render(painter)
        painter.end()
        
        # Set the icon
        self.setIcon(QIcon(pixmap))
        self.setIconSize(QSize(self.size, self.size))
        
    def mousePressEvent(self, event):
        """Handle mouse press to emit the clicked signal."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Toggle state locally
            self._subtitles_enabled = not self._subtitles_enabled
            self.update_icon()
            # Emit signal
            self.clicked.emit()
        super().mousePressEvent(event)


class SubtitleLanguageLabel(QLabel):
    """
    Label displaying the current subtitle language code.
    Clicking opens a context menu with all available subtitle tracks.
    """
    
    clicked = pyqtSignal()  # Signal emitted when label is clicked (legacy)
    language_selected = pyqtSignal(int)  # Signal emitted when a language is selected from menu (track_id)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Initialize with no language
        self._language = ""
        self._has_subtitles = False
        self._subtitle_tracks = []
        
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
        self.setToolTip("Click to select subtitle language")
        
        # Hide initially
        self.hide()
        
    def set_language(self, language_code="", has_subtitles=False):
        """
        Set the displayed language code and visibility.
        
        Args:
            language_code (str): Two-letter language code (e.g., "EN")
            has_subtitles (bool): Whether subtitles are available
        """
        self._language = language_code.upper() if language_code else ""
        self._has_subtitles = has_subtitles
        
        # Update text and visibility
        if self._has_subtitles:
            self.setText(self._language if self._language else "SUB")
            self.show()
            # Set color to normal (white)
            self.setStyleSheet("""
                background-color: #3c3c3c;
                color: white;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                padding: 2px;
            """)
        else:
            self.hide()
            
    def update_enabled_state(self, is_enabled):
        """Update the label styling based on whether subtitles are enabled"""
        if self._has_subtitles:
            # If subtitles are available but disabled, use muted text color
            if not is_enabled:
                muted_color = self.theme_manager.get_color('text', 'muted')
                self.setStyleSheet(f"""
                    background-color: #3c3c3c;
                    color: {muted_color};
                    border-radius: 3px;
                    font-size: 10px;
                    font-weight: bold;
                    padding: 2px;
                """)
            else:
                # If subtitles are enabled, use normal (white) text
                self.setStyleSheet("""
                    background-color: #3c3c3c;
                    color: white;
                    border-radius: 3px;
                    font-size: 10px;
                    font-weight: bold;
                    padding: 2px;
                """)
                
    def set_subtitle_tracks(self, tracks):
        """Set the available subtitle tracks for the context menu."""
        self._subtitle_tracks = tracks
        
    def mousePressEvent(self, event):
        """Handle mouse press to show context menu with available subtitle tracks."""
        if event.button() == Qt.MouseButton.LeftButton and self._has_subtitles:
            self._show_subtitle_menu(event.globalPosition().toPoint())
        super().mousePressEvent(event)
        
    def _extract_clean_track_name(self, track, include_language=True):
        """
        Extract a clean display name for the subtitle track.
        
        Args:
            track (dict): The subtitle track dictionary
            include_language (bool): Whether to include language code in brackets
            
        Returns:
            str: A clean display name for the menu
        """
        # Start with track ID as fallback
        track_id = track['id']
        
        # First try the display_name if available
        display_name = track.get('display_name', '')
        
        # If not, try to decode the name if it's bytes
        if not display_name and 'name' in track:
            name = track['name']
            if isinstance(name, bytes):
                try:
                    display_name = name.decode('utf-8')
                except Exception:
                    try:
                        display_name = name.decode('latin-1')
                    except Exception:
                        display_name = ""
            else:
                display_name = name
                
        # Clean up the display name
        if display_name:
            # Remove "Track X - " prefix if present
            import re
            cleaned = re.sub(r'^Track\s+\d+\s*[\-:]\s*', '', display_name)
            # Remove brackets but preserve language codes
            lang_code = ""
            lang_match = re.search(r'\[([a-zA-Z]{2,3})\]', cleaned)
            if lang_match:
                lang_code = lang_match.group(1).upper()
                cleaned = re.sub(r'\[[^\]]*\]', '', cleaned)
            
            # Trim spaces
            cleaned = cleaned.strip()
            
            # If there's a language code and we want to include it, add it to the end
            if lang_code and include_language:
                if cleaned:
                    return f"{cleaned} [{lang_code}]"
                else:
                    return lang_code
                    
            # Return cleaned name or original if cleaning removed everything
            return cleaned if cleaned else display_name
        
        # No usable name found, return generic track name
        return f"Track {track_id}"
            
    def _show_subtitle_menu(self, position):
        """Show the context menu with all available subtitle tracks."""
        if not self._subtitle_tracks:
            # If no tracks available, just emit the legacy clicked signal
            self.clicked.emit()
            return
            
        # Create the context menu
        menu = QMenu(self)
        
        # Add action to disable subtitles
        disable_action = menu.addAction("Disable Subtitles")
        disable_action.triggered.connect(lambda: self.language_selected.emit(-1))
        menu.addSeparator()
        
        # Add an action for each subtitle track
        for track in self._subtitle_tracks:
            if track['id'] < 0:
                # Skip the "Disable" track as we already added it
                continue
                
            # Get a clean display name for the track
            display_name = self._extract_clean_track_name(track)
            
            # Create the action
            action = menu.addAction(display_name)
            track_id = track['id']
            action.triggered.connect(lambda checked=False, tid=track_id: self.language_selected.emit(tid))
        
        # Show the menu at the specified position
        menu.exec(position)


class SubtitleControls(QWidget):
    """
    Widget combining subtitle toggle button and language label.
    """
    
    toggle_subtitles = pyqtSignal()  # Signal to toggle subtitles on/off
    next_subtitle = pyqtSignal()     # Signal to cycle to next subtitle track (legacy)
    subtitle_selected = pyqtSignal(int)  # Signal emitted when a subtitle track is selected from menu
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Create components
        self.toggle_button = SubtitleToggleButton(self)
        self.language_label = SubtitleLanguageLabel(self)
        
        # Set up layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)  # Spacing between icon and label
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.language_label)
        
        # Connect signals
        self.toggle_button.clicked.connect(self.toggle_subtitles)
        self.language_label.clicked.connect(self.next_subtitle)  # Legacy support
        self.language_label.language_selected.connect(self.subtitle_selected)
        
        # Hide initially
        self.hide()
        
    def set_state(self, has_subtitles, is_enabled, language="", tracks=None):
        """
        Update the control's state.
        
        Args:
            has_subtitles (bool): Whether subtitles are available
            is_enabled (bool): Whether subtitles are enabled
            language (str): Language code of current subtitles
            tracks (list, optional): List of available subtitle tracks
        """
        # Update components
        self.toggle_button.set_enabled_state(is_enabled)
        self.language_label.set_language(language, has_subtitles)
        self.language_label.update_enabled_state(is_enabled)
        
        # Update subtitle tracks for the context menu if provided
        if tracks is not None:
            self.language_label.set_subtitle_tracks(tracks)
        
        # Show/hide the entire control based on subtitle availability
        self.setVisible(has_subtitles) 