"""
Page for browsing local file system directories.
"""
import os
import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFileDialog, QLabel,
    QSizePolicy, QMessageBox
)
from PyQt6.QtCore import Qt, QSize, pyqtSlot, QTimer
from PyQt6.QtGui import QIcon
import qtawesome as qta

# Import from framework and components
from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.models.settings_manager import SettingsManager, SettingType
from music_player.ui.components.round_button import RoundButton
# Reuse helpers from selection_pool for table items and formatting
from music_player.ui.components.playlist_components.selection_pool import (
    SizeAwareTableItem, DateAwareTableItem, format_file_size, format_modified_time
)
# Import OPlayer service and overlay
from music_player.services.oplayer_service import OPlayerService
from music_player.ui.components.upload_status_overlay import UploadStatusOverlay

class BrowserPage(QWidget):
    """
    Page that allows browsing a selected directory and viewing its contents.
    """
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

        self._setup_ui()
        self._connect_signals()
        self._load_column_widths() # Load saved widths
        self._update_sort_indicators() # Set initial sort indicator
        self._update_empty_message() # Show initial message

    def _setup_ui(self):
        # Main layout
        self.main_layout = QVBoxLayout(self)
        # Use margins from the parent dashboard/content area
        self.main_layout.setContentsMargins(16, 16, 16, 16) 
        self.main_layout.setSpacing(16)

        # --- File Table ---
        self.file_table = QTableWidget()
        self.file_table.setObjectName("browserFileTable")
        self.file_table.setColumnCount(3)
        self.file_table.setHorizontalHeaderLabels(["Filename", "Size", "Modified"])
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.file_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.file_table.setAlternatingRowColors(True)
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.file_table.horizontalHeader().setStretchLastSection(True)
        self.file_table.horizontalHeader().setSortIndicatorShown(True)
        self.file_table.setSortingEnabled(False)  # Disable automatic sorting
        self.file_table.setShowGrid(False)
        self.file_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu) # Add later if needed
        
        # Set default row height
        self.file_table.verticalHeader().setDefaultSectionSize(22)

        # Apply styling similar to other tables
        self.file_table.setStyleSheet(f"""
            QTableWidget#browserFileTable {{
                background-color: transparent;
                alternate-background-color: {self.theme.get_color('background', 'alternate_row')};
                border: 1px solid {self.theme.get_color('border', 'secondary')};
                border-radius: 4px;
                padding: 0px;
                selection-background-color: {self.theme.get_color('background', 'selected_row')};
                selection-color: {self.theme.get_color('text', 'primary')};
            }}
            QTableWidget#browserFileTable::item {{
                padding: 0px 8px;
                height: 22px;
                min-height: 22px;
                border: none; /* No item border */
            }}
            QTableWidget#browserFileTable::item:selected {{
                background-color: {self.theme.get_color('background', 'selected_row')};
                color: {self.theme.get_color('text', 'primary')};
                border-radius: 0px;
            }}
            QHeaderView::section {{
                background-color: {self.theme.get_color('background', 'tertiary')};
                color: {self.theme.get_color('text', 'secondary')};
                padding: 0px 5px;
                height: 22px;
                border: none;
                border-bottom: 1px solid {self.theme.get_color('border', 'secondary')};
                border-right: 1px solid {self.theme.get_color('border', 'secondary')};
            }}
            QHeaderView::section:last {{
                 border-right: none;
            }}
            QHeaderView::section:hover {{
                background-color: {self.theme.get_color('background', 'quaternary')};
            }}
        """)

        # Add empty message label (initially hidden)
        self.empty_label = QLabel("Select a folder to browse its contents.")
        self.empty_label.setObjectName("browserEmptyLabel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {self.theme.get_color('text', 'secondary')}; font-style: italic;")
        self.empty_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.empty_label.hide()
        
        # Add table and label to layout
        self.main_layout.addWidget(self.file_table, 1) # Table takes most space
        self.main_layout.addWidget(self.empty_label, 1) # Label shown when table is hidden

        # --- Overlay Button --- 
        self.browse_button = RoundButton(
            parent=self,
            icon_name="fa5s.folder-open",
            text="📂",
            size=48,
            icon_size=24,
            bg_opacity=0.5
        )
        self.browse_button.setToolTip("Select Folder to Browse")
        
        # Create OPlayer upload button
        self.oplayer_button = RoundButton(
            parent=self,
            text="OP",
            size=48,
            bg_opacity=0.5
        )
        self.oplayer_button.setToolTip("Upload Selected Files to OPlayer")

        # Create upload status overlay
        self.upload_status = UploadStatusOverlay(self)

    def _connect_signals(self):
        self.browse_button.clicked.connect(self._browse_folder)
        self.file_table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        # Connect column resize signal
        self.file_table.horizontalHeader().sectionResized.connect(self._on_column_resized)
        # Connect OPlayer button
        self.oplayer_button.clicked.connect(self._on_oplayer_upload_selected_clicked)
        # Connect OPlayer service signals
        self.oplayer_service.upload_started.connect(self._on_upload_started)
        self.oplayer_service.upload_progress.connect(self._on_upload_progress)
        self.oplayer_service.upload_completed.connect(self._on_upload_completed)
        self.oplayer_service.upload_failed.connect(self._on_upload_failed)
        
        # Connect double click if needed later
        # self.file_table.doubleClicked.connect(self._on_item_double_clicked)

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

    def _populate_table(self, directory_path: Path):
        """Clears and fills the table with contents of the directory."""
        self.file_table.setRowCount(0) # Clear existing rows
        
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
        self.file_table.show()
        
        # Populate the table
        self.file_table.setSortingEnabled(False) # Disable during population
        for row, data in enumerate(files_data):
            self.file_table.insertRow(row)
            self.file_table.setRowHeight(row, 22)
            
            # Filename item (with icon for directory)
            filename_item = QTableWidgetItem(data['filename'])
            filename_item.setData(Qt.ItemDataRole.UserRole, data['path']) # Store full path
            filename_item.setToolTip(data['path'])
            if data['is_dir']:
                 filename_item.setIcon(qta.icon('fa5s.folder', color=self.theme.get_color('text', 'secondary')))
            else:
                 filename_item.setIcon(qta.icon('fa5s.file', color=self.theme.get_color('text', 'secondary')))
                 
            self.file_table.setItem(row, self.COL_FILENAME, filename_item)

            # Size item
            size_item = SizeAwareTableItem(data['size_str'], data['size_bytes'])
            self.file_table.setItem(row, self.COL_SIZE, size_item)

            # Modified item
            modified_item = DateAwareTableItem(data['mod_str'], data['mod_stamp'])
            self.file_table.setItem(row, self.COL_MODIFIED, modified_item)
            
        self.file_table.setSortingEnabled(True) # Re-enable sorting
        # Apply current sort order
        self.file_table.sortItems(self.sort_column, self.sort_order)
        self._update_sort_indicators()
        # Restore row heights after sort
        for row in range(self.file_table.rowCount()):
            self.file_table.setRowHeight(row, 22)

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
            self.file_table.show()

    def _on_header_clicked(self, column_index):
        """Handle column header clicks for sorting."""
        if self.sort_column == column_index:
            self.sort_order = Qt.SortOrder.DescendingOrder if self.sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            self.sort_column = column_index
            self.sort_order = Qt.SortOrder.AscendingOrder
            
        self._update_sort_indicators()
        self.file_table.sortItems(self.sort_column, self.sort_order)
        # Restore row heights after sort
        for row in range(self.file_table.rowCount()):
            self.file_table.setRowHeight(row, 22)
            
    def _update_sort_indicators(self):
        """Update the sort indicators in headers."""
        header = self.file_table.horizontalHeader()
        for col in range(header.count()):
            header_item = self.file_table.horizontalHeaderItem(col)
            if header_item:
                if col == self.sort_column:
                    icon = self.sort_up_icon if self.sort_order == Qt.SortOrder.AscendingOrder else self.sort_down_icon
                    header_item.setIcon(icon)
                else:
                    header_item.setIcon(QIcon()) # Clear icon

    def _on_column_resized(self, column, oldWidth, newWidth):
        """Save column widths when resized."""
        self._save_column_widths()
        
    def _save_column_widths(self):
        """Save column widths to settings."""
        column_widths = {
            'filename': self.file_table.columnWidth(self.COL_FILENAME),
            'size': self.file_table.columnWidth(self.COL_SIZE),
            'modified': self.file_table.columnWidth(self.COL_MODIFIED)
        }
        self.settings.set('ui/browser_table/column_widths', column_widths, SettingType.DICT)
        
    def _load_column_widths(self):
        """Load column widths from settings."""
        default_widths = {'filename': 350, 'size': 100, 'modified': 150}
        column_widths = self.settings.get('ui/browser_table/column_widths', default_widths, SettingType.DICT)
        
        self.file_table.setColumnWidth(self.COL_FILENAME, column_widths['filename'])
        self.file_table.setColumnWidth(self.COL_SIZE, column_widths['size'])
        self.file_table.setColumnWidth(self.COL_MODIFIED, column_widths['modified'])

    def resizeEvent(self, event):
        """Handle resize event to reposition overlay button."""
        super().resizeEvent(event)
        # Position Browse button overlay in bottom-right corner
        margin = 20
        button_x = self.width() - self.browse_button.width() - margin
        button_y = self.height() - self.browse_button.height() - margin
        self.browse_button.move(button_x, button_y)
        self.browse_button.raise_() # Ensure it's on top 
        
        # Position OPlayer button next to browse button
        oplayer_button_x = button_x - self.oplayer_button.width() - 10 # 10px spacing
        self.oplayer_button.move(oplayer_button_x, button_y)
        self.oplayer_button.raise_()

        # Position the upload status overlay
        self._update_upload_status_position()
        
    def _update_upload_status_position(self):
        """Update the position of the upload status overlay"""
        # Center horizontally, position near the top
        status_x = (self.width() - self.upload_status.width()) // 2
        status_y = 60  # Position below the potential header bar
        self.upload_status.move(status_x, status_y)
        self.upload_status.raise_()  # Ensure it's on top 

    def showEvent(self, event):
        """
        Automatically load the last browsed directory when the page is shown.
        """
        super().showEvent(event)
        
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
        
    # --- OPlayer Upload Handlers --- 

    def _on_oplayer_upload_selected_clicked(self):
        """Handles click on the OPlayer upload button for selected files."""
        selected_items = self.file_table.selectedItems()
        self._files_to_upload = []
        
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select one or more files to upload.")
            return

        # Get paths of selected *files* only
        for item in selected_items:
            # Check the Filename column and retrieve stored path
            if item.column() == self.COL_FILENAME:
                file_path = item.data(Qt.ItemDataRole.UserRole)
                # Simple check: is it likely a directory based on stored data or typical size?
                # A more robust check would involve re-statting or storing 'is_dir' boolean
                size_item = self.file_table.item(item.row(), self.COL_SIZE)
                is_dir = size_item and size_item.text() == "<DIR>" # Check based on display text
                
                if file_path and not is_dir and os.path.exists(file_path):
                     if file_path not in self._files_to_upload: # Avoid duplicates from multi-column selection
                         self._files_to_upload.append(file_path)
        
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