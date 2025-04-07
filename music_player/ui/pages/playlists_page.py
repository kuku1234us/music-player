"""
Playlists page for the Music Player application.
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QInputDialog,
    QFileDialog, QMenu
)
from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QAction
import qtawesome as qta
from pathlib import Path
from music_player.models.settings_manager import SettingsManager, SettingType

from music_player.ui.components import DashboardCard


class PlaylistItem(QListWidgetItem):
    """
    Custom list item for displaying playlists.
    """
    def __init__(self, playlist_name, playlist_path, parent=None):
        super().__init__(parent)
        self.playlist_name = playlist_name
        self.playlist_path = playlist_path
        self.setText(playlist_name)
        
        # Set icon for the playlist
        self.setIcon(QIcon(qta.icon('fa5s.list', color='#a1a1aa').pixmap(32, 32)))


class PlaylistsPage(QWidget):
    """
    Page for managing music playlists.
    """
    # Signal emitted when a playlist is selected to play
    playlist_selected = pyqtSignal(str)  # playlist_path
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Set widget properties
        self.setObjectName("playlistsPage")
        
        # Initialize settings
        self.settings = SettingsManager.instance()
        
        # Update to use modern styles
        self.setStyleSheet("""
            #playlistsPage {
                background-color: #09090b;
            }
            QLabel {
                color: #fafafa;
            }
            QPushButton {
                background-color: #3f3f46;
                color: #ffffff;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #52525b;
            }
            QPushButton:pressed {
                background-color: #27272a;
            }
            QListWidget {
                background-color: #18181b;
                color: #fafafa;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 8px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
                margin-bottom: 2px;
            }
            QListWidget::item:selected {
                background-color: #3f3f46;
            }
            QListWidget::item:hover {
                background-color: #27272a;
            }
        """)
        
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the UI for the playlists page."""
        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 24, 24, 24)
        self.main_layout.setSpacing(24)
        
        # Page title
        self.title_label = QLabel("Playlists")
        self.title_label.setObjectName("titleLabel")
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.main_layout.addWidget(self.title_label)
        
        # Description
        self.description_label = QLabel("Create and manage your music playlists")
        self.description_label.setObjectName("descriptionLabel")
        description_font = QFont()
        description_font.setPointSize(12)
        self.description_label.setFont(description_font)
        self.main_layout.addWidget(self.description_label)
        
        # Buttons layout
        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.setSpacing(16)
        
        # Create new playlist button
        self.new_playlist_button = QPushButton("New Playlist")
        self.new_playlist_button.setIcon(QIcon(qta.icon('fa5s.plus', color='#ffffff').pixmap(16, 16)))
        self.new_playlist_button.clicked.connect(self.create_new_playlist)
        self.buttons_layout.addWidget(self.new_playlist_button)
        
        # Import playlist button
        self.import_playlist_button = QPushButton("Import Playlist")
        self.import_playlist_button.setIcon(QIcon(qta.icon('fa5s.file-import', color='#ffffff').pixmap(16, 16)))
        self.import_playlist_button.clicked.connect(self.import_playlist)
        self.buttons_layout.addWidget(self.import_playlist_button)
        
        self.buttons_layout.addStretch(1)
        
        # Refresh playlists button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setIcon(QIcon(qta.icon('fa5s.sync', color='#ffffff').pixmap(16, 16)))
        self.refresh_button.clicked.connect(self.load_playlists)
        self.buttons_layout.addWidget(self.refresh_button)
        
        self.main_layout.addLayout(self.buttons_layout)
        
        # Playlists list
        self.playlists_card = DashboardCard("Your Playlists")
        self.playlists_list = QListWidget()
        self.playlists_list.setMinimumHeight(300)
        self.playlists_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlists_list.customContextMenuRequested.connect(self.show_context_menu)
        self.playlists_list.itemDoubleClicked.connect(self.on_playlist_double_clicked)
        
        self.playlists_card.add_widget(self.playlists_list)
        self.main_layout.addWidget(self.playlists_card)
        
        # Empty state label
        self.empty_label = QLabel("No playlists found. Create a new playlist or set a playlists directory in Preferences.")
        self.empty_label.setStyleSheet("color: #a1a1aa; font-style: italic;")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.playlists_card.add_widget(self.empty_label)
        
        # Add a stretch at the end to push all content to the top
        self.main_layout.addStretch(1)
        
        # Load playlists
        self.load_playlists()
        
    def load_playlists(self):
        """
        Load playlists from the configured directory.
        """
        self.playlists_list.clear()
        
        # Get playlists directory from settings
        playlists_dir = self.settings.get('preferences/playlists_dir', str(Path.home()), SettingType.PATH)
        
        if not playlists_dir or not os.path.exists(str(playlists_dir)):
            self.empty_label.setText("No playlists directory set. Please configure it in Preferences.")
            self.empty_label.setVisible(True)
            return
        
        # Scan for playlist files (.m3u, .m3u8, .pls)
        playlist_extensions = ['.m3u', '.m3u8', '.pls']
        found_playlists = False
        
        for filename in os.listdir(str(playlists_dir)):
            file_path = os.path.join(str(playlists_dir), filename)
            if os.path.isfile(file_path) and any(filename.lower().endswith(ext) for ext in playlist_extensions):
                # Extract playlist name (without extension)
                playlist_name = os.path.splitext(filename)[0]
                
                # Create playlist item
                item = PlaylistItem(playlist_name, file_path)
                self.playlists_list.addItem(item)
                found_playlists = True
        
        # Show or hide the empty state message
        self.empty_label.setVisible(not found_playlists)
        if not found_playlists:
            self.empty_label.setText("No playlists found. Create a new playlist or import one.")
    
    def create_new_playlist(self):
        """
        Create a new empty playlist file.
        """
        # Get playlists directory from settings
        playlists_dir = self.settings.get('preferences/playlists_dir', str(Path.home()), SettingType.PATH)
        
        if not playlists_dir or not os.path.exists(str(playlists_dir)):
            QMessageBox.warning(
                self,
                "Playlists Directory Not Set",
                "Please set a playlists directory in Preferences before creating playlists."
            )
            return
        
        # Ask for playlist name
        playlist_name, ok = QInputDialog.getText(
            self, 
            "Create New Playlist",
            "Enter a name for the new playlist:"
        )
        
        if ok and playlist_name:
            # Create a new .m3u8 file
            file_path = os.path.join(str(playlists_dir), f"{playlist_name}.m3u8")
            
            # Check if file already exists
            if os.path.exists(file_path):
                QMessageBox.warning(
                    self,
                    "Playlist Already Exists",
                    f"A playlist named '{playlist_name}' already exists."
                )
                return
            
            # Create an empty playlist file with UTF-8 encoding header
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                f.write("#Created by Music Player\n")
            
            # Refresh the list
            self.load_playlists()
    
    def import_playlist(self):
        """
        Import an existing playlist file.
        """
        # Get playlists directory from settings
        playlists_dir = self.settings.get('preferences/playlists_dir', str(Path.home()), SettingType.PATH)
        
        if not playlists_dir or not os.path.exists(str(playlists_dir)):
            QMessageBox.warning(
                self,
                "Playlists Directory Not Set",
                "Please set a playlists directory in Preferences before importing playlists."
            )
            return
        
        # Open file dialog
        file_filter = "Playlist files (*.m3u *.m3u8 *.pls);;All files (*)"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Playlist",
            str(playlists_dir),
            file_filter
        )
        
        if file_path:
            # Copy the file to playlists directory
            filename = os.path.basename(file_path)
            dest_path = os.path.join(str(playlists_dir), filename)
            
            # Check if file already exists
            if os.path.exists(dest_path):
                overwrite = QMessageBox.question(
                    self,
                    "Playlist Already Exists",
                    f"A playlist named '{filename}' already exists. Overwrite?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                
                if overwrite != QMessageBox.StandardButton.Yes:
                    return
            
            # Copy file contents
            try:
                with open(file_path, 'r', encoding='utf-8') as src:
                    content = src.read()
                
                with open(dest_path, 'w', encoding='utf-8') as dest:
                    dest.write(content)
                    
                # Refresh the list
                self.load_playlists()
                
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Import Error",
                    f"Failed to import playlist: {str(e)}"
                )
    
    def show_context_menu(self, position):
        """
        Show context menu for playlist items.
        """
        item = self.playlists_list.itemAt(position)
        if not item:
            return
            
        # Create context menu
        context_menu = QMenu(self)
        
        # Add actions
        play_action = QAction("Play", self)
        play_action.triggered.connect(lambda: self.on_playlist_double_clicked(item))
        
        edit_action = QAction("Edit", self)
        edit_action.triggered.connect(lambda: self.edit_playlist(item))
        
        rename_action = QAction("Rename", self)
        rename_action.triggered.connect(lambda: self.rename_playlist(item))
        
        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(lambda: self.delete_playlist(item))
        
        # Add actions to menu
        context_menu.addAction(play_action)
        context_menu.addAction(edit_action)
        context_menu.addAction(rename_action)
        context_menu.addSeparator()
        context_menu.addAction(delete_action)
        
        # Show the menu
        context_menu.exec(self.playlists_list.mapToGlobal(position))
    
    def on_playlist_double_clicked(self, item):
        """
        Handle double-click on a playlist item.
        """
        if isinstance(item, PlaylistItem):
            # Emit signal with playlist path
            self.playlist_selected.emit(item.playlist_path)
    
    def edit_playlist(self, item):
        """
        Open the playlist file in a text editor for manual editing.
        """
        if isinstance(item, PlaylistItem):
            # Open the playlist in a simple text viewer/editor
            # Note: In a real app, you might want to implement a more sophisticated playlist editor
            QMessageBox.information(
                self,
                "Edit Playlist",
                f"Opening {item.playlist_path} for editing is not implemented yet.\n\n"
                "In a future version, this will open a dedicated playlist editor."
            )
    
    def rename_playlist(self, item):
        """
        Rename a playlist file.
        """
        if isinstance(item, PlaylistItem):
            # Ask for new name
            new_name, ok = QInputDialog.getText(
                self, 
                "Rename Playlist",
                "Enter a new name for the playlist:",
                text=item.playlist_name
            )
            
            if ok and new_name and new_name != item.playlist_name:
                # Get playlists directory and file extension
                playlists_dir = os.path.dirname(item.playlist_path)
                _, extension = os.path.splitext(item.playlist_path)
                
                # Create new file path
                new_path = os.path.join(playlists_dir, f"{new_name}{extension}")
                
                # Check if new file already exists
                if os.path.exists(new_path):
                    QMessageBox.warning(
                        self,
                        "Playlist Already Exists",
                        f"A playlist named '{new_name}' already exists."
                    )
                    return
                
                # Rename the file
                try:
                    os.rename(item.playlist_path, new_path)
                    
                    # Refresh the list
                    self.load_playlists()
                    
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Rename Error",
                        f"Failed to rename playlist: {str(e)}"
                    )
    
    def delete_playlist(self, item):
        """
        Delete a playlist file.
        """
        if isinstance(item, PlaylistItem):
            # Confirm deletion
            confirm = QMessageBox.question(
                self,
                "Delete Playlist",
                f"Are you sure you want to delete the playlist '{item.playlist_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if confirm == QMessageBox.StandardButton.Yes:
                # Delete the file
                try:
                    os.remove(item.playlist_path)
                    
                    # Refresh the list
                    self.load_playlists()
                    
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Delete Error",
                        f"Failed to delete playlist: {str(e)}"
                    ) 