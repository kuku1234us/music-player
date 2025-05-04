"""
Dashboard page for the Music Player application.
"""
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGridLayout, QSizePolicy, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QColor

# Try to import qtawesome for icons
try:
    import qtawesome as qta
    HAS_QTAWESOME = True
except ImportError:
    HAS_QTAWESOME = False

# Import BaseCard from the framework
from qt_base_app.components.base_card import BaseCard
from qt_base_app.theme.theme_manager import ThemeManager

# Import Recently Played Model
from music_player.models.recently_played import RecentlyPlayedModel
from music_player.models.playlist import Playlist, PlaylistManager

# Remove import for unused ActivityItem
# from music_player.ui.components import ActivityItem


class DashboardPage(QWidget):
    """
    Main dashboard page showing welcome message and recently played items.
    """
    # Define signals to request playback
    play_single_file_requested = pyqtSignal(str) # Emits filepath
    play_playlist_requested = pyqtSignal(Playlist) # Emits Playlist object
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Set widget properties
        self.setObjectName("dashboardPage")
        self.setProperty('page_id', 'dashboard')
        
        # Get theme manager and recently played model
        self.theme = ThemeManager.instance()
        self.recently_played_model = RecentlyPlayedModel.instance()
        
        self.setup_ui()
        self.load_recently_played()
    
    def setup_ui(self):
        """Set up the UI for the dashboard page."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 24, 24, 24)
        self.main_layout.setSpacing(16) # Reduced spacing slightly
        
        # Welcome message - REMOVED
        # self.welcome_label = QLabel("Welcome Back") # Simpler welcome
        # self.welcome_label.setObjectName("welcomeLabel")
        # self.welcome_label.setStyleSheet(f"""
        #     color: {self.theme.get_color('text', 'primary')};
        #     font-size: 20px; /* Slightly smaller */
        #     font-weight: bold;
        #     margin-bottom: 16px;
        # """)
        # self.main_layout.addWidget(self.welcome_label)
        
        # --- Recently Played Section --- 
        # Remove BaseCard wrapper
        # self.recently_played_card = BaseCard("Recently Played")
        
        self.recently_played_list = QListWidget()
        self.recently_played_list.setObjectName("recentlyPlayedList")
        self.recently_played_list.setAlternatingRowColors(True)
        # Apply styles similar to the Selection Pool table widget
        self.recently_played_list.setStyleSheet(f"""
            QListWidget#recentlyPlayedList {{
                background-color: {self.theme.get_color('background', 'secondary')}20; /* Match pool table background */
                alternate-background-color: {self.theme.get_color('background', 'alternate_row')};
                border: 1px solid {self.theme.get_color('border', 'secondary')}; /* Match pool table border */
                border-radius: 4px; /* Match pool table radius */
                padding: 5px; /* Add overall padding like pool table */
                selection-background-color: {self.theme.get_color('background', 'selected_row')}; /* Match selection bg */
                selection-color: {self.theme.get_color('text', 'primary')}; /* Match selection text */
            }}
            QListWidget#recentlyPlayedList::item {{
                padding: 0px 5px; /* Adjust padding to match table item */
                height: 22px; /* Match table item height */
                min-height: 22px;
                border: none; /* Remove bottom border */
                color: {self.theme.get_color('text', 'primary')}; /* Use primary text color for items */
            }}
            QListWidget#recentlyPlayedList::item:selected {{
                background-color: {self.theme.get_color('background', 'selected_row')}; /* Explicitly define selection bg */
                color: {self.theme.get_color('text', 'primary')}; /* Explicitly define selection text */
                border-radius: 0px; /* Remove border radius from selected item */
                border: none; /* Ensure no border on selected item */
            }}
        """)
        self.recently_played_list.itemDoubleClicked.connect(self._on_recent_item_double_clicked)
        
        # Add the list widget directly to the main layout
        self.main_layout.addWidget(self.recently_played_list, 1)
        
        # Add a stretch to push everything up if needed (or remove if card should fill space)
        # self.main_layout.addStretch()
    
    def load_recently_played(self):
        """Load items from the model and populate the list widget."""
        self.recently_played_list.clear()
        items = self.recently_played_model.get_items()
        
        if not items:
            # Optional: Show a message if the list is empty
            item = QListWidgetItem("No recently played items yet.")
            # Convert color string to QColor
            item.setForeground(QColor(self.theme.get_color('text', 'disabled')))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable) # Make it non-selectable
            self.recently_played_list.addItem(item)
            return
            
        for item_data in items:
            item_type = item_data.get('type')
            name = item_data.get('name', 'Unknown')
            path = item_data.get('path')
            
            list_item = QListWidgetItem(name)
            list_item.setData(Qt.ItemDataRole.UserRole, item_data) # Store the full data dict
            
            # Set icon based on type
            icon_name = 'fa5s.music' # Default icon
            if item_type == 'file':
                icon_name = 'fa5s.file-audio'
            elif item_type == 'playlist':
                icon_name = 'fa5s.list'
            
            if HAS_QTAWESOME:
                # Change icon color to match primary text color
                icon = qta.icon(icon_name, color=self.theme.get_color('text', 'primary'))
                # Create a smaller pixmap and set it
                small_icon_size = QSize(18, 18) # Target size (adjust as needed)
                small_pixmap = icon.pixmap(small_icon_size)
                list_item.setIcon(QIcon(small_pixmap))
                
            self.recently_played_list.addItem(list_item)
            
    def _on_recent_item_double_clicked(self, item: QListWidgetItem):
        """Handle double-click on a recently played item."""
        item_data = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(item_data, dict):
            print("[DashboardPage] Error: No data associated with clicked item.")
            return
            
        item_type = item_data.get('type')
        path = item_data.get('path')
        name = item_data.get('name')
        
        if not path or not item_type:
            print("[DashboardPage] Error: Invalid item data.")
            return
            
        print(f"[DashboardPage] Double-clicked recent item: Type={item_type}, Path={path}")
        
        if item_type == 'file':
            if os.path.exists(path):
                self.play_single_file_requested.emit(path)
            else:
                print(f"[DashboardPage] Error: File path does not exist: {path}")
                # Optionally remove from recent list here? or show message
        elif item_type == 'playlist':
            playlist_path = Path(path)
            if playlist_path.exists():
                # Need to load the Playlist object first
                # Remove unnecessary PlaylistManager instance
                # playlist_manager = PlaylistManager()
                # Call the static method on the Playlist class directly
                playlist = Playlist.load_from_file(playlist_path)
                if playlist:
                    # Remove the global state update - MainPlayer should handle this
                    # player_state.set_current_playlist(playlist)
                    self.play_playlist_requested.emit(playlist)
                else:
                    print(f"[DashboardPage] Error: Failed to load playlist: {path}")
            else:
                print(f"[DashboardPage] Error: Playlist path does not exist: {path}")
                # Optionally remove from recent list here? or show message

    def showEvent(self, event):
        """
        Reload the recently played list when the page becomes visible.
        """
        super().showEvent(event)
        self.load_recently_played()

