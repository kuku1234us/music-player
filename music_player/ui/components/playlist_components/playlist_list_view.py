from PyQt6.QtWidgets import QListWidget
from PyQt6.QtCore import Qt

class PlaylistListView(QListWidget):
    """
    Widget to display a list of playlists.
    (Currently a placeholder layout)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playlistListView")

        # Basic styling (can be enhanced later)
        self.setStyleSheet("""
            QListWidget {
                border: 1px solid #444;
                border-radius: 4px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #555;
                color: white;
            }
        """)
        self.setMinimumHeight(200) # Ensure it has some initial size 