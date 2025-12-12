"""
Manages the full-screen video experience, including a dedicated host window
and on-screen controls.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy, QHBoxLayout
from PyQt6.QtCore import Qt, QObject, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QKeyEvent
from typing import Optional
from qt_base_app.models.logger import Logger

# Forward declaration for type hinting if VideoWidget is in another file and causes circular import
# For now, assuming direct import is fine or will be resolved.
# class VideoWidget(QWidget): pass
# class MainPlayer(QObject): pass # Assuming MainPlayer is a QObject or QWidget

class FullScreenVideoHostWindow(QWidget):
    """
    A frameless window to host the VideoWidget and on-screen controls
    when in full-screen mode.
    """
    # Signal to indicate ESC key was pressed for exiting full screen
    escape_pressed = pyqtSignal()
    # --- Add F12 pressed signal ---
    f12_pressed_in_host = pyqtSignal()
    # -----------------------------

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("FullScreenVideoHostWindow")

        # Configure window flags for a frameless, top-level window
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True) # For stylesheet application

        # Set a default background color (e.g., black)
        # This ensures no desktop content shows through if video has letterboxing
        self.setStyleSheet("QWidget#FullScreenVideoHostWindow { background-color: black; }")

        # Main layout for this host window
        # This layout will hold the VideoWidget and later the OnScreenControlsPanel
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0) # No margins, video should fill
        self._main_layout.setSpacing(0)
        # self.setLayout(self._main_layout)

        # Placeholder for VideoWidget and OnScreenControlsPanel
        # These will be added/managed by FullScreenManager
        self._video_widget_placeholder: Optional[QWidget] = None
        self._controls_panel_placeholder: Optional[QWidget] = None
        
        # Ensure it can receive key events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_video_widget(self, video_widget: QWidget):
        """
        Sets the VideoWidget to be displayed in this host window.
        (Actual re-parenting and layout addition will be managed by FullScreenManager)
        """
        # For now, just store a reference or use a placeholder.
        # In a later step, this is where video_widget would be added to _main_layout.
        # Example of adding to layout (actual addition will be in FullScreenManager during transition):
        # if self._video_widget_placeholder:
        #     self._main_layout.removeWidget(self._video_widget_placeholder)
        # self._video_widget_placeholder = video_widget
        # self._main_layout.addWidget(self._video_widget_placeholder, 1) # Video widget gets stretch factor
        pass

    def set_controls_panel(self, controls_panel: QWidget):
        """
        Sets the OnScreenControlsPanel to be displayed over the video.
        """
        # Example of adding to layout (actual addition will be in FullScreenManager during transition):
        # if self._controls_panel_placeholder:
        #     self._main_layout.removeWidget(self._controls_panel_placeholder)
        # self._controls_panel_placeholder = controls_panel
        # self._controls_panel_placeholder.addWidget(self._controls_panel_placeholder, 0) # Controls panel, no stretch
        # self._controls_panel_placeholder.raise_() # Ensure it's on top
        pass
        
    def keyPressEvent(self, event: QKeyEvent) -> None: # Corrected type hint
        """Handle key press events, specifically ESC for exiting full screen."""
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            event.accept()
        # --- Handle F12 in host window --- 
        elif event.key() == Qt.Key.Key_F12:
            self.f12_pressed_in_host.emit()
            event.accept()
        # ---------------------------------
        else:
            # Important: Forward other key events to allow main player hotkeys to work
            # This might need to be more sophisticated depending on focus and event propagation strategy
            # For now, let parent (if any) or Qt handle it.
            # If this window is top-level, unhandled events might not propagate easily.
            # We will refine this in Milestone 7 (Ensuring Consistent Hotkey Operation).
            super().keyPressEvent(event)


class FullScreenManager(QObject):
    """
    Manages the transition to and from full-screen video playback.
    Handles the FullScreenVideoHostWindow, re-parenting of VideoWidget,
    and coordination of on-screen controls.
    """
    # Define VideoWidget and MainPlayer types more concretely if possible, or use 'QWidget' and 'QObject'
    # from music_player.ui.components.player_components.video_widget import VideoWidget # Assuming this path
    # from music_player.ui.vlc_player.main_player import MainPlayer # Assuming this path

    # --- Add signal for ESC exit request ---
    exit_requested_via_escape = pyqtSignal()
    # ---------------------------------------
    # --- Add signal for when exit is complete ---
    did_exit_full_screen = pyqtSignal()
    # -----------------------------------------

    def __init__(self, 
                 video_widget: QWidget, # Actual type: VideoWidget
                 main_player: QObject,  # Actual type: MainPlayer
                 parent: Optional[QObject] = None):
        super().__init__(parent)

        self._is_full_screen: bool = False
        
        self._video_widget_ref: QWidget = video_widget # Store reference to the actual VideoWidget
        self._main_player_ref: QObject = main_player   # Store reference to MainPlayer
        
        # To store original state of the VideoWidget
        self._original_parent_widget_ref: Optional[QWidget] = None # Renamed for clarity
        self._original_layout_ref: Optional[QVBoxLayout | QHBoxLayout] = None # Store layout ref
        self._original_layout_index: int = -1
        self._original_layout_stretch: int = 0
        self._original_geometry = None # To store video_widget's geometry if needed
        self._original_window_flags = None # To store video_widget's original window flags if it was a window
        self._video_widget_was_visible: bool = True

        # Create the dedicated host window instance
        self._host_window = FullScreenVideoHostWindow()
        # --- Connect escape_pressed to new internal slot --- 
        self._host_window.escape_pressed.connect(self._emit_exit_request_due_to_escape)
        # --- Connect F12 pressed in host to toggle_full_screen --- 
        self._host_window.f12_pressed_in_host.connect(self.toggle_full_screen)
        # ---------------------------------------------------------

        # Placeholder for OnScreenControlsPanel instance
        self._on_screen_controls: Optional[QWidget] = None # To be created in Milestone 5

    @property
    def is_full_screen(self) -> bool:
        """Returns True if currently in full-screen mode, False otherwise."""
        return self._is_full_screen

    def toggle_full_screen(self):
        """Toggles the full-screen mode."""
        if self._is_full_screen:
            self.exit_full_screen()
        else:
            self.enter_full_screen()

    def enter_full_screen(self):
        """Enters full-screen mode."""
        if self._is_full_screen or not self._video_widget_ref:
            return

        # 1. Store original parent and layout information
        self._original_parent_widget_ref = self._video_widget_ref.parentWidget()
        self._video_widget_was_visible = self._video_widget_ref.isVisible()
        self._original_geometry = self._video_widget_ref.geometry() # Store geometry
        self._original_window_flags = self._video_widget_ref.windowFlags() # Store flags if it was a window
        
        if self._original_parent_widget_ref:
            original_layout = self._original_parent_widget_ref.layout()
            if original_layout and isinstance(original_layout, (QVBoxLayout, QHBoxLayout)):
                self._original_layout_ref = original_layout
                self._original_layout_index = original_layout.indexOf(self._video_widget_ref)
                if self._original_layout_index != -1:
                    item = original_layout.itemAt(self._original_layout_index)
                    if item:
                        self._original_layout_stretch = original_layout.stretch(self._original_layout_index)
                # Remove from original layout
                original_layout.removeWidget(self._video_widget_ref)
            else:
                self._original_layout_ref = None # Not a recognized QBoxLayout
                self._original_layout_index = -1

        # 2. Re-parent VideoWidget to the host window
        self._video_widget_ref.setParent(self._host_window)
        
        # 3. Add VideoWidget to host window's layout
        host_layout = self._host_window._main_layout # Directly access the layout we know was created
        
        # Clear any previous widget from the layout
        while host_layout.count() > 0:
            item = host_layout.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None) 
        
        host_layout.addWidget(self._video_widget_ref, 1) 

        # 4. Show host window in full screen
        self._video_widget_ref.show() # Ensure video widget is visible within the new parent
        self._host_window.showFullScreen()
        self._host_window.activateWindow() # Bring to front and give focus
        self._host_window.raise_()
        self._host_window.setFocus()
        # --- Try to force geometry update for scaling ---
        if self._host_window.layout():
            self._host_window.layout().activate()
        self._video_widget_ref.updateGeometry()
        # --- Explicitly set VideoWidget geometry to fill host window ---
        self._video_widget_ref.setGeometry(self._host_window.contentsRect())
        # -------------------------------------------------------------
        # -------------------------------------------------
        
        # 5. Update VLC backend HWND
        # MainPlayer's _set_vlc_window_handle method is the designated way to interact
        # with the VLC backend for setting the video output.
        if hasattr(self._main_player_ref, '_set_vlc_window_handle'):
            # pylint: disable=protected-access
            self._main_player_ref._set_vlc_window_handle(self._video_widget_ref) # type: ignore
        else:
            Logger.instance().warning(caller="FullScreenManager", msg="[FullScreenManager] Warning: MainPlayer does not have the _set_vlc_window_handle method.")

        self._is_full_screen = True
        Logger.instance().debug(caller="FullScreenManager", msg="[FullScreenManager] Entered full-screen mode.")

    def exit_full_screen(self):
        """Exits full-screen mode."""
        if not self._is_full_screen or not self._video_widget_ref:
            return

        # 1. Remove VideoWidget from host window's layout
        host_layout = self._host_window.layout()
        if host_layout:
            host_layout.removeWidget(self._video_widget_ref)
        
        # 2. Detach VideoWidget by setting its parent to None.
        # PlayerPage will be responsible for making it visible in its QStackedWidget.
        self._video_widget_ref.setParent(None) 
        
        # Restore original window flags if it was a standalone window before
        # This case is less likely if VideoWidget always lives within PlayerPage initially.
        if not self._original_parent_widget_ref: # Was a top-level window before full screen
            self._video_widget_ref.setWindowFlags(self._original_window_flags or Qt.WindowType.Widget)
            # Geometry and visibility will be handled by PlayerPage or its own logic if it's shown standalone

        # 3. Hide host window
        self._host_window.showNormal() # Recommended before hide if it was full screen
        self._host_window.hide()

        # 4. Update VLC backend HWND
        # When exiting full screen, the VideoWidget is detached.
        # MainPlayer's _set_vlc_window_handle(None) will tell the backend to detach.
        if hasattr(self._main_player_ref, '_set_vlc_window_handle'):
            # pylint: disable=protected-access
            self._main_player_ref._set_vlc_window_handle(None) # type: ignore
        else:
            Logger.instance().warning(caller="FullScreenManager", msg="[FullScreenManager] Warning: MainPlayer does not have the _set_vlc_window_handle method for exit.")
        
        # Visibility of _video_widget_ref is now PlayerPage's responsibility via _sync_player_page_display
        # We removed the explicit self._video_widget_ref.show()/hide() here.

        # --- Add diagnostic prints --- 
        Logger.instance().debug(caller="full_screen_video", msg=f"[FullScreenManager exit] VideoWidget parent after setParent(None): {self._video_widget_ref.parentWidget()}")
        Logger.instance().debug(caller="full_screen_video", msg=f"[FullScreenManager exit] VideoWidget visible (state before PlayerPage sync): {self._video_widget_ref.isVisible()}")
        Logger.instance().debug(caller="full_screen_video", msg=f"[FullScreenManager exit] VideoWidget geometry (state before PlayerPage sync): {self._video_widget_ref.geometry()}")
        # The following might be None now if original_layout_ref was for a different parent structure
        # if self._original_parent_widget_ref and self._original_parent_widget_ref.layout():
        # -----------------------------
            
        # Restore focus to the main application window or original parent's window.
        main_app_window = None
        if self._original_parent_widget_ref:
            main_app_window = self._original_parent_widget_ref.window()
        elif hasattr(self._main_player_ref, 'window'): # If MainPlayer is a QWidget
             main_app_window = self._main_player_ref.window() # type: ignore
        elif isinstance(self._main_player_ref, QWidget):
             main_app_window = self._main_player_ref.window()
        
        if main_app_window and main_app_window.isActiveWindow():
            main_app_window.activateWindow()
            main_app_window.setFocus()
        elif main_app_window: # If not active, still try to show and activate
            main_app_window.show()
            main_app_window.activateWindow()
            main_app_window.setFocus()

        self._is_full_screen = False
        Logger.instance().debug(caller="FullScreenManager", msg="[FullScreenManager] Exited full-screen mode (VideoWidget detached).")
        self.did_exit_full_screen.emit() # Emit signal after exit is complete

    # --- Add new slot to emit dedicated signal for ESC --- 
    @pyqtSlot()
    def _emit_exit_request_due_to_escape(self):
        """Emits a signal indicating an exit was requested via ESC key from host window."""
        if self._is_full_screen: # Only emit if we are actually in full screen
            Logger.instance().debug(caller="FullScreenManager", msg="[FullScreenManager] Exit requested via ESC, emitting signal.")
            self.exit_requested_via_escape.emit()
    # -----------------------------------------------------

    def cleanup(self):
        """Clean up resources, like closing the host window if it's not parented."""
        if self._host_window:
            self._host_window.close() # Explicitly close the window
            # self._host_window.deleteLater() # Ensure it's deleted if it has no parent

