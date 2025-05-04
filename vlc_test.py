import sys
import os
import vlc
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QFileDialog, QFrame
)
from PyQt6.QtCore import Qt

class SimpleVLCTest(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Minimal VLC + Qt Test")
        self.setGeometry(100, 100, 640, 480)

        # --- VLC Setup ---
        # No extra arguments initially to keep it simple
        self.instance = vlc.Instance() 
        self.media_player = self.instance.media_player_new()
        # -----------------

        # --- UI Setup ---
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # Video Frame (just a QWidget)
        self.video_frame = QFrame(self)
        self.video_frame.setFrameShape(QFrame.Shape.Box)
        self.video_frame.setFrameShadow(QFrame.Shadow.Sunken)
        self.video_frame.setStyleSheet("background-color: black;")
        self.layout.addWidget(self.video_frame, 1) # Make it expand

        # Buttons
        self.select_button = QPushButton("Select Video and Play")
        self.stop_button = QPushButton("Stop")
        self.layout.addWidget(self.select_button)
        self.layout.addWidget(self.stop_button)
        # -----------------

        # --- Connections ---
        self.select_button.clicked.connect(self._select_and_play)
        self.stop_button.clicked.connect(self._stop_video)
        # -------------------

        # Store video frame handle (important!)
        # We get the handle once the widget is created, 
        # it should remain valid unless the widget is destroyed.
        self.video_frame_handle = int(self.video_frame.winId())
        print(f"[VLCTest] Video Frame Handle (HWND): {self.video_frame_handle}")

    def _select_and_play(self):
        """Open a file dialog and play the selected video."""
        filepath, _ = QFileDialog.getOpenFileName(self, "Select Video File")
        if not filepath:
            print("[VLCTest] No file selected.")
            return

        print(f"[VLCTest] Selected file: {filepath}")

        # Create new media
        media = self.instance.media_new(filepath)
        if not media:
            print("[VLCTest] Failed to create media object.")
            return

        # Stop previous playback if any (important for testing switching)
        if self.media_player.is_playing():
            print("[VLCTest] Stopping previous media before playing new one...")
            self.media_player.stop()
            # Optional: A small delay might sometimes help, but let's test without first
            # time.sleep(0.1) 

        # Set media and window handle
        self.media_player.set_media(media)
        print(f"[VLCTest] Setting HWND: {self.video_frame_handle}")
        self.media_player.set_hwnd(self.video_frame_handle)

        # Play
        print("[VLCTest] Starting playback...")
        play_result = self.media_player.play()
        if play_result == -1:
            print("[VLCTest] Error starting playback.")
        else:
            print("[VLCTest] Play command issued.")

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
