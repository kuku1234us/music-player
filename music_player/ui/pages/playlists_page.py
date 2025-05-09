"""
Playlists page for the Music Player application.
Handles switching between Dashboard and Play modes.
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QInputDialog,
    QFileDialog, QMenu, QStackedWidget
)
from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QAction, QColor
import qtawesome as qta
from pathlib import Path

# Import from the framework
from qt_base_app.components.base_card import BaseCard
from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.models.settings_manager import SettingsManager, SettingType

# Import playlist specific components
from music_player.models.playlist import Playlist, PlaylistManager
from music_player.models import player_state
from music_player.ui.components.playlist_components.playlist_dashboard import PlaylistDashboardWidget
from music_player.ui.components.playlist_components.playlist_playmode import PlaylistPlaymodeWidget

# Import settings definitions
from music_player.models.settings_defs import PREF_WORKING_DIR_KEY, DEFAULT_WORKING_DIR


class PlaylistsPage(QWidget):
    """
    Page for managing music playlists. Switches between modes.
    """
    # Signal emitted when a playlist is selected to play
    playlist_selected_for_playback = pyqtSignal(Playlist) # Emits the Playlist object
    # Re-emit the signal from PlaylistPlaymodeWidget
    playlist_play_requested = pyqtSignal(Playlist)

    def __init__(self, parent=None):
        """
        Initializes the PlaylistsPage.
        
        Args:
            parent (QWidget, optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.setObjectName("playlistsPage")
        self.setProperty('page_id', 'playlists')
        
        # Initialize settings and theme
        self.settings = SettingsManager.instance()
        self.theme = ThemeManager.instance()
        # Defer PlaylistManager initialization to when it's needed
        self.playlist_manager = None

        # Internal state
        self._current_mode = "dashboard" # "dashboard" or "play"
        self._current_playlist_in_edit = None

        self.setup_ui()
        self._connect_signals()
        self.load_playlists_into_dashboard()

    def setup_ui(self):
        """Set up the UI with a stacked widget for modes."""
        # Main layout - Takes margins from parent dashboard
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Stacked widget to switch between modes
        self.stacked_widget = QStackedWidget(self)

        # --- Dashboard Mode Widget --- 
        self.dashboard_widget = PlaylistDashboardWidget(self)
        self.stacked_widget.addWidget(self.dashboard_widget)

        # --- Play Mode Widget ---
        # Revert instantiation - no longer pass ai_config
        self.play_mode_widget = PlaylistPlaymodeWidget(parent=self)
        self.stacked_widget.addWidget(self.play_mode_widget)

        self.main_layout.addWidget(self.stacked_widget)

        # Set initial mode
        self.stacked_widget.setCurrentWidget(self.dashboard_widget)

    def _connect_signals(self):
        """Connect signals from child widgets to page slots."""
        # Dashboard Widget Signals
        self.dashboard_widget.create_new_playlist_requested.connect(self.create_new_playlist)
        self.dashboard_widget.import_playlist_requested.connect(self.import_playlist)
        self.dashboard_widget.refresh_playlists_requested.connect(self.load_playlists_into_dashboard)
        self.dashboard_widget.playlist_selected.connect(self._handle_playlist_selected)
        # Context menu signals will need connections once context menu is in dashboard widget
        # self.dashboard_widget.edit_playlist_requested.connect(self.edit_playlist)
        # self.dashboard_widget.rename_playlist_requested.connect(self.rename_playlist)
        # self.dashboard_widget.delete_playlist_requested.connect(self.delete_playlist)

        # Connect signals for PlayModeWidget
        self.play_mode_widget.back_requested.connect(self._enter_dashboard_mode)
        # Connect the new signal from PlaylistPlaymodeWidget
        self.play_mode_widget.playlist_play_requested.connect(self.playlist_play_requested) # Relay the signal

    # --- Mode Switching --- 
    def _enter_dashboard_mode(self):
        self._current_mode = "dashboard"
        # Note: We don't reset _current_playlist_in_edit here so playback can continue
        self.stacked_widget.setCurrentWidget(self.dashboard_widget)
        self.load_playlists_into_dashboard() # Refresh list when returning

    def _enter_play_mode(self, playlist: Playlist):
        self._current_mode = "play"
        self._current_playlist_in_edit = playlist
        
        # Update the global reference to the current playlist
        player_state.set_current_playlist(playlist)
        
        # Load playlist into the play mode widget
        self.play_mode_widget.load_playlist(playlist)
        
        # Make sure the widget is visible
        self.play_mode_widget.setVisible(True)
        self.stacked_widget.setCurrentWidget(self.play_mode_widget)
        
        # Force update (Can sometimes help with UI refresh issues)
        self.stacked_widget.update()
        self.update()

        # Emit signal to start playback
        self.playlist_selected_for_playback.emit(playlist)

    # --- Playlist Management Logic --- 
    def load_playlists_into_dashboard(self):
        """
        Loads playlists using PlaylistManager and populates the dashboard list.
        Ensures the manager uses the current working directory setting.
        """
        # Initialize/Re-initialize PlaylistManager here to get the latest setting
        self.playlist_manager = PlaylistManager()

        list_widget = self.dashboard_widget.get_playlist_list_widget()
        list_widget.clear()
        playlists = self.playlist_manager.load_playlists()

        if not playlists:
            self.dashboard_widget.set_empty_message("No playlists found. Create or import one.")
            self.dashboard_widget.show_empty_message(True)
            return

        self.dashboard_widget.show_empty_message(False)
        for playlist in playlists:
            # Use simple QListWidgetItem for now, storing Playlist object
            item = QListWidgetItem(playlist.name)
            item.setData(Qt.ItemDataRole.UserRole, playlist) # Store object
            item.setIcon(QIcon(qta.icon('fa5s.list', color='#a1a1aa').pixmap(32, 32)))
            list_widget.addItem(item)

    def create_new_playlist(self):
        """
        Handles the request to create a new playlist.
        """
        # Ensure playlist manager is initialized
        if not self.playlist_manager:
            self.playlist_manager = PlaylistManager()

        playlist_name, ok = QInputDialog.getText(
            self,
            "Create New Playlist",
            "Enter a name for the new playlist:"
        )

        if ok and playlist_name:
            new_playlist_path = self.playlist_manager.get_playlist_path(playlist_name)
            if new_playlist_path.exists():
                QMessageBox.warning(self, "Playlist Exists", f"A playlist named '{playlist_name}' already exists.")
                return

            try:
                new_playlist = Playlist(name=playlist_name)
                if self.playlist_manager.save_playlist(new_playlist):
                    self.load_playlists_into_dashboard()
                else:
                    QMessageBox.critical(self, "Error", "Failed to save the new playlist file.")
            except ValueError as e:
                 QMessageBox.warning(self, "Invalid Name", str(e))
            except Exception as e:
                QMessageBox.critical(self, "Error", f"An unexpected error occurred: {str(e)}")

    def import_playlist(self):
        """
        Handles the request to import playlist files.
        """
        # Ensure playlist manager is initialized
        if not self.playlist_manager:
            self.playlist_manager = PlaylistManager()

        # Use the configured working directory as the default starting point
        working_dir = self.settings.get(PREF_WORKING_DIR_KEY, DEFAULT_WORKING_DIR, SettingType.PATH)

        # Open file dialog to select playlist files
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Playlist Files",
            str(working_dir), # Start browsing from the working directory
            "Playlist files (*.m3u *.m3u8 *.pls *.json)" # Add JSON
        )

        if not files:
            return # User canceled

        import_count = 0
        skipped_count = 0
        error_count = 0
        # Use the playlist_dir from the manager instance, which is derived from working_dir
        target_dir = self.playlist_manager.playlist_dir

        for file_path_str in files:
            file_path = Path(file_path_str)
            target_name = file_path.stem # Use filename without extension as potential name
            target_path = self.playlist_manager.get_playlist_path(target_name, target_dir)

            # Check if a playlist with the sanitized target name already exists
            if target_path.exists():
                reply = QMessageBox.question(
                    self,
                    "File Already Exists",
                    f"A playlist derived from '{file_path.name}' (named '{target_path.stem}') already exists. Overwrite?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    skipped_count += 1
                    continue # Skip this file

            # Handle different import types
            try:
                imported_playlist = None
                if file_path.suffix.lower() == '.json':
                    # Directly load our format
                    imported_playlist = Playlist.load_from_file(file_path)
                    if imported_playlist:
                         # Ensure it gets saved to the managed directory with correct name/path
                         imported_playlist.filepath = None # Clear old path
                         imported_playlist.name = target_path.stem # Use sanitized name
                         if not self.playlist_manager.save_playlist(imported_playlist):
                             raise IOError("Failed to save imported JSON playlist.")

                # TODO: Add parsing logic for M3U, PLS if needed
                # elif file_path.suffix.lower() in ['.m3u', '.m3u8']:
                #    # Parse M3U, create Playlist object
                #    pass
                # elif file_path.suffix.lower() == '.pls':
                #    # Parse PLS, create Playlist object
                #    pass
                else:
                    # Simple copy for now if not JSON (basic fallback)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as src, \
                         open(target_path, 'w', encoding='utf-8') as dst:
                        # Basic copy, doesn't guarantee internal format is useful later
                        dst.write(src.read())
                    print(f"Warning: Copied non-JSON playlist '{file_path.name}'. Internal parsing not implemented.")
                    # Create a placeholder Playlist object if needed for UI update
                    # imported_playlist = Playlist(name=target_path.stem, filepath=target_path)

                # If parsing/saving was successful (or basic copy done)
                # For JSON, save_playlist handles the success check
                if file_path.suffix.lower() == '.json':
                    if imported_playlist:
                        import_count += 1
                    else:
                        error_count +=1 # Failed to load/save JSON
                else: # Assume basic copy succeeded if no exception
                    import_count += 1

            except Exception as e:
                error_count += 1
                QMessageBox.warning(
                    self,
                    "Import Error",
                    f"Failed to import '{file_path.name}': {str(e)}"
                )

        if import_count > 0 or error_count > 0 or skipped_count > 0:
            self.load_playlists_into_dashboard()
            message = f"Import finished:\n- Imported: {import_count}\n- Skipped: {skipped_count}\n- Errors: {error_count}"
            QMessageBox.information(self, "Import Complete", message)

    def _handle_playlist_selected(self, item: QListWidgetItem):
        """
        Handles when a playlist is selected (e.g., double-clicked) in the dashboard.
        Switches to Play Mode.
        """
        playlist = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(playlist, Playlist):
            self._enter_play_mode(playlist)
        else:
            print(f"Error: Could not retrieve Playlist object from selected item: {item.text()}")

    # --- Placeholder methods for context menu actions --- 
    # These will eventually be connected to signals from PlaylistDashboardWidget
    def edit_playlist(self, item: QListWidgetItem):
        # Ensure playlist manager is initialized
        if not self.playlist_manager:
            self.playlist_manager = PlaylistManager()

        playlist = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(playlist, Playlist): return
        QMessageBox.information(self, "Edit Playlist", f"Editing: {playlist.name}\n(Not Implemented Yet)")

    def rename_playlist(self, item: QListWidgetItem):
        # Ensure playlist manager is initialized
        if not self.playlist_manager:
            self.playlist_manager = PlaylistManager()

        playlist = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(playlist, Playlist): return

        old_name = playlist.name
        old_path = playlist.filepath

        new_name, ok = QInputDialog.getText(
            self,
            "Rename Playlist",
            "Enter new name:",
            text=old_name
        )

        if ok and new_name and new_name != old_name:
            try:
                new_path = self.playlist_manager.get_playlist_path(new_name)
                if new_path.exists():
                    raise FileExistsError(f"A playlist named '{new_name}' already exists.")

                # Rename file if it exists
                if old_path and old_path.exists():
                    os.rename(old_path, new_path)

                # Update playlist object and save its new state (name and path)
                playlist.name = new_name
                playlist.filepath = new_path
                if not self.playlist_manager.save_playlist(playlist):
                     # Attempt to revert rename if save fails?
                     if old_path and new_path.exists(): os.rename(new_path, old_path)
                     raise IOError("Failed to save renamed playlist file.")

                self.load_playlists_into_dashboard() # Refresh view
            except FileExistsError as e:
                QMessageBox.warning(self, "Rename Error", str(e))
            except (OSError, IOError) as e:
                QMessageBox.critical(self, "Rename Error", f"Failed to rename playlist file: {str(e)}")
            except Exception as e:
                 QMessageBox.critical(self, "Rename Error", f"An unexpected error occurred: {str(e)}")

    def delete_playlist(self, item: QListWidgetItem):
        # Ensure playlist manager is initialized
        if not self.playlist_manager:
            self.playlist_manager = PlaylistManager()

        playlist = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(playlist, Playlist): return

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete the playlist '{playlist.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self.playlist_manager.delete_playlist(playlist):
                self.load_playlists_into_dashboard()
            else:
                QMessageBox.critical(self, "Delete Error", f"Failed to delete playlist '{playlist.name}'.")

    # --- Access to current playlist ---
    @staticmethod
    def get_current_playing_playlist() -> Playlist:
        """
        Returns the current playlist that's being played.
        This is intended to be used by the main player or other components.
        
        Returns:
            Playlist: The current playlist or None if none is loaded/playing
        """
        return player_state.get_current_playlist()
        
    def showEvent(self, event):
        """
        Called when the page becomes visible. 
        Reloads playlists to show current contents of working directory.
        """
        super().showEvent(event)
        
        # Only reload playlists if we're in dashboard mode
        # This prevents disrupting the playback when switching between pages
        if self._current_mode == "dashboard":
            self.load_playlists_into_dashboard()


