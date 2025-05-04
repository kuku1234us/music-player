"""
Page for browsing local file system directories.
"""
import os
import shutil # Add shutil for directory removal
import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFileDialog, QLabel,
    QSizePolicy, QMessageBox, QHBoxLayout, QLineEdit, QSpinBox, QPushButton
)
from PyQt6.QtCore import Qt, QSize, pyqtSlot, QTimer, pyqtSignal, QSortFilterProxyModel, QRegularExpression
from PyQt6.QtGui import QIcon, QRegularExpressionValidator
import qtawesome as qta

# Import from framework and components
from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.models.settings_manager import SettingsManager, SettingType
from music_player.ui.components.round_button import RoundButton
# Import OPlayer service and overlay
from music_player.services.oplayer_service import OPlayerService
from music_player.ui.components.upload_status_overlay import UploadStatusOverlay
from music_player.ui.components.base_table import BaseTableModel, ColumnDefinition
from music_player.ui.components.browser_components.browser_table import BrowserTableView

# --- Helper functions for formatting ---
def format_file_size(size_bytes):
    if size_bytes == -1:
        return "<DIR>"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024*1024:
        return f"{size_bytes/1024:.1f} KB"
    if size_bytes < 1024*1024*1024:
        return f"{size_bytes/(1024*1024):.1f} MB"
    return f"{size_bytes/(1024*1024*1024):.1f} GB"

def format_modified_time(mod_time):
    if not mod_time:
        return "Unknown"
    try:
        dt = datetime.datetime.fromtimestamp(mod_time)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "Invalid Date"

# --- Column Definitions for Browser Table ---
browser_col_defs = [
    ColumnDefinition(
        header="Filename", data_key='filename', sort_key=lambda d: d.get('filename', '').lower(),
        width=350, tooltip_key='path', stretch=1
    ),
    ColumnDefinition(
        header="Size", data_key='size_bytes', display_formatter=format_file_size,
        sort_key='size_bytes', width=100,
        alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        sort_role=Qt.ItemDataRole.EditRole
    ),
    ColumnDefinition(
        header="Modified", data_key='mod_stamp', display_formatter=format_modified_time,
        sort_key='mod_stamp', width=150,
        sort_role=Qt.ItemDataRole.EditRole
    ),
]

