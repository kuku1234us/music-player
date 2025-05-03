"""
Video widget for displaying video output using VLC.
"""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt

class VideoWidget(QWidget):
    """
    A simple QWidget subclass intended to be used as a video output surface for VLC.
    Sets a black background by default.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # Enable background styling
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Set background color to black using palette
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor('black'))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # Optional: Set size policies or minimum size if needed later
        # Example: Make it expand horizontally and vertically
        # from PyQt6.QtWidgets import QSizePolicy
        # self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # self.setMinimumSize(320, 180) # Set a minimum size
