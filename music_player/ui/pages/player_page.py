"""
Player page for the music player application.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
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

# Import AlbumArtDisplay for large album art view
from music_player.ui.vlc_player.album_art_display import AlbumArtDisplay
from music_player.ui.vlc_player.speed_overlay import SpeedOverlay


class PlayerPage(QWidget):
    """
    Audio player page that displays large album art and playback controls.
    Uses the persistent player at the bottom of the app for actual playback.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playerPage")  # Add object name for styling
        self.setProperty('page_id', 'player')
        
        # Initialize theme manager
        self.theme = ThemeManager.instance()
        
        # Enable background styling for the widget (needed for border visibility)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        # Find the persistent player from the dashboard
        self.persistent_player = None
        # We'll connect to it in showEvent
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 24, 24, 24)
        self.main_layout.setSpacing(24)
        
        # Create Open File button without any container card
        self.open_file_button = QPushButton()
        self.open_file_button.setObjectName("openFileButton")
        self.open_file_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_file_button.setFixedSize(48, 48)
        self.open_file_button.setStyleSheet(f"""
            background-color: {self.theme.get_color('background', 'tertiary')};
            border-radius: 24px;
            padding: 8px;
        """)
        
        # Add icon if qtawesome is available
        if HAS_QTAWESOME:
            self.open_file_button.setIcon(qta.icon("fa5s.folder-open", color=self.theme.get_color('text', 'primary')))
            self.open_file_button.setIconSize(QSize(24, 24))
        else:
            # Fallback to text if icons not available
            self.open_file_button.setText("📂")
            self.open_file_button.setStyleSheet(self.open_file_button.styleSheet() + """
                font-size: 24px;
                font-weight: bold;
            """)
        
        self.open_file_button.clicked.connect(self._on_open_file_clicked)
        
        # Create a container for the button that aligns it to the left
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addWidget(self.open_file_button)  # Add button first (left-aligned)
        button_layout.addStretch()  # Add stretch after button to push it left
        
        # Create a simple card for album art with no title
        self.album_art_card = BaseCard("")  # Create with empty title
        
        # Create a large album art display to fill the entire card
        self.album_art = AlbumArtDisplay()
        self.album_art.setMinimumSize(300, 300)
        
        # Add album art directly to the card
        self.album_art_card.add_widget(self.album_art)
        
        # Create speed overlay for the album art
        self.speed_overlay = SpeedOverlay(self.album_art_card)
        self.speed_overlay.hide()  # Initially hidden
        
        # Modify the card's content margin
        card_content = None
        for i in range(self.album_art_card.layout.count()):
            item = self.album_art_card.layout.itemAt(i)
            if item.widget() and item.widget().objectName() == "cardContent":
                card_content = item.widget()
                if card_content.layout():
                    card_content.layout().setContentsMargins(0, 0, 0, 0)
                    card_content.layout().setSpacing(0)
        
        # Hidden track info (for storage only)
        self.track_info_container = QWidget()
        self.track_info_container.hide()
        track_info_layout = QVBoxLayout(self.track_info_container)
        track_info_layout.setContentsMargins(0, 0, 0, 0)
        
        self.track_title_label = QLabel("No Track Playing")
        self.track_artist_label = QLabel("")
        
        track_info_layout.addWidget(self.track_title_label)
        track_info_layout.addWidget(self.track_artist_label)
        
        # Add components to main layout
        self.main_layout.addWidget(button_container)
        self.main_layout.addWidget(self.album_art_card, 1)  # Give album art card more space
    
    def _on_open_file_clicked(self):
        """Handle open file button click by delegating to the persistent player"""
        if self.persistent_player:
            self.persistent_player.load_media()
    
    def _update_track_info(self, metadata):
        """Update just the album art when track changes"""
        artwork_path = metadata.get('artwork_path')
        
        if artwork_path:
            self.album_art.set_image(artwork_path)
            
            # Force the album art display to be visible and update
            self.album_art.setVisible(True)
            self.album_art.update()
            self.album_art_card.setVisible(True)
            self.album_art_card.update()
        else:
            # Set placeholder for no artwork
            self.album_art._set_placeholder()
        
        # Still store track info in the labels in case we need it later
        title = metadata.get('title', 'Unknown Track')
        artist = metadata.get('artist', 'Unknown Artist')
        
        self.track_title_label.setText(title)
        self.track_artist_label.setText(artist)
        
    def showEvent(self, event):
        """
        Override show event to connect to the persistent player.
        
        Args:
            event: The show event
        """
        super().showEvent(event)
        
        # Set a larger minimum size for the album art when shown
        window_size = self.size()
        min_dimension = min(window_size.width(), window_size.height()) - 100
        self.album_art.setMinimumSize(min_dimension, min_dimension)
        
        # Find the persistent player if we haven't already
        if not self.persistent_player:
            # Navigate up to find the dashboard
            parent = self.parent()
            while parent and not hasattr(parent, 'player'):
                parent = parent.parent()
            
            if parent and hasattr(parent, 'player'):
                self.set_persistent_player(parent.player) # Call setup method
                # No need to connect or update here, set_persistent_player handles it
                
    
    def keyPressEvent(self, event):
        """
        Handle key events at the page level.
        
        Args:
            event: The key event
        """
        # Forward key events to the persistent player
        if self.persistent_player:
            self.persistent_player.keyPressEvent(event)
        else:
            # Otherwise, use default handling
            super().keyPressEvent(event)

    def set_persistent_player(self, player):
        """
        Set the persistent player instance directly.
        This is called from MusicPlayerDashboard during initialization.
        
        Args:
            player: The MainPlayer instance
        """
        self.persistent_player = player
        
        # Disconnect any existing connections first to avoid duplicates
        try:
            self.persistent_player.track_changed.disconnect(self._update_track_info)
            self.persistent_player.player_widget.rate_changed.disconnect(self._on_rate_changed)
        except:
            pass  # No connection existed
            
        # Connect to track changed signal
        self.persistent_player.track_changed.connect(self._update_track_info)
        
        # Connect to rate changed signal
        self.persistent_player.player_widget.rate_changed.connect(self._on_rate_changed)
        
        # Set a minimum size for the album art
        self.album_art.setMinimumSize(400, 400)
        
        # Immediately fetch and display current track info if available
        current_metadata = self.persistent_player.get_current_track_metadata()
        if current_metadata:
            self._update_track_info(current_metadata)
        
        # Direct access to artwork path as fallback
        if hasattr(self.persistent_player, 'get_current_artwork_path'):
            artwork_path = self.persistent_player.get_current_artwork_path()
            if artwork_path:
                self.album_art.set_image(artwork_path)
                self.album_art.setVisible(True)
                self.album_art.update()
                self.album_art_card.setVisible(True)
                self.album_art_card.update()
                
        # Force an update
        self.update()
        QTimer.singleShot(100, self.update)  # Schedule another update after event processing

    def resizeEvent(self, event):
        """Handle resize event to adjust album art size"""
        super().resizeEvent(event)
        
        # Dynamically adjust album art size based on window size
        window_size = self.size()
        min_dimension = min(window_size.width(), window_size.height()) - 100
        self.album_art.setMinimumSize(min_dimension, min_dimension)
        
        # Position the speed overlay in the top-right corner of the album art card
        self._update_speed_overlay_position()
        
    def _update_speed_overlay_position(self):
        """Update the position of the speed overlay"""
        # Position the speed overlay in the top-right corner with balanced margins
        top_margin = 30     # Increased top margin for better vertical spacing
        right_margin = 10   # Decreased right margin for better horizontal spacing
        
        # Get the actual album art dimensions and position
        art_rect = self.album_art.geometry()
        
        # Set the overlay position relative to the album art
        # The overlay is a child of the album_art_card, so we position it using card coordinates
        self.speed_overlay.setGeometry(
            art_rect.right() - self.speed_overlay.width() - right_margin,  # X: right aligned
            art_rect.top() + top_margin,  # Y: top aligned with increased margin
            100,  # Width
            40   # Height
        )
        
    def _on_rate_changed(self, rate):
        """Handle rate change from player"""
        # Show the speed overlay with the current rate
        self.speed_overlay.show_speed(rate)
        # Update position in case it's the first time showing
        QTimer.singleShot(10, self._update_speed_overlay_position) 