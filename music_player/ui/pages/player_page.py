"""
Player page for the music player application.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QIcon

# Import QtAwesome for icons if available, otherwise use text
try:
    import qtawesome as qta
    HAS_QTAWESOME = True
except ImportError:
    HAS_QTAWESOME = False

# Import from the framework
from qt_base_app.components.base_card import BaseCard
from qt_base_app.theme.theme_manager import ThemeManager

# Import the MainPlayer instead of PlayerWidget for better integration
from music_player.ui.vlc_player import MainPlayer


class PlayerPage(QWidget):
    """
    Audio player page that displays the player widget and related controls.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playerPage")  # Add object name for styling
        self.setProperty('page_id', 'player')
        
        # Initialize theme manager
        self.theme = ThemeManager.instance()
        
        # Enable background styling for the widget (needed for border visibility)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 24, 24, 24)
        self.main_layout.setSpacing(24)
        
        # Player controls card
        self.controls_card = BaseCard("Player Controls")
        
        # Controls layout - contains the open file button
        controls_container = QWidget()
        self.controls_layout = QHBoxLayout(controls_container)
        self.controls_layout.setContentsMargins(0, 0, 0, 0)
        self.controls_layout.setSpacing(16)
        
        # Create Open File button
        self.open_file_button = QPushButton("Open File")
        self.open_file_button.setObjectName("openFileButton")
        self.open_file_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_file_button.setStyleSheet(f"""
            background-color: {self.theme.get_color('background', 'tertiary')};
            color: {self.theme.get_color('text', 'primary')};
            border-radius: 4px;
            padding: 8px 16px;
            font-weight: bold;
        """)
        
        # Add icon if qtawesome is available
        if HAS_QTAWESOME:
            self.open_file_button.setIcon(qta.icon("fa5s.folder-open", color=self.theme.get_color('text', 'primary')))
            self.open_file_button.setIconSize(QSize(16, 16))
        
        self.open_file_button.clicked.connect(self._on_open_file_clicked)
        
        # Add button to controls layout
        self.controls_layout.addWidget(self.open_file_button)
        self.controls_layout.addStretch()
        
        # Add the controls to the card
        self.controls_card.add_widget(controls_container)
        
        # Player card
        self.player_card = BaseCard("Media Player")
        
        # Player widget - using MainPlayer instead of PlayerWidget
        self.player_widget = MainPlayer()
        
        # Add the player to the card
        self.player_card.add_widget(self.player_widget)
        
        # Add components to main layout
        self.main_layout.addWidget(self.controls_card)
        self.main_layout.addWidget(self.player_card, 1)  # Give player card more space
    
    def _on_open_file_clicked(self):
        """Handle open file button click by delegating to the player widget"""
        self.player_widget.load_media()
        
    def showEvent(self, event):
        """
        Override show event to set focus to the player widget.
        
        Args:
            event: The show event
        """
        super().showEvent(event)
        # Use a short timer to ensure the focus is set after all widgets are shown
        QTimer.singleShot(100, self._set_focus_to_player)
    
    def _set_focus_to_player(self):
        """Set focus to the player widget"""
        if self.player_widget:
            self.player_widget.setFocus()
            
    def keyPressEvent(self, event):
        """
        Handle key events at the page level.
        
        Args:
            event: The key event
        """
        # By default, just forward to the player widget if it exists
        if self.player_widget:
            # Forward the event to the player widget
            self.player_widget.keyPressEvent(event)
        else:
            # Otherwise, use default handling
            super().keyPressEvent(event) 