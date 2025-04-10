"""
Upload status overlay component.
"""
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QProgressBar
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

from qt_base_app.theme.theme_manager import ThemeManager

class UploadStatusOverlay(QWidget):
    """
    Overlay widget that shows upload status and progress.
    Automatically hides itself after completion or error.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = ThemeManager.instance()
        self.setup_ui()
        self.hide()
        
    def setup_ui(self):
        """Set up the overlay UI"""
        # Set up the layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(5)
        
        # Status label
        self.status_label = QLabel()
        self.status_label.setStyleSheet(f"""
            color: {self.theme.get_color('text', 'primary')};
            font-size: 14px;
        """)
        layout.addWidget(self.status_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {self.theme.get_color('background', 'tertiary')};
                border: none;
                border-radius: 3px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {self.theme.get_color('accent', 'primary')};
                border-radius: 3px;
            }}
        """)
        layout.addWidget(self.progress_bar)
        
        # Set fixed size
        self.setFixedSize(300, 80)
        
        # Style the widget
        self.setStyleSheet(f"""
            background-color: {self.theme.get_color('background', 'secondary')};
            border: 1px solid {self.theme.get_color('border', 'primary')};
            border-radius: 5px;
        """)
        
    def show_upload_started(self, filename):
        """Show upload started status"""
        self.status_label.setText(f"Uploading: {filename}")
        self.progress_bar.setValue(0)
        self.show()
        self.raise_()
        
    def show_upload_progress(self, percentage):
        """Update progress bar"""
        self.progress_bar.setValue(percentage)
        
    def show_upload_completed(self, filename):
        """Show upload completed status"""
        self.status_label.setText(f"Upload completed: {filename}")
        self.progress_bar.setValue(100)
        # Hide after 3 seconds
        QTimer.singleShot(3000, self.hide)
        
    def show_upload_failed(self, error_msg):
        """Show upload failed status"""
        self.status_label.setText(f"Upload failed: {error_msg}")
        self.status_label.setStyleSheet(f"""
            color: {self.theme.get_color('error', 'primary')};
            font-size: 14px;
        """)
        # Hide after 5 seconds
        QTimer.singleShot(5000, self.hide)
        
    def hideEvent(self, event):
        """Reset styles when hiding"""
        super().hideEvent(event)
        self.status_label.setStyleSheet(f"""
            color: {self.theme.get_color('text', 'primary')};
            font-size: 14px;
        """)
        self.progress_bar.setValue(0) 