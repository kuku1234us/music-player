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

# Import OPlayer service
from music_player.services.oplayer_service import OPlayerService


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
        
        # Initialize OPlayer service for settings
        self.oplayer_service = OPlayerService()
        
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
        self.seek_interval_spinbox.valueChanged.connect(self.save_settings)
        self.seek_interval_spinbox.setStyleSheet(input_style)
        
        form_layout.addRow(self.seek_interval_label, self.seek_interval_spinbox)
        
        # --- Library Settings ---
        
        # Playlists directory setting
        self.playlists_dir_label = QLabel("Playlists directory:")
        self.playlists_dir_label.setStyleSheet(label_style)
        
        self.playlists_dir_container = QWidget()
        self.playlists_dir_layout = QHBoxLayout(self.playlists_dir_container)
        self.playlists_dir_layout.setContentsMargins(0, 0, 0, 0)
        self.playlists_dir_layout.setSpacing(8)
        
        self.playlists_dir_edit = QLineEdit()
        self.playlists_dir_edit.setPlaceholderText("Choose playlists directory")
        self.playlists_dir_edit.setReadOnly(True)
        self.playlists_dir_edit.setStyleSheet(input_style)
        
        self.browse_button = QPushButton("Browse...")
        self.browse_button.setMaximumWidth(100)
        self.browse_button.clicked.connect(self.browse_playlists_dir)
        self.browse_button.setStyleSheet(button_style)
        
        self.playlists_dir_layout.addWidget(self.playlists_dir_edit)
        self.playlists_dir_layout.addWidget(self.browse_button)
        
        form_layout.addRow(self.playlists_dir_label, self.playlists_dir_container)
        
        # --- OPlayer Settings ---
        
        # FTP Host setting with port on the same line
        self.ftp_host_label = QLabel("FTP Server Address:")
        self.ftp_host_label.setStyleSheet(label_style)
        
        # Container for host and port on the same line
        self.ftp_connection_container = QWidget()
        self.ftp_connection_layout = QHBoxLayout(self.ftp_connection_container)
        self.ftp_connection_layout.setContentsMargins(0, 0, 0, 0)
        self.ftp_connection_layout.setSpacing(8)
        
        # FTP host input
        self.ftp_host_edit = QLineEdit()
        self.ftp_host_edit.setPlaceholderText("Enter OPlayer IP address (e.g., 192.168.0.107)")
        # IP address validation: Allow standard IPv4 addresses
        ip_regex = QRegularExpression(
            "^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$"
        )
        ip_validator = QRegularExpressionValidator(ip_regex)
        self.ftp_host_edit.setValidator(ip_validator)
        self.ftp_host_edit.editingFinished.connect(self.save_oplayer_settings)
        self.ftp_host_edit.setStyleSheet(input_style)
        
        # Port colon label
        port_colon = QLabel(":")
        port_colon.setStyleSheet(label_style)
        
        # FTP port input
        self.ftp_port_spinbox = QSpinBox()
        self.ftp_port_spinbox.setMinimum(1)
        self.ftp_port_spinbox.setMaximum(65535)
        self.ftp_port_spinbox.setValue(2121)  # Default value
        self.ftp_port_spinbox.valueChanged.connect(self.save_oplayer_settings)
        self.ftp_port_spinbox.setStyleSheet(input_style)
        self.ftp_port_spinbox.setFixedWidth(80)  # Make the port input smaller
        
        # Add components to the layout
        self.ftp_connection_layout.addWidget(self.ftp_host_edit, 1)  # IP gets more space
        self.ftp_connection_layout.addWidget(port_colon)
        self.ftp_connection_layout.addWidget(self.ftp_port_spinbox, 0)  # Port gets less space
        
        # Add to form layout
        form_layout.addRow(self.ftp_host_label, self.ftp_connection_container)
        
        # Add form layout to main layout
        self.main_layout.addLayout(form_layout)
        
        # --- Reset button ---
        
        # Add some space before the reset button
        self.main_layout.addSpacing(20)
        
        # Reset button container
        reset_container = QWidget()
        reset_layout = QHBoxLayout(reset_container)
        reset_layout.setContentsMargins(0, 0, 0, 0)
        reset_layout.setSpacing(16)
        
        self.reset_button = QPushButton("Reset to Defaults")
        self.reset_button.clicked.connect(self.reset_settings)
        self.reset_button.setStyleSheet(button_style)
        
        reset_layout.addWidget(self.reset_button)
        reset_layout.addStretch(1)
        
        self.main_layout.addWidget(reset_container)
        
        # Add a stretch at the end to push all content to the top
        self.main_layout.addStretch(1)
        
    def load_settings(self):
        """Load settings from SettingsManager"""
        # Load general settings
        seek_interval = self.settings.get('preferences/seek_interval', 3, SettingType.INT)
        self.seek_interval_spinbox.setValue(seek_interval)
        
        playlists_dir = self.settings.get('preferences/playlists_dir', str(Path.home()), SettingType.PATH)
        self.playlists_dir_edit.setText(str(playlists_dir))
        
        # Load OPlayer settings
        ftp_host = self.settings.get('oplayer/ftp_host', OPlayerService.DEFAULT_HOST, SettingType.STRING)
        self.ftp_host_edit.setText(ftp_host)
        
        ftp_port = self.settings.get('oplayer/ftp_port', OPlayerService.DEFAULT_PORT, SettingType.INT)
        self.ftp_port_spinbox.setValue(ftp_port)
        
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
        
    def save_oplayer_settings(self):
        """Save OPlayer connection settings when focus leaves the fields"""
        host = self.ftp_host_edit.text().strip()
        port = self.ftp_port_spinbox.value()
        
        if host:
            # Use the OPlayerService to update the connection settings
            # This will also save them to the SettingsManager
            self.oplayer_service.update_connection_settings(host=host, port=port)
            print(f"[PreferencePage] Updated OPlayer FTP settings: {host}:{port}")
        
    def test_oplayer_connection(self):
        """Test the connection to the OPlayer device using current settings"""
        # First, save any pending changes
        self.save_oplayer_settings()
        
        # Now test the connection
        if self.oplayer_service.test_connection():
            QMessageBox.information(
                self,
                "Connection Successful",
                f"Successfully connected to OPlayer FTP server at {self.ftp_host_edit.text()}:{self.ftp_port_spinbox.value()}"
            )
        else:
            QMessageBox.critical(
                self,
                "Connection Failed",
                f"Could not connect to OPlayer FTP server at {self.ftp_host_edit.text()}:{self.ftp_port_spinbox.value()}.\n\nPlease check:\n- OPlayer device is powered on\n- Your device is connected to the same network\n- The IP address and port are correct"
            )
        
    def reset_settings(self):
        """Reset settings to default values"""
        # Reset general settings
        self.seek_interval_spinbox.setValue(3)  # Default seek interval
        self.playlists_dir_edit.setText(str(Path.home()))  # Default playlists directory
        
        # Reset OPlayer settings
        self.ftp_host_edit.setText(OPlayerService.DEFAULT_HOST)
        self.ftp_port_spinbox.setValue(OPlayerService.DEFAULT_PORT)
        
        # Save all settings
        self.save_settings()
        self.save_oplayer_settings()
        
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