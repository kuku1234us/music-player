# ./music_player/ui/components/player_components/player_overlay.py
import sys
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QMouseEvent

from qt_base_app.theme.theme_manager import ThemeManager
from music_player.ui.components.round_button import RoundButton

class PlayerOverlay(QWidget):
    """
    An overlay panel containing multiple RoundButton controls.
    Designed to be a child widget within another widget (e.g., PlayerPage),
    with a transparent background (only buttons are visible).
    """
    openFileClicked = pyqtSignal()
    oplayerClicked = pyqtSignal()

    def __init__(
        self,
        parent: QWidget = None,
        button_diameter=48,
        button_spacing=10,
        button_icon_size=24
    ):
        super().__init__(parent=parent)

        self.button_diameter = button_diameter
        self.button_spacing = button_spacing
        self.button_icon_size = button_icon_size
        self.theme = ThemeManager.instance()

        self._video_mode_active = False # State to track if video is playing

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

        self._setup_ui()

        # Initially visible by default (non-video mode)
        self.setVisible(True)

    def _setup_ui(self):
        """Set up the internal RoundButton widgets."""
        button_bg_opacity = 0.5

        self.file_button = RoundButton(
            parent=self,
            icon_name="fa5s.folder-open",
            text="📂",
            diameter=self.button_diameter,
            icon_size=self.button_icon_size,
            bg_opacity=button_bg_opacity
        )
        self.file_button.setToolTip("Open File")
        self.file_button.clicked.connect(self.openFileClicked.emit)

        self.oplayer_button = RoundButton(
            parent=self,
            text="OP",
            diameter=self.button_diameter,
            icon_size=self.button_icon_size,
            bg_opacity=button_bg_opacity
        )
        self.oplayer_button.setToolTip("Upload to OPlayer")
        self.oplayer_button.clicked.connect(self.oplayerClicked.emit)

        self.buttons = [self.file_button, self.oplayer_button]

        margin = 5
        current_x = margin
        for i, button in enumerate(self.buttons):
            button.move(current_x, margin)
            current_x += self.button_diameter + self.button_spacing

        overlay_width = margin + 2 * self.button_diameter + 1 * self.button_spacing + margin
        overlay_height = margin + self.button_diameter + margin
        self.setFixedSize(overlay_width, overlay_height)

    def set_video_mode(self, active: bool):
        """Called by PlayerPage to set the overlay behavior based on media type."""
        self._video_mode_active = active
        # Set initial visibility based on mode
        self.setVisible(not self._video_mode_active)

    def show_overlay(self):
        """Explicitly makes the overlay visible."""
        self.setVisible(True)

    def hide_overlay(self):
        """Explicitly makes the overlay hidden."""
        self.setVisible(False)

    def paintEvent(self, event):
        """Override paintEvent to do nothing (transparent background)."""
        pass # Explicitly do nothing
