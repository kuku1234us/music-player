"""
Player page for the music player application.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSizePolicy, QMessageBox
from PyQt6.QtCore import Qt, QSize, QTimer, QPoint, QRect
from PyQt6.QtGui import QIcon, QCursor
from qt_base_app.models.logger import Logger

# Import QStackedWidget
from PyQt6.QtWidgets import QStackedWidget

# Import os for path checking
import os
# Imports for standalone VLC test
import sys
import vlc

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
# Import the new VideoWidget
from music_player.ui.components.player_components.video_widget import VideoWidget
# from music_player.ui.components.float_button import FloatButton # Removed
# Import the new PlayerOverlay
from music_player.ui.components.player_components.player_overlay import PlayerOverlay # Added
from music_player.ui.components.upload_status_overlay import UploadStatusOverlay
from music_player.services.oplayer_service import OPlayerService

# --- ADD TYPING IMPORTS ---
from typing import TYPE_CHECKING
# -------------------------

# --- ADD GUARDED IMPORT ---
# Import MainPlayer only for type checking to avoid circular import
if TYPE_CHECKING:
    from music_player.ui.vlc_player import MainPlayer
# --------------------------

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
        self._hotkey_handler = None

        # Track all created video surfaces by HWND so we can delete them safely later
        self._surface_by_hwnd: dict[int, VideoWidget] = {}
        
        # --- Add Mouse Tracking Timer ---
        self.mouse_tracking_timer = QTimer(self)
        self.mouse_tracking_timer.setInterval(100) # Check every 100ms
        self.mouse_tracking_timer.timeout.connect(self._check_mouse_over_video)
        # ------------------------------
        
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

        # Video output surfaces:
        # Instead of reusing a fixed set of 2 widgets, we create a fresh VideoWidget per switch.
        # This matches `vlc_test_ab.py` and prevents libVLC from fighting over a reused HWND while
        # an old instance is still tearing down in the background (a common cause of VLC popups).
        self.video_stack = QStackedWidget(self)
        self._current_video_widget = self._create_and_activate_video_surface()

        # Create the QStackedWidget to hold album art and video stack
        self.media_display_stack = QStackedWidget(self)
        self.media_display_stack.addWidget(self.album_art) # Index 0: Album Art
        self.media_display_stack.addWidget(self.video_stack) # Index 1: Video Stack (Double Buffered)

        # Add the stack to the main layout instead of just the album art
        self.main_layout.addWidget(self.media_display_stack, 1) # Add stack with stretch factor

        # Set initial display to album art
        self.media_display_stack.setCurrentIndex(0)
        
        # --- Define relative positions --- 
        margin = 20
        overlay_pos = QPoint(margin, margin)
        
        # --- Create PlayerOverlay --- 
        self.player_overlay = PlayerOverlay(
            parent=self # Set direct parent
        )
        # Connect signals from the overlay to page methods
        self.player_overlay.openFileClicked.connect(self._on_open_file_clicked)
        self.player_overlay.oplayerClicked.connect(self._on_oplayer_upload_clicked)
        # ---------------------------
        
        # Create upload status overlay
        self.upload_status = UploadStatusOverlay(self)
        
        # Create speed overlay
        self.speed_overlay = SpeedOverlay(self)
        self.speed_overlay.hide()  # Initially hidden
        
        # Connect album art click to toggle play/pause
        self.album_art.clicked.connect(self._toggle_play_pause)
        
    def swap_video_surface(self) -> int:
        """
        Allocates a NEW video surface and returns its winId (HWND).
        We avoid reusing old surfaces because background VLC teardown can take seconds.
        """
        self._current_video_widget = self._create_and_activate_video_surface()
        hwnd = int(self._current_video_widget.winId())
        Logger.instance().debug(caller="PlayerPage", msg=f"[PlayerPage] Allocated new video surface hwnd={hwnd}")
        self._current_video_widget.setVisible(True)
        self._current_video_widget.setFocus()
        return hwnd

    def _create_and_activate_video_surface(self) -> VideoWidget:
        """Create a new VideoWidget surface, add it to the stack, and make it current."""
        w = VideoWidget(self)
        w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if self._hotkey_handler and hasattr(w, "set_hotkey_handler"):
            w.set_hotkey_handler(self._hotkey_handler)

        self.video_stack.addWidget(w)
        self.video_stack.setCurrentWidget(w)

        hwnd = int(w.winId())
        self._surface_by_hwnd[hwnd] = w
        return w

    def release_video_surface(self, hwnd: int):
        """
        Remove and delete an old video surface after its VLC worker has fully finished.
        """
        try:
            hwnd_int = int(hwnd)
        except Exception:
            return

        w = self._surface_by_hwnd.pop(hwnd_int, None)
        if not w:
            return

        # Never delete the currently active surface
        if w is self._current_video_widget:
            self._surface_by_hwnd[hwnd_int] = w
            return

        try:
            self.video_stack.removeWidget(w)
        except Exception:
            pass
        w.deleteLater()

    def get_current_video_widget(self):
        """Returns the currently active video widget."""
        return self._current_video_widget

    def _on_open_file_clicked(self):
        """Handle open file button click by delegating to the persistent player"""
        if self.persistent_player:
            # Original call
            self.persistent_player.load_media()
    
    def _on_oplayer_upload_clicked(self):
        """Handle OPlayer upload button click"""
        if not self.persistent_player:
            Logger.instance().error(caller="PlayerPage", msg="[PlayerPage] Error: No persistent player available")
            return
            
        # Get current media path - access through backend
        media_path = self.persistent_player.backend.get_current_media_path()
        Logger.instance().debug(caller="PlayerPage", msg=f"[PlayerPage] Current media path: {media_path}")
        
        if not media_path:
            error_msg = "No media currently playing. Please select a file to upload."
            Logger.instance().error(caller="PlayerPage", msg=f"[PlayerPage] Error: {error_msg}")
            QMessageBox.warning(
                self,
                "Upload Error",
                error_msg
            )
            return
            
        # Test connection before attempting upload
        Logger.instance().debug(caller="PlayerPage", msg="[PlayerPage] Testing connection to OPlayer device...")
        if not self.oplayer_service.test_connection():
            error_msg = "Could not connect to OPlayer device. Please check your network connection and device status."
            Logger.instance().error(caller="PlayerPage", msg=f"[PlayerPage] Error: {error_msg}")
            QMessageBox.critical(
                self,
                "Connection Error",
                error_msg
            )
            return
            
        # Start upload
        Logger.instance().info(caller="PlayerPage", msg=f"[PlayerPage] Starting upload of: {media_path}")
        self.oplayer_service.upload_file(media_path)
        
    def _on_upload_started(self, filename):
        """Handle upload started signal"""
        Logger.instance().info(caller="PlayerPage", msg=f"[PlayerPage] Upload started: {filename}")
        self.upload_status.show_upload_started(filename)
        self._update_upload_status_position()
        
    def _on_upload_progress(self, percentage):
        """Handle upload progress signal"""
        Logger.instance().debug(caller="PlayerPage", msg=f"[PlayerPage] Upload progress: {percentage}%")
        self.upload_status.show_upload_progress(percentage)
        
    def _on_upload_completed(self, filename):
        """Handle upload completed signal"""
        Logger.instance().info(caller="PlayerPage", msg=f"[PlayerPage] Upload completed: {filename}")
        self.upload_status.show_upload_completed(filename)
        
    def _on_upload_failed(self, error_msg):
        """Handle upload failed signal"""
        Logger.instance().error(caller="PlayerPage", msg=f"[PlayerPage] Upload failed: {error_msg}")
        self.upload_status.show_upload_failed(error_msg)
        
    def _update_track_info(self, metadata):
        """Update just the album art when track changes"""
        artwork_path = metadata.get('artwork_path')
        
        if artwork_path:
            self.album_art.set_image(artwork_path)
            self.album_art.update()
        else:
            # Set placeholder for no artwork
            self.album_art._set_placeholder()
        
    def showEvent(self, event):
        """
        Override show event to connect to the persistent player.
        """
        super().showEvent(event)
        
        # Set a larger minimum size for the album art when shown
        window_size = self.size()
        min_dimension = min(window_size.width(), window_size.height()) - 100
        
        # Find the persistent player if we haven't already
        if not self.persistent_player:
            # Navigate up to find the dashboard
            parent = self.parent()
            while parent and not hasattr(parent, 'player'):
                parent = parent.parent()
            if parent and hasattr(parent, 'player'):
                self.set_persistent_player(parent.player) # Call setup method

        if not self.persistent_player:
             Logger.instance().error(caller="PlayerPage", msg="[PlayerPage] Error: Could not find persistent player in showEvent.")
    
    def keyPressEvent(self, event):
        """
        Handle key events at the page level.
        """
        # Forward key events to the persistent player
        if self.persistent_player:
            self.persistent_player.keyPressEvent(event)
        else:
            # Otherwise, use default handling
            super().keyPressEvent(event)

    def hideEvent(self, event):
        """Handle hide event."""
        super().hideEvent(event)

    def set_persistent_player(self, player: 'MainPlayer'):
        """ Sets the persistent player instance and connects signals. """
        self.persistent_player = player
        
        if self.persistent_player:
            # Connect media_changed
            if hasattr(self.persistent_player, 'media_changed'): 
                self.persistent_player.media_changed.connect(self._on_media_loaded) 
            
            # --- Pass HotkeyHandler to BOTH VideoWidgets --- 
            if hasattr(self.persistent_player, 'hotkey_handler'):
                handler = self.persistent_player.hotkey_handler
                self._hotkey_handler = handler
                # Apply to all existing surfaces
                for w in list(self._surface_by_hwnd.values()):
                    if hasattr(w, 'set_hotkey_handler'):
                        w.set_hotkey_handler(handler)
                if hasattr(self.album_art, 'set_hotkey_handler'):
                    self.album_art.set_hotkey_handler(handler)
            # -----------------------------------------------

            # Update UI immediately with current player state/media if available
            current_metadata = self.persistent_player.get_current_track_metadata()
            if current_metadata:
                self._update_track_info(current_metadata)
        
            # Direct access to artwork path as fallback
            if hasattr(self.persistent_player, 'get_current_artwork_path'):
                artwork_path = self.persistent_player.get_current_artwork_path()
                if artwork_path:
                    self.album_art.set_image(artwork_path)
                    self.album_art.update()

            # Register with MainPlayer so it can callback for surface swaps
            if hasattr(self.persistent_player, 'register_player_page'):
                self.persistent_player.register_player_page(self)
                
        # Force an update
        self.update()
        QTimer.singleShot(100, self.update)  # Schedule another update after event processing

    def resizeEvent(self, event):
        """Handle resize event to position stack and overlays."""
        super().resizeEvent(event)
        
        page_rect = self.rect()

        # --- Position Media Stack ---
        self.media_display_stack.setGeometry(page_rect)
        
        # --- Position Player Overlay ---
        overlay_margin = 20
        self.player_overlay.move(overlay_margin, overlay_margin)

        # --- Position Speed Overlay ---
        speed_overlay_size = self.speed_overlay.sizeHint()
        speed_top_margin = 30
        speed_right_margin = 20
        self.speed_overlay.move(
            self.width() - speed_overlay_size.width() - speed_right_margin,
            speed_top_margin
        )

        # --- Position Upload Status ---
        upload_status_size = self.upload_status.sizeHint()
        upload_top_margin = 100 # Below potential player overlay
        self.upload_status.move(
            (self.width() - upload_status_size.width()) // 2,
            upload_top_margin
        )

        # --- Raise Overlays ---
        self.player_overlay.raise_()
        self.upload_status.raise_()
        self.speed_overlay.raise_() 

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

    def _on_media_loaded(self, metadata: dict, is_video: bool):
        """Handle media loaded signal (incl. type) from MainPlayer."""
        Logger.instance().debug(caller="PlayerPage", msg=f"[PlayerPage] Media loaded: is_video={is_video}")
        self.player_overlay.set_video_mode(is_video) # Inform overlay

        if is_video:
            Logger.instance().debug(caller="PlayerPage", msg="[PlayerPage] Switching display to Video Widget.")
            self.media_display_stack.setCurrentIndex(1)
            # Ensure current video widget is visible (it should be, but be safe)
            self._current_video_widget.setVisible(True) 
            self.album_art.setVisible(False)
            
            # --- Start mouse tracking timer --- 
            self.mouse_tracking_timer.start()
        else:
            # --- Stop mouse tracking timer --- 
            if self.mouse_tracking_timer.isActive():
                self.mouse_tracking_timer.stop()
            
            Logger.instance().debug(caller="PlayerPage", msg="[PlayerPage] Switching display to Album Art.")
            self.media_display_stack.setCurrentIndex(0)
            self.album_art.setVisible(True)
            self.video_stack.setVisible(False) # Hide the whole video stack
            
            # Ensure overlay is visible when not in video mode
            self.player_overlay.show_overlay() 
            
            if self.persistent_player:
                self._update_track_info(metadata) 

    def _check_mouse_over_video(self):
        """Called by timer to check mouse position relative to the overlay widget."""
        # Use _current_video_widget
        if not self._current_video_widget.isVisible() or not self.player_overlay._video_mode_active:
            if self.mouse_tracking_timer.isActive() and not self.player_overlay._video_mode_active:
                self.mouse_tracking_timer.stop()
            if self.player_overlay._video_mode_active:
                self.player_overlay.hide_overlay()
            return

        global_mouse_pos = QCursor.pos()
        overlay_global_top_left = self.player_overlay.mapToGlobal(QPoint(0, 0))
        overlay_global_rect = QRect(overlay_global_top_left, self.player_overlay.size())

        if overlay_global_rect.contains(global_mouse_pos):
            if not self.player_overlay.isVisible():
                self.player_overlay.show_overlay()
        else:
            if self.player_overlay.isVisible():
                self.player_overlay.hide_overlay()

    def show_video_view(self):
        """Switches the PlayerPage to display the video widget."""
        self.media_display_stack.setCurrentIndex(1)
        self.video_stack.setVisible(True)
        self._current_video_widget.setVisible(True)
        self.setFocus()
        self._current_video_widget.setFocus()

    def show_album_art_view(self):
        """Switches the PlayerPage to display the album art."""
        self.media_display_stack.setCurrentIndex(0)
        self.album_art.setVisible(True)
