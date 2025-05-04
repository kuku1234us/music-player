"""
Video widget for displaying video output using VLC.
"""
# --- Use PyQt6 --- 
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt
# ------------------

class VideoWidget(QWidget):
    """
    A simple QWidget subclass intended to be used as a video output surface for VLC.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # Enable background styling - Still potentially useful for styling borders etc.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Removed background color settings to let VLC draw

        # Set size policy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
