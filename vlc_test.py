import sys
import os
import vlc
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QFileDialog, QFrame
)
# Import QEvent and QMouseEvent, QKeyEvent for event handling
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QMouseEvent, QKeyEvent, QColor, QPalette

# Define the test video path
TEST_VIDEO_PATH = "d:\\test.mp4" # Make sure this file exists

class TestWidget(QWidget):
    """A QWidget subclass with event handlers for testing."""
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor('darkcyan')) # Visible background
        self.setPalette(palette)
        # Need focus policy to receive key events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        print("[TestWidget] Initialized.")

    def mousePressEvent(self, event: QMouseEvent):
        print(f"[TestWidget] mousePressEvent detected! Button: {event.button()}")
        super().mousePressEvent(event) # Call base class

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        print(f"[TestWidget] mouseDoubleClickEvent detected! Button: {event.button()}")
        super().mouseDoubleClickEvent(event) # Call base class

    def keyPressEvent(self, event: QKeyEvent):
        print(f"[TestWidget] keyPressEvent detected! Key: {event.key()}")
        super().keyPressEvent(event) # Call base class

class SimpleVLCTest(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VLC Input Test")
        self.setGeometry(100, 100, 640, 480)

        # --- VLC Setup ---
        self.instance = vlc.Instance()
        self.media_player = self.instance.media_player_new()
        # -----------------

        # --- UI Setup ---
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # Video Frame replaced with TestWidget
        self.test_widget = TestWidget(self) # Use our custom widget
        self.layout.addWidget(self.test_widget, 1) # Make it expand

        # Buttons
        self.play_test_button = QPushButton(f"Play Test Video ({os.path.basename(TEST_VIDEO_PATH)})")
        self.stop_button = QPushButton("Stop")
        self.layout.addWidget(self.play_test_button)
        self.layout.addWidget(self.stop_button)
        # -----------------

        # --- Connections ---
        self.play_test_button.clicked.connect(self._play_test_video)
        self.stop_button.clicked.connect(self._stop_video)
        # -------------------

        # Store widget handle (important!)
        # Get the handle AFTER the widget is created and potentially shown
        self.test_widget_handle = 0 # Initialize
        # We'll get the handle reliably in showEvent or just before playing

    def showEvent(self, event):
        """Get handle once widget is shown."""
        super().showEvent(event)
        # Getting handle here is generally more reliable
        if not self.test_widget_handle:
             self.test_widget_handle = int(self.test_widget.winId())
             print(f"[VLCTest] TestWidget Handle (HWND) obtained: {self.test_widget_handle}")

    def _play_test_video(self):
        """Play the predefined test video."""
        if not os.path.exists(TEST_VIDEO_PATH):
            print(f"[VLCTest] Error: Test video file not found at '{TEST_VIDEO_PATH}'")
            return

        # Ensure handle is valid
        if not self.test_widget_handle:
             self.test_widget_handle = int(self.test_widget.winId())
             if not self.test_widget_handle:
                  print("[VLCTest] Error: Could not get valid HWND for TestWidget.")
                  return
             print(f"[VLCTest] TestWidget Handle (HWND) obtained: {self.test_widget_handle}")


        print(f"[VLCTest] Playing test file: {TEST_VIDEO_PATH}")

        # Create new media
        media = self.instance.media_new(TEST_VIDEO_PATH)
        if not media:
            print("[VLCTest] Failed to create media object.")
            return

        # Stop previous playback if any
        if self.media_player.is_playing():
            print("[VLCTest] Stopping previous media...")
            self.media_player.stop()

        # Set media
        self.media_player.set_media(media)

        # Set HWND
        print(f"[VLCTest] Setting HWND: {self.test_widget_handle}")
        self.media_player.set_hwnd(self.test_widget_handle)

        # !!! Disable VLC Input Handling !!!
        try:
            self.media_player.video_set_mouse_input(False)
            print("[VLCTest] Called video_set_mouse_input(False)")
            self.media_player.video_set_key_input(False)
            print("[VLCTest] Called video_set_key_input(False)")
        except Exception as e:
            print(f"[VLCTest] Error disabling VLC input: {e}")


        # Play
        print("[VLCTest] Starting playback...")
        play_result = self.media_player.play()
        if play_result == -1:
            print("[VLCTest] Error starting playback.")
        else:
            print("[VLCTest] Play command issued.")
            # Give focus to the widget after starting playback
            self.test_widget.setFocus()


    def _stop_video(self):
        """Stop the VLC player."""
        print("[VLCTest] Attempting to stop media player...")
        self.media_player.stop()
        print("[VLCTest] Stop command issued.")

    def closeEvent(self, event):
        """Release VLC resources on close."""
        print("[VLCTest] Releasing VLC resources...")
        if self.media_player:
            self.media_player.stop() # Ensure stopped before release
            self.media_player.release()
        if self.instance:
            self.instance.release()
        print("[VLCTest] VLC resources released.")
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SimpleVLCTest()
    window.show()
    sys.exit(app.exec())
