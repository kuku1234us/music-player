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
from PyQt6.QtGui import QFont, QIcon, QAction, QColor
import qtawesome as qta
from pathlib import Path

# Import from the framework
from qt_base_app.components.base_card import BaseCard
from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.models.settings_manager import SettingsManager, SettingType


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
        self.setProperty('page_id', 'playlists')
        
        # Initialize settings and theme
        self.settings = SettingsManager.instance()
        self.theme = ThemeManager.instance()
        
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the UI for the playlists page."""
        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 24, 24, 24)
        self.main_layout.setSpacing(24)
        
        # Buttons card
        self.buttons_card = BaseCard("Actions")
        buttons_container = QWidget()
        self.buttons_layout = QHBoxLayout(buttons_container)
        self.buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.buttons_layout.setSpacing(16)
        
        # Create new playlist button
        self.new_playlist_button = QPushButton("New Playlist")
        self.new_playlist_button.setIcon(QIcon(qta.icon('fa5s.plus', color=self.theme.get_color('text', 'primary')).pixmap(16, 16)))
        self.new_playlist_button.clicked.connect(self.create_new_playlist)
        self.new_playlist_button.setStyleSheet(f"""
            background-color: {self.theme.get_color('background', 'tertiary')};
            color: {self.theme.get_color('text', 'primary')};
            border-radius: 4px;
            padding: 8px 16px;
            font-weight: bold;
        """)
        self.buttons_layout.addWidget(self.new_playlist_button)
        
        # Import playlist button
        self.import_playlist_button = QPushButton("Import Playlist")
        self.import_playlist_button.setIcon(QIcon(qta.icon('fa5s.file-import', color=self.theme.get_color('text', 'primary')).pixmap(16, 16)))
        self.import_playlist_button.clicked.connect(self.import_playlist)
        self.import_playlist_button.setStyleSheet(f"""
            background-color: {self.theme.get_color('background', 'tertiary')};
            color: {self.theme.get_color('text', 'primary')};
            border-radius: 4px;
            padding: 8px 16px;
            font-weight: bold;
        """)
        self.buttons_layout.addWidget(self.import_playlist_button)
        
        self.buttons_layout.addStretch(1)
        
        # Refresh playlists button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setIcon(QIcon(qta.icon('fa5s.sync', color=self.theme.get_color('text', 'primary')).pixmap(16, 16)))
        self.refresh_button.clicked.connect(self.load_playlists)
        self.refresh_button.setStyleSheet(f"""
            background-color: {self.theme.get_color('background', 'tertiary')};
            color: {self.theme.get_color('text', 'primary')};
            border-radius: 4px;
            padding: 8px 16px;
            font-weight: bold;
        """)
        self.buttons_layout.addWidget(self.refresh_button)
        
        self.buttons_card.add_widget(buttons_container)
        self.main_layout.addWidget(self.buttons_card)
        
        # Playlists list
        self.playlists_card = BaseCard(
            "My Playlists", 
            border_style=f"1px solid {self.theme.get_color('accent', 'secondary')}",
            background_style=f"{self.theme.get_color('background', 'tertiary')}20"  # 20% opacity
        )
        
        # Playlists container
        playlists_container = QWidget()
        playlists_container_layout = QVBoxLayout(playlists_container)
        playlists_container_layout.setContentsMargins(0, 0, 0, 0)
        playlists_container_layout.setSpacing(16)
        
        self.playlists_list = QListWidget()
        self.playlists_list.setMinimumHeight(300)
        self.playlists_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlists_list.customContextMenuRequested.connect(self.show_context_menu)
        self.playlists_list.itemDoubleClicked.connect(self.on_playlist_double_clicked)
        self.playlists_list.setStyleSheet(f"""
            background-color: {self.theme.get_color('background', 'tertiary')};
            color: {self.theme.get_color('text', 'primary')};
            border: 1px solid {self.theme.get_color('border', 'primary')};
            border-radius: 4px;
            padding: 8px;
        """)
        
        playlists_container_layout.addWidget(self.playlists_list)
        
        # Empty state label
        self.empty_label = QLabel("No playlists found. Create a new playlist or set a playlists directory in Preferences.")
        self.empty_label.setStyleSheet(f"color: {self.theme.get_color('text', 'tertiary')}; font-style: italic;")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        playlists_container_layout.addWidget(self.empty_label)
        
        self.playlists_card.add_widget(playlists_container)
        self.main_layout.addWidget(self.playlists_card)
        
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
        
        # Open file dialog to select playlist files
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Playlist Files",
            str(Path.home()),
            "Playlist files (*.m3u *.m3u8 *.pls)"
        )
        
        if not files:
            return  # User canceled
        
        import_count = 0
        for file_path in files:
            # Get filename and check if it already exists in the target directory
            filename = os.path.basename(file_path)
            target_path = os.path.join(str(playlists_dir), filename)
            
            if os.path.exists(target_path):
                # Ask if user wants to overwrite
                reply = QMessageBox.question(
                    self,
                    "File Already Exists",
                    f"The file '{filename}' already exists. Overwrite?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                
                if reply != QMessageBox.StandardButton.Yes:
                    continue  # Skip this file
            
            # Copy the file to the playlists directory
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as src:
                    content = src.read()
                
                with open(target_path, 'w', encoding='utf-8') as dst:
                    dst.write(content)
                
                import_count += 1
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Import Error",
                    f"Failed to import '{filename}': {str(e)}"
                )
        
        if import_count > 0:
            # Refresh the list
            self.load_playlists()
            QMessageBox.information(
                self,
                "Import Successful",
                f"Successfully imported {import_count} playlist(s)."
            )
    
    def show_context_menu(self, position):
        """
        Show context menu for playlist items.
        
        Args:
            position: Position where right-click occurred
        """
        item = self.playlists_list.itemAt(position)
        if not item:
            return
        
        context_menu = QMenu(self)
        
        # Play action
        play_action = QAction(QIcon(qta.icon('fa5s.play', color=self.theme.get_color('text', 'primary'))), "Play", self)
        play_action.triggered.connect(lambda: self.on_playlist_double_clicked(item))
        context_menu.addAction(play_action)
        
        # Edit action
        edit_action = QAction(QIcon(qta.icon('fa5s.edit', color=self.theme.get_color('text', 'primary'))), "Edit", self)
        edit_action.triggered.connect(lambda: self.edit_playlist(item))
        context_menu.addAction(edit_action)
        
        # Rename action
        rename_action = QAction(QIcon(qta.icon('fa5s.font', color=self.theme.get_color('text', 'primary'))), "Rename", self)
        rename_action.triggered.connect(lambda: self.rename_playlist(item))
        context_menu.addAction(rename_action)
        
        # Delete action
        delete_action = QAction(QIcon(qta.icon('fa5s.trash-alt', color=self.theme.get_color('text', 'primary'))), "Delete", self)
        delete_action.triggered.connect(lambda: self.delete_playlist(item))
        context_menu.addAction(delete_action)
        
        # Show the context menu
        context_menu.exec(self.playlists_list.mapToGlobal(position))
    
    def on_playlist_double_clicked(self, item):
        """
        Handle double-click on a playlist item.
        
        Args:
            item: The clicked PlaylistItem
        """
        self.playlist_selected.emit(item.playlist_path)
    
    def edit_playlist(self, item):
        """
        Open external editor for the playlist file.
        
        Args:
            item: The PlaylistItem to edit
        """
        # This is a placeholder - in a real application,
        # you would implement a proper playlist editor
        QMessageBox.information(
            self, 
            "Edit Playlist",
            f"Editing playlist: {item.playlist_name}\n\nThis feature is not yet implemented."
        )
    
    def rename_playlist(self, item):
        """
        Rename the selected playlist.
        
        Args:
            item: The PlaylistItem to rename
        """
        # Get playlists directory from settings
        playlists_dir = self.settings.get('preferences/playlists_dir', str(Path.home()), SettingType.PATH)
        
        # Ask for new playlist name
        new_name, ok = QInputDialog.getText(
            self, 
            "Rename Playlist",
            "Enter new name for the playlist:",
            text=item.playlist_name
        )
        
        if ok and new_name and new_name != item.playlist_name:
            # Get file extension from original file
            _, ext = os.path.splitext(item.playlist_path)
            
            # Create new file path
            new_path = os.path.join(str(playlists_dir), f"{new_name}{ext}")
            
            # Check if file already exists
            if os.path.exists(new_path):
                QMessageBox.warning(
                    self,
                    "Playlist Already Exists",
                    f"A playlist named '{new_name}' already exists."
                )
                return
            
            try:
                # Rename the file
                os.rename(item.playlist_path, new_path)
                
                # Refresh the list
                self.load_playlists()
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Rename Error",
                    f"Failed to rename playlist: {str(e)}"
                )
    
    def delete_playlist(self, item):
        """
        Delete the selected playlist.
        
        Args:
            item: The PlaylistItem to delete
        """
        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete the playlist '{item.playlist_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            # Delete the file
            os.remove(item.playlist_path)
            
            # Refresh the list
            self.load_playlists()
        except Exception as e:
            QMessageBox.warning(
                self,
                "Delete Error",
                f"Failed to delete playlist: {str(e)}"
            ) 