# Example Usage (Conceptual - will be integrated into MainPlayer/UI Controller)
if __name__ == '__main__':
    from PyQt6.QtWidgets import QApplication, QPushButton, QFrame
    import sys

    app = QApplication(sys.argv)

    # Create dummy VideoWidget and MainPlayer for testing FullScreenManager structure
    class DummyVideoWidget(QFrame): # Use QFrame for easy visualization
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setStyleSheet("background-color: blue; border: 2px solid red;")
            self.setMinimumSize(320, 240)
            self.label = QVBoxLayout(self) # Changed from QLabel to QVBoxLayout
            # temp_label = QLabel("Video Output Area", self) # Create a QLabel
            # self.label.addWidget(temp_label) # Add QLabel to QVBoxLayout
            self.setLayout(self.label)


    class DummyMainPlayer(QObject):
        def _set_vlc_window_handle(self, widget): # type: ignore
            if widget:
                Logger.instance().debug(caller="full_screen_video", msg=f"DummyMainPlayer: Setting VLC HWND to {widget.winId()}")
            else:
                Logger.instance().debug(caller="full_screen_video", msg="DummyMainPlayer: Clearing VLC HWND")

    # Main application window (simulating the context where VideoWidget lives)
    main_app_window = QWidget()
    main_app_window.setWindowTitle("Main Application Window")
    main_app_layout = QVBoxLayout(main_app_window)
    
    video_widget_container = QWidget() # A container for the video widget
    video_widget_container_layout = QVBoxLayout(video_widget_container)
    
    actual_video_widget = DummyVideoWidget()
    video_widget_container_layout.addWidget(actual_video_widget)
    
    main_app_layout.addWidget(video_widget_container)
    
    dummy_main_player = DummyMainPlayer()

    # Instantiate the FullScreenManager
    # Pass the actual video widget and a dummy main player
    fs_manager = FullScreenManager(video_widget=actual_video_widget, main_player=dummy_main_player)

    toggle_button = QPushButton("Toggle Full Screen (M1 Test)")
    def on_toggle():
        # fs_manager.toggle_full_screen() # This will be fully implemented in M2
        # For M1, let's just test showing/hiding the host window normally
        if fs_manager.is_full_screen:
            Logger.instance().debug(caller="full_screen_video", msg="M1 Test: Requesting exit from pseudo-fullscreen")
            fs_manager.exit_full_screen() # Now calls the M2 implemented logic
            # fs_manager._host_window.hide() # Manually hide for M1 test - NO LONGER NEEDED
            # In M2, VideoWidget would be re-parented back here
            # if actual_video_widget.parent() != video_widget_container: # If it was detached
            #     video_widget_container_layout.addWidget(actual_video_widget) # Add it back
            # actual_video_widget.show() # Should be handled by exit_full_screen


        else:
            Logger.instance().debug(caller="full_screen_video", msg="M1 Test: Requesting entry to pseudo-fullscreen")
            fs_manager.enter_full_screen() # Now calls the M2 implemented logic
             # In M2, VideoWidget would be re-parented to host_window
            # actual_video_widget.setParent(None) # Detach from current parent for M1 test - NO LONGER NEEDED
            # fs_manager._host_window.layout().addWidget(actual_video_widget) # NO LONGER NEEDED, handled by enter_full_screen
            # fs_manager._host_window.show() # Show host window normally for M1 - NO LONGER NEEDED
            # fs_manager._host_window.resize(640,480) # Give it a size - NO LONGER NEEDED

    toggle_button.clicked.connect(on_toggle)
    main_app_layout.addWidget(toggle_button)
    
    main_app_window.resize(400, 300)
    main_app_window.show()

    sys.exit(app.exec()) 