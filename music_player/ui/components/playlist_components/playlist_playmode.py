# ui/components/playlist_components/playlist_playmode.py

import os
import datetime
from pathlib import Path
from typing import List, Optional, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea,
    QMenu, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QSortFilterProxyModel, QModelIndex
from PyQt6.QtGui import QFont, QIcon, QCursor
import qtawesome as qta

from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.models.settings_manager import SettingsManager, SettingType
from music_player.models.playlist import Playlist
from music_player.models import player_state
from .selection_pool import SelectionPoolWidget, format_file_size, format_modified_time
from music_player.ui.components.icon_button import IconButton
from music_player.ui.components.base_table import BaseTableModel, ColumnDefinition
from music_player.models.file_pool_model import FilePoolModel
from qt_base_app.models.logger import Logger
from .playlist_table_view import PlaylistTableView

# Define common audio file extensions (can be moved to a shared location)
AUDIO_EXTENSIONS = {
    '.mp3', '.flac', '.wav', '.ogg', '.aac', '.m4a', '.wma', 
    '.opus', '.aiff', '.ape', '.mpc'
}

# --- Column Definitions for Playlist Table ---
def get_track_stat(track_data: dict, stat_key: str) -> Any:
    """Helper to safely get file stats, returning 0 on error."""
    path_str = track_data.get('path')
    if not path_str:
        return 0
    try:
        stats = Path(path_str).stat()
        if stat_key == 'size': return stats.st_size
        if stat_key == 'modified': return stats.st_mtime
    except Exception:
        pass
    return 0

def get_added_timestamp(track_data: dict) -> float:
    """Helper to safely parse added_time string to timestamp."""
    added_time_str = track_data.get('added_time')
    if added_time_str:
        try:
            return datetime.datetime.fromisoformat(added_time_str).timestamp()
        except (ValueError, TypeError):
            pass
    return 0

def format_added_time(timestamp: float) -> str:
    """Helper to format timestamp from get_added_timestamp."""
    if not timestamp:
        return "Unknown"
    try:
        dt = datetime.datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "Invalid Date"

playlist_col_defs = [
    ColumnDefinition(
        header="Filename",
        # Get filename from the 'path' in track_data dict
        data_key=lambda td: Path(td.get('path', '')).name,
        sort_key=lambda td: Path(td.get('path', '')).name.lower(), # Sort by lowercased filename
        width=300, stretch=1, # Give it stretch factor
        tooltip_key='path' # Show full path in tooltip
    ),
    ColumnDefinition(
        header="Size",
        data_key=lambda td: get_track_stat(td, 'size'),
        display_formatter=format_file_size,
        sort_key=lambda td: get_track_stat(td, 'size'), # Sort by raw bytes
        width=100,
        alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        sort_role=Qt.ItemDataRole.EditRole # Use EditRole for sorting raw bytes
    ),
    ColumnDefinition(
        header="Modified",
        data_key=lambda td: get_track_stat(td, 'modified'),
        display_formatter=format_modified_time, # Use existing formatter
        sort_key=lambda td: get_track_stat(td, 'modified'), # Sort by raw timestamp
        width=150,
        sort_role=Qt.ItemDataRole.EditRole # Use EditRole for sorting timestamp
    ),
    ColumnDefinition(
        header="Date Added",
        data_key=get_added_timestamp, # Use helper to get timestamp
        display_formatter=format_added_time, # Use helper to format timestamp
        sort_key=get_added_timestamp, # Sort by raw timestamp
        width=150,
        sort_role=Qt.ItemDataRole.EditRole # Use EditRole for sorting timestamp
    ),
]

