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
        self.seek_interval_spinbox.valueChanged.connect(self._save_seek_interval)
        self.seek_interval_spinbox.setStyleSheet(input_style)
        
        form_layout.addRow(self.seek_interval_label, self.seek_interval_spinbox)
        
        # --- Library Settings ---
        
        # Working directory setting
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
        
        working_dir = self.settings.get('preferences/working_dir', str(Path.home()), SettingType.PATH)
        self.working_dir_edit.setText(str(working_dir))
        
        # Load OPlayer settings
        ftp_host = self.settings.get('oplayer/ftp_host', OPlayerService.DEFAULT_HOST, SettingType.STRING)
        self.ftp_host_edit.setText(ftp_host)
        
        ftp_port = self.settings.get('oplayer/ftp_port', OPlayerService.DEFAULT_PORT, SettingType.INT)
        self.ftp_port_spinbox.setValue(ftp_port)
        
    def _save_seek_interval(self):
        """Save only the seek interval setting."""
        seek_interval = self.seek_interval_spinbox.value()
        self.settings.set('preferences/seek_interval', seek_interval, SettingType.INT)
        self.settings.sync() # Sync immediately after changing this setting
        
    def save_settings(self):
        """Save settings to SettingsManager - DEPRECATED/REMOVED: Use specific save methods."""
        # This method is no longer connected or used for general saving.
        # Specific controls save their own settings.
        # Kept temporarily to avoid breaking reset_settings logic, will refactor reset.
        pass # Do nothing here anymore
        
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
        """Reset settings to default values and save them immediately."""
        # Reset general settings
        default_seek = 3
        self.seek_interval_spinbox.setValue(default_seek)
        self.settings.set('preferences/seek_interval', default_seek, SettingType.INT)

        default_working_dir = Path.home()
        self.working_dir_edit.setText(str(default_working_dir))
        self.settings.set('preferences/working_dir', default_working_dir, SettingType.PATH)
        
        # Reset OPlayer settings
        default_host = OPlayerService.DEFAULT_HOST
        default_port = OPlayerService.DEFAULT_PORT
        self.ftp_host_edit.setText(default_host)
        self.ftp_port_spinbox.setValue(default_port)
        # Use the service method which also calls settings.set and sync
        self.oplayer_service.update_connection_settings(host=default_host, port=default_port)
        
        # Sync all changes made during reset (oplayer syncs itself)
        self.settings.sync()
        
    def browse_working_dir(self):
        """Open directory browser dialog to select working directory"""
        current_dir = self.settings.get('preferences/working_dir', str(Path.home()), SettingType.PATH)
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
                self.settings.set('preferences/working_dir', path_obj, SettingType.PATH)
                self.settings.sync() # Persist changes immediately
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Save Error",
                    f"Failed to save working directory setting: {str(e)}"
                ) 