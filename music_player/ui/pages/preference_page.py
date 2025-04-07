"""
Preferences page for the Music Player application.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSpinBox, QFormLayout, QGroupBox,
    QLineEdit, QFileDialog
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from pathlib import Path
from music_player.models.settings_manager import SettingsManager, SettingType


class PreferencePage(QWidget):
    """
    Preferences page allowing users to customize application settings.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # Set widget properties
        self.setObjectName("preferencePage")
        
        # Initialize settings
        self.settings = SettingsManager.instance()
        
        # Update to use modern styles
        self.setStyleSheet("""
            #preferencePage {
                background-color: #09090b;
            }
            QLabel {
                color: #fafafa;
            }
            QGroupBox {
                color: #fafafa;
                font-weight: bold;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                margin-top: 1.5em;
                padding-top: 0.5em;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                background-color: #4a4a4a;
                color: #ffffff;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
            QPushButton:pressed {
                background-color: #3a3a3a;
            }
            QSpinBox {
                background-color: #18181b;
                color: #ffffff;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        
        self.setup_ui()
        self.load_settings()
        
    def setup_ui(self):
        """Set up the UI for the preferences page."""
        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 24, 24, 24)
        self.main_layout.setSpacing(24)
        
        # Page title
        self.title_label = QLabel("Preferences")
        self.title_label.setObjectName("titleLabel")
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.main_layout.addWidget(self.title_label)
        
        # Description
        self.description_label = QLabel("Customize your Music Player experience")
        self.description_label.setObjectName("descriptionLabel")
        description_font = QFont()
        description_font.setPointSize(12)
        self.description_label.setFont(description_font)
        self.main_layout.addWidget(self.description_label)
        
        # Playback preferences group
        self.playback_group = QGroupBox("Playback")
        playback_layout = QFormLayout(self.playback_group)
        playback_layout.setContentsMargins(16, 24, 16, 16)
        playback_layout.setSpacing(16)
        
        # Seek interval setting
        self.seek_interval_label = QLabel("Seek interval (seconds):")
        self.seek_interval_spinbox = QSpinBox()
        self.seek_interval_spinbox.setMinimum(1)
        self.seek_interval_spinbox.setMaximum(60)
        self.seek_interval_spinbox.setValue(3)  # Default value
        self.seek_interval_spinbox.valueChanged.connect(self.save_settings)
        
        playback_layout.addRow(self.seek_interval_label, self.seek_interval_spinbox)
        
        # Add the playback group to the main layout
        self.main_layout.addWidget(self.playback_group)
        
        # Library preferences group
        self.library_group = QGroupBox("Library")
        library_layout = QFormLayout(self.library_group)
        library_layout.setContentsMargins(16, 24, 16, 16)
        library_layout.setSpacing(16)
        
        # Playlists directory setting
        self.playlists_dir_label = QLabel("Playlists directory:")
        self.playlists_dir_container = QWidget()
        self.playlists_dir_layout = QHBoxLayout(self.playlists_dir_container)
        self.playlists_dir_layout.setContentsMargins(0, 0, 0, 0)
        self.playlists_dir_layout.setSpacing(8)
        
        self.playlists_dir_edit = QLineEdit()
        self.playlists_dir_edit.setPlaceholderText("Choose playlists directory")
        self.playlists_dir_edit.setReadOnly(True)
        self.playlists_dir_edit.setStyleSheet("""
            QLineEdit {
                background-color: #18181b;
                color: #ffffff;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        
        self.browse_button = QPushButton("Browse...")
        self.browse_button.setMaximumWidth(100)
        self.browse_button.clicked.connect(self.browse_playlists_dir)
        
        self.playlists_dir_layout.addWidget(self.playlists_dir_edit)
        self.playlists_dir_layout.addWidget(self.browse_button)
        
        library_layout.addRow(self.playlists_dir_label, self.playlists_dir_container)
        
        # Add the library group to the main layout
        self.main_layout.addWidget(self.library_group)
        
        # Save and Reset buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(16)
        
        self.reset_button = QPushButton("Reset to Defaults")
        self.reset_button.clicked.connect(self.reset_settings)
        
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_settings)
        
        buttons_layout.addWidget(self.reset_button)
        buttons_layout.addStretch(1)
        buttons_layout.addWidget(self.save_button)
        
        self.main_layout.addLayout(buttons_layout)
        
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
        seek_interval = self.seek_interval_spinbox.value()
        self.settings.set('preferences/seek_interval', seek_interval, SettingType.INT)
        
        playlists_dir = Path(self.playlists_dir_edit.text())
        self.settings.set('preferences/playlists_dir', playlists_dir, SettingType.PATH)
        
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
            self.playlists_dir_edit.setText(directory)
            self.save_settings() 