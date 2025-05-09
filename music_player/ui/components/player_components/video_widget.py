"""
Video widget for displaying video output using VLC.
"""
# --- Use PyQt6 --- 
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
# --- Add QKeyEvent import --- 
from PyQt6.QtGui import QKeyEvent, QMouseEvent
# ----------------------------
# --- Add typing for handler --- 
from typing import Optional
from music_player.ui.vlc_player.hotkey_handler import HotkeyHandler # Import for type hint
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
        
        # --- Set focus policy --- 
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        # ------------------------
        
        # --- Add handler reference --- 
        self.hotkey_handler: Optional[HotkeyHandler] = None
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
