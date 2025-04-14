# ui/components/playlist_components/playlist_playmode.py

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QListWidget, QListWidgetItem, QScrollArea, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
import qtawesome as qta
from pathlib import Path

from qt_base_app.theme.theme_manager import ThemeManager
from music_player.models.playlist import Playlist
from .selection_pool import SelectionPoolWidget

class PlaylistPlaymodeWidget(QWidget):
    """
    Widget representing the Play Mode of the Playlists page.
    Displays the contents of a selected playlist with a breadcrumb navigation.
    """
    # Signals to be emitted to the parent PlaylistsPage
    back_requested = pyqtSignal()  # Signal to go back to Dashboard Mode

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playlistPlaymodeWidget")
        self.theme = ThemeManager.instance()
        self.current_playlist = None  # The currently loaded playlist
        
        # Allow for absolute positioning of children
        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)
        
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
        
        breadcrumb_layout.addWidget(self.back_button)
        breadcrumb_layout.addWidget(self.playlist_name_label)
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
        
        # --- Track List ---
        self.tracks_list = QListWidget()
        self.tracks_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.tracks_list.setHorizontalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.tracks_list.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                padding: 5px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {self.theme.get_color('background', 'secondary')}80;
                color: {self.theme.get_color('text', 'primary')};
            }}
        """)
        
        # Add empty message when no tracks
        self.empty_label = QLabel("No tracks in this playlist")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {self.theme.get_color('text', 'secondary')}; font-style: italic;")
        self.empty_label.hide()
        
        # Add components to content layout
        content_layout.addWidget(self.tracks_list)
        content_layout.addWidget(self.empty_label)
        
        # --- Selection Pool --- 
        self.selection_pool_widget = SelectionPoolWidget(self.content_widget)
        content_layout.addWidget(self.selection_pool_widget)
        
        # Position the content below the breadcrumb
        self.content_widget.setGeometry(0, 32, self.width(), self.height() - 32)
    
    def _connect_signals(self):
        """Connect signals after UI elements are created."""
        self.back_button.clicked.connect(self.back_requested)
        self.selection_pool_widget.add_selected_requested.connect(self._handle_add_selected_from_pool)
    
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
        # Explicitly check for None, don't rely on boolean evaluation of Playlist object
        if playlist is None:
            return
            
        self.current_playlist = playlist
        
        # Update the playlist name immediately in the breadcrumb
        display_name = playlist.name if playlist.name else "Untitled Playlist"
        self.playlist_name_label.setText(display_name)
        self.playlist_name_label.repaint() # Force repaint
        
        # Clear and populate the tracks list
        self.tracks_list.clear()
        
        if not playlist.tracks:
            self.tracks_list.hide()
            self.empty_label.show()
            # Don't return here, still need to potentially clear pool if needed
        else: # Only show list if there are tracks
            self.empty_label.hide()
            self.tracks_list.show()
            
            for track_path in playlist.tracks:
                # Extract just the filename to display
                path = Path(track_path)
                filename = path.name
                
                item = QListWidgetItem(filename)
                item.setData(Qt.ItemDataRole.UserRole, track_path)  # Store full path
                self.tracks_list.addItem(item)
                
        # Optionally clear the selection pool when loading a new playlist
        # self.selection_pool_widget.clear_pool() # Uncomment if desired
            
    def get_current_playlist(self) -> Playlist:
        """
        Returns the currently loaded playlist.
        
        Returns:
            Playlist: The current playlist or None if none is loaded
        """
        return self.current_playlist

    def _handle_add_selected_from_pool(self, tracks_to_add: list):
        """
        Handles adding tracks from the selection pool to the current playlist.
        
        Args:
            tracks_to_add (list): List of full track file paths.
        """
        # Explicitly check for None
        if self.current_playlist is None:
            print("[PlayMode] _handle_add_selected_from_pool: No current playlist. Aborting.")
            return
        if not tracks_to_add:
            print("[PlayMode] _handle_add_selected_from_pool: No tracks to add. Aborting.")
            return
            
        added_count = 0
        for track_path in tracks_to_add:
            if self.current_playlist.add_track(track_path):
                added_count += 1
            # else: # Optionally print if track already exists 
                # print(f"[PlayMode] _handle_add_selected_from_pool: Failed to add (already exists?): {track_path}")
                
        if added_count > 0:
            # Save the updated playlist
            save_success = self.current_playlist.save()
            if not save_success:
                print(f"Error: Failed to save playlist '{self.current_playlist.name}' after adding tracks.")
                # Consider how to handle save failure - rollback?
                return # Stop if save failed
                
            # Refresh the track list view to show the newly added tracks
            self.load_playlist(self.current_playlist)
            
            # Remove the added tracks from the selection pool
            self.selection_pool_widget.remove_tracks(tracks_to_add)
