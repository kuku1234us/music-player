"""
UI component to display the progress of video compression operations.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QStyleOption, QStyle
from PyQt6.QtCore import Qt, QTimer
from typing import Optional
from PyQt6.QtGui import QPainter, QColor

from qt_base_app.theme.theme_manager import ThemeManager

class VideoCompressionProgress(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = ThemeManager.instance()
        self.setObjectName("videoCompressionProgressOverlay")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Internal state for current file progress tracking
        self._current_task_id: Optional[str] = None
        
        self._default_progress_bar_chunk_style = ""

        self._setup_ui()
        self._apply_theme_styles()
        self.hide() # Hidden by default

    def _apply_theme_styles(self):
        sidebar_bg_hex = self.theme.get_color('background', 'sidebar')
        # Helper to convert hex to rgb tuple, assuming ThemeManager returns hex like "#RRGGBB"
        try:
            if sidebar_bg_hex.startswith('#') and len(sidebar_bg_hex) == 7:
                r, g, b = tuple(int(sidebar_bg_hex[i:i+2], 16) for i in (1, 3, 5))
            else: # Fallback if color format is unexpected
                r, g, b = 30, 30, 30 # Default dark gray
        except Exception:
            r, g, b = 30, 30, 30 # Default dark gray on any error

        self.setStyleSheet(f"""
            #videoCompressionProgressOverlay {{
                background-color: rgba({r}, {g}, {b}, 0.7);
                border-radius: 8px;
                color: {self.theme.get_color('text', 'primary')};
            }}
            #videoCompressionStatusLabel {{
                font-size: 10pt;
                font-weight: bold;
                color: {self.theme.get_color('text', 'primary')};
            }}
            #videoCompressionDetailsLabel {{
                font-size: 9pt;
                color: {self.theme.get_color('text', 'secondary')};
            }}
            #videoCompressionProgressBar {{
                font-size: 8pt;
                min-height: 12px;
                max-height: 12px;
                color: {self.theme.get_color('text', 'primary')}; /* Text color for progress bar text */
                background-color: {self.theme.get_color('background', 'tertiary')}; /* BG for the trough */
                border: 1px solid {self.theme.get_color('border', 'primary')};
                border-radius: 6px;
            }}
            #videoCompressionProgressBar::chunk {{
                background-color: {self.theme.get_color('colors', 'primary')}; /* Using theme primary for chunk */
                border-radius: 6px;
            }}
        """)
        # Store the default stylesheet part for the chunk for error state later
        self._default_progress_bar_chunk_style = f"background-color: {self.theme.get_color('colors', 'primary')}; border-radius: 6px;"

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 10, 15, 10)
        self.main_layout.setSpacing(8)

        self.status_label = QLabel("Video compression starting...")
        self.status_label.setObjectName("videoCompressionStatusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.details_label = QLabel("") # For current file name or specific errors
        self.details_label.setObjectName("videoCompressionDetailsLabel")
        self.details_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.details_label.setWordWrap(True)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("videoCompressionProgressBar")
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)

        self.main_layout.addWidget(self.status_label)
        self.main_layout.addWidget(self.details_label)
        self.main_layout.addWidget(self.progress_bar)

    def _reset_progress_bar_style(self):
        """Resets the progress bar to its default appearance."""
        self.progress_bar.setStyleSheet(f"""
            #videoCompressionProgressBar::chunk {{
                {self._default_progress_bar_chunk_style}
            }}
            #videoCompressionProgressBar {{ 
                font-size: 8pt; 
                min-height: 12px; 
                max-height: 12px; 
                color: {self.theme.get_color('text', 'primary')};
                background-color: {self.theme.get_color('background', 'tertiary')};
                border: 1px solid {self.theme.get_color('border', 'primary')};
                border-radius: 6px;
            }}
        """)
        self.progress_bar.show() # Ensure it is visible

    def show_compression_started(self, total_files: int):
        self._current_task_id = None # No specific task active yet
        self._reset_progress_bar_style()
        self.status_label.setText(f"Starting video compression for {total_files} file(s)...")
        self.details_label.setText("Please wait...")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Waiting...")
        print(f"[VideoCompressionProgress DEBUG] show_compression_started: About to show. Current size: {self.size()}, isVisible before show: {self.isVisible()}")
        self.show()
        self.adjustSize()
        print(f"[VideoCompressionProgress DEBUG] show_compression_started: Shown. New size: {self.size()}, isVisible after show: {self.isVisible()}")

    def show_file_progress(self, task_id: str, filename: str, current_file_index: int, total_files: int, percentage: float):
        """Called when a new file starts or its progress updates for the first time."""
        print(f"[VideoCompressionProgress DEBUG] show_file_progress: task_id={task_id}, filename={filename}, current_task_id={self._current_task_id}")
        self._current_task_id = task_id
        self._reset_progress_bar_style() # Reset style in case previous was an error
        
        self.status_label.setText(f"Compressing video {current_file_index + 1} of {total_files}:")
        self.details_label.setText(filename)
        self.progress_bar.setValue(int(percentage * 100))
        self.progress_bar.setFormat(f"{int(percentage * 100)}%")
        if not self.isVisible():
            self.show()
        self.adjustSize()

    def update_current_file_progress(self, task_id: str, percentage: float):
        """Updates progress for the currently displayed file if task_id matches."""
        if self._current_task_id == task_id:
            self.progress_bar.setValue(int(percentage * 100))
            self.progress_bar.setFormat(f"{int(percentage * 100)}%")
            # self.adjustSize() # Usually not needed for just progress value change
        else:
            print(f"[VideoCompressionProgress DEBUG] Ignoring progress update for task_id={task_id}, current_task_id={self._current_task_id}")
        # else: task_id does not match, this progress update is for a different (or old) task.

    def show_file_completed(self, original_filename: str, compressed_filename: str):
        # Progress bar should be at 100% from the last update_current_file_progress call
        self._reset_progress_bar_style() # Ensure it's not red
        self.details_label.setText(f"Completed: {original_filename} → {compressed_filename}")
        # Status label remains "Compressing video X of Y"
        self.adjustSize()

    def show_file_failed(self, filename: str, error_message: str):
        self.details_label.setText(f"Failed: {filename}\nError: {error_message}")
        # Change progress bar color to red for the error
        error_chunk_style = f"background-color: {self.theme.get_color('status', 'error')}; border-radius: 6px;"
        self.progress_bar.setStyleSheet(f"""
            #videoCompressionProgressBar::chunk {{
                {error_chunk_style}
            }}
            #videoCompressionProgressBar {{ 
                font-size: 8pt; 
                min-height: 12px; 
                max-height: 12px; 
                color: {self.theme.get_color('text', 'on_error')}; 
                background-color: {self.theme.get_color('background', 'tertiary')};
                border: 1px solid {self.theme.get_color('border', 'primary')};
                border-radius: 6px;
            }}
        """)
        self.progress_bar.setFormat("Failed")
        self.adjustSize()

    def show_batch_finished(self):
        self._current_task_id = None # No specific task active
        self._reset_progress_bar_style()
        self.status_label.setText("All video compressions finished!")
        self.details_label.setText("")
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("Complete")
        QTimer.singleShot(3000, self.hide) # Auto-hide after 3 seconds
        self.adjustSize()

    def show_error(self, message: str):
        self._current_task_id = None
        self.status_label.setText("Error")
        self.details_label.setText(message)
        self.progress_bar.hide() # Hide progress bar for general errors
        if not self.isVisible(): self.show()
        self.adjustSize()

    def paintEvent(self, event):
        # This paintEvent is necessary to make background-color and border-radius work correctly
        # for a QWidget that is styled using stylesheets, especially with WA_StyledBackground.
        opt = QStyleOption()
        opt.initFrom(self) # Initialize style option from the widget
        painter = QPainter(self)
        # Let the style draw the control, respecting the stylesheet for #videoCompressionProgressOverlay
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, painter, self)
        super().paintEvent(event) 