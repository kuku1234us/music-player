import os
import sys
import vlc
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QStackedWidget, QLabel
)
from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal, pyqtSlot

# Configuration
VLC_ARGS = [
    "--no-video-title-show",
    "--avcodec-hw=any",
    "--vout=directdraw",
    "--quiet"
]

TEST_FILES = [
    r"D:\test\Thank you for coming to see me.webm",
    r"D:\test\Solo dance at sunset beach.webm",
    r"D:\test\Turn up the volume.webm",
    r"D:\test\I took good care of myself.webm"
]

class VLCWorker(QObject):
    """
    Handles VLC playback for a SINGLE session. 
    Once stopped, this worker and its thread are intended to be destroyed.
    """
    # Signal to trigger stop from main thread (connected to internal slot)
    sig_stop_command = pyqtSignal()
    # Signal when cleanup is complete and thread can die
    sig_done = pyqtSignal()

    def __init__(self, name, surface_id, file_path):
        super().__init__()
        self.name = name
        self.surface_id = surface_id
        self.file_path = file_path
        self.instance = None
        self.player = None
        
        # Connect the command signal to the implementation slot
        self.sig_stop_command.connect(self.stop_and_cleanup)

    @pyqtSlot()
    def run_play(self):
        """Initializes and starts playback. Called when thread starts."""
        print(f"[{self.name}] Initializing & Playing: {os.path.basename(self.file_path)}")
        try:
            self.instance = vlc.Instance(VLC_ARGS)
            self.player = self.instance.media_player_new()
            
            if sys.platform == "win32":
                self.player.set_hwnd(self.surface_id)
            
            media = self.instance.media_new(self.file_path)
            self.player.set_media(media)
            self.player.play()
        except Exception as e:
            print(f"[{self.name}] Error starting playback: {e}")

    @pyqtSlot()
    def stop_and_cleanup(self):
        """Stops playback and releases resources. This is where it might block."""
        print(f"[{self.name}] Stopping... (might block)")
        if self.player:
            self.player.stop()
            self.player.release()
            self.player = None
        
        if self.instance:
            self.instance.release()
            self.instance = None
            
        print(f"[{self.name}] Cleanup finished. Emitting done.")
        self.sig_done.emit()

class VideoSurface(QWidget):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.setStyleSheet("background-color: black; border: 2px solid #333;")
        self.label = QLabel(name, self)
        self.label.setStyleSheet("color: white; font-weight: bold; background: rgba(0,0,0,0.5);")
        self.label.move(10, 10)

class MultiThreadTestPlayer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VLC Full Multi-Threading (Safe Cleanup)")
        self.resize(1000, 750)

        # UI Components
        layout = QVBoxLayout(self)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # Controls
        btn_layout = QHBoxLayout()
        for path in TEST_FILES:
            btn = QPushButton(os.path.basename(path))
            btn.setFixedHeight(40)
            btn.clicked.connect(lambda checked, p=path: self.play_new(p))
            btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)

        self.status = QLabel("Ready")
        layout.addWidget(self.status)

        # Track current active components
        self.current_surface = None
        self.current_worker = None
        self.current_thread = None
        
        # Keep references to dying threads to prevent premature GC/Crash
        self.zombie_threads = [] 
        
        self.counter = 0

    def play_new(self, file_path):
        self.counter += 1
        worker_name = f"Worker_{self.counter}"
        print(f"\n--- UI REQUEST: Play {os.path.basename(file_path)} ({worker_name}) ---")

        # 1. Prepare OLD components for cleanup
        old_surface = self.current_surface
        old_worker = self.current_worker
        old_thread = self.current_thread

        if old_worker and old_thread:
            print(f"--- Signaling {old_worker.name} to stop/die in background ---")
            
            # Store reference to prevent GC
            self.zombie_threads.append(old_thread)
            
            # Trigger the stop
            old_worker.sig_stop_command.emit()
            
            # Setup cleanup chain
            old_worker.sig_done.connect(old_thread.quit)
            
            # When thread actually finishes (after stop() is done)
            old_thread.finished.connect(lambda t=old_thread: self.cleanup_zombie(t))
            old_thread.finished.connect(old_thread.deleteLater)
            old_thread.finished.connect(old_worker.deleteLater)
            old_thread.finished.connect(old_surface.deleteLater)
            old_thread.finished.connect(lambda n=old_worker.name: print(f"[{n}] Thread & Surface Destroyed"))

        # 2. Create NEW components
        new_surface = VideoSurface(f"Surface {self.counter}")
        self.stack.addWidget(new_surface)
        
        new_thread = QThread()
        new_worker = VLCWorker(worker_name, int(new_surface.winId()), file_path)
        new_worker.moveToThread(new_thread)
        
        new_thread.started.connect(new_worker.run_play)
        
        # 3. Update State & Switch UI
        self.current_surface = new_surface
        self.current_worker = new_worker
        self.current_thread = new_thread
        
        self.stack.setCurrentWidget(new_surface)
        self.status.setText(f"Active: {worker_name} | File: {os.path.basename(file_path)}")
        
        # 4. Launch Thread
        new_thread.start()

    def cleanup_zombie(self, thread):
        if thread in self.zombie_threads:
            self.zombie_threads.remove(thread)
            # print(f"Removed zombie thread. Remaining: {len(self.zombie_threads)}")

    def closeEvent(self, event):
        # Stop current
        if self.current_worker:
            self.current_worker.sig_stop_command.emit()
            self.current_thread.quit()
            self.current_thread.wait()
            
        # Wait for all zombies
        if self.zombie_threads:
            print(f"Waiting for {len(self.zombie_threads)} background threads to finish...")
            for t in self.zombie_threads:
                t.quit()
                t.wait()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MultiThreadTestPlayer()
    window.show()
    sys.exit(app.exec())