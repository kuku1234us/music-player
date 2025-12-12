# ./music_player/ui/components/float_button.py
import sys
from PyQt6.QtWidgets import QWidget, QApplication # Added QApplication for potential testing
from PyQt6.QtCore import Qt, QSize, QPoint, QEvent, QRectF, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QIcon

from qt_base_app.theme.theme_manager import ThemeManager

# Import QtAwesome for icons if available
try:
    import qtawesome as qta
    HAS_QTAWESOME = True
except ImportError:
    HAS_QTAWESOME = False

class FloatButton(QWidget):
    """
    A floating circular button widget that stays on top and follows a parent window.
    Displays either an icon or short text with a semi-transparent background.
    """
    clicked = pyqtSignal() # Add the clicked signal

    def __init__(
        self,
        logical_parent: QWidget, # The window this button should follow
        relative_pos: QPoint,   # Position relative to the parent's top-left
        icon_name=None,         # QtAwesome icon name (e.g., "fa5s.folder-open")
        text=None,              # Alternative text if no icon or icon not available
        diameter=48,            # Button diameter in pixels
        icon_size=24,           # Icon size in pixels
        bg_opacity=0.5          # Background opacity (0.0 to 1.0)
    ):
        # Initialize as a top-level window, not a child
        super().__init__(parent=None)

        self.logical_parent = logical_parent
        self.relative_pos = relative_pos
        self.icon_name = icon_name
        self._text = text # Store text internally
        self.diameter = diameter
        self.icon_size = icon_size
        self.bg_opacity = bg_opacity

        self.theme = ThemeManager.instance()
        self.current_icon = QIcon() # Store the current icon

        # --- Window Setup ---
        self.setFixedSize(diameter, diameter)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | # No border or title bar
            Qt.WindowType.Tool |                # Behaves like a tool window (often doesn't appear in taskbar)
            Qt.WindowType.WindowStaysOnTopHint  # Keep it above other windows
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True) # May not be needed with manual paint
        self.setAutoFillBackground(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # --------------------

        self._setup_visuals()

        # Install event filter on the logical parent to track its movement/resizing
        if self.logical_parent:
            self.logical_parent.installEventFilter(self)
            # self._update_position() # Remove initial position setting again

    def _hex_to_rgb(self, hex_color):
        """Convert hex color to RGB tuple."""
        try:
            if hex_color.startswith('#') and len(hex_color) == 7:
                hex_color = hex_color.lstrip('#')
                return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        except (ValueError, AttributeError):
            pass
        # Fallback theme color or a default
        return self._hex_to_rgb(self.theme.get_color('background', 'tertiary', '#333333'))

    def _get_background_color(self):
        """Gets the background color with appropriate opacity."""
        tertiary_bg_hex = self.theme.get_color('background', 'tertiary')
        rgb = self._hex_to_rgb(tertiary_bg_hex)
        return QColor(rgb[0], rgb[1], rgb[2], int(self.bg_opacity * 255))

    def _setup_visuals(self):
        """Load icon or set text."""
        if self.icon_name and HAS_QTAWESOME:
            self.set_icon(self.icon_name)
        elif self._text:
            self.set_text(self._text)
        else:
            # Default: clear text and icon if none provided initially
            self._text = ""
            self.current_icon = QIcon()

    def set_icon(self, icon_name):
        """Set or update the button's icon."""
        self.icon_name = icon_name
        self._text = "" # Clear text when setting icon
        if HAS_QTAWESOME:
            self.current_icon = qta.icon(icon_name, color=self.theme.get_color('text', 'primary'))
        else:
            self.current_icon = QIcon() # Clear icon if qtawesome not available
        self.update() # Trigger repaint

    def set_text(self, text):
        """Set or update the button's text."""
        self._text = text
        self.icon_name = None # Clear icon name when setting text
        self.current_icon = QIcon() # Clear icon
        self.update() # Trigger repaint

    def paintEvent(self, event):
        """Custom painting for the circular button."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw background circle
        bg_color = self._get_background_color()
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.drawEllipse(QRectF(self.rect()))

        # Draw icon or text
        if not self.current_icon.isNull():
            icon_rect = QRectF(0, 0, self.icon_size, self.icon_size)
            icon_rect.moveCenter(self.rect().center())
            self.current_icon.paint(painter, icon_rect.toRect())
        elif self._text:
            painter.setPen(QPen(QColor(self.theme.get_color('text', 'primary'))))
            # Simple font sizing approximation
            font = painter.font()
            font_size = int(self.diameter * 0.35 / len(self._text)**0.5) if len(self._text) > 0 else int(self.diameter * 0.4)
            font.setPointSize(max(font_size, 6)) # Ensure minimum size
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)

    def eventFilter(self, watched, event):
        """Filters events from the logical parent window."""
        if watched == self.logical_parent:
            if event.type() == QEvent.Type.Move or event.type() == QEvent.Type.Resize or event.type() == QEvent.Type.WindowStateChange:
                # Update position when parent moves, resizes, or changes state (like maximizing)
                self._update_position()
            elif event.type() == QEvent.Type.Close:
                 # Hide or close the float button when the parent closes
                 self.close()
                 return True # Indicate event handled
            elif event.type() == QEvent.Type.Hide:
                 # Optionally hide the float button when the parent hides
                 self.hide()
                 return True
            elif event.type() == QEvent.Type.Show:
                 # Use QTimer to delay position update slightly after parent is shown
                 QTimer.singleShot(0, self._update_position)
                 return True

        return super().eventFilter(watched, event)

    def _update_position(self):
        """Calculates and sets the button's position based on the parent."""
        if self.logical_parent and self.logical_parent.isVisible():
            parent_global_pos = self.logical_parent.mapToGlobal(QPoint(0, 0))
            target_pos = parent_global_pos + self.relative_pos
            self.move(target_pos)
            if not self.isVisible(): # Ensure visibility if parent becomes visible
                self.show()
        else:
            # Hide if the parent is not visible
            self.hide()

    def mousePressEvent(self, event):
        """Handle mouse press to emit clicked signal (like QPushButton)."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def showEvent(self, event):
        """Ensure position is updated when shown."""
        self._update_position()
        super().showEvent(event)

    def closeEvent(self, event):
        """Clean up event filter when the button itself is closed."""
        if self.logical_parent:
            try:
                self.logical_parent.removeEventFilter(self)
            except RuntimeError: # Parent might already be destroyed
                pass
        super().closeEvent(event)

# Example Usage (Optional: run this file directly for testing)
if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Create a dummy parent window
    parent_window = QWidget()
    parent_window.setWindowTitle("Parent Window")
    parent_window.setGeometry(200, 200, 400, 300)
    parent_window.setStyleSheet("background-color: #555;")
    parent_window.show()

    # Create float buttons relative to the parent
    button1 = FloatButton(parent_window, QPoint(20, 20), icon_name="fa5s.folder-open")
    button2 = FloatButton(parent_window, QPoint(80, 20), text="OP", diameter=40)

    # Show the float buttons (initial position set in constructor/showEvent)
    button1.show()
    button2.show()

    sys.exit(app.exec())
