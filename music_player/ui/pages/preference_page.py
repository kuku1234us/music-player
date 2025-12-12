"""
Preferences page for the Music Player application.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSpinBox, QFormLayout, QGroupBox,
    QLineEdit, QFileDialog, QMessageBox, QDoubleSpinBox,
    QCheckBox, QProgressBar
)
from PyQt6.QtCore import Qt, QRegularExpression, QTimer, pyqtSlot
from PyQt6.QtGui import QFont, QColor, QRegularExpressionValidator
from pathlib import Path

# Import from the framework
from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.models.settings_manager import SettingsManager, SettingType
from qt_base_app.models.logger import Logger
# Import keys and defaults from settings_defs
from music_player.models.settings_defs import (
    PREF_SEEK_INTERVAL_KEY, DEFAULT_SEEK_INTERVAL,
    PREF_WORKING_DIR_KEY, DEFAULT_WORKING_DIR,
    YT_DOWNLOAD_DIR_KEY, DEFAULT_YT_DOWNLOAD_DIR,
    # Import QSettings keys for API keys
    YT_API_QSETTINGS_KEY, DEFAULT_YT_API_KEY, 
    GROQ_API_QSETTINGS_KEY, DEFAULT_GROQ_API_KEY,
    # --- NEW: Import Conversion Setting --- #
    CONVERSION_MP3_BITRATE_KEY, DEFAULT_CONVERSION_MP3_BITRATE
)

# Import yt-dlp updater settings and components
try:
    from music_player.models.yt_dlp_updater.updater import YtDlpUpdater
    from music_player.models.yt_dlp_updater.update_database_manager import YtDlpUpdateManager
    from music_player.models.yt_dlp_updater.version_manager import VersionManager
    YTDLP_UPDATER_AVAILABLE = True
except ImportError as e:
    Logger.instance().warning(caller="preference_page", msg=f"Warning: yt-dlp updater not available in preferences: {e}")
    YTDLP_UPDATER_AVAILABLE = False


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
        self.logger = Logger.instance()
        
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
        
        self.seek_interval_spinbox = QDoubleSpinBox()
        self.seek_interval_spinbox.setMinimum(0.1)
        self.seek_interval_spinbox.setMaximum(60.0)
        self.seek_interval_spinbox.setDecimals(1)
        self.seek_interval_spinbox.setSingleStep(0.5)
        self.seek_interval_spinbox.setValue(3.0)
        self.seek_interval_spinbox.valueChanged.connect(self._save_seek_interval)
        self.seek_interval_spinbox.setStyleSheet(input_style)
        
        form_layout.addRow(self.seek_interval_label, self.seek_interval_spinbox)
        
        # --- NEW: Conversion Settings --- #
        self.mp3_bitrate_label = QLabel("MP3 Bitrate (kbps):")
        self.mp3_bitrate_label.setStyleSheet(label_style)
        
        self.mp3_bitrate_spinbox = QSpinBox()
        self.mp3_bitrate_spinbox.setMinimum(32)  # Min typical MP3 bitrate
        self.mp3_bitrate_spinbox.setMaximum(320) # Max typical MP3 bitrate
        self.mp3_bitrate_spinbox.setSingleStep(16) # Steps like 64, 96, 128, 192, 256, 320
        self.mp3_bitrate_spinbox.setValue(DEFAULT_CONVERSION_MP3_BITRATE)
        self.mp3_bitrate_spinbox.valueChanged.connect(self._save_mp3_bitrate)
        self.mp3_bitrate_spinbox.setStyleSheet(input_style)
        form_layout.addRow(self.mp3_bitrate_label, self.mp3_bitrate_spinbox)
        # --- END NEW --- #
        
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

        # --- Playback Position Settings ---
        self.position_cleanup_label = QLabel("Saved Positions:")
        self.position_cleanup_label.setStyleSheet(label_style)

        self.position_cleanup_container = QWidget()
        self.position_cleanup_layout = QHBoxLayout(self.position_cleanup_container)
        self.position_cleanup_layout.setContentsMargins(0, 0, 0, 0)
        self.position_cleanup_layout.setSpacing(12)

        self.position_stats_label = QLabel("Loading...")
        self.position_stats_label.setStyleSheet(input_style + """
            border: none;
            background-color: transparent;
            padding: 4px;
        """)
        self.position_stats_label.setWordWrap(True)
        self.position_stats_label.setMinimumHeight(32)
        self.position_stats_label.setSizePolicy(
            self.position_stats_label.sizePolicy().horizontalPolicy(),
            self.position_stats_label.sizePolicy().verticalPolicy()
        )

        self.cleanup_positions_button = QPushButton("Clean Up Deleted Files")
        self.cleanup_positions_button.clicked.connect(self.cleanup_playback_positions)
        self.cleanup_positions_button.setStyleSheet(button_style)

        self.position_cleanup_layout.addWidget(self.position_stats_label, 1)
        self.position_cleanup_layout.addWidget(self.cleanup_positions_button, 0)

        form_layout.addRow(self.position_cleanup_label, self.position_cleanup_container)

        # --- Yt-dlp Update Settings ---
        if YTDLP_UPDATER_AVAILABLE:
            # Enable automatic updates
            self.ytdlp_enabled_label = QLabel("Enable yt-dlp Updates:")
            self.ytdlp_enabled_label.setStyleSheet(label_style)
            
            self.ytdlp_enabled_checkbox = QCheckBox()
            self.ytdlp_enabled_checkbox.setChecked(True)  # Default value
            self.ytdlp_enabled_checkbox.stateChanged.connect(self._save_ytdlp_enabled)
            
            form_layout.addRow(self.ytdlp_enabled_label, self.ytdlp_enabled_checkbox)
            
            # Auto-update setting
            self.ytdlp_auto_update_label = QLabel("Enable Auto-Updates:")
            self.ytdlp_auto_update_label.setStyleSheet(label_style)
            
            self.ytdlp_auto_update_checkbox = QCheckBox()
            self.ytdlp_auto_update_checkbox.setChecked(True)  # Default value
            self.ytdlp_auto_update_checkbox.stateChanged.connect(self._save_ytdlp_auto_update)
            
            form_layout.addRow(self.ytdlp_auto_update_label, self.ytdlp_auto_update_checkbox)
            
            # Check interval setting
            self.ytdlp_check_interval_label = QLabel("Check Interval (hours):")
            self.ytdlp_check_interval_label.setStyleSheet(label_style)
            
            self.ytdlp_check_interval_spinbox = QSpinBox()
            self.ytdlp_check_interval_spinbox.setMinimum(1)
            self.ytdlp_check_interval_spinbox.setMaximum(168)  # 1 week
            self.ytdlp_check_interval_spinbox.setValue(24)  # Default value
            self.ytdlp_check_interval_spinbox.valueChanged.connect(self._save_ytdlp_check_interval)
            self.ytdlp_check_interval_spinbox.setStyleSheet(input_style)
            
            form_layout.addRow(self.ytdlp_check_interval_label, self.ytdlp_check_interval_spinbox)
            
            # Installation path setting
            self.ytdlp_install_path_label = QLabel("Installation Path:")
            self.ytdlp_install_path_label.setStyleSheet(label_style)
            
            self.ytdlp_install_path_container = QWidget()
            self.ytdlp_install_path_layout = QHBoxLayout(self.ytdlp_install_path_container)
            self.ytdlp_install_path_layout.setContentsMargins(0, 0, 0, 0)
            self.ytdlp_install_path_layout.setSpacing(8)
            
            self.ytdlp_install_path_edit = QLineEdit()
            self.ytdlp_install_path_edit.setPlaceholderText("Choose yt-dlp installation path")
            self.ytdlp_install_path_edit.setText(r'C:\yt-dlp\yt-dlp.exe')  # Default value
            self.ytdlp_install_path_edit.textChanged.connect(self._save_ytdlp_install_path)
            self.ytdlp_install_path_edit.setStyleSheet(input_style)
            
            self.browse_ytdlp_install_path_button = QPushButton("Browse...")
            self.browse_ytdlp_install_path_button.setMaximumWidth(100)
            self.browse_ytdlp_install_path_button.clicked.connect(self.browse_ytdlp_install_path)
            self.browse_ytdlp_install_path_button.setStyleSheet(button_style)
            
            self.ytdlp_install_path_layout.addWidget(self.ytdlp_install_path_edit)
            self.ytdlp_install_path_layout.addWidget(self.browse_ytdlp_install_path_button)
            
            form_layout.addRow(self.ytdlp_install_path_label, self.ytdlp_install_path_container)
            
            # Current status display
            self.ytdlp_status_label = QLabel("Current Status:")
            self.ytdlp_status_label.setStyleSheet(label_style)
            
            self.ytdlp_status_container = QWidget()
            self.ytdlp_status_layout = QVBoxLayout(self.ytdlp_status_container)
            self.ytdlp_status_layout.setContentsMargins(0, 0, 0, 0)
            self.ytdlp_status_layout.setSpacing(4)
            
            self.ytdlp_version_label = QLabel("Version: Loading...")
            self.ytdlp_version_label.setStyleSheet(input_style + """
                border: none;
                background-color: transparent;
                padding: 4px;
            """)
            self.ytdlp_version_label.setWordWrap(True)
            
            self.ytdlp_last_check_label = QLabel("Last Check: Loading...")
            self.ytdlp_last_check_label.setStyleSheet(input_style + """
                border: none;
                background-color: transparent;
                padding: 4px;
            """)
            self.ytdlp_last_check_label.setWordWrap(True)
            
            self.ytdlp_check_now_button = QPushButton("Check Now")
            self.ytdlp_check_now_button.clicked.connect(self.check_ytdlp_update_now)
            self.ytdlp_check_now_button.setStyleSheet(button_style)
            
            self.ytdlp_status_layout.addWidget(self.ytdlp_version_label)
            self.ytdlp_status_layout.addWidget(self.ytdlp_last_check_label)
            self.ytdlp_status_layout.addWidget(self.ytdlp_check_now_button)
            
            form_layout.addRow(self.ytdlp_status_label, self.ytdlp_status_container)

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
        seek_interval = self.settings.get(PREF_SEEK_INTERVAL_KEY, DEFAULT_SEEK_INTERVAL, SettingType.FLOAT)
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
        
        # --- NEW: Load MP3 Bitrate --- #
        mp3_bitrate = self.settings.get(CONVERSION_MP3_BITRATE_KEY, DEFAULT_CONVERSION_MP3_BITRATE, SettingType.INT)
        self.mp3_bitrate_spinbox.setValue(mp3_bitrate)
        # --- END NEW --- #
        
        # Load yt-dlp update settings
        if YTDLP_UPDATER_AVAILABLE:
            try:
                db_manager = YtDlpUpdateManager.instance()
                ytdlp_settings = db_manager.get_settings()
                
                self.ytdlp_enabled_checkbox.setChecked(ytdlp_settings.get('enabled', True))
                self.ytdlp_auto_update_checkbox.setChecked(ytdlp_settings.get('auto_update', True))
                self.ytdlp_check_interval_spinbox.setValue(ytdlp_settings.get('check_interval_hours', 24))
                self.ytdlp_install_path_edit.setText(ytdlp_settings.get('install_path', r'C:\yt-dlp\yt-dlp.exe'))
                
                # Update yt-dlp status display
                self.update_ytdlp_status()
            except Exception as e:
                self.logger.error("PreferencePage", f"Error loading yt-dlp settings: {e}")
        
        # Update position database stats
        self.update_position_stats()
        
    def _save_seek_interval(self):
        """Save the seek interval setting."""
        seek_interval = self.seek_interval_spinbox.value()
        self.settings.set(PREF_SEEK_INTERVAL_KEY, seek_interval, SettingType.FLOAT)
        self.settings.sync() # Sync immediately after changing this setting
        
    def _save_yt_api_key(self):
        """Save the YouTube API key setting."""
        api_key = self.yt_api_key_edit.text()
        self.settings.set(YT_API_QSETTINGS_KEY, api_key, SettingType.STRING)
        self.settings.sync()
        
    def _save_groq_api_key(self):
        """Save the Groq API key setting."""
        api_key = self.groq_api_key_edit.text()
        self.settings.set(GROQ_API_QSETTINGS_KEY, api_key, SettingType.STRING)
        self.settings.sync()
        
    # --- NEW: Save MP3 Bitrate --- #    
    def _save_mp3_bitrate(self):
        """Save the MP3 bitrate setting."""
        bitrate = self.mp3_bitrate_spinbox.value()
        self.settings.set(CONVERSION_MP3_BITRATE_KEY, bitrate, SettingType.INT)
        self.settings.sync()
    # --- END NEW --- #
        
    def reset_settings(self):
        """Reset settings to default values."""
        # Reset UI fields
        self.seek_interval_spinbox.setValue(DEFAULT_SEEK_INTERVAL)
        self.working_dir_edit.setText(str(DEFAULT_WORKING_DIR))
        self.download_dir_edit.setText(str(DEFAULT_YT_DOWNLOAD_DIR))
        self.yt_api_key_edit.setText(DEFAULT_YT_API_KEY)
        self.groq_api_key_edit.setText(DEFAULT_GROQ_API_KEY)
        # --- NEW: Reset MP3 Bitrate UI --- #
        self.mp3_bitrate_spinbox.setValue(DEFAULT_CONVERSION_MP3_BITRATE)
        # --- END NEW --- #
        
        # Reset yt-dlp update settings UI
        if YTDLP_UPDATER_AVAILABLE:
            self.ytdlp_enabled_checkbox.setChecked(True)
            self.ytdlp_auto_update_checkbox.setChecked(True)
            self.ytdlp_check_interval_spinbox.setValue(24)
            self.ytdlp_install_path_edit.setText(r'C:\yt-dlp\yt-dlp.exe')
        
        # Set QSettings back to defaults
        self.settings.set(PREF_SEEK_INTERVAL_KEY, DEFAULT_SEEK_INTERVAL, SettingType.FLOAT)
        self.settings.set(PREF_WORKING_DIR_KEY, DEFAULT_WORKING_DIR, SettingType.PATH)
        self.settings.set(YT_DOWNLOAD_DIR_KEY, DEFAULT_YT_DOWNLOAD_DIR, SettingType.PATH)
        self.settings.set(YT_API_QSETTINGS_KEY, DEFAULT_YT_API_KEY, SettingType.STRING)
        self.settings.set(GROQ_API_QSETTINGS_KEY, DEFAULT_GROQ_API_KEY, SettingType.STRING)
        # --- NEW: Reset MP3 Bitrate in QSettings --- #
        self.settings.set(CONVERSION_MP3_BITRATE_KEY, DEFAULT_CONVERSION_MP3_BITRATE, SettingType.INT)
        # --- END NEW --- #
        
        # Reset yt-dlp database settings
        if YTDLP_UPDATER_AVAILABLE:
            try:
                db_manager = YtDlpUpdateManager.instance()
                db_manager.reset_settings_to_defaults()
            except Exception as e:
                self.logger.error("PreferencePage", f"Error resetting yt-dlp settings: {e}")
        
        self.settings.sync()
        self.logger.info("PreferencePage", "Settings reset to defaults")
        
        # Update status displays
        self.update_position_stats()
        if YTDLP_UPDATER_AVAILABLE:
            self.update_ytdlp_status()
        
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

    def cleanup_playback_positions(self):
        """Clean up playback positions for deleted files"""
        from music_player.models.position_manager import PlaybackPositionManager

        try:
            position_manager = PlaybackPositionManager.instance()
            removed_count = position_manager.cleanup_deleted_files()

            QMessageBox.information(
                self,
                "Cleanup Complete",
                f"Removed {removed_count} position entries for deleted files."
            )

            # Refresh stats display
            self.update_position_stats()
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Cleanup Error", 
                f"Failed to clean up position database: {str(e)}"
            )

    def update_position_stats(self):
        """Update the display of position database statistics"""
        try:
            from music_player.models.position_manager import PlaybackPositionManager

            position_manager = PlaybackPositionManager.instance()
            stats = position_manager.get_database_stats()

            # Format the stats for display
            total_files = stats.get('total_files', 0)
            total_hours = stats.get('total_hours', 0.0)
            total_duration_hours = stats.get('total_duration_hours', 0.0)
            db_size_mb = stats.get('database_size_mb', 0.0)
            
            if total_files == 0:
                stats_text = "No saved positions"
            else:
                # Create a compact single-line stats display for horizontal layout
                stats_parts = [f"{total_files} files", f"{total_hours:.1f}h saved"]
                
                if total_duration_hours > 0:
                    completion_percentage = (total_hours / total_duration_hours) * 100
                    stats_parts.append(f"{completion_percentage:.1f}% avg")
                
                if db_size_mb > 0.1:
                    stats_parts.append(f"{db_size_mb:.1f} MB")
                
                stats_text = " • ".join(stats_parts)

            self.position_stats_label.setText(stats_text)
            
        except Exception as e:
            self.position_stats_label.setText(f"Error loading stats: {str(e)}")

    # --- Yt-dlp Update Methods ---
    
    def _save_ytdlp_enabled(self):
        """Save the yt-dlp updates enabled setting."""
        if not YTDLP_UPDATER_AVAILABLE:
            return
        enabled = self.ytdlp_enabled_checkbox.isChecked()
        try:
            db_manager = YtDlpUpdateManager.instance()
            db_manager.update_setting('enabled', enabled)
            self.logger.info("PreferencePage", f"yt-dlp updates enabled: {enabled}")
        except Exception as e:
            self.logger.error("PreferencePage", f"Error saving yt-dlp enabled setting: {e}")

    def _save_ytdlp_auto_update(self):
        """Save the yt-dlp auto-update setting."""
        if not YTDLP_UPDATER_AVAILABLE:
            return
        auto_update = self.ytdlp_auto_update_checkbox.isChecked()
        try:
            db_manager = YtDlpUpdateManager.instance()
            db_manager.update_setting('auto_update', auto_update)
            self.logger.info("PreferencePage", f"yt-dlp auto-update: {auto_update}")
        except Exception as e:
            self.logger.error("PreferencePage", f"Error saving yt-dlp auto-update setting: {e}")

    def _save_ytdlp_check_interval(self):
        """Save the yt-dlp check interval setting."""
        if not YTDLP_UPDATER_AVAILABLE:
            return
        interval = self.ytdlp_check_interval_spinbox.value()
        try:
            db_manager = YtDlpUpdateManager.instance()
            db_manager.update_setting('check_interval_hours', interval)
            self.logger.info("PreferencePage", f"yt-dlp check interval: {interval} hours")
        except Exception as e:
            self.logger.error("PreferencePage", f"Error saving yt-dlp check interval setting: {e}")

    def _save_ytdlp_install_path(self):
        """Save the yt-dlp installation path setting."""
        if not YTDLP_UPDATER_AVAILABLE:
            return
        path = self.ytdlp_install_path_edit.text()
        try:
            db_manager = YtDlpUpdateManager.instance()
            db_manager.update_setting('install_path', path)
            self.logger.info("PreferencePage", f"yt-dlp install path: {path}")
        except Exception as e:
            self.logger.error("PreferencePage", f"Error saving yt-dlp install path setting: {e}")

    def browse_ytdlp_install_path(self):
        """Browse for yt-dlp installation path."""
        if not YTDLP_UPDATER_AVAILABLE:
            return
        
        current_path = self.ytdlp_install_path_edit.text()
        if current_path:
            initial_dir = str(Path(current_path).parent)
        else:
            initial_dir = str(Path.home())
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Choose yt-dlp installation location",
            initial_dir + "/yt-dlp.exe",
            "Executable Files (*.exe);;All Files (*)"
        )
        
        if file_path:
            self.ytdlp_install_path_edit.setText(file_path)

    def check_ytdlp_update_now(self):
        """Manually trigger yt-dlp update check."""
        if not YTDLP_UPDATER_AVAILABLE:
            QMessageBox.warning(self, "Update Check", "yt-dlp updater is not available.")
            return
        
        # Disable the button during update check
        self.ytdlp_check_now_button.setEnabled(False)
        self.ytdlp_check_now_button.setText("Checking...")
        
        try:
            updater = YtDlpUpdater.instance()
            result = updater.check_and_update_async(force_check=True)
            
            if result.success:
                if result.updated:
                    QMessageBox.information(
                        self, 
                        "Update Complete", 
                        f"yt-dlp has been updated to {result.latest_version}"
                    )
                else:
                    QMessageBox.information(
                        self, 
                        "No Update Needed", 
                        f"yt-dlp is already up to date: {result.current_version}"
                    )
            else:
                QMessageBox.warning(
                    self, 
                    "Update Failed", 
                    f"Failed to check for updates: {result.error_message}"
                )
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Update Error", 
                f"An error occurred during update check: {str(e)}"
            )
        finally:
            # Re-enable the button and update status
            self.ytdlp_check_now_button.setEnabled(True)
            self.ytdlp_check_now_button.setText("Check Now")
            self.update_ytdlp_status()

    def update_ytdlp_status(self):
        """Update the yt-dlp status display."""
        if not YTDLP_UPDATER_AVAILABLE:
            return
        
        try:
            updater = YtDlpUpdater.instance()
            status = updater.get_update_status()
            
            # Format current version
            current_version = status.get('current_version', 'Unknown')
            if current_version == 'unknown':
                if status.get('file_exists', False):
                    current_version = "Installed (version unknown)"
                else:
                    current_version = "Not installed"
            
            self.ytdlp_version_label.setText(f"Version: {current_version}")
            
            # Format last check time
            last_check = status.get('last_check_time')
            if last_check:
                if isinstance(last_check, str):
                    from datetime import datetime
                    try:
                        last_check_dt = datetime.fromisoformat(last_check)
                        time_diff = datetime.now() - last_check_dt
                        if time_diff.days > 0:
                            last_check_text = f"{time_diff.days} days ago"
                        elif time_diff.seconds > 3600:
                            hours = time_diff.seconds // 3600
                            last_check_text = f"{hours} hours ago"
                        else:
                            minutes = time_diff.seconds // 60
                            last_check_text = f"{minutes} minutes ago"
                    except ValueError:
                        last_check_text = "Recently"
                else:
                    last_check_text = "Recently"
            else:
                last_check_text = "Never"
            
            self.ytdlp_last_check_label.setText(f"Last Check: {last_check_text}")
            
            # Show error if there was one
            if status.get('last_error'):
                self.ytdlp_last_check_label.setText(
                    f"Last Check: {last_check_text} (Error: {status['last_error']})"
                )
                
        except Exception as e:
            self.ytdlp_version_label.setText(f"Version: Error loading status")
            self.ytdlp_last_check_label.setText(f"Last Check: Error ({str(e)})")
            self.logger.error("PreferencePage", f"Error updating yt-dlp status: {e}")