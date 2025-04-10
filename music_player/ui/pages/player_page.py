"""
Player page for the music player application.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSizePolicy, QMessageBox
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
from music_player.ui.components.round_button import RoundButton
from music_player.ui.components.upload_status_overlay import UploadStatusOverlay
from music_player.services.oplayer_service import OPlayerService


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
        
        # Initialize OPlayer service
        self.oplayer_service = OPlayerService(self)
        self._connect_oplayer_signals()
        
        # Find the persistent player from the dashboard
        self.persistent_player = None
        # We'll connect to it later
        
        self.setup_ui()
    
    def _connect_oplayer_signals(self):
        """Connect to OPlayer service signals"""
        self.oplayer_service.upload_started.connect(self._on_upload_started)
        self.oplayer_service.upload_progress.connect(self._on_upload_progress)
        self.oplayer_service.upload_completed.connect(self._on_upload_completed)
        self.oplayer_service.upload_failed.connect(self._on_upload_failed)
        
    def setup_ui(self):
        """Set up the user interface."""
        # Main layout - No margins for full bleed album art
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0) # Remove margins
        self.main_layout.setSpacing(0) # Remove spacing
        
        # Album art display - Takes up all space, no rounded corners
        self.album_art = AlbumArtDisplay(self, corner_radius=0) # Parent is self, radius 0
        self.album_art.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.album_art.setMinimumSize(300, 300) # Keep a minimum size
        self.main_layout.addWidget(self.album_art, 1) # Add directly with stretch factor
        
        # Create Open File button using RoundButton
        self.open_file_button = RoundButton(
            parent=self,
            icon_name="fa5s.folder-open",  # Use folder icon if available
            text="📂",                     # Fallback text if icons not available
            size=48,
            icon_size=24,
            bg_opacity=0.5
        )
        self.open_file_button.clicked.connect(self._on_open_file_clicked)
        
        # Create OPlayer upload button
        self.oplayer_button = RoundButton(
            parent=self,
            text="OP",
            size=48,
            bg_opacity=0.5
        )
        self.oplayer_button.clicked.connect(self._on_oplayer_upload_clicked)
        
        # Create upload status overlay
        self.upload_status = UploadStatusOverlay(self)
        
        # Create speed overlay
        self.speed_overlay = SpeedOverlay(self)
        self.speed_overlay.hide()  # Initially hidden
        
        # Initial positioning will be done in resizeEvent
        
        # Connect album art click to toggle play/pause
        self.album_art.clicked.connect(self._toggle_play_pause)
        
    def _on_open_file_clicked(self):
        """Handle open file button click by delegating to the persistent player"""
        if self.persistent_player:
            self.persistent_player.load_media()
    
    def _on_oplayer_upload_clicked(self):
        """Handle OPlayer upload button click"""
        if not self.persistent_player:
            print("[PlayerPage] Error: No persistent player available")
            return
            
        # Get current media path - access through backend
        media_path = self.persistent_player.backend.get_current_media_path()
        print(f"[PlayerPage] Current media path: {media_path}")
        
        if not media_path:
            error_msg = "No media currently playing. Please select a file to upload."
            print(f"[PlayerPage] Error: {error_msg}")
            QMessageBox.warning(
                self,
                "Upload Error",
                error_msg
            )
            return
            
        # Test connection before attempting upload
        print("[PlayerPage] Testing connection to OPlayer device...")
        if not self.oplayer_service.test_connection():
            error_msg = "Could not connect to OPlayer device. Please check your network connection and device status."
            print(f"[PlayerPage] Error: {error_msg}")
            QMessageBox.critical(
                self,
                "Connection Error",
                error_msg
            )
            return
            
        # Start upload
        print(f"[PlayerPage] Starting upload of: {media_path}")
        self.oplayer_service.upload_file(media_path)
        
    def _on_upload_started(self, filename):
        """Handle upload started signal"""
        print(f"[PlayerPage] Upload started: {filename}")
        self.upload_status.show_upload_started(filename)
        self._update_upload_status_position()
        
    def _on_upload_progress(self, percentage):
        """Handle upload progress signal"""
        print(f"[PlayerPage] Upload progress: {percentage}%")
        self.upload_status.show_upload_progress(percentage)
        
    def _on_upload_completed(self, filename):
        """Handle upload completed signal"""
        print(f"[PlayerPage] Upload completed: {filename}")
        self.upload_status.show_upload_completed(filename)
        
    def _on_upload_failed(self, error_msg):
        """Handle upload failed signal"""
        print(f"[PlayerPage] Upload failed: {error_msg}")
        self.upload_status.show_upload_failed(error_msg)
        
    def _update_track_info(self, metadata):
        """Update just the album art when track changes"""
        artwork_path = metadata.get('artwork_path')
        
        if artwork_path:
            self.album_art.set_image(artwork_path)
            
            # Force the album art display to be visible and update
            self.album_art.setVisible(True)
            self.album_art.update()
        else:
            # Set placeholder for no artwork
            self.album_art._set_placeholder()
        
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
                
        # Force an update
        self.update()
        QTimer.singleShot(100, self.update)  # Schedule another update after event processing

    def resizeEvent(self, event):
        """Handle resize event to adjust album art size and reposition overlays"""
        super().resizeEvent(event)
        
        # Position Open File button overlay in top-left corner
        margin = 20
        button_spacing = 10  # Space between buttons
        self.open_file_button.move(margin, margin)
        
        # Position OPlayer button to the right of the open file button
        self.oplayer_button.move(
            margin + self.open_file_button.width() + button_spacing,
            margin
        )
        
        # Position the speed overlay (top-right)
        self._update_speed_overlay_position()
        
        # Position the upload status overlay
        self._update_upload_status_position()
        
    def _update_speed_overlay_position(self):
        """Update the position of the speed overlay relative to the PlayerPage"""
        top_margin = 30
        right_margin = 20 # Adjusted for consistency with button margin
        
        # Position relative to the PlayerPage bounds
        self.speed_overlay.move(
            self.width() - self.speed_overlay.width() - right_margin,
            top_margin
        )

    def _on_rate_changed(self, rate):
        """Handle rate change from player"""
        # Show the speed overlay with the current rate
        self.speed_overlay.show_speed(rate)
        self.speed_overlay.raise_() # Ensure overlay is on top

    def _toggle_play_pause(self):
        """Toggle play/pause state of the persistent player."""
        if self.persistent_player:
            if self.persistent_player.is_playing():
                self.persistent_player.pause()
            else:
                self.persistent_player.play() 

    def _update_upload_status_position(self):
        """Update the position of the upload status overlay"""
        # Center horizontally, position near the top
        status_x = (self.width() - self.upload_status.width()) // 2
        status_y = 100  # Position below the top buttons
        self.upload_status.move(status_x, status_y)
        self.upload_status.raise_()  # Ensure it's on top 