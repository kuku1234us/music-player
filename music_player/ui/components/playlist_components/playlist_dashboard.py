# ui/components/playlist_components/playlist_dashboard.py

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QListWidgetItem)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QIcon
import qtawesome as qta

from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.components.base_card import BaseCard
from music_player.ui.components.round_button import RoundButton
from .playlist_list_view import PlaylistListView

class PlaylistDashboardWidget(QWidget):
    """
    Widget representing the Dashboard mode of the Playlists page.
    Displays the list of playlists and action buttons.
    """
    # Signals to be emitted to the parent PlaylistsPage
    create_new_playlist_requested = pyqtSignal()
    import_playlist_requested = pyqtSignal()
    refresh_playlists_requested = pyqtSignal()
    playlist_selected = pyqtSignal(QListWidgetItem) # Specifically use QListWidgetItem
    edit_playlist_requested = pyqtSignal(QListWidgetItem) # Specifically use QListWidgetItem
    rename_playlist_requested = pyqtSignal(QListWidgetItem) # Specifically use QListWidgetItem
    delete_playlist_requested = pyqtSignal(QListWidgetItem) # Specifically use QListWidgetItem

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playlistDashboardWidget")
        self.theme = ThemeManager.instance()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16) # Add margins to the layout
        layout.setSpacing(24)

        # --- Playlists List --- 
        playlists_card = BaseCard(
            "My Playlists",
            border_style=f"1px solid {self.theme.get_color('accent', 'secondary')}",
            background_style=f"{self.theme.get_color('background', 'tertiary')}20" # 20% opacity
        )
        playlists_container = QWidget()
        playlists_container_layout = QVBoxLayout(playlists_container)
        playlists_container_layout.setContentsMargins(0, 0, 0, 0)
        playlists_container_layout.setSpacing(16)

        self.playlists_list_view = PlaylistListView() # Use the component
        # Connect signals from the list view to re-emit them
        self.playlists_list_view.itemDoubleClicked.connect(self.playlist_selected)
        # Need to add context menu handling here or connect to parent

        playlists_container_layout.addWidget(self.playlists_list_view)

        # Update the empty label with muted gray color
        self.empty_label = QLabel("No playlists found. Create or import one.")
        self.empty_label.setStyleSheet(f"color: #71717a; font-style: italic;") # Muted gray color
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.hide() # Initially hidden
        playlists_container_layout.addWidget(self.empty_label)

        playlists_card.add_widget(playlists_container)
        layout.addWidget(playlists_card)
        layout.addStretch(1) # Push content to top

        # --- Add Floating Button using RoundButton ---
        self.add_button = RoundButton(
            parent=self,
            text="+",
            size=48,  # Same size as player page's open file button
            bg_opacity=0.5
        )
        self.add_button.clicked.connect(self.create_new_playlist_requested)
        
        # Position the button at bottom center
        self.add_button.setParent(self)
        self.add_button.move(
            int((self.width() - self.add_button.size) / 2),
            self.height() - self.add_button.size - 24  # 24px from bottom
        )
        
    def resizeEvent(self, event):
        """Reposition the floating button when the widget is resized"""
        super().resizeEvent(event)
        # Update button position
        self.add_button.move(
            int((self.width() - self.add_button.size) / 2),
            self.height() - self.add_button.size - 24  # 24px from bottom
        )

    # --- Public Methods --- 
    def get_playlist_list_widget(self):
        """Return the internal QListWidget for manipulation by the parent."""
        return self.playlists_list_view

    def set_empty_message(self, message: str):
        """Set the text of the empty label."""
        self.empty_label.setText(message)

    def show_empty_message(self, show: bool):
        """Show or hide the empty message label."""
        self.empty_label.setVisible(show)
        self.playlists_list_view.setVisible(not show)

    # --- Context Menu (to be implemented) ---
    # TODO: Add context menu handling for playlist items