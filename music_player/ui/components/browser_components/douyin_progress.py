from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer
from qt_base_app.theme.theme_manager import ThemeManager

class DouyinProgress(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = ThemeManager.instance()
        self.setObjectName("douyinProgressOverlay")
        self.hide()
        self.main_layout = QVBoxLayout(self)
        self.status_label = QLabel("Starting...")
        self.main_layout.addWidget(self.status_label)
        self.setStyleSheet(f"background-color: {self.theme.get_color('background', 'primary')}; border: 1px solid {self.theme.get_color('border', 'primary')}; border-radius: 5px;")

    def show_trimming_started(self, total_files):
        self.status_label.setText(f"Re-encoding & trimming {total_files} files (720p, max 3 concurrent)...")
        self.show()

    def show_file_progress(self, task_id, filename, index, total, percent):
        self.status_label.setText(f"Processing [{index}/{total}]: {filename} ({percent:.0%})")
        self.show()

    def update_current_file_progress(self, task_id, percent):
        # Update logic here if needed, for now covered by show_file_progress
        pass

    def show_file_completed(self, filename, new_filename):
        self.status_label.setText(f"Re-encoded & trimmed: {filename}")
        self.show()

    def show_file_failed(self, filename, error):
        self.status_label.setText(f"Failed: {filename}\nError: {error}")
        self.show()

    def show_batch_finished(self):
        self.status_label.setText("Re-encoding complete. Merging videos...")
        self.show()

    def show_merge_started(self):
        self.status_label.setText("Merging videos (stream copy - fast)...")
        self.show()

    def show_merge_progress(self, percent):
        self.status_label.setText(f"Merging with stream copy... ({percent:.0%})")
        self.show()

    def show_merge_completed(self, output_filename):
        self.status_label.setText(f"Merge complete: {output_filename}")
        QTimer.singleShot(3000, self.hide)
        self.show()

    def show_merge_failed(self, error):
        self.status_label.setText(f"Merge failed: {error}")
        QTimer.singleShot(3000, self.hide)
        self.show()

    def show_process_finished(self):
        self.status_label.setText("Douyin processing complete!")
        QTimer.singleShot(2000, self.hide)
        self.show() 