class PlaylistPlaymodeWidget(QWidget):
    """
    Widget representing the Play Mode of the Playlists page.
    Displays the contents of a selected playlist with a breadcrumb navigation.
    """
    back_requested = pyqtSignal()  # Signal to go back to Dashboard Mode
    track_selected_for_playback = pyqtSignal(str) # Emits filepath when a track is selected for playback
    playlist_play_requested = pyqtSignal(Playlist) # Signal to request playing the entire current playlist

    def __init__(self, parent=None):
        """
        Initializes the PlaylistPlaymodeWidget.

        Args:
            parent (QWidget, optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.setObjectName("playlistPlaymodeWidget")
        
        self.theme = ThemeManager.instance()
        self.settings = SettingsManager.instance()
        self.current_playlist: Optional[Playlist] = None # Type hint
        self.model: Optional[FilePoolModel] = None # <-- Use FilePoolModel
        self.proxy_model: Optional[QSortFilterProxyModel] = None # Proxy model reference
        
        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)
        self.setAcceptDrops(True)
        
        self._setup_ui()
        self._connect_signals() # Connect signals after UI setup
    
    def _setup_ui(self):
        # Create a breadcrumb container that will be positioned absolutely
        self.breadcrumb_container = QWidget(self)
        self.breadcrumb_container.setObjectName("breadcrumbContainer")
        self.breadcrumb_container.setFixedHeight(32)  # Fixed height for the breadcrumb
        
        # Style the breadcrumb container
        self.breadcrumb_container.setStyleSheet(f"""
            #breadcrumbContainer {{
                background-color: transparent;
            }}
        """)
        
        # Breadcrumb layout
        breadcrumb_layout = QHBoxLayout(self.breadcrumb_container)
        breadcrumb_layout.setContentsMargins(16, 0, 16, 0)
        breadcrumb_layout.setSpacing(8)
        
        # Back button with plain text "<"
        self.back_button = QPushButton("<")
        self.back_button.setToolTip("Back to playlists")
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.setFixedWidth(24)
        self.back_button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                padding: 4px;
                color: {self.theme.get_color('text', 'primary')};
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background-color: {self.theme.get_color('background', 'secondary')}40;
                border-radius: 4px;
            }}
        """)
        
        # Playlist name label with 9pt regular font
        self.playlist_name_label = QLabel("Loading...")
        self.playlist_name_label.setStyleSheet(f"""
            color: {self.theme.get_color('text', 'primary')};
            font-size: 9pt;
            font-weight: normal;
        """)
        
        # Play Playlist Button - Use IconButton
        self.play_playlist_button = IconButton(
            icon_name='fa5s.play',
            tooltip="Play this playlist",
            icon_color_key=('text', 'primary'), # Use primary text color for icon
            fixed_size=QSize(24, 24),      # Keep original fixed size
            icon_size=QSize(12, 12),       # Keep original icon size
            parent=self
        )
        
        breadcrumb_layout.addWidget(self.back_button)
        breadcrumb_layout.addWidget(self.playlist_name_label)
        breadcrumb_layout.addWidget(self.play_playlist_button) # Add the play button
        breadcrumb_layout.addStretch(1)  # Push content to the left
        
        # Position the breadcrumb at the very top
        self.breadcrumb_container.setGeometry(0, 0, self.width(), 32)
        
        # Create a content widget for tracks that will be positioned below the breadcrumb
        self.content_widget = QWidget(self)
        self.content_widget.setObjectName("contentWidget")
        
        # Content layout
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(16, 8, 16, 16)
        content_layout.setSpacing(16) # Add spacing between list and pool
        
        # --- Track Table ---
        self.tracks_table = PlaylistTableView(table_name="playlist_tracks_table", parent=self.content_widget)
        # No need for manual setup (columns, headers, styling, sorting, context menu policy)
        # Persistence is handled by BaseTableView via table_name
        # self.tracks_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu) # Disabled for now
        
        # Add empty message when no tracks
        self.empty_label = QLabel("No tracks in this playlist")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {self.theme.get_color('text', 'secondary')}; font-style: italic;")
        self.empty_label.hide()
        
        # Add components to content layout
        content_layout.addWidget(self.tracks_table)
        content_layout.addWidget(self.empty_label)
        
        # --- Selection Pool --- 
        self.selection_pool_widget = SelectionPoolWidget(parent=self.content_widget)
        content_layout.addWidget(self.selection_pool_widget)
        
        # Position the content below the breadcrumb
        self.content_widget.setGeometry(0, 32, self.width(), self.height() - 32)
    
    def _connect_signals(self):
        """Connect signals after UI elements are created."""
        self.back_button.clicked.connect(self.back_requested)
        self.selection_pool_widget.add_selected_requested.connect(self._handle_add_selected_from_pool)
        self.tracks_table.doubleClicked.connect(self._on_track_double_clicked)
        self.play_playlist_button.clicked.connect(self._on_play_playlist_requested)
        # Connect delete signal from PlaylistTableView
        self.tracks_table.delete_requested_from_playlist.connect(self._handle_delete_requested)
        # Connect sort indicator signal
        self.tracks_table.horizontalHeader().sortIndicatorChanged.connect(self._on_sort_changed)
    
    def _on_track_double_clicked(self, index: QModelIndex): # Takes QModelIndex
        """Handle double-click on a track item to play it."""
        if not self.current_playlist or not index.isValid() or not self.proxy_model:
            return
            
        # Get the source object (track dictionary) using UserRole
        source_object = self.proxy_model.data(index, Qt.ItemDataRole.UserRole)
        if source_object and isinstance(source_object, dict):
            track_path = source_object.get('path')
            if track_path and track_path in (t.get('path') for t in self.current_playlist.tracks):
                player_state.set_current_playlist(self.current_playlist)
                self.track_selected_for_playback.emit(track_path)
            else:
                print(f"[PlayMode] Double-clicked path not found in current playlist: {track_path}")
        else:
             print("[PlayMode] Could not retrieve source object on double click.")
    
    def resizeEvent(self, event):
        # Update widget sizes when the parent widget is resized
        super().resizeEvent(event)
        width = event.size().width()
        height = event.size().height()
        
        # Update breadcrumb width to match parent
        self.breadcrumb_container.setFixedWidth(width)
        
        # Update content area size
        self.content_widget.setGeometry(0, 32, width, height - 32)
    
    def load_playlist(self, playlist: Playlist):
        """
        Load a playlist into the view and display its tracks.
        
        Args:
            playlist (Playlist): The playlist to display and play
        """
        if playlist is None:
            self.current_playlist = None
            self.model = None
            self.proxy_model = None
            self.tracks_table.setModel(None) # Clear the table
            self.playlist_name_label.setText("No Playlist Selected")
            self.tracks_table.hide()
            self.empty_label.show()
            return
            
        self.current_playlist = playlist
        display_name = playlist.name if playlist.name else "Untitled Playlist"
        self.playlist_name_label.setText(display_name)
        logger = Logger.instance() # Get logger instance
        logger.info(self.__class__.__name__, f"[PlayMode] Loading playlist '{display_name}' into view.") # Log playlist name
        
        # --- Prepare data for the model, adding original index --- 
        source_track_data = []
        for index, track_dict in enumerate(playlist.tracks):
            # Create a copy and add the original index
            model_track_dict = track_dict.copy()
            model_track_dict['original_index'] = index
            source_track_data.append(model_track_dict)
        # --------------------------------------------------------

        if not source_track_data: # Check the prepared list
            self.tracks_table.hide()
            self.empty_label.show()
            # --- Use FilePoolModel ---
            logger.debug(self.__class__.__name__, "[PlayMode] Playlist is empty, creating empty FilePoolModel.")
            self.model = FilePoolModel(source_objects=[], column_definitions=playlist_col_defs)
            # -------------------------
        else:
            self.empty_label.hide()
            self.tracks_table.show()
            # --- Use FilePoolModel ---
            logger.debug(self.__class__.__name__, f"[PlayMode] Creating FilePoolModel for playlist with {len(source_track_data)} tracks.")
            self.model = FilePoolModel(source_objects=source_track_data, column_definitions=playlist_col_defs)
            # -------------------------
        
        # Set up proxy model and link to table
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.tracks_table.setModel(self.proxy_model)
        # BaseTableView handles loading saved state (widths, sort) in setModel
        # No need for manual sorting or width setting here
        self.tracks_table.resizeRowsToContents()
        # --- Explicitly update playlist sort order after initial load & sort --- 
        self._update_playlist_model_sort_order()
        # ---------------------------------------------------------------------

    def _handle_delete_requested(self, objects_to_delete: List[Any]):
        """Handles the delete request signal from PlaylistTableView."""
        logger = Logger.instance()
        if not self.current_playlist or not objects_to_delete:
            return
        
        logger.debug(self.__class__.__name__, f"[PlayMode] Handling delete request for {len(objects_to_delete)} items.")
        paths_to_remove = []
        successfully_removed_from_playlist_obj = True # Assume success initially

        # 1. Update the Playlist object
        for track_obj in objects_to_delete:
            if isinstance(track_obj, dict):
                path = track_obj.get('path')
                if path:
                    paths_to_remove.append(path)
                    # Try removing from the playlist DATA model
                    if not self.current_playlist.remove_track(path):
                        successfully_removed_from_playlist_obj = False
                        logger.warning(self.__class__.__name__, f"[PlayMode] Path '{path}' requested for delete, but not found in playlist object data.")
                else:
                     successfully_removed_from_playlist_obj = False # Track object had no path
                     logger.warning(self.__class__.__name__, f"[PlayMode] Track object requested for delete missing 'path': {track_obj}")
            else:
                successfully_removed_from_playlist_obj = False # Item wasn't a dict
                logger.warning(self.__class__.__name__, f"[PlayMode] Item requested for delete was not a dictionary: {track_obj}")

        # 2. Save the Playlist (only if all removals from Playlist object seemed successful)
        if successfully_removed_from_playlist_obj:
            save_success = self.current_playlist.save()
            if not save_success:
                logger.error(self.__class__.__name__, f"[PlayMode] ERROR saving playlist '{self.current_playlist.name}' after track removal! View may be inconsistent.")
                # Decide how to handle save failure? Maybe don't update view?
                # For now, we proceed but log the error.
        else:
            logger.error(self.__class__.__name__, "[PlayMode] Not saving playlist or updating view due to errors removing tracks from Playlist object.")
            return # Stop here if the Playlist object wasn't updated correctly

        # 3. Add removed tracks to selection pool (use the collected paths)
        if paths_to_remove:
             self.selection_pool_widget.add_tracks(paths_to_remove)

        # 4. Tell the model to remove rows (this updates the view)
        target_model = self.model # Directly target the source FilePoolModel
        if target_model and hasattr(target_model, 'remove_rows_by_objects') and callable(target_model.remove_rows_by_objects):
             # --- Pass the ORIGINAL objects received from the signal --- 
             logger.debug(self.__class__.__name__, f"[PlayMode] Requesting model remove {len(objects_to_delete)} object(s) received from view signal.")
             target_model.remove_rows_by_objects(objects_to_delete)
             # --------------------------------------------------------
        else:
             logger.error(self.__class__.__name__, "[PlayMode] Could not find remove_rows_by_objects method on model to update view.")
             
        # Update empty message if needed
        if target_model and target_model.rowCount() == 0: # Check model row count AFTER potential removal
            self.tracks_table.hide()
            self.empty_label.show()

    def _handle_add_selected_from_pool(self, tracks_to_add: list):
        if self.current_playlist is None or not tracks_to_add:
            return
        if self.model is None:
            print("[PlayMode] Cannot add tracks: Table model not initialized.")
            return
            
        # Create track data dictionaries for the model
        new_track_objects = []
        added_to_playlist_count = 0
        paths_actually_added = []
        
        for track_path in tracks_to_add:
            if self.current_playlist.add_track(track_path):
                 # Create the dictionary expected by the model/column defs
                 new_track_objects.append({
                     'path': track_path,
                     'added_time': datetime.datetime.now().isoformat() # Add current time
                     # Other fields (filename, size, modified) will be derived by helpers/lambdas
                 })
                 paths_actually_added.append(track_path)
                 added_to_playlist_count += 1
            
        if added_to_playlist_count > 0:
            save_success = self.current_playlist.save()
            if not save_success:
                print(f"Error: Failed to save playlist '{self.current_playlist.name}' after adding tracks.")
                # Should probably revert the playlist.add_track calls if save fails?
                return
                
            # --- Insert rows into the MODEL --- 
            # Determine insertion point (e.g., end of table)
            insert_row_index = self.model.rowCount() 
            if self.model.insert_rows(insert_row_index, new_track_objects):
                 print(f"[PlayMode] Inserted {len(new_track_objects)} rows into model.")
                 # View updates automatically via model signals
            else:
                 print("[PlayMode] ERROR: Failed to insert rows into model.")
                 # UI might be out of sync with playlist file
            
            # Remove from selection pool
            self.selection_pool_widget.remove_tracks(paths_actually_added)
            
            # Ensure table is visible if it was hidden
            if self.model.rowCount() > 0:
                 self.empty_label.hide()
                 self.tracks_table.show()

    def _on_play_playlist_requested(self):
        """Emit signal to request playback of the entire current playlist."""
        if self.current_playlist:
            print(f"[PlayMode] Play playlist requested for: {self.current_playlist.name}")
            self.playlist_play_requested.emit(self.current_playlist)
        else:
            print("[PlayMode] Play playlist requested but no playlist loaded.")

    def get_current_playlist(self) -> Optional[Playlist]: # Added Optional
        return self.current_playlist

    # --- Drag and Drop Handling ---
    
    def dragEnterEvent(self, event):
        """Accept drag events if they contain file URLs."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            print("[PlayMode] Drag Enter accepted.") # Debug
        else:
            event.ignore()
            print("[PlayMode] Drag Enter ignored.") # Debug

    def dragMoveEvent(self, event):
        """Accept move events during drag."""
        if event.mimeData().hasUrls(): # Check again for safety
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Handle dropped files/folders based on drop location."""
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        event.acceptProposedAction()
        urls = event.mimeData().urls()
        paths_to_process = [url.toLocalFile() for url in urls]

        drop_pos = event.position().toPoint()
        selection_pool_rect = self.selection_pool_widget.geometry()

        if selection_pool_rect.contains(drop_pos):
            # Dropped onto Selection Pool - Requires filtering existing playlist/pool
            files_to_add_to_pool = self._process_dropped_paths(paths_to_process)
            if files_to_add_to_pool:
                self.selection_pool_widget.add_tracks(files_to_add_to_pool)
        else:
            # Dropped onto Playlist Area - Add directly to playlist/model
            print("[PlayMode] Drop onto playlist area - using _handle_add_selected_from_pool logic.")
            # Simplified: Treat drop onto playlist like adding from pool
            # This reuses the logic for adding to playlist object, saving, inserting rows
            # Note: This doesn't filter duplicates already in the playlist efficiently before calling add_track
            # It relies on playlist.add_track to handle duplicates internally.
            
            # Scan folders first to get individual files
            scanned_files = []
            for path_str in paths_to_process:
                try:
                    p = Path(path_str)
                    if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS:
                         scanned_files.append(str(p.resolve()))
                    elif p.is_dir():
                        for root, _, files in os.walk(p):
                            for filename in files:
                                if Path(filename).suffix.lower() in AUDIO_EXTENSIONS:
                                    full_path = os.path.join(root, filename)
                                    scanned_files.append(str(Path(full_path).resolve()))
                except Exception as e:
                     print(f"[PlayMode] Error processing path {path_str} during drop scan: {e}")
            
            if scanned_files:
                 # Call the same handler used for adding from the pool
                 self._handle_add_selected_from_pool(scanned_files)

    def _process_dropped_paths(self, paths_to_process: List[str]) -> List[str]:
        """Processes a list of dropped file/folder paths, returning valid audio files.

        Filters extensions and removes duplicates already present in the current playlist
        or the selection pool.

        Args:
            paths_to_process: List of paths from the drop event.

        Returns:
            List of unique, valid, absolute audio file paths.
        """
        print(f"[PlayMode] Processing dropped paths: {paths_to_process}")
        audio_files_found = []
        for path_str in paths_to_process:
            try:
                p = Path(path_str)
                if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS:
                    audio_files_found.append(str(p.resolve())) # Store resolved path
                elif p.is_dir():
                    print(f"[PlayMode] Scanning dropped folder: {p}") # Debug
                    for root, _, files in os.walk(p):
                        for filename in files:
                            if Path(filename).suffix.lower() in AUDIO_EXTENSIONS:
                                full_path = os.path.join(root, filename)
                                audio_files_found.append(str(Path(full_path).resolve())) # Store resolved path
            except Exception as e:
                print(f"[PlayMode] Error processing dropped path {path_str}: {e}")

        print(f"[PlayMode] Found {len(audio_files_found)} potential audio files.")
        if not audio_files_found:
            return [] # Nothing to add

        # --- Filter out duplicates from playlist and pool --- 
        current_playlist_tracks_set = set()
        if self.current_playlist:
             # Access model data if available for current paths
             if self.model:
                 current_playlist_tracks_set = set(os.path.normpath(track_obj.get('path', ''))
                                                 for track_obj in self.model.get_all_objects())
             else: # Fallback to playlist object if model not ready
                 current_playlist_tracks_set = set(os.path.normpath(p.get('path', ''))
                                                     for p in self.current_playlist.tracks)

        # === Get pool paths from the SELECTION POOL MODEL ===
        current_pool_tracks_set = set()
        if self.selection_pool_widget.model: # Check if model exists
             # Call the model's method to get all paths
             pool_paths_list = self.selection_pool_widget.model.get_all_paths()
             current_pool_tracks_set = set(os.path.normpath(p) for p in pool_paths_list)
        # ====================================================
        
        files_to_add = []
        for file_path in audio_files_found:
            norm_path = os.path.normpath(file_path) # Normalize path for comparison
            if norm_path not in current_playlist_tracks_set and norm_path not in current_pool_tracks_set:
                files_to_add.append(file_path) # Add the original resolved path
            # else: # Debugging
                # reason = "playlist" if norm_path in current_playlist_tracks_set else "pool"
                # print(f"[PlayMode] Skipping duplicate ({reason}): {norm_path}")

        print(f"[PlayMode] Filtered duplicates, {len(files_to_add)} files remain to be added.")
        return files_to_add

    def _on_sort_changed(self, logicalIndex: int, order: Qt.SortOrder):
        """Slot connected to the header's sortIndicatorChanged signal."""
        # Simply call the helper method to update the playlist model
        self._update_playlist_model_sort_order()

    # --- New helper method --- 
    def _update_playlist_model_sort_order(self):
        """Gets the current visual order and updates the Playlist object."""
        if not self.current_playlist or not self.tracks_table.model():
            # print("[PlayMode] _update_playlist_model_sort_order called but no playlist or model.") # Can be noisy
            return

        # Get the source objects in the current visual order
        ordered_track_objects = self.tracks_table.get_visible_items_data_in_order()

        # Extract the original indices from these objects
        sorted_original_indices = []
        for track_obj in ordered_track_objects:
            if isinstance(track_obj, dict) and 'original_index' in track_obj:
                sorted_original_indices.append(track_obj['original_index'])
            else:
                # This indicates a problem with data preparation or retrieval
                print(f"[PlayMode] Warning: Could not find 'original_index' in ordered track object during sort update: {track_obj}")

        # Update the Playlist object with the new order
        if sorted_original_indices:
            # print(f"[PlayMode] Updating playlist sort order with {len(sorted_original_indices)} indices.") # Can be noisy
            self.current_playlist.update_sort_order(sorted_original_indices)
        # else: # No need to warn if list is empty, just means table was empty
            # print("[PlayMode] Warning: Could not extract sorted original indices during sort update.")