class BrowserPage(QWidget):
    """
    Page that allows browsing a selected directory and viewing its contents.
    """
    # Signal to request playing a single file
    play_single_file_requested = pyqtSignal(str) # Emits filepath
    
    # Define a custom role for storing the is_dir flag
    IS_DIR_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("browserPage")
        self.setProperty('page_id', 'browser')
        self.theme = ThemeManager.instance()
        self.settings = SettingsManager.instance()

        # Enable background styling
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Column indices
        self.COL_FILENAME = 0
        self.COL_SIZE = 1
        self.COL_MODIFIED = 2

        # Sorting state
        self.sort_column = self.COL_FILENAME
        self.sort_order = Qt.SortOrder.AscendingOrder
        
        # Sort indicator icons
        self.sort_up_icon = qta.icon('fa5s.sort-up', color=self.theme.get_color('text', 'secondary'))
        self.sort_down_icon = qta.icon('fa5s.sort-down', color=self.theme.get_color('text', 'secondary'))

        self._current_directory = None
        
        # OPlayer Service and Upload State
        self.oplayer_service = OPlayerService(self)
        self._files_to_upload = []
        self._current_upload_index = 0
        self._total_files_to_upload = 0

        # Timer for temporary messages
        self.temp_message_timer = QTimer(self)
        self.temp_message_timer.setSingleShot(True)
        self.temp_message_timer.setInterval(2000) # 2 seconds

        self._setup_ui()
        self._connect_signals()
        self._update_empty_message() # Show initial message

    def _setup_ui(self):
        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(16)

        # --- START: OPlayer Settings Row --- 
        self.oplayer_settings_container = QWidget()
        self.oplayer_settings_layout = QHBoxLayout(self.oplayer_settings_container)
        self.oplayer_settings_layout.setContentsMargins(0, 0, 0, 0) # No extra margins
        self.oplayer_settings_layout.setSpacing(8)

        # Style for input fields in this row
        input_style = f"""
            background-color: {self.theme.get_color('background', 'secondary')};
            color: {self.theme.get_color('text', 'primary')};
            border: 1px solid {self.theme.get_color('border', 'primary')};
            border-radius: 4px;
            padding: 4px 6px; 
            font-size: 9pt; 
        """
        # Style for the button
        button_style = f"""
            background-color: {self.theme.get_color('background', 'tertiary')};
            color: {self.theme.get_color('text', 'primary')};
            border-radius: 4px;
            padding: 5px 10px; 
            font-size: 9pt;
            font-weight: bold;
        """

        # Host Label and Input
        self.ftp_host_label = QLabel("OPlayer FTP:")
        self.ftp_host_label.setStyleSheet(f"color: {self.theme.get_color('text', 'secondary')}; font-size: 9pt;")
        self.ftp_host_edit = QLineEdit()
        self.ftp_host_edit.setPlaceholderText("IP Address")
        ip_regex = QRegularExpression(
            "^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$"
        )
        ip_validator = QRegularExpressionValidator(ip_regex)
        self.ftp_host_edit.setValidator(ip_validator)
        self.ftp_host_edit.setStyleSheet(input_style)
        self.ftp_host_edit.setMinimumWidth(120)

        # Port Label and Input
        self.ftp_port_label = QLabel(":")
        self.ftp_port_label.setStyleSheet(f"color: {self.theme.get_color('text', 'secondary')}; font-size: 9pt;")
        self.ftp_port_spinbox = QSpinBox()
        self.ftp_port_spinbox.setMinimum(1)
        self.ftp_port_spinbox.setMaximum(65535)
        self.ftp_port_spinbox.setValue(OPlayerService.DEFAULT_PORT) # Use default from service
        self.ftp_port_spinbox.setStyleSheet(input_style)
        self.ftp_port_spinbox.setFixedWidth(70)

        # Add to layout
        self.oplayer_settings_layout.addWidget(self.ftp_host_label)
        self.oplayer_settings_layout.addWidget(self.ftp_host_edit, 1) # Host gets stretch
        self.oplayer_settings_layout.addWidget(self.ftp_port_label)
        self.oplayer_settings_layout.addWidget(self.ftp_port_spinbox)
        self.oplayer_settings_layout.addStretch(0) # Push elements together

        # Add the settings row to the main layout
        self.main_layout.addWidget(self.oplayer_settings_container)
        # --- END: OPlayer Settings Row --- 

        # --- Browser Table ---
        self.file_table = BrowserTableView(table_name="browser_file_table", parent=self)
        self.file_table.setObjectName("browserFileTable")
        self.file_table.hide()  # Hide until data is loaded
        self.main_layout.addWidget(self.file_table, 1)

        # --- Empty Message Label ---
        self.empty_label = QLabel("Select a folder to browse its contents.")
        self.empty_label.setObjectName("browserEmptyLabel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {self.theme.get_color('text', 'secondary')}; font-style: italic;")
        self.empty_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.empty_label.hide()
        self.main_layout.addWidget(self.empty_label, 1)

        # --- Temporary Message Label ---
        self.temp_message_label = QLabel(self)
        self.temp_message_label.setObjectName("tempMessageLabel")
        self.temp_message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.temp_message_label.setStyleSheet(f"""
            QLabel#tempMessageLabel {{
                background-color: rgba(0, 0, 0, 0.7);
                color: white;
                padding: 8px 15px;
                border-radius: 5px;
                font-size: 9pt;
            }}
        """)
        self.temp_message_label.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.temp_message_label.adjustSize()
        self.temp_message_label.hide()

        # --- Overlay Buttons ---
        self.browse_button = RoundButton(
            parent=self,
            icon_name="fa5s.folder-open",
            text="📂",
            diameter=48,
            icon_size=24,
            bg_opacity=0.5
        )
        self.browse_button.setToolTip("Select Folder to Browse")

        self.oplayer_button = RoundButton(
            parent=self,
            text="OP",
            diameter=48,
            bg_opacity=0.5
        )
        self.oplayer_button.setToolTip("Upload Selected Files to OPlayer")

        self.refresh_button = RoundButton(
            parent=self,
            icon_name="fa5s.sync-alt",
            diameter=48,
            icon_size=20,
            bg_opacity=0.5
        )
        self.refresh_button.setToolTip("Refresh Folder View")

        self.upload_status = UploadStatusOverlay(self)

    def _connect_signals(self):
        self.browse_button.clicked.connect(self._browse_folder)
        self.file_table.fileDoubleClicked.connect(self._on_file_double_clicked)
        self.file_table.directoryDoubleClicked.connect(self._on_directory_double_clicked)
        self.file_table.itemsDeletedFromDisk.connect(self._on_items_deleted_from_disk)
        self.oplayer_button.clicked.connect(self._on_oplayer_upload_selected_clicked)
        self.refresh_button.clicked.connect(self._refresh_view)
        self.oplayer_service.upload_started.connect(self._on_upload_started)
        self.oplayer_service.upload_progress.connect(self._on_upload_progress)
        self.oplayer_service.upload_completed.connect(self._on_upload_completed)
        self.oplayer_service.upload_failed.connect(self._on_upload_failed)
        self.temp_message_timer.timeout.connect(self.temp_message_label.hide)
        self.ftp_host_edit.editingFinished.connect(self._handle_oplayer_setting_changed)
        self.ftp_port_spinbox.valueChanged.connect(self._handle_oplayer_setting_changed)

    def _browse_folder(self):
        """Opens a directory dialog and populates the table."""
        last_dir = self.settings.get('browser/last_browse_dir', str(Path.home()), SettingType.PATH)
        
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Folder to Browse",
            str(last_dir),
            QFileDialog.Option.ShowDirsOnly
        )
        
        if directory:
            self._current_directory = Path(directory)
            self.settings.set('browser/last_browse_dir', directory, SettingType.PATH)
            self.settings.sync()
            self._populate_table(self._current_directory)
        else:
             # User cancelled - keep existing view or message
             self._update_empty_message() # Ensure message reflects state

    def _refresh_view(self):
        """Refreshes the table view for the current directory."""
        if self._current_directory and self._current_directory.is_dir():
            print(f"[BrowserPage] Refreshing view for: {self._current_directory}")
            self._populate_table(self._current_directory)
        else:
            print("[BrowserPage] Cannot refresh: No valid directory selected.")
            # Optionally show a message if needed

    def _populate_table(self, directory_path: Path):
        """Clears and fills the table with contents of the directory."""
        # self.file_table.setRowCount(0) # Clear existing rows <-- Removed: Not needed/valid for QTableView+Model

        files_data = []
        try:
            for item_path in directory_path.iterdir(): # Iterate through items directly
                try:
                    # Get stats - skip if error (e.g., permissions, broken link)
                    stats = item_path.stat()
                    is_dir = item_path.is_dir()
                    filename = item_path.name
                    filesize_bytes = stats.st_size if not is_dir else -1 # Size -1 for dirs
                    filesize_str = format_file_size(filesize_bytes) if not is_dir else "<DIR>"
                    mod_time_stamp = stats.st_mtime
                    mod_time_str = format_modified_time(mod_time_stamp)
                    
                    # Add data for sorting/display
                    files_data.append({
                        'path': str(item_path),
                        'filename': filename,
                        'size_bytes': filesize_bytes,
                        'size_str': filesize_str,
                        'mod_stamp': mod_time_stamp,
                        'mod_str': mod_time_str,
                        'is_dir': is_dir
                    })
                except Exception as e:
                    print(f"[BrowserPage] Error accessing item {item_path}: {e}")
                    continue # Skip this item
                    
        except Exception as e:
            print(f"[BrowserPage] Error listing directory {directory_path}: {e}")
            self.empty_label.setText(f"Error accessing directory: {directory_path.name}")
            self.file_table.hide()
            self.empty_label.show()
            return

        if not files_data:
            self._update_empty_message(is_empty=True)
            return
        
        # We have files, show table and hide message
        self.empty_label.hide()
        self.file_table.show() # Show the table directly
        
        # Set up model and proxy
        self.model = BaseTableModel(source_objects=files_data, column_definitions=browser_col_defs)
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.file_table.setModel(self.proxy_model)

        self.file_table.resizeRowsToContents()

    def _update_empty_message(self, is_empty: bool = False):
        """Shows or hides the empty message based on directory state."""
        if self._current_directory and is_empty:
            self.empty_label.setText(f"Directory is empty: {self._current_directory.name}")
            self.file_table.hide()
            self.empty_label.show()
        elif not self._current_directory:
            self.empty_label.setText("Select a folder to browse its contents.")
            self.file_table.hide()
            self.empty_label.show()
        else:
            # We have a directory and it's not empty (or not checked yet)
            self.empty_label.hide()
            self.file_table.show() # Show the table directly

    def _on_file_double_clicked(self, filepath):
        if filepath and os.path.isfile(filepath):
            self.play_single_file_requested.emit(filepath)

    def _on_directory_double_clicked(self, dirpath):
        if dirpath and os.path.isdir(dirpath):
            self._current_directory = Path(dirpath)
            self._populate_table(self._current_directory)

    def _on_items_deleted_from_disk(self, deleted_count, error_messages):
        if deleted_count > 0:
            message = f"Deleted {deleted_count} item(s)."
            if error_messages:
                message += f"\n({len(error_messages)} errors occurred)"
            self._show_temporary_message(message)
        elif error_messages:
            message = f"Failed to delete selected items.\n{error_messages[0]}"
            if len(error_messages) > 1:
                message += " (and others)"
            self._show_temporary_message(message, is_error=True)

    def _on_oplayer_upload_selected_clicked(self):
        """Handles click on the OPlayer upload button for selected files."""
        selected_objects = self.file_table.get_selected_items_data()
        self._files_to_upload = []
        
        if not selected_objects:
            QMessageBox.warning(self, "No Selection", "Please select one or more files to upload.")
            return

        # Get paths of selected *files* only
        for obj in selected_objects:
            path = obj.get('path')
            is_dir = obj.get('is_dir', False)
            if path and not is_dir and os.path.exists(path):
                if path not in self._files_to_upload: # Avoid duplicates from multi-column selection
                    self._files_to_upload.append(path)
        
        if not self._files_to_upload:
            QMessageBox.warning(self, "No Files Selected", "The current selection contains only directories or invalid files.")
            return

        # Test connection first
        print("[BrowserPage] Testing connection to OPlayer device...")
        if not self.oplayer_service.test_connection():
            error_msg = "Could not connect to OPlayer device. Check connection and device status."
            print(f"[BrowserPage] Error: {error_msg}")
            QMessageBox.critical(self, "Connection Error", error_msg)
            return

        # Reset state and start the first upload
        self._current_upload_index = 0
        self._total_files_to_upload = len(self._files_to_upload)
        print(f"[BrowserPage] Starting upload of {self._total_files_to_upload} files.")
        self._start_next_upload()
        
    def _start_next_upload(self):
        """Initiates the upload for the next file in the queue."""
        if self._current_upload_index < self._total_files_to_upload:
            file_path = self._files_to_upload[self._current_upload_index]
            print(f"[BrowserPage] Uploading file {self._current_upload_index + 1}/{self._total_files_to_upload}: {file_path}")
            # Start the upload via the service
            if not self.oplayer_service.upload_file(file_path):
                 # Handle immediate failure from service (e.g., file vanished)
                 self._on_upload_failed(f"Could not start upload for {os.path.basename(file_path)}")
                 # No need to call _start_next_upload here, _on_upload_failed will do it.
        else:
            print("[BrowserPage] All file uploads finished or attempted.")
            # Optionally show a final summary message or just hide the overlay after a delay
            # self.upload_status.show_upload_completed(f"Finished uploading {self._total_files_to_upload} files.")
            # For now, let the last completion/failure message linger

    @pyqtSlot(str)
    def _on_upload_started(self, filename):
        """Handle upload started signal"""
        status_text = f"Uploading {self._current_upload_index + 1}/{self._total_files_to_upload}: {filename}"
        print(f"[BrowserPage] {status_text}")
        self.upload_status.show_upload_started(status_text)
        self._update_upload_status_position()
        
    @pyqtSlot(int)
    def _on_upload_progress(self, percentage):
        """Handle upload progress signal"""
        # print(f"[BrowserPage] Upload progress: {percentage}%") # Can be noisy - Keep commented
        self.upload_status.show_upload_progress(percentage)
        
    @pyqtSlot(str)
    def _on_upload_completed(self, filename):
        """Handle upload completed signal"""
        status_text = f"Completed {self._current_upload_index + 1}/{self._total_files_to_upload}: {filename}"
        print(f"[BrowserPage] {status_text}")
        self.upload_status.show_upload_completed(status_text) # Show completion briefly
        
        # Move to the next file
        self._current_upload_index += 1
        # Use QTimer to start next upload slightly later, allowing completion message to be seen
        QTimer.singleShot(1000, self._start_next_upload) 

    @pyqtSlot(str)
    def _on_upload_failed(self, error_msg):
        """Handle upload failed signal"""
        filename = "Unknown File"
        if self._current_upload_index < self._total_files_to_upload:
             filename = os.path.basename(self._files_to_upload[self._current_upload_index])
             
        status_text = f"Failed {self._current_upload_index + 1}/{self._total_files_to_upload}: {filename}"
        print(f"[BrowserPage] Upload Failed: {status_text} - Error: {error_msg}")
        self.upload_status.show_upload_failed(f"{status_text}\n{error_msg}") # Show failure
        
        # Move to the next file even if one failed
        self._current_upload_index += 1
        # Use QTimer to start next upload slightly later, allowing failure message to be seen
        QTimer.singleShot(2500, self._start_next_upload) # Longer delay for errors 

    def resizeEvent(self, event):
        """Handle resize event to reposition overlay button."""
        super().resizeEvent(event)

        # --- Position BrowserPage Overlays ---
        margin = 20
        button_y = self.height() - self.browse_button.height() - margin
        browse_button_x = self.width() - self.browse_button.width() - margin
        self.browse_button.move(browse_button_x, button_y)
        self.browse_button.raise_()
        oplayer_button_x = browse_button_x - self.oplayer_button.width() - 10
        self.oplayer_button.move(oplayer_button_x, button_y)
        self.oplayer_button.raise_()
        refresh_button_x = oplayer_button_x - self.refresh_button.width() - 10
        self.refresh_button.move(refresh_button_x, button_y)
        self.refresh_button.raise_()

        # Position the upload status overlay (relative to BrowserPage)
        self._update_upload_status_position()

        # Position the temporary message label (relative to BrowserPage)
        self._update_temp_message_position()

    def _update_upload_status_position(self):
        """Update the position of the upload status overlay (relative to BrowserPage)"""
        # Center horizontally, position near the top
        status_x = (self.width() - self.upload_status.width()) // 2
        status_y = 60  # Position below the potential header bar
        self.upload_status.move(status_x, status_y)
        self.upload_status.raise_()  # Ensure it's on top

    def _update_temp_message_position(self):
        """Update the position of the temporary message label (centered in BrowserPage)."""
        if self.temp_message_label.isVisible():
            self.temp_message_label.adjustSize()

            # Calculate the center point of the BrowserPage widget itself
            page_center_x = self.width() // 2
            page_center_y = self.height() // 2

            # Calculate the top-left position for the label to center it
            label_width = self.temp_message_label.width()
            label_height = self.temp_message_label.height()
            label_x = page_center_x - label_width // 2
            label_y = page_center_y - label_height // 2

            # Position relative to the BrowserPage
            self.temp_message_label.move(label_x, label_y)
            # Raise within the BrowserPage
            self.temp_message_label.raise_()

    def showEvent(self, event):
        """
        Load settings and automatically load the last browsed directory 
        when the page is shown.
        """
        super().showEvent(event)
        
        # --- Load OPlayer settings into UI --- 
        ftp_host = self.settings.get('oplayer/ftp_host', OPlayerService.DEFAULT_HOST, SettingType.STRING)
        ftp_port = self.settings.get('oplayer/ftp_port', OPlayerService.DEFAULT_PORT, SettingType.INT)
        self.ftp_host_edit.setText(ftp_host)
        self.ftp_port_spinbox.setValue(ftp_port)
        # Ensure the service instance also has the latest settings on show
        self.oplayer_service.update_connection_settings(host=ftp_host, port=ftp_port)
        # --------------------------------------
        
        # Get the last browsed directory from settings
        last_dir_str = self.settings.get('browser/last_browse_dir', None, SettingType.PATH)
        
        if last_dir_str:
            last_dir_path = Path(last_dir_str)
            # Check if it exists, is a directory, AND is different from the current view
            if last_dir_path.is_dir() and last_dir_path != self._current_directory:
                print(f"[BrowserPage] Automatically loading last directory: {last_dir_path}")
                self._current_directory = last_dir_path
                self._populate_table(self._current_directory)
            elif not last_dir_path.is_dir() and self._current_directory is None:
                 # If saved path is invalid and nothing is loaded, ensure empty message
                 self._update_empty_message()
        elif self._current_directory is None:
            # If no setting exists and nothing loaded, show empty message
            self._update_empty_message()
        
    def _handle_oplayer_setting_changed(self):
        """Handles changes in OPlayer host or port fields and saves them."""
        host = self.ftp_host_edit.text().strip()
        port = self.ftp_port_spinbox.value()

        # Validate host input (simple check for non-empty)
        if not host:
            # Maybe briefly highlight the field or show a status icon?
            # For now, just log and don't save if host is empty. 
            # The validator should prevent invalid IPs, but not empty strings.
            print("[BrowserPage] OPlayer host cannot be empty. Settings not saved.")
            return
        
        # Check if settings actually changed compared to current service config
        # to avoid unnecessary updates/logs
        current_host = self.oplayer_service.host
        current_port = self.oplayer_service.ftp_port
        if host == current_host and port == current_port:
            # print("[BrowserPage] OPlayer settings unchanged.") # Optional: reduce noise
            return

        # 1. Save to SettingsManager
        print(f"[BrowserPage] Auto-saving OPlayer settings: {host}:{port}")
        self.settings.set('oplayer/ftp_host', host, SettingType.STRING)
        self.settings.set('oplayer/ftp_port', port, SettingType.INT)
        self.settings.sync() # Persist immediately

        # 2. Update the service instance used by this page
        self.oplayer_service.update_connection_settings(host=host, port=port)

        # 3. Log success (no temporary message needed for auto-save)
        print("[BrowserPage] OPlayer settings updated and service reconfigured.")

    def _show_temporary_message(self, message: str, is_error: bool = False):
        """Displays a temporary message overlay."""
        self.temp_message_label.setText(message)
        # Ensure the label is visible *before* positioning
        self.temp_message_label.show()
        # Adjust size *after* setting text and showing
        self.temp_message_label.adjustSize()
        # Position it correctly relative to BrowserPage center
        self._update_temp_message_position()
        # Raise it again just in case
        self.temp_message_label.raise_()
        self.temp_message_timer.start() # Timer will hide it after interval 

        # Adjust style based on error or success
        if is_error:
             style = f"""
                background-color: {self.theme.get_color('status', 'error')};
                color: {self.theme.get_color('text', 'on_error')};
             """
        else:
             style = f"""
                background-color: {self.theme.get_color('status', 'success')};
                color: {self.theme.get_color('text', 'on_success')};
             """
        self.temp_message_label.setStyleSheet(f"""
            QLabel#tempMessageLabel {{ 
                {style} 
                padding: 8px 15px; 
                border-radius: 5px; 
                font-size: 9pt; 
            }}
        """) 