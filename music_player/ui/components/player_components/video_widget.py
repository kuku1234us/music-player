"""
Video widget for displaying video output using VLC.
"""
from qt_base_app.models.logger import Logger
# --- Use PyQt6 --- 
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QUrl
# --- Add QKeyEvent import --- 
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QDragEnterEvent, QDropEvent
# --- Add drag and drop imports ---
from PyQt6.QtCore import QMimeData
# ----------------------------
# --- Add typing for handler --- 
from typing import Optional
from music_player.ui.vlc_player.hotkey_handler import HotkeyHandler # Import for type hint
# --- Add os import for file validation ---
import os
# --------------------------

class VideoWidget(QWidget):
    """
    A simple QWidget subclass intended to be used as a video output surface for VLC.
    """
    # Signal to request toggling full-screen mode
    fullScreenRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Enable background styling - Still potentially useful for styling borders etc.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # IMPORTANT (Windows/VLC embedding):
        # Ensure this widget is backed by a real native window handle (HWND).
        # If VLC does not receive a valid HWND, it may open its own popup window.
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        try:
            # Force creation of the native handle early
            _ = self.winId()
        except Exception:
            pass
        
        # --- Set focus policy --- 
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        # ------------------------
        
        # --- Enable drag and drop ---
        self.setAcceptDrops(True)
        # ---------------------------
        
        # --- Add handler reference --- 
        self.hotkey_handler: Optional[HotkeyHandler] = None
        # --- Add main player reference for drag and drop ---
        self.main_player = None
        # -----------------------------

        # Removed background color settings to let VLC draw

        # Set size policy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # --- Add click timer to handle double-click detection ---
        self._click_timer = QTimer()
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(200)  # 200ms is typical double-click threshold
        self._click_timer.timeout.connect(self._handle_single_click)
        self._pending_click = False
        # -----------------------------------------------------
    
    # --- Add handler setter --- 
    def set_hotkey_handler(self, handler: Optional[HotkeyHandler]):
        """Sets the hotkey handler instance to use."""
        self.hotkey_handler = handler
    # --------------------------
    
    # --- Add main player setter ---
    def set_main_player(self, main_player):
        """Sets the main player instance for drag and drop functionality."""
        self.main_player = main_player
    # ------------------------------
    
    # --- Implement keyPressEvent --- 
    def keyPressEvent(self, event: QKeyEvent):
        """Handle key press events by forwarding to the hotkey handler if available."""
        if self.hotkey_handler:
            handled = self.hotkey_handler.handle_key_press(event)
            if handled:
                event.accept() # Consume the event if handled
                return
                
        # If not handled or no handler, call base implementation
        super().keyPressEvent(event)
    # -------------------------------

    # --- Modified mousePressEvent --- 
    def mousePressEvent(self, event):
        """Handle left mouse clicks to toggle play/pause with double-click detection."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Start the timer and flag that we have a pending click
            self._pending_click = True
            self._click_timer.start()
            
        # Always call base implementation to handle focus etc.
        super().mousePressEvent(event)
    # ---------------------------------

    # --- Add method to handle single click after timer ---
    def _handle_single_click(self):
        """Called when click timer expires - confirmed to be a single click."""
        if self._pending_click and self.hotkey_handler:
            self.hotkey_handler._toggle_play_pause()
        self._pending_click = False
    # ---------------------------------------------------

    # --- Modified mouseDoubleClickEvent ---
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Handle left mouse double-clicks to request full-screen toggle."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Cancel the pending single click
            self._pending_click = False
            self._click_timer.stop()
            
            # Request fullscreen mode
            self.fullScreenRequested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
    # --------------------------------------

    # --- Add drag enter event handler ---
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events to accept media files."""
        if event.mimeData().hasUrls():
            # Check if any of the URLs are media files
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if self._is_media_file(file_path):
                        event.acceptProposedAction()
                        return
        event.ignore()
    # -----------------------------------

    # --- Add drop event handler ---
    def dropEvent(self, event: QDropEvent):
        """Handle drop events to load and play media files."""
        if not self.main_player:
            Logger.instance().warning(caller="VideoWidget", msg="[VideoWidget] Warning: No main player reference set for drag and drop")
            event.ignore()
            return
            
        if event.mimeData().hasUrls():
            # Get the first valid media file from the dropped URLs
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if self._is_media_file(file_path) and os.path.exists(file_path):
                        Logger.instance().debug(caller="VideoWidget", msg=f"[VideoWidget] Media file dropped: {file_path}")
                        
                        # Use the uniform loading method from MainPlayer
                        success = self.main_player.load_media_unified(file_path, "drag_and_drop")
                        
                        if success:
                            event.acceptProposedAction()
                            Logger.instance().debug(caller="VideoWidget", msg=f"[VideoWidget] Successfully loaded dropped media: {os.path.basename(file_path)}")
                        else:
                            Logger.instance().error(caller="VideoWidget", msg=f"[VideoWidget] Failed to load dropped media: {file_path}")
                            event.ignore()
                        return
                        
        event.ignore()
    # ------------------------------

    # --- Add helper method to check if file is a media file ---
    def _is_media_file(self, file_path: str) -> bool:
        """
        Check if the given file path is a supported media file.
        
        Args:
            file_path (str): Path to the file to check
            
        Returns:
            bool: True if the file is a supported media file, False otherwise
        """
        if not file_path:
            return False
            
        # Get file extension
        _, ext = os.path.splitext(file_path.lower())
        
        # Define supported media extensions
        supported_extensions = {
            # Audio formats
            '.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.wma', '.opus',
            # Video formats  
            '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.m4v', '.webm',
            '.mpg', '.mpeg', '.3gp', '.ts', '.mts', '.m2ts', '.vob', '.divx',
            # Playlist formats
            '.m3u', '.m3u8', '.pls'
        }
        
        return ext in supported_extensions
    # ----------------------------------------------------------
