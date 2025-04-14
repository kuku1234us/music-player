# ./music_player/ui/components/playlist_components/selection_pool.py
import os
from pathlib import Path
from typing import List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QListWidget, QListWidgetItem, QFileDialog, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal
import qtawesome as qta

from qt_base_app.theme.theme_manager import ThemeManager

# Define common audio file extensions
AUDIO_EXTENSIONS = {
    '.mp3', '.flac', '.wav', '.ogg', '.aac', '.m4a', '.wma', 
    '.opus', '.aiff', '.ape', '.mpc'
}

class SelectionPoolWidget(QWidget):
    """
    Widget representing the Selection Pool area in Play Mode.
    Allows staging tracks via DND, Browse, or deletion from playlist.
    """
    # Signal to request adding selected tracks to the main playlist
    add_selected_requested = pyqtSignal(list) # Emits list of track paths
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("selectionPoolWidget")
        self.theme = ThemeManager.instance()
        
        # Keep track of added paths to avoid duplicates in the list view
        self._pool_paths = set()
        
        self._setup_ui()
        self._connect_signals()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0) # Add some top margin
        layout.setSpacing(8)
        
        # --- Header --- 
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        
        title_label = QLabel("Selection Pool")
        title_label.setStyleSheet(f"""
            color: {self.theme.get_color('text', 'secondary')};
            font-weight: bold;
            font-size: 10pt;
        """)
        
        self.browse_button = QPushButton()
        self.browse_button.setIcon(qta.icon('fa5s.folder-open'))
        self.browse_button.setToolTip("Browse folder to add tracks")
        self.browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_button.setFlat(True)
        self.browse_button.setIconSize(self.browse_button.sizeHint() / 1.5)
        self.browse_button.setStyleSheet(f"""
            QPushButton {{ border: none; padding: 2px; color: {self.theme.get_color('text', 'secondary')}; }}
            QPushButton:hover {{ background-color: {self.theme.get_color('background', 'secondary')}40; border-radius: 3px; }}
        """)
        
        # Add Button (Placeholder - connect later)
        self.add_selected_button = QPushButton("Add Selected")
        self.add_selected_button.setToolTip("Add selected tracks to current playlist")
        self.add_selected_button.setStyleSheet(f"""
            padding: 4px 8px; 
            font-size: 8pt;
            border-radius: 3px;
            background-color: {self.theme.get_color('background', 'tertiary')};
            color: {self.theme.get_color('text', 'secondary')};
        """)
        self.add_selected_button.setCursor(Qt.CursorShape.PointingHandCursor)

        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.browse_button)
        header_layout.addWidget(self.add_selected_button)
        
        # --- Pool List --- 
        self.pool_list = QListWidget()
        self.pool_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection) # Allow multi-select
        self.pool_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {self.theme.get_color('background', 'secondary')}20; /* Slightly different bg */
                border: 1px solid {self.theme.get_color('border', 'secondary')};
                border-radius: 4px;
                padding: 5px;
            }}
            QListWidget::item {{
                padding: 5px;
                border-radius: 3px;
            }}
            QListWidget::item:selected {{
                background-color: {self.theme.get_color('accent', 'primary')}80;
                color: {self.theme.get_color('text', 'primary')};
                border: none;
            }}
        """)
        self.pool_list.setMinimumHeight(100) # Give it some initial size
        
        # Add components to main layout
        layout.addLayout(header_layout)
        layout.addWidget(self.pool_list)
        
    def _connect_signals(self):
        self.browse_button.clicked.connect(self._browse_folder)
        self.add_selected_button.clicked.connect(self._emit_add_selected)

    def add_tracks(self, track_paths: List[str]):
        """
        Adds a list of track file paths to the selection pool, avoiding duplicates.
        
        Args:
            track_paths (List[str]): A list of absolute paths to track files.
        """
        added_count = 0
        for path_str in track_paths:
            # Normalize path for consistent checking
            norm_path = os.path.normpath(path_str)
            if norm_path not in self._pool_paths:
                self._pool_paths.add(norm_path)
                
                # Display only the filename
                filename = Path(norm_path).name
                item = QListWidgetItem(filename)
                item.setData(Qt.ItemDataRole.UserRole, norm_path) # Store full path
                item.setToolTip(norm_path) # Show full path on hover
                self.pool_list.addItem(item)
                added_count += 1
        # print(f"Added {added_count} tracks to selection pool.")
        
    def get_selected_tracks(self) -> List[str]:
        """
        Returns a list of full file paths for the currently selected items in the pool.
        """
        selected_paths = []
        for item in self.pool_list.selectedItems():
            full_path = item.data(Qt.ItemDataRole.UserRole)
            if full_path:
                selected_paths.append(full_path)
        return selected_paths
        
    def remove_tracks(self, track_paths: List[str]):
        """
        Removes tracks from the pool based on a list of full file paths.
        """
        items_to_remove = []
        paths_to_remove_set = {os.path.normpath(p) for p in track_paths}
        
        for i in range(self.pool_list.count()):
            item = self.pool_list.item(i)
            item_path = os.path.normpath(item.data(Qt.ItemDataRole.UserRole))
            if item_path in paths_to_remove_set:
                items_to_remove.append(item)
                # Remove from internal tracking set as well
                if item_path in self._pool_paths:
                    self._pool_paths.remove(item_path)
                    
        # Remove items from the list widget (iterate backwards if removing by row index)
        for item in items_to_remove:
            # QListWidget.takeItem requires the row index
            row = self.pool_list.row(item)
            self.pool_list.takeItem(row)
            
    def clear_pool(self):
        """
        Removes all items from the selection pool list and internal set.
        """
        self.pool_list.clear()
        self._pool_paths.clear()
        
    def _browse_folder(self):
        """
        Opens a directory dialog and scans the selected folder for media files.
        """
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Folder to Scan",
            ".", # Start in current directory or remember last?
            QFileDialog.Option.ShowDirsOnly
        )
        
        if directory:
            found_files = []
            try:
                for root, _, files in os.walk(directory):
                    for filename in files:
                        if Path(filename).suffix.lower() in AUDIO_EXTENSIONS:
                            full_path = os.path.join(root, filename)
                            found_files.append(full_path)
            except Exception as e:
                print(f"Error scanning directory '{directory}': {e}")
                # Optionally show a message box to the user
                return
                
            if found_files:
                self.add_tracks(found_files)
            else:
                print(f"No audio files found in '{directory}'")
                # Optionally show a message box
                
    def _emit_add_selected(self):
        """
        Emits the signal to add the selected tracks to the main playlist.
        Optionally removes them from the pool after emitting.
        """
        selected_paths = self.get_selected_tracks()
        if selected_paths:
            self.add_selected_requested.emit(selected_paths)
            # Decide if items should be removed from pool after adding
            # self.remove_tracks(selected_paths) # Uncomment to remove after adding

