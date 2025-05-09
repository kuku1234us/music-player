"""
Preferences page for the Music Player application.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSpinBox, QFormLayout, QGroupBox,
    QLineEdit, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QRegularExpression
from PyQt6.QtGui import QFont, QColor, QRegularExpressionValidator
from pathlib import Path

# Import from the framework
from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.models.settings_manager import SettingsManager, SettingType
# Import keys and defaults from settings_defs
from music_player.models.settings_defs import (
    PREF_SEEK_INTERVAL_KEY, DEFAULT_SEEK_INTERVAL,
    PREF_WORKING_DIR_KEY, DEFAULT_WORKING_DIR,
    YT_DOWNLOAD_DIR_KEY, DEFAULT_YT_DOWNLOAD_DIR,
    # Import QSettings keys for API keys
    YT_API_QSETTINGS_KEY, DEFAULT_YT_API_KEY, 
    GROQ_API_QSETTINGS_KEY, DEFAULT_GROQ_API_KEY 
)


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
        self.main_layout.setSpacing(20)
        
        # Form layout for all settings
        form_layout = QFormLayout()
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(16)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        
        # Style for all labels
        label_style = f"color: {self.theme.get_color('text', 'primary')};"
        
        # Input field style
        input_style = f"""
            background-color: {self.theme.get_color('background', 'tertiary')};
            color: {self.theme.get_color('text', 'primary')};
            border: 1px solid {self.theme.get_color('border', 'primary')};
            border-radius: 4px;
            padding: 6px;
        """
        
        # Button style
        button_style = f"""
            background-color: {self.theme.get_color('background', 'tertiary')};
            color: {self.theme.get_color('text', 'primary')};
            border-radius: 4px;
            padding: 8px 16px;
            font-weight: bold;
        """
        
        # --- Playback Settings ---
        
        # Seek interval setting
        self.seek_interval_label = QLabel("Seek interval (seconds):")
        self.seek_interval_label.setStyleSheet(label_style)
        
        self.seek_interval_spinbox = QSpinBox()
        self.seek_interval_spinbox.setMinimum(1)
        self.seek_interval_spinbox.setMaximum(60)
        self.seek_interval_spinbox.setValue(3)  # Default value
        self.seek_interval_spinbox.valueChanged.connect(self._save_seek_interval)
        self.seek_interval_spinbox.setStyleSheet(input_style)
        
        form_layout.addRow(self.seek_interval_label, self.seek_interval_spinbox)
        
        # --- Library Settings ---
        
        # Renamed this setting to Working Directory
        self.working_dir_label = QLabel("Working Directory:")
        self.working_dir_label.setStyleSheet(label_style)
        
        self.working_dir_container = QWidget()
        self.working_dir_layout = QHBoxLayout(self.working_dir_container)
        self.working_dir_layout.setContentsMargins(0, 0, 0, 0)
        self.working_dir_layout.setSpacing(8)
        
        self.working_dir_edit = QLineEdit()
        self.working_dir_edit.setPlaceholderText("Choose working directory")
        self.working_dir_edit.setReadOnly(True)
        self.working_dir_edit.setStyleSheet(input_style)
        
        self.browse_working_dir_button = QPushButton("Browse...")
        self.browse_working_dir_button.setMaximumWidth(100)
        self.browse_working_dir_button.clicked.connect(self.browse_working_dir)
        self.browse_working_dir_button.setStyleSheet(button_style)
        
        self.working_dir_layout.addWidget(self.working_dir_edit)
        self.working_dir_layout.addWidget(self.browse_working_dir_button)
        
        form_layout.addRow(self.working_dir_label, self.working_dir_container)
        
        # --- Download Settings ---
        
        # Add Download Directory setting
        self.download_dir_label = QLabel("Download Directory:")
        self.download_dir_label.setStyleSheet(label_style)
        
        self.download_dir_container = QWidget()
        self.download_dir_layout = QHBoxLayout(self.download_dir_container)
        self.download_dir_layout.setContentsMargins(0, 0, 0, 0)
        self.download_dir_layout.setSpacing(8)
        
        self.download_dir_edit = QLineEdit()
        self.download_dir_edit.setPlaceholderText("Choose download directory")
        self.download_dir_edit.setReadOnly(True)
        self.download_dir_edit.setStyleSheet(input_style)
        
        self.browse_download_dir_button = QPushButton("Browse...")
        self.browse_download_dir_button.setMaximumWidth(100)
        self.browse_download_dir_button.clicked.connect(self.browse_download_dir)
        self.browse_download_dir_button.setStyleSheet(button_style)
        
        self.download_dir_layout.addWidget(self.download_dir_edit)
        self.download_dir_layout.addWidget(self.browse_download_dir_button)
        
        form_layout.addRow(self.download_dir_label, self.download_dir_container)
        
        # --- Youtube API Key (Uses QSettings Key) ---
        self.yt_api_key_label = QLabel("YouTube API Key:")
        self.yt_api_key_label.setStyleSheet(label_style)
        self.yt_api_key_edit = QLineEdit()
        self.yt_api_key_edit.setPlaceholderText("Enter YouTube Data API v3 key")
        self.yt_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password) 
        self.yt_api_key_edit.setStyleSheet(input_style)
        self.yt_api_key_edit.textChanged.connect(self._save_yt_api_key)
        form_layout.addRow(self.yt_api_key_label, self.yt_api_key_edit)

        # --- Groq API Key (Uses QSettings Key) ---
        self.groq_api_key_label = QLabel("Groq API Key:")
        self.groq_api_key_label.setStyleSheet(label_style)
        self.groq_api_key_edit = QLineEdit()
        self.groq_api_key_edit.setPlaceholderText("Enter Groq API key")
        self.groq_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password) 
        self.groq_api_key_edit.setStyleSheet(input_style)
        self.groq_api_key_edit.textChanged.connect(self._save_groq_api_key)
        form_layout.addRow(self.groq_api_key_label, self.groq_api_key_edit)

        self.main_layout.addLayout(form_layout)
        
        # --- Buttons --- 
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.reset_button = QPushButton("Reset All Settings")
        self.reset_button.setStyleSheet(button_style + " background-color: #502020;") 
        button_layout.addWidget(self.reset_button)
        self.main_layout.addLayout(button_layout)
        self.main_layout.addStretch(1)
        
        # Connect reset button
        self.reset_button.clicked.connect(self.reset_settings)
        
    def load_settings(self):
        """Load settings from SettingsManager"""
        # Load general settings
        seek_interval = self.settings.get(PREF_SEEK_INTERVAL_KEY, DEFAULT_SEEK_INTERVAL, SettingType.INT)
        self.seek_interval_spinbox.setValue(seek_interval)
        
        # Load working directory (using specific key)
        working_dir = self.settings.get(PREF_WORKING_DIR_KEY, DEFAULT_WORKING_DIR, SettingType.PATH)
        self.working_dir_edit.setText(str(working_dir))

        # Load download directory
        download_dir = self.settings.get(YT_DOWNLOAD_DIR_KEY, DEFAULT_YT_DOWNLOAD_DIR, SettingType.PATH)
        self.download_dir_edit.setText(str(download_dir))
        
        # Load API keys using QSettings keys
        yt_api_key = self.settings.get(YT_API_QSETTINGS_KEY, DEFAULT_YT_API_KEY, SettingType.STRING)
        self.yt_api_key_edit.setText(yt_api_key)
        
        groq_api_key = self.settings.get(GROQ_API_QSETTINGS_KEY, DEFAULT_GROQ_API_KEY, SettingType.STRING)
        self.groq_api_key_edit.setText(groq_api_key)
        
    def _save_seek_interval(self):
        """Save the seek interval setting."""
        seek_interval = self.seek_interval_spinbox.value()
        self.settings.set(PREF_SEEK_INTERVAL_KEY, seek_interval, SettingType.INT)
        self.settings.sync() # Sync immediately after changing this setting
        print("[PreferencePage] Seek interval saved:", seek_interval)
        
    def _save_yt_api_key(self):
        """Save the YouTube API key setting."""
        api_key = self.yt_api_key_edit.text()
        self.settings.set(YT_API_QSETTINGS_KEY, api_key, SettingType.STRING)
        self.settings.sync()
        print("[PreferencePage] YouTube API key saved")
        
    def _save_groq_api_key(self):
        """Save the Groq API key setting."""
        api_key = self.groq_api_key_edit.text()
        self.settings.set(GROQ_API_QSETTINGS_KEY, api_key, SettingType.STRING)
        self.settings.sync()
        print("[PreferencePage] Groq API key saved")
        
    def reset_settings(self):
        """Reset settings to default values."""
        # Reset UI fields
        self.seek_interval_spinbox.setValue(DEFAULT_SEEK_INTERVAL)
        self.working_dir_edit.setText(str(DEFAULT_WORKING_DIR))
        self.download_dir_edit.setText(str(DEFAULT_YT_DOWNLOAD_DIR))
        self.yt_api_key_edit.setText(DEFAULT_YT_API_KEY)
        self.groq_api_key_edit.setText(DEFAULT_GROQ_API_KEY)
        
        # Set QSettings back to defaults
        self.settings.set(PREF_SEEK_INTERVAL_KEY, DEFAULT_SEEK_INTERVAL, SettingType.INT)
        self.settings.set(PREF_WORKING_DIR_KEY, DEFAULT_WORKING_DIR, SettingType.PATH)
        self.settings.set(YT_DOWNLOAD_DIR_KEY, DEFAULT_YT_DOWNLOAD_DIR, SettingType.PATH)
        self.settings.set(YT_API_QSETTINGS_KEY, DEFAULT_YT_API_KEY, SettingType.STRING)
        self.settings.set(GROQ_API_QSETTINGS_KEY, DEFAULT_GROQ_API_KEY, SettingType.STRING)
        # Add sets for any other QSettings managed here
        
        self.settings.sync()
        print("[PreferencePage] Settings reset.")
        
    def showEvent(self, event):
        """Reload settings when the page becomes visible"""
        super().showEvent(event)
        # Reload settings to ensure we display the most current values
        self.load_settings()
        
    def browse_working_dir(self):
        """Open directory browser dialog to select working directory"""
        current_dir = self.settings.get(PREF_WORKING_DIR_KEY, DEFAULT_WORKING_DIR, SettingType.PATH)
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Working Directory",
            str(current_dir),
            QFileDialog.Option.ShowDirsOnly
        )
        
        if directory:
            # Update the text field
            self.working_dir_edit.setText(directory)
            
            # Save the new directory path
            try:
                # Convert to Path object and save
                path_obj = Path(directory)
                self.settings.set(PREF_WORKING_DIR_KEY, path_obj, SettingType.PATH)
                self.settings.sync() # Persist changes immediately
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Save Error",
                    f"Failed to save working directory: {str(e)}"
                ) 

    def browse_download_dir(self):
        """Open directory browser dialog to select download directory"""
        current_dir = self.settings.get(YT_DOWNLOAD_DIR_KEY, DEFAULT_YT_DOWNLOAD_DIR, SettingType.PATH)
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Download Directory",
            str(current_dir),
            QFileDialog.Option.ShowDirsOnly
        )
        
        if directory:
            # Update the text field
            self.download_dir_edit.setText(directory)
            
            # Save the new directory path
            try:
                # Convert to Path object and save
                path_obj = Path(directory)
                self.settings.set(YT_DOWNLOAD_DIR_KEY, path_obj, SettingType.PATH)
                self.settings.sync() # Persist changes immediately
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Save Error",
                    f"Failed to save download directory: {str(e)}"
                ) 