"""
Player page for the music player application.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSizePolicy, QMessageBox
from PyQt6.QtCore import Qt, QSize, QTimer, QPoint, QRect
from PyQt6.QtGui import QIcon, QCursor

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
        self.persistent_player = None # Keep this maybe? Or comment out?
        # We'll connect to it later (comment out for now)

        # --- REVERTED: Variables for Standalone VLC Test ---
        # self._test_vlc_instance: Optional[vlc.Instance] = None
        # self._test_vlc_player: Optional[vlc.MediaPlayer] = None
        # --------------------------------------------------

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

        # --- NEW: Create Video Widget and Stack --- 
        # Create the video widget instance
        self.video_widget = VideoWidget(self)
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # --- Remove Event Filter --- 
        # self.video_widget.installEventFilter(self) # Filter events for video_widget
        # --------------------------

        # Create the QStackedWidget to hold album art and video
        self.media_display_stack = QStackedWidget(self)
        self.media_display_stack.addWidget(self.album_art) # Index 0: Album Art
        self.media_display_stack.addWidget(self.video_widget) # Index 1: Video Widget

        # Add the stack to the main layout instead of just the album art
        self.main_layout.addWidget(self.media_display_stack, 1) # Add stack with stretch factor

        # Set initial display to album art
        self.media_display_stack.setCurrentIndex(0)
        # -----------------------------------------
        
        # --- Define relative positions --- 
        margin = 20
        # button_spacing = 10 # No longer needed for individual button spacing
        # Define position for the overlay panel
        overlay_pos = QPoint(margin, margin)
        
        # --- Create PlayerOverlay --- Added
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
        
        # Initial positioning will be done in resizeEvent
        
        # Connect album art click to toggle play/pause
        # Note: Clicking the video widget area won't do this yet.
        self.album_art.clicked.connect(self._toggle_play_pause)
        
    def _on_open_file_clicked(self):
        """Handle open file button click by delegating to the persistent player"""
        if self.persistent_player:
            # Original call
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
            # self.album_art.setVisible(True) # Visibility now controlled by stack
            self.album_art.update()
        else:
            # Set placeholder for no artwork
            self.album_art._set_placeholder()
        
        # --- Ensure Album Art is shown if stack is currently on index 0 --- 
        # Commented out as the _on_media_type_determined slot should handle this visibility now
        # if self.media_display_stack.currentIndex() == 0:
        #     self.album_art.setVisible(True)
        #     self.video_widget.setVisible(False)
        # -------------------------------------------------------------------
        
    def showEvent(self, event):
        """
        Override show event to connect to the persistent player.
        
        Args:
            event: The show event
        """
        # print("[PlayerPage STANDALONE TEST] showEvent triggered.")
        super().showEvent(event)
        
        # --- RESTORED: Persistent player logic ---
        # Set a larger minimum size for the album art when shown
        window_size = self.size()
        min_dimension = min(window_size.width(), window_size.height()) - 100
        # self.album_art.setMinimumSize(min_dimension, min_dimension)
        # Set minimum size on the stack instead if desired
        # self.media_display_stack.setMinimumSize(min_dimension, min_dimension)
        
        # Find the persistent player if we haven't already
        if not self.persistent_player:
            # Navigate up to find the dashboard
            parent = self.parent()
            while parent and not hasattr(parent, 'player'):
                parent = parent.parent()
            if parent and hasattr(parent, 'player'):
                self.set_persistent_player(parent.player) # Call setup method
        # ---------------------------------------------

        # --- RESTORED: Original logic for passing handle to persistent player ---
        # if self.persistent_player and hasattr(self, 'video_widget'):
        #     # --- Pass video widget handle to player (original intent) ---
        #     print("[PlayerPage] Passing video widget handle to MainPlayer in showEvent.")
        #     self.persistent_player.set_video_widget(self.video_widget)
        elif not self.persistent_player:
             print("[PlayerPage] Error: Could not find persistent player in showEvent.")
        else: # Player exists but no video_widget?
             print("[PlayerPage] Warning: Persistent player found in showEvent, but no video_widget attribute.")
        # ------------------------------------------------------------------------
    
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

    def hideEvent(self, event):
        """Handle hide event."""
        # print("[PlayerPage STANDALONE TEST] hideEvent triggered.")
        # if self._test_vlc_player:
        #     print("[PlayerPage STANDALONE TEST] Stopping test VLC player.")
        #     self._test_vlc_player.stop()
        #     # Optional: Release resources if needed, might be handled by garbage collection
        #     # self._test_vlc_player = None
        #     # self._test_vlc_instance = None
        super().hideEvent(event)

    def set_persistent_player(self, player: 'MainPlayer'):
        """ Sets the persistent player instance and connects signals. """
        self.persistent_player = player
        
        # --- Connect player signals --- 
        if self.persistent_player:
            # --- REMOVE OLD CONNECTION ---
            # if hasattr(self.persistent_player, 'video_media_detected'):
            #     self.persistent_player.video_media_detected.connect(self._on_media_type_determined)
            # ---------------------------

            # --- CORRECTED CONNECTION --- 
            # Connect media_changed (which now includes is_video) to the updated slot
            if hasattr(self.persistent_player, 'media_changed'): # <-- Corrected signal name
                self.persistent_player.media_changed.connect(self._on_media_loaded) 
            # ------------------------
            
            # --- ADD HWND SETUP HERE --- 
            # Set the video widget handle in the player *immediately* when connected
            if hasattr(self.persistent_player, 'set_video_widget') and self.video_widget:
                print("[PlayerPage] Setting video widget in persistent player during connection.")
                self.persistent_player.set_video_widget(self.video_widget)
            # ---------------------------

            # --- Pass HotkeyHandler to VideoWidget --- 
            if self.persistent_player and hasattr(self.persistent_player, 'hotkey_handler') \
               and self.video_widget and hasattr(self.video_widget, 'set_hotkey_handler'):
                print("[PlayerPage] Passing HotkeyHandler to VideoWidget.")
                handler = self.persistent_player.hotkey_handler
                self.video_widget.set_hotkey_handler(handler)
            # -----------------------------------------
            
            # --- Pass HotkeyHandler to AlbumArtDisplay --- 
            if self.persistent_player and hasattr(self.persistent_player, 'hotkey_handler') \
               and self.album_art and hasattr(self.album_art, 'set_hotkey_handler'):
                print("[PlayerPage] Passing HotkeyHandler to AlbumArtDisplay.")
                handler = self.persistent_player.hotkey_handler
                self.album_art.set_hotkey_handler(handler)
            # -------------------------------------------

            # Update UI immediately with current player state/media if available
            # Get current media info
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
        """Handle resize event to position stack and overlays."""
        super().resizeEvent(event)
        
        page_rect = self.rect()

        # --- Position Media Stack ---
        # Make the stack fill the entire page
        self.media_display_stack.setGeometry(page_rect)
        
        # --- Position Player Overlay ---
        overlay_margin = 20
        overlay_size = self.player_overlay.sizeHint() # Get preferred size
        # Position at top-left
        self.player_overlay.move(overlay_margin, overlay_margin)
        # Or use setGeometry if specific size needed:
        # self.player_overlay.setGeometry(overlay_margin, overlay_margin, overlay_size.width(), overlay_size.height())

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
        # Raise player overlay above the media stack
        self.player_overlay.raise_()
        # Raise other overlays as needed (they are siblings, order matters if they overlap)
        self.upload_status.raise_()
        self.speed_overlay.raise_() # Speed overlay potentially highest

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
        print(f"[PlayerPage] Media loaded: is_video={is_video}")
        self.player_overlay.set_video_mode(is_video) # Inform overlay

        if is_video:
            print("[PlayerPage] Switching display to Video Widget.")
            self.media_display_stack.setCurrentIndex(1)
            self.video_widget.setVisible(True)
            self.album_art.setVisible(False)
            # --- Start mouse tracking timer --- 
            print("[PlayerPage] Starting mouse tracking timer.")
            self.mouse_tracking_timer.start()
            # ----------------------------------
        else:
            # --- Stop mouse tracking timer --- 
            if self.mouse_tracking_timer.isActive():
                print("[PlayerPage] Stopping mouse tracking timer.")
                self.mouse_tracking_timer.stop()
            # ---------------------------------
            print("[PlayerPage] Switching display to Album Art.")
            self.media_display_stack.setCurrentIndex(0)
            self.album_art.setVisible(True)
            self.video_widget.setVisible(False)
            # Ensure overlay is visible when not in video mode
            self.player_overlay.show_overlay() 
            # Ensure album art is updated if needed (metadata might have changed)
            if self.persistent_player:
                # Use the metadata received directly from the signal
                self._update_track_info(metadata) 
                # current_metadata = self.persistent_player.get_current_track_metadata()
                # if current_metadata:
                #     self._update_track_info(current_metadata) 

    # +++ Add Timer Callback Method +++
    def _check_mouse_over_video(self):
        """Called by timer to check mouse position relative to the overlay widget."""
        if not self.video_widget.isVisible() or not self.player_overlay._video_mode_active:
            if self.mouse_tracking_timer.isActive() and not self.player_overlay._video_mode_active:
                self.mouse_tracking_timer.stop()
            # Ensure overlay is hidden if timer stops unexpectedly while video mode is active
            if self.player_overlay._video_mode_active:
                self.player_overlay.hide_overlay()
            return

        global_mouse_pos = QCursor.pos()
        
        # --- Get Overlay Global Geometry --- 
        # video_global_top_left = self.video_widget.mapToGlobal(QPoint(0, 0))
        # video_global_rect = QRect(video_global_top_left, self.video_widget.size())
        overlay_global_top_left = self.player_overlay.mapToGlobal(QPoint(0, 0))
        overlay_global_rect = QRect(overlay_global_top_left, self.player_overlay.size())
        # ----------------------------------

        # --- Check against Overlay Bounds --- 
        # if video_global_rect.contains(global_mouse_pos):
        if overlay_global_rect.contains(global_mouse_pos):
            # Mouse is inside overlay bounds
            if not self.player_overlay.isVisible():
                # print("[PlayerPage Timer Check] Mouse IN overlay - showing overlay") # Debug
                self.player_overlay.show_overlay()
        else:
            # Mouse is outside overlay bounds
            if self.player_overlay.isVisible():
                # print("[PlayerPage Timer Check] Mouse OUT overlay - hiding overlay") # Debug
                self.player_overlay.hide_overlay()
    # +++++++++++++++++++++++++++++++++

    # --- Add Event Filter Method +++