"""
Preferences page for the Music Player application.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSpinBox, QFormLayout, QGroupBox,
    QLineEdit, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from pathlib import Path

# Import from the framework
from qt_base_app.components.base_card import BaseCard
from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.models.settings_manager import SettingsManager, SettingType


class PreferencePage(QWidget):
    """
    Preferences page allowing users to customize application settings.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # Set widget properties
        self.setObjectName("preferencePage")
        self.setProperty('page_id', 'preferences')
        
        # Initialize settings
        self.settings = SettingsManager.instance()
        self.theme = ThemeManager.instance()
        
        self.setup_ui()
        self.load_settings()
        
    def setup_ui(self):
        """Set up the UI for the preferences page."""
        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 24, 24, 24)
        self.main_layout.setSpacing(24)
        
        # Playback preferences card
        self.playback_card = BaseCard("Playback")
        playback_container = QWidget()
        playback_layout = QFormLayout(playback_container)
        playback_layout.setContentsMargins(0, 0, 0, 0)
        playback_layout.setSpacing(16)
        
        # Seek interval setting
        self.seek_interval_label = QLabel("Seek interval (seconds):")
        self.seek_interval_label.setStyleSheet(f"color: {self.theme.get_color('text', 'primary')};")
        
        self.seek_interval_spinbox = QSpinBox()
        self.seek_interval_spinbox.setMinimum(1)
        self.seek_interval_spinbox.setMaximum(60)
        self.seek_interval_spinbox.setValue(3)  # Default value
        self.seek_interval_spinbox.valueChanged.connect(self.save_settings)
        self.seek_interval_spinbox.setStyleSheet(f"""
            background-color: {self.theme.get_color('background', 'tertiary')};
            color: {self.theme.get_color('text', 'primary')};
            border: 1px solid {self.theme.get_color('border', 'primary')};
            border-radius: 4px;
            padding: 4px;
        """)
        
        playback_layout.addRow(self.seek_interval_label, self.seek_interval_spinbox)
        self.playback_card.add_widget(playback_container)
        
        # Add the playback card to the main layout
        self.main_layout.addWidget(self.playback_card)
        
        # Library preferences card
        self.library_card = BaseCard("Library")
        library_container = QWidget()
        library_layout = QFormLayout(library_container)
        library_layout.setContentsMargins(0, 0, 0, 0)
        library_layout.setSpacing(16)
        
        # Playlists directory setting
        self.playlists_dir_label = QLabel("Playlists directory:")
        self.playlists_dir_label.setStyleSheet(f"color: {self.theme.get_color('text', 'primary')};")
        
        self.playlists_dir_container = QWidget()
        self.playlists_dir_layout = QHBoxLayout(self.playlists_dir_container)
        self.playlists_dir_layout.setContentsMargins(0, 0, 0, 0)
        self.playlists_dir_layout.setSpacing(8)
        
        self.playlists_dir_edit = QLineEdit()
        self.playlists_dir_edit.setPlaceholderText("Choose playlists directory")
        self.playlists_dir_edit.setReadOnly(True)
        self.playlists_dir_edit.setStyleSheet(f"""
            background-color: {self.theme.get_color('background', 'tertiary')};
            color: {self.theme.get_color('text', 'primary')};
            border: 1px solid {self.theme.get_color('border', 'primary')};
            border-radius: 4px;
            padding: 6px;
        """)
        
        self.browse_button = QPushButton("Browse...")
        self.browse_button.setMaximumWidth(100)
        self.browse_button.clicked.connect(self.browse_playlists_dir)
        self.browse_button.setStyleSheet(f"""
            background-color: {self.theme.get_color('background', 'tertiary')};
            color: {self.theme.get_color('text', 'primary')};
            border-radius: 4px;
            padding: 8px 16px;
            font-weight: bold;
        """)
        
        self.playlists_dir_layout.addWidget(self.playlists_dir_edit)
        self.playlists_dir_layout.addWidget(self.browse_button)
        
        library_layout.addRow(self.playlists_dir_label, self.playlists_dir_container)
        self.library_card.add_widget(library_container)
        
        # Add the library card to the main layout
        self.main_layout.addWidget(self.library_card)
        
        # Reset button card
        self.reset_card = BaseCard()
        reset_container = QWidget()
        reset_layout = QHBoxLayout(reset_container)
        reset_layout.setContentsMargins(0, 0, 0, 0)
        reset_layout.setSpacing(16)
        
        self.reset_button = QPushButton("Reset to Defaults")
        self.reset_button.clicked.connect(self.reset_settings)
        self.reset_button.setStyleSheet(f"""
            background-color: {self.theme.get_color('background', 'tertiary')};
            color: {self.theme.get_color('text', 'primary')};
            border-radius: 4px;
            padding: 8px 16px;
            font-weight: bold;
        """)
        
        reset_layout.addWidget(self.reset_button)
        reset_layout.addStretch(1)
        
        self.reset_card.add_widget(reset_container)
        self.main_layout.addWidget(self.reset_card)
        
        # Add a stretch at the end to push all content to the top
        self.main_layout.addStretch(1)
        
    def load_settings(self):
        """Load settings from SettingsManager"""
        seek_interval = self.settings.get('preferences/seek_interval', 3, SettingType.INT)
        self.seek_interval_spinbox.setValue(seek_interval)
        
        playlists_dir = self.settings.get('preferences/playlists_dir', str(Path.home()), SettingType.PATH)
        self.playlists_dir_edit.setText(str(playlists_dir))
        
    def save_settings(self):
        """Save settings to SettingsManager"""
        # Save seek interval
        seek_interval = self.seek_interval_spinbox.value()
        self.settings.set('preferences/seek_interval', seek_interval, SettingType.INT)
        
        # Save playlists directory if it exists
        playlist_dir_text = self.playlists_dir_edit.text().strip()
        if playlist_dir_text:
            try:
                dir_path = Path(playlist_dir_text)
                # Make sure the path exists, if not use the home directory
                if not dir_path.exists():
                    dir_path = Path.home()
                    self.playlists_dir_edit.setText(str(dir_path))
                
                # Save the directory path
                self.settings.set('preferences/playlists_dir', dir_path, SettingType.PATH)
            except Exception as e:
                print(f"Error saving playlists directory: {e}")
                # Fall back to home directory
                self.settings.set('preferences/playlists_dir', Path.home(), SettingType.PATH)
        
        # Sync to persist changes
        self.settings.sync()
        
    def reset_settings(self):
        """Reset settings to default values"""
        self.seek_interval_spinbox.setValue(3)  # Default seek interval
        self.playlists_dir_edit.setText(str(Path.home()))  # Default playlists directory
        self.save_settings()
        
    def browse_playlists_dir(self):
        """Open directory browser dialog to select playlists directory"""
        current_dir = self.settings.get('preferences/playlists_dir', str(Path.home()), SettingType.PATH)
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Playlists Directory",
            str(current_dir),
            QFileDialog.Option.ShowDirsOnly
        )
        
        if directory:
            # Update the text field
            self.playlists_dir_edit.setText(directory)
            
            # Save the new directory path
            try:
                # Convert to Path object and save
                path_obj = Path(directory)
                self.settings.set('preferences/playlists_dir', path_obj, SettingType.PATH)
                self.settings.sync()
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Save Error",
                    f"Failed to save playlists directory setting: {str(e)}"
                ) 