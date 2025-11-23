"""
Base customizable UI component for displaying progress overlays.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QStyleOption, QStyle
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter
from qt_base_app.theme.theme_manager import ThemeManager

class BaseProgressOverlay(QWidget):
    """
    A generic, customizable progress overlay component.
    Can be subclassed or used directly for various progress reporting tasks.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = ThemeManager.instance()
        # Default object name for basic styling hook, subclasses can override or add their own ID
        self.setObjectName("baseProgressOverlay")
        
        # Window flags: No frame, stays on top (of parent usually)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Internal state
        self._current_task_id = None
        self._default_progress_bar_chunk_style = ""

        self._setup_ui()
        self._apply_base_styles()
        self.hide()

    def _setup_ui(self):
        """Initialize the layout and child widgets."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 10, 15, 10)
        self.main_layout.setSpacing(8)

        # Status Label (e.g., "Processing file 1 of 5...")
        self.status_label = QLabel("Starting...")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Details Label (e.g., Filename or specific step)
        self.details_label = QLabel("")
        self.details_label.setObjectName("detailsLabel")
        self.details_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.details_label.setWordWrap(True)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)

        self.main_layout.addWidget(self.status_label)
        self.main_layout.addWidget(self.details_label)
        self.main_layout.addWidget(self.progress_bar)

    def _apply_base_styles(self):
        """Applies default theming. Can be overridden or extended."""
        # Get a background color, default to a semi-transparent dark
        sidebar_bg_hex = self.theme.get_color('background', 'sidebar')
        try:
            if sidebar_bg_hex.startswith('#') and len(sidebar_bg_hex) == 7:
                r, g, b = tuple(int(sidebar_bg_hex[i:i+2], 16) for i in (1, 3, 5))
            else:
                r, g, b = 30, 30, 30
        except Exception:
            r, g, b = 30, 30, 30

        # Base stylesheet
        self.setStyleSheet(f"""
            #{self.objectName()} {{
                background-color: rgba({r}, {g}, {b}, 0.9);
                border-radius: 8px;
                color: {self.theme.get_color('text', 'primary')};
                border: 1px solid {self.theme.get_color('border', 'primary')};
            }}
            #statusLabel {{
                font-size: 10pt;
                font-weight: bold;
                color: {self.theme.get_color('text', 'primary')};
            }}
            #detailsLabel {{
                font-size: 9pt;
                color: {self.theme.get_color('text', 'secondary')};
            }}
            #progressBar {{
                font-size: 8pt;
                min-height: 12px;
                max-height: 12px;
                color: {self.theme.get_color('text', 'primary')};
                background-color: {self.theme.get_color('background', 'tertiary')};
                border: 1px solid {self.theme.get_color('border', 'primary')};
                border-radius: 6px;
            }}
            #progressBar::chunk {{
                background-color: {self.theme.get_color('colors', 'primary')};
                border-radius: 6px;
            }}
        """)
        self._default_progress_bar_chunk_style = f"background-color: {self.theme.get_color('colors', 'primary')}; border-radius: 6px;"

    def _reset_progress_bar_style(self):
        """Restores the progress bar to its normal (non-error) state."""
        # Only need to update the chunk style specifically if we changed it (e.g. for error)
        # Re-applying the full stylesheet or just the chunk part.
        # Ideally we just inject the chunk style back into the current stylesheet or reset.
        # For simplicity, let's update the specific widget style if possible, or re-apply base.
        # Here we set the stylesheet on the progress bar directly to override any previous error state.
        self.progress_bar.setStyleSheet(f"""
            QProgressBar::chunk {{
                {self._default_progress_bar_chunk_style}
            }}
            QProgressBar {{
                font-size: 8pt;
                min-height: 12px;
                max-height: 12px;
                color: {self.theme.get_color('text', 'primary')};
                background-color: {self.theme.get_color('background', 'tertiary')};
                border: 1px solid {self.theme.get_color('border', 'primary')};
                border-radius: 6px;
            }}
        """)
        self.progress_bar.show()

    def show_progress(self, status_text: str, details_text: str = "", percentage: int = 0, task_id: str = None):
        """
        Generic method to update and show the overlay.
        
        Args:
            status_text: Main status line (bold)
            details_text: Secondary info line
            percentage: 0-100
            task_id: Optional ID to track current task and avoid stale updates
        """
        self._current_task_id = task_id
        self._reset_progress_bar_style()
        
        self.status_label.setText(status_text)
        self.details_label.setText(details_text)
        self.progress_bar.setValue(percentage)
        self.progress_bar.setFormat(f"{percentage}%")
        
        if not self.isVisible():
            self.show()
        self.adjustSize()

    def update_progress_value(self, percentage: int, task_id: str = None):
        """Updates just the progress bar value, validating task_id if provided."""
        if task_id is not None and self._current_task_id != task_id:
            return # Ignore updates for other tasks
            
        self.progress_bar.setValue(percentage)
        self.progress_bar.setFormat(f"{percentage}%")

    def show_complete(self, message: str = "Finished!", auto_hide_delay: int = 2000):
        """Shows 100% completion state and auto-hides."""
        self._current_task_id = None
        self._reset_progress_bar_style()
        self.status_label.setText(message)
        self.details_label.setText("")
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("Complete")
        self.adjustSize()
        
        if auto_hide_delay > 0:
            QTimer.singleShot(auto_hide_delay, self.hide)

    def show_error(self, status_text: str, error_details: str, auto_hide_delay: int = 0):
        """Shows error state with red progress bar."""
        self.status_label.setText(status_text)
        self.details_label.setText(error_details)
        
        # Error styling
        error_color = self.theme.get_color('status', 'error')
        text_on_error = self.theme.get_color('text', 'on_error')
        
        self.progress_bar.setStyleSheet(f"""
            QProgressBar::chunk {{
                background-color: {error_color};
                border-radius: 6px;
            }}
            QProgressBar {{
                font-size: 8pt;
                min-height: 12px;
                max-height: 12px;
                color: {text_on_error};
                background-color: {self.theme.get_color('background', 'tertiary')};
                border: 1px solid {self.theme.get_color('border', 'primary')};
                border-radius: 6px;
            }}
        """)
        self.progress_bar.setFormat("Error")
        self.adjustSize()

        if auto_hide_delay > 0:
            QTimer.singleShot(auto_hide_delay, self.hide)

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, painter, self)
        super().paintEvent(event)

