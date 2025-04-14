"""
Player Controls component for handling playback buttons.
"""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, 
    QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QFont, QPainter, QColor, QPen, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from .play_button import PlayButton
from .repeat_button import RepeatButton


class PlayerControls(QWidget):
    """
    Widget containing playback control buttons.
    """
    
    play_clicked = pyqtSignal()
    pause_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    previous_clicked = pyqtSignal()
    repeat_state_changed = pyqtSignal(str)  # Signal for repeat mode change ("no_repeat", "repeat_all", "repeat_one")
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playerControls")
        
        # Remove internal state tracking - MainPlayer is the single source of truth
        
        # SVG Definitions
        self.next_button_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-skip-forward-icon lucide-skip-forward"><polygon points="5 4 15 12 5 20 5 4"/><line x1="19" x2="19" y1="5" y2="19"/></svg>"""
        self.previous_button_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-skip-back-icon lucide-skip-back"><polygon points="19 20 9 12 19 4 19 20"/><line x1="5" x2="5" y1="19" y2="5"/></svg>"""
        
        # UI Components
        self.prev_button = QPushButton(self)
        self.play_pause_button = PlayButton(self, size=48)  # Use custom PlayButton
        self.next_button = QPushButton(self)
        
        self._setup_ui()
        self._connect_signals()
        
    def _setup_ui(self):
        """Set up the controls UI layout and styling"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)
        
        # Configure regular buttons
        for button in [self.prev_button, self.next_button]:
            button.setFixedSize(40, 40)
            button.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border-radius: 20px;
                    padding: 5px;
                }
                QPushButton:hover {
                    background-color: #3d3d3d;
                }
                QPushButton:pressed {
                    background-color: #505050;
                }
            """)
        
        # Set SVG icons for buttons
        self._setup_svg_icons()
        
        # Create button container for centering
        buttons_container = QWidget()
        buttons_layout = QHBoxLayout(buttons_container)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(10)
        buttons_layout.addWidget(self.prev_button)
        buttons_layout.addWidget(self.play_pause_button)
        buttons_layout.addWidget(self.next_button)
        
        # Add to main layout with stretches on both sides for centering
        layout.addStretch(1)
        layout.addWidget(buttons_container)
        layout.addStretch(1)
        
        self.setLayout(layout)
    
    def _setup_svg_icons(self):
        """Setup SVG icons for the next and previous buttons"""
        # Set icon for previous button
        prev_icon = self._create_icon_from_svg(self.previous_button_svg)
        self.prev_button.setIcon(prev_icon)
        self.prev_button.setIconSize(self.prev_button.size() * 0.6)
        
        # Set icon for next button
        next_icon = self._create_icon_from_svg(self.next_button_svg)
        self.next_button.setIcon(next_icon)
        self.next_button.setIconSize(self.next_button.size() * 0.6)
    
    def _create_icon_from_svg(self, svg_content):
        """Creates a QIcon from the given SVG content"""
        # Replace currentColor with white if needed
        svg_content = svg_content.replace('currentColor', 'white')
        
        # Create a renderer with the SVG content
        renderer = QSvgRenderer(bytes(svg_content, 'utf-8'))
        
        # Create a pixmap to draw on
        size = 24
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        # Draw the SVG on the pixmap
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        
        # Create and return an icon from the pixmap
        return QIcon(pixmap)
        
    def _connect_signals(self):
        """Connect button signals to corresponding slots"""
        self.prev_button.clicked.connect(self.previous_clicked)
        self.play_pause_button.clicked.connect(self._on_play_pause_clicked)
        self.next_button.clicked.connect(self.next_clicked)
        
    def _on_play_pause_clicked(self):
        """
        Handle play/pause button click by emitting the appropriate signal based on 
        the current visual state of the button.
        """
        # Check the current state of the PlayButton
        if self.play_pause_button.is_playing:
            # Button shows pause icon, so emit pause
            self.pause_clicked.emit()
        else:
            # Button shows play icon, so emit play
            self.play_clicked.emit()
    
    def set_playing_state(self, is_playing):
        """
        Update UI to reflect playing/paused state.
        This method only updates the visual state without tracking state internally.
        """
        # Update PlayButton's visual state
        self.play_pause_button.set_playing(is_playing)
    
    def set_next_enabled(self, enabled=True):
        """Enable or disable the next button"""
        self.next_button.setEnabled(enabled)
        
    def set_prev_enabled(self, enabled=True):
        """Enable or disable the previous button"""
        self.prev_button.setEnabled(enabled)
        
    def enable_controls(self, enabled=True):
        """Enable or disable all control buttons"""
        self.prev_button.setEnabled(enabled)
        # No need to disable the custom play button as it handles its own state
        self.next_button.setEnabled(enabled) 