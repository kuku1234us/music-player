# ./music_player/ui/components/playlist_components/selection_pool.py
import os
import datetime
from pathlib import Path
from typing import List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFileDialog, QAbstractItemView, QMenu, QApplication,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QCursor, QIcon
import qtawesome as qta

from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.models.settings_manager import SettingsManager, SettingType
# Import the new SearchField component
from music_player.ui.components.search_field import SearchField

# Define common audio file extensions
AUDIO_EXTENSIONS = {
    '.mp3', '.flac', '.wav', '.ogg', '.aac', '.m4a', '.wma', 
    '.opus', '.aiff', '.ape', '.mpc'
}

def format_file_size(size_bytes):
    """Format file size from bytes to human-readable format"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes/(1024*1024):.1f} MB"
    else:
        return f"{size_bytes/(1024*1024*1024):.1f} GB"

def format_modified_time(mod_time):
    """Format modified time to human-readable format"""
    dt = datetime.datetime.fromtimestamp(mod_time)
    return dt.strftime("%Y-%m-%d %H:%M")

class SizeAwareTableItem(QTableWidgetItem):
    """Custom QTableWidgetItem that correctly sorts file sizes"""
    def __init__(self, text, size_bytes):
        super().__init__(text)
        self.size_bytes = size_bytes
        
    def __lt__(self, other):
        if isinstance(other, SizeAwareTableItem):
            return self.size_bytes < other.size_bytes
        return super().__lt__(other)

class DateAwareTableItem(QTableWidgetItem):
    """Custom QTableWidgetItem that correctly sorts dates"""
    def __init__(self, text, timestamp):
        super().__init__(text)
        self.timestamp = timestamp
        
    def __lt__(self, other):
        if isinstance(other, DateAwareTableItem):
            return self.timestamp < other.timestamp
        return super().__lt__(other)

class SelectionPoolWidget(QWidget):
    """
    Widget representing the Selection Pool area in Play Mode.
    Allows staging tracks via DND, Browse, or deletion from playlist.
    """
    # Signal to request adding selected tracks to the main playlist
    add_selected_requested = pyqtSignal(list) # Emits list of track paths
    # Signal to request playing a single file
    play_single_file_requested = pyqtSignal(str) # Emits filepath
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("selectionPoolWidget")
        self.theme = ThemeManager.instance()
        self.settings = SettingsManager.instance()
        
        # Keep track of added paths to avoid duplicates in the table
        self._pool_paths = set()
        
        # Column indices
        self.COL_FILENAME = 0
        self.COL_SIZE = 1
        self.COL_MODIFIED = 2
        
        # Sorting state
        self.sort_column = self.COL_FILENAME
        self.sort_order = Qt.SortOrder.AscendingOrder
        
        # Sort indicator icons
        self.sort_up_icon = qta.icon('fa5s.sort-up', color=self.theme.get_color('text', 'secondary'))
        self.sort_down_icon = qta.icon('fa5s.sort-down', color=self.theme.get_color('text', 'secondary'))
        
        self._setup_ui()
        self._connect_signals()
        
        # Load column widths from settings
        self._load_column_widths()
        
        # Set initial sort indicator
        self._update_sort_indicators()
        
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
        
        # Add the SearchField component
        self.search_field = SearchField(placeholder="Filter pool...")
        # Set a maximum width or flexible sizing as needed
        # self.search_field.setMaximumWidth(250) 
        
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
        
        # Add Button - Changed to Icon Button
        self.add_selected_button = QPushButton() # Removed text
        self.add_selected_button.setIcon(qta.icon('fa5s.plus', color=self.theme.get_color('text', 'secondary'))) # Added icon
        self.add_selected_button.setToolTip("Add selected tracks to current playlist")
        self.add_selected_button.setFlat(True) # Make flat like browse button
        self.add_selected_button.setIconSize(self.browse_button.sizeHint() / 1.5) # Use similar icon size
        self.add_selected_button.setStyleSheet(f""" 
            QPushButton {{ border: none; padding: 2px; color: {self.theme.get_color('text', 'secondary')}; }}
            QPushButton:hover {{ background-color: {self.theme.get_color('background', 'secondary')}40; border-radius: 3px; }}
        """) # Applied similar styling
        self.add_selected_button.setCursor(Qt.CursorShape.PointingHandCursor)

        header_layout.addWidget(title_label)
        # Add the search field next to the title - WITH stretch factor
        header_layout.addWidget(self.search_field, 1) # Re-added stretch factor , 1
        # Add stretch AFTER the search field to push buttons right - REMOVED
        # header_layout.addStretch(1) 
        # header_layout.addStretch(1) # Remove or adjust stretch if needed - Already removed
        header_layout.addWidget(self.browse_button)
        header_layout.addWidget(self.add_selected_button)
        
        # --- Pool Table --- 
        self.pool_table = QTableWidget()
        self.pool_table.setColumnCount(3)
        self.pool_table.setHorizontalHeaderLabels(["Filename", "Size", "Modified"])
        self.pool_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.pool_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.pool_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.pool_table.setAlternatingRowColors(True)
        self.pool_table.verticalHeader().setVisible(False)
        self.pool_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.pool_table.horizontalHeader().setStretchLastSection(True)
        self.pool_table.horizontalHeader().setSortIndicatorShown(True)
        self.pool_table.setSortingEnabled(False)  # Disable automatic sorting
        self.pool_table.setShowGrid(False)
        self.pool_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        
        # Set default row height for the vertical header
        self.pool_table.verticalHeader().setDefaultSectionSize(22)
        
        # Set initial column widths
        self.pool_table.setColumnWidth(self.COL_FILENAME, 250)
        self.pool_table.setColumnWidth(self.COL_SIZE, 80)
        
        # Style the table
        self.pool_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {self.theme.get_color('background', 'secondary')}20;
                alternate-background-color: {self.theme.get_color('background', 'alternate_row')};
                border: 1px solid {self.theme.get_color('border', 'secondary')};
                border-radius: 4px;
                padding: 5px;
                selection-background-color: {self.theme.get_color('background', 'selected_row')};
                selection-color: {self.theme.get_color('text', 'primary')};
            }}
            QTableWidget::item {{
                padding: 0px 5px;
                height: 22px;
                min-height: 22px;
            }}
            QTableWidget::item:selected {{
                background-color: {self.theme.get_color('background', 'selected_row')};
                color: {self.theme.get_color('text', 'primary')};
                border-radius: 0px;
                border: none;
            }}
            QHeaderView::section {{
                background-color: {self.theme.get_color('background', 'tertiary')};
                color: {self.theme.get_color('text', 'secondary')};
                padding: 0px 5px;
                height: 22px;
                border: none;
                border-right: 1px solid {self.theme.get_color('border', 'secondary')};
            }}
            QHeaderView::section:hover {{
                background-color: {self.theme.get_color('background', 'quaternary')};
            }}
        """)
        self.pool_table.setMinimumHeight(100) # Give it some initial size
        
        # Add components to main layout
        layout.addLayout(header_layout)
        layout.addWidget(self.pool_table)
        
    def _connect_signals(self):
        self.browse_button.clicked.connect(self._browse_folder)
        self.add_selected_button.clicked.connect(self._emit_add_selected)
        self.pool_table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.pool_table.customContextMenuRequested.connect(self._show_context_menu)
        # Connect the search field signal
        self.search_field.textChanged.connect(self._filter_pool_table)
        # Connect double-click signal
        self.pool_table.doubleClicked.connect(self._on_item_double_clicked)
        
        # Connect column resize signal
        self.pool_table.horizontalHeader().sectionResized.connect(self._on_column_resized)

    def _show_context_menu(self, position):
        """Display context menu for selection pool items"""
        if self.pool_table.rowCount() == 0:
            return
            
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {self.theme.get_color('background', 'primary')};
                color: {self.theme.get_color('text', 'primary')};
                border: 1px solid {self.theme.get_color('border', 'primary')};
                border-radius: 4px;
                padding: 5px;
            }}
            QMenu::item {{
                padding: 5px 15px;
                border-radius: 3px;
            }}
            QMenu::item:selected {{
                background-color: {self.theme.get_color('background', 'secondary')};
            }}
        """)
        
        selected_items = self.pool_table.selectedItems()
        if selected_items:
            # Copy to clipboard action
            copy_action = menu.addAction("Copy Path")
            copy_action.triggered.connect(lambda: self._copy_selected_paths_to_clipboard())
            
            # Remove from selection pool action
            remove_action = menu.addAction("Remove from Selection Pool")
            remove_action.triggered.connect(lambda: self._remove_selected_items())
            
            # Add to playlist action (same as add selected button)
            add_to_playlist_action = menu.addAction("Add to Current Playlist")
            add_to_playlist_action.triggered.connect(self._emit_add_selected)
            
            # Select all action
            menu.addSeparator()
            select_all_action = menu.addAction("Select All")
            select_all_action.triggered.connect(self.pool_table.selectAll)
            
            # Clear selection action
            clear_selection_action = menu.addAction("Clear Selection")
            clear_selection_action.triggered.connect(self.pool_table.clearSelection)
            
            menu.addSeparator()
            # Clear pool action
            clear_pool_action = menu.addAction("Clear Pool")
            clear_pool_action.triggered.connect(self.clear_pool)
        
        menu.exec(QCursor.pos())
        
    def _copy_selected_paths_to_clipboard(self):
        """Copy selected file paths to clipboard"""
        selected_paths = []
        for item in self.pool_table.selectedItems():
            if item.column() == self.COL_FILENAME:
                path = item.data(Qt.ItemDataRole.UserRole)
                if path:
                    selected_paths.append(path)
        
        if selected_paths:
            clipboard = QApplication.clipboard()
            clipboard.setText("\n".join(selected_paths))
            
    def _remove_selected_items(self):
        """Remove selected items from the selection pool"""
        selected_paths = []
        for item in self.pool_table.selectedItems():
            if item.column() == self.COL_FILENAME:
                path = item.data(Qt.ItemDataRole.UserRole)
                if path:
                    selected_paths.append(path)
                    
        if selected_paths:
            self.remove_tracks(selected_paths)

    def _on_header_clicked(self, column_index):
        """Handle column header clicks for sorting"""
        if self.sort_column == column_index:
            # Toggle sort order if clicking the same column again
            new_order = Qt.SortOrder.DescendingOrder if self.sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
            self.sort_order = new_order
        else:
            # Set new sort column with default ascending order
            self.sort_column = column_index
            self.sort_order = Qt.SortOrder.AscendingOrder
        
        # Update sort indicator in headers
        self._update_sort_indicators()
            
        self.pool_table.sortItems(column_index, self.sort_order)
        
        # Ensure row heights are maintained after sorting
        for row in range(self.pool_table.rowCount()):
            self.pool_table.setRowHeight(row, 22)
            
    def _update_sort_indicators(self):
        """Update the sort indicators in headers"""
        header = self.pool_table.horizontalHeader()
        
        # Clear all previous indicators
        for col in range(header.count()):
            header_item = self.pool_table.horizontalHeaderItem(col)
            if header_item:
                header_item.setIcon(QIcon())
        
        # Add indicator to the sorted column
        header_item = self.pool_table.horizontalHeaderItem(self.sort_column)
        if header_item:
            if self.sort_order == Qt.SortOrder.AscendingOrder:
                header_item.setIcon(self.sort_up_icon)
            else:
                header_item.setIcon(self.sort_down_icon)
                
    def _on_column_resized(self, column, oldWidth, newWidth):
        """Save column widths when resized"""
        self._save_column_widths()
        
    def _save_column_widths(self):
        """Save column widths to settings"""
        column_widths = {
            'filename': self.pool_table.columnWidth(self.COL_FILENAME),
            'size': self.pool_table.columnWidth(self.COL_SIZE),
            'modified': self.pool_table.columnWidth(self.COL_MODIFIED)
        }
        self.settings.set('ui/selection_pool/column_widths', column_widths, SettingType.DICT)
        
    def _load_column_widths(self):
        """Load column widths from settings"""
        default_widths = {
            'filename': 250,
            'size': 80,
            'modified': 170
        }
        column_widths = self.settings.get('ui/selection_pool/column_widths', default_widths, SettingType.DICT)
        
        self.pool_table.setColumnWidth(self.COL_FILENAME, column_widths['filename'])
        self.pool_table.setColumnWidth(self.COL_SIZE, column_widths['size'])
        self.pool_table.setColumnWidth(self.COL_MODIFIED, column_widths['modified'])

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
                
                # Get file info
                file_path = Path(norm_path)
                filename = file_path.name
                
                # Get file size and modified time if available
                try:
                    file_stats = file_path.stat()
                    file_size = format_file_size(file_stats.st_size)
                    file_size_bytes = file_stats.st_size
                    modified_time = format_modified_time(file_stats.st_mtime)
                    modified_timestamp = file_stats.st_mtime
                except Exception:
                    file_size = "Unknown"
                    file_size_bytes = 0
                    modified_time = "Unknown"
                    modified_timestamp = 0
                
                # Insert a new row
                row_position = self.pool_table.rowCount()
                self.pool_table.insertRow(row_position)
                # Set fixed row height explicitly
                self.pool_table.setRowHeight(row_position, 22)
                
                # Filename
                filename_item = QTableWidgetItem(filename)
                filename_item.setData(Qt.ItemDataRole.UserRole, norm_path)  # Store full path
                filename_item.setToolTip(norm_path)  # Show full path on hover
                self.pool_table.setItem(row_position, self.COL_FILENAME, filename_item)
                
                # File size with proper sorting
                size_item = SizeAwareTableItem(file_size, file_size_bytes)
                self.pool_table.setItem(row_position, self.COL_SIZE, size_item)
                
                # Modified time with proper sorting
                modified_item = DateAwareTableItem(modified_time, modified_timestamp)
                self.pool_table.setItem(row_position, self.COL_MODIFIED, modified_item)
                
                added_count += 1
                
        # Auto sort after adding new items
        if added_count > 0:
            self.pool_table.sortItems(self.sort_column, self.sort_order)
            
            # Ensure row heights are maintained after sorting
            for row in range(self.pool_table.rowCount()):
                self.pool_table.setRowHeight(row, 22)
                
            # Update the sort indicators
            self._update_sort_indicators()
        
    def get_selected_tracks(self) -> List[str]:
        """
        Returns a list of full file paths for the currently selected items in the pool.
        """
        selected_paths = []
        for item in self.pool_table.selectedItems():
            # Only process items from the filename column
            if item.column() == self.COL_FILENAME:
                full_path = item.data(Qt.ItemDataRole.UserRole)
                if full_path:
                    selected_paths.append(full_path)
        return selected_paths
        
    def remove_tracks(self, track_paths: List[str]):
        """
        Removes tracks from the pool based on a list of full file paths.
        """
        paths_to_remove_set = {os.path.normpath(p) for p in track_paths}
        
        # We need to remove rows from bottom to top to avoid index shifting issues
        rows_to_remove = []
        
        for row in range(self.pool_table.rowCount()):
            item = self.pool_table.item(row, self.COL_FILENAME)
            if item:
                item_path = os.path.normpath(item.data(Qt.ItemDataRole.UserRole))
                if item_path in paths_to_remove_set:
                    rows_to_remove.append(row)
                    # Remove from internal tracking set as well
                    if item_path in self._pool_paths:
                        self._pool_paths.remove(item_path)
        
        # Remove rows in reverse order to avoid index shifting
        for row in sorted(rows_to_remove, reverse=True):
            self.pool_table.removeRow(row)
            
    def clear_pool(self):
        """
        Removes all items from the selection pool table and internal set.
        """
        self.pool_table.setRowCount(0)
        self._pool_paths.clear()
        
    def _browse_folder(self):
        """
        Opens a directory dialog and scans the selected folder for media files.
        The last used directory is remembered for future sessions.
        """
        # Get the last used directory from settings, or default to user's home
        last_dir = self.settings.get('playlists/last_browse_dir', str(Path.home()), SettingType.PATH)
        
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Folder to Scan",
            str(last_dir),  # Convert Path to string for QFileDialog
            QFileDialog.Option.ShowDirsOnly
        )
        
        if directory:
            # Save the selected directory for next time
            self.settings.set('playlists/last_browse_dir', directory, SettingType.PATH)
            self.settings.sync()  # Ensure settings are saved immediately
            
            # --- Get current playlist tracks (if available) --- 
            current_playlist_tracks_set = set()
            # Try to access the parent PlaylistPlaymodeWidget and its playlist
            try:
                # Assuming SelectionPoolWidget is directly inside content_widget,
                # and content_widget is directly inside PlaylistPlaymodeWidget
                playlist_playmode_widget = self.parentWidget().parentWidget()
                if hasattr(playlist_playmode_widget, 'current_playlist') and playlist_playmode_widget.current_playlist:
                    current_playlist_tracks_set = set(os.path.normpath(p) for p in playlist_playmode_widget.current_playlist.tracks)
                    print(f"[SelectionPool] Found {len(current_playlist_tracks_set)} tracks in current playlist to exclude.")
            except AttributeError:
                 print("[SelectionPool] Could not reliably access parent playlist tracks.")
                 # Proceed without excluding playlist tracks if access fails
                 pass 

            found_files_initial = []
            try:
                for root, _, files in os.walk(directory):
                    for filename in files:
                        if Path(filename).suffix.lower() in AUDIO_EXTENSIONS:
                            full_path = os.path.join(root, filename)
                            found_files_initial.append(full_path)
            except Exception as e:
                print(f"Error scanning directory '{directory}': {e}")
                # Optionally show a message box to the user
                return

            # --- Filter and Delete Hidden/Small Files ---
            files_to_add_to_pool = []
            deleted_count = 0
            KB_SIZE = 1024
            for file_path_str in found_files_initial:
                try:
                    p = Path(file_path_str)
                    filename = p.name
                    norm_path = os.path.normpath(file_path_str) # Normalize path early
                    
                    # --- Check if already in pool or playlist --- 
                    if norm_path in self._pool_paths:
                        # print(f"[SelectionPool] Skipping (already in pool): {norm_path}")
                        continue # Skip if already in the pool
                    if norm_path in current_playlist_tracks_set:
                        # print(f"[SelectionPool] Skipping (already in current playlist): {norm_path}")
                        continue # Skip if already in the current playlist
                        
                    # --- Proceed with stats and deletion check --- 
                    file_size = p.stat().st_size

                    # Check deletion criteria for hidden/small files
                    if filename.startswith('._') and file_size < KB_SIZE:
                        try:
                            os.remove(file_path_str)
                            print(f"[SelectionPool] Deleted hidden/small file: {file_path_str}")
                            deleted_count += 1
                        except OSError as del_e:
                            print(f"[SelectionPool] Error deleting file '{file_path_str}': {del_e}")
                    else:
                        # If not deleted, add it to the list for the pool
                        files_to_add_to_pool.append(file_path_str)

                except FileNotFoundError:
                    print(f"[SelectionPool] Warning: File disappeared during scan: {file_path_str}")
                except Exception as stat_e:
                    print(f"[SelectionPool] Error accessing file info for '{file_path_str}': {stat_e}")
                    # Decide whether to add the file even if info failed - probably not

            if deleted_count > 0:
                print(f"[SelectionPool] Finished cleanup. Deleted {deleted_count} hidden/small files.")
                
            # Add the filtered list to the pool
            if files_to_add_to_pool:
                self.add_tracks(files_to_add_to_pool)
            elif not found_files_initial: # Only show message if initial scan found nothing
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

    def _filter_pool_table(self, text: str):
        """Filters the pool table rows based on the search text, using an AND logic for space-separated tokens."""
        search_text = text.lower().strip()
        search_tokens = search_text.split() if search_text else []
        
        for row in range(self.pool_table.rowCount()):
            filename_item = self.pool_table.item(row, self.COL_FILENAME)
            should_hide = False # Default to showing the row
            if filename_item:
                filename = filename_item.text().lower()
                # Hide if there are tokens and any token is NOT found in the filename
                if search_tokens:
                    should_hide = not all(token in filename for token in search_tokens)
            else:
                # If somehow the item doesn't exist, hide the row during filtering if there are tokens
                should_hide = bool(search_tokens)
                
            self.pool_table.setRowHidden(row, should_hide)

    def keyPressEvent(self, event):
        """Handle key press events, specifically the Delete key."""
        if event.key() == Qt.Key.Key_Delete:
            if self.pool_table.selectedItems():
                print("[SelectionPool] Delete key pressed, removing selected items.")
                self._remove_selected_items()
                event.accept() # Indicate we handled the event
                return
                
        # If not handled, pass to parent
        super().keyPressEvent(event)

    def _on_item_double_clicked(self, index):
        """Handle double-click on an item in the pool table."""
        if index.isValid():
            item = self.pool_table.item(index.row(), self.COL_FILENAME)
            if item:
                filepath = item.data(Qt.ItemDataRole.UserRole)
                if filepath and os.path.isfile(filepath): # Ensure it's a file
                    print(f"[SelectionPool] Double-click detected, requesting single play: {filepath}")
                    self.play_single_file_requested.emit(filepath)

