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
        
    def reset_settings(self):
        """Reset settings to default values and save them immediately."""
        # Reset general settings
        default_seek = 3
        self.seek_interval_spinbox.setValue(default_seek)
        self.settings.set('preferences/seek_interval', default_seek, SettingType.INT)

        default_working_dir = Path.home()
        self.working_dir_edit.setText(str(default_working_dir))
        self.settings.set('preferences/working_dir', default_working_dir, SettingType.PATH)
        
        # Reset OPlayer settings DIRECTLY in SettingsManager
        # Need to import OPlayerService just for defaults, or define defaults elsewhere
        # Temporary workaround: Define defaults locally (better: centralize defaults)
        DEFAULT_HOST = "192.168.0.107" # Assuming this was the default
        DEFAULT_PORT = 2121           # Assuming this was the default
        self.settings.set('oplayer/ftp_host', DEFAULT_HOST, SettingType.STRING)
        self.settings.set('oplayer/ftp_port', DEFAULT_PORT, SettingType.INT)
        
        # Sync all changes made during reset
        self.settings.sync()
        
    def showEvent(self, event):
        """Reload settings when the page becomes visible"""
        super().showEvent(event)
        # Reload settings to ensure we display the most current values
        self.load_settings()
        
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