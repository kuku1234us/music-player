"""
Page for browsing local file system directories.
"""
import os
import shutil # Add shutil for directory removal
import datetime
from pathlib import Path
import concurrent.futures
from functools import partial
from qt_base_app.models.logger import Logger

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFileDialog, QLabel,
    QSizePolicy, QMessageBox, QHBoxLayout, QLineEdit, QSpinBox, QPushButton,
    QDialog, QDialogButtonBox # Added QDialog components
)
from PyQt6.QtCore import (
    Qt, QSize, pyqtSlot, QTimer, pyqtSignal, QSortFilterProxyModel, 
    QRegularExpression, QThreadPool, QRunnable, QObject
)
from PyQt6.QtGui import QIcon, QRegularExpressionValidator
import qtawesome as qta

# Import from framework and components
from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.models.settings_manager import SettingsManager, SettingType
from music_player.ui.components.round_button import RoundButton
# Import OPlayer service and overlay
from music_player.services.oplayer_service import OPlayerService
from music_player.ui.components.upload_status_overlay import UploadStatusOverlay
# --- NEW IMPORTS FOR CONVERSION --- #
from music_player.models.conversion_manager import ConversionManager
from music_player.ui.components.browser_components.conversion_progress import ConversionProgress
# --- END NEW IMPORTS --- #
# --- NEW IMPORTS FOR VIDEO COMPRESSION --- #
from music_player.models.video_compression_manager import VideoCompressionManager
from music_player.ui.components.browser_components.video_compression_progress import VideoCompressionProgress
from music_player.ui.components.browser_components.video_process_options_dialog import VideoProcessOptionsDialog
from music_player.models.douyin_processor import DouyinProcessor
from music_player.ui.components.browser_components.douyin_progress import DouyinProgress
from music_player.ui.components.browser_components.douyin_options_dialog import DouyinOptionsDialog
# --- END NEW IMPORTS --- #
from music_player.ui.components.base_table import BaseTableModel, ColumnDefinition
from music_player.ui.components.browser_components.browser_table import BrowserTableView
from music_player.models.video_file_utils import is_video_file, get_all_video_files

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

# --- Directory Worker Signals ---
class DirectoryWorkerSignals(QObject):
    """Signals for the directory loading worker"""
    progress = pyqtSignal(int, int)  # current count, total count
    finished = pyqtSignal(list)  # list of file data dictionaries
    error = pyqtSignal(str)  # error message
    
# --- Directory Worker ---
class DirectoryWorker(QRunnable):
    """Worker to load directory contents in a background thread"""
    
    def __init__(self, directory_path: Path, batch_size=100):
        super().__init__()
        self.directory_path = directory_path
        self.batch_size = batch_size
        self.signals = DirectoryWorkerSignals()
        self.is_cancelled = False
        
    def run(self):
        """Main worker method that runs in a separate thread"""
        files_data = []
        processed_count = 0
        
        try:
            # First, just get directory listing without processing
            # This is much faster than iterdir() + stat() in a loop
            items = list(self.directory_path.iterdir())
            total_items = len(items)
            
            # Process in batches
            for i, item_path in enumerate(items):
                if self.is_cancelled:
                    return
                    
                try:
                    # Get stats - skip if error (e.g., permissions, broken link)
                    stats = item_path.stat()
                    is_dir = item_path.is_dir()
                    filename = item_path.name
                    filesize_bytes = stats.st_size if not is_dir else -1  # Size -1 for dirs
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
                    Logger.instance().error(caller="DirectoryWorker", msg=f"[DirectoryWorker] Error accessing item {item_path}: {e}")
                    continue  # Skip this item
                
                processed_count += 1
                
                # Emit progress periodically (not for every file to reduce signal overhead)
                if processed_count % self.batch_size == 0 or i == total_items - 1:
                    self.signals.progress.emit(processed_count, total_items)
                
        except Exception as e:
            error_msg = f"Error listing directory {self.directory_path}: {e}"
            Logger.instance().error(caller="DirectoryWorker", msg=f"[DirectoryWorker] {error_msg}")
            self.signals.error.emit(error_msg)
            return
            
        self.signals.finished.emit(files_data)
    
    def cancel(self):
        """Flag the worker to stop processing"""
        self.is_cancelled = True

class SilentConfirmDialog(QDialog):
    """A dialog that does not emit system sound on show."""
    def __init__(self, parent, filename):
        super().__init__(parent)
        self.setWindowTitle("Confirm Deletion")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Are you sure you want to delete:\n{filename}?"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

class BrowserPage(QWidget):
    """
    Page that allows browsing a selected directory and viewing its contents.
    """
    # Signal to request playing a single file
    play_single_file_requested = pyqtSignal(str) # Emits filepath
    request_stop_playback = pyqtSignal() # Request stop playback
    
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
        self.persistent_player = None # Will be set via dashboard/parent
        
        # Flag to track if we're in the middle of programmatic navigation
        self._navigation_in_progress = False
        
        # OPlayer Service and Upload State
        self.oplayer_service = OPlayerService(self)
        self._files_to_upload = []
        self._current_upload_index = 0
        self._total_files_to_upload = 0

        # --- NEW: Conversion Manager and Progress UI --- #
        self.conversion_manager = ConversionManager(self)
        self.conversion_progress_overlay = ConversionProgress(self)
        # --- END NEW --- #

        # --- NEW: Video Compression Manager and Progress UI --- #
        self.video_compression_manager = VideoCompressionManager(self)
        self.video_compression_progress_overlay = VideoCompressionProgress(self)
        # --- END NEW --- #

        # --- NEW: Douyin Processor --- #
        self.douyin_processor = DouyinProcessor(self)
        self.douyin_progress_overlay = DouyinProgress(self)
        
        # Configure concurrent encoding limit based on system capabilities
        DouyinProcessor.set_max_concurrent_encoding(3)
        # --- END NEW --- #

        # Timer for temporary messages
        self.temp_message_timer = QTimer(self)
        self.temp_message_timer.setSingleShot(True)
        self.temp_message_timer.setInterval(2000) # 2 seconds
        
        # Directory worker
        self.thread_pool = QThreadPool.globalInstance()
        self.current_directory_worker = None
        self.loading_timer = QTimer(self)
        self.loading_timer.setInterval(100)  # 100ms interval for loading animation
        self.loading_timer.timeout.connect(self._update_loading_animation)
        self.loading_animation_step = 0
        self.loading_animation_chars = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
        
        # State for pending selection after async load
        self._pending_selection_dir = None
        self._pending_selection_filename = None

        self._setup_ui()
        self._connect_signals()
        self._update_empty_message() # Show initial message

    # ... [Keep existing methods unchanged until _connect_signals] ...
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

        # --- NEW: MP3 Conversion Button --- #
        self.mp3_convert_button = RoundButton(
            parent=self,
            text="MP3", 
            diameter=48,
            bg_opacity=0.5
        )
        self.mp3_convert_button.setToolTip("Convert Selected to MP3")
        # --- END NEW --- #

        # --- NEW: Video Compression Button --- #
        self.video_compress_button = RoundButton(
            parent=self,
            icon_name="fa5s.video",  
            diameter=48,
            icon_size=20,
            bg_opacity=0.5
        )
        self.video_compress_button.setToolTip("Compress Selected Videos to 720p")
        # --- END NEW --- #

        # --- NEW: Douyin Process Button --- #
        self.douyin_button = RoundButton(
            parent=self,
            text="抖",
            diameter=48,
            bg_opacity=0.5
        )
        self.douyin_button.setToolTip("Process Douyin Videos")
        # --- END NEW --- #

        # --- NEW: Cancel Conversion Button --- #
        self.cancel_conversion_button = RoundButton(
            parent=self,
            icon_name="fa5s.times-circle", 
            diameter=48,
            icon_size=24,
            bg_opacity=0.5
        )
        self.cancel_conversion_button.setToolTip("Cancel Ongoing Conversions")
        self.cancel_conversion_button.hide() 
        # --- END NEW --- #

        # --- NEW: Cancel Video Compression Button --- #
        self.cancel_video_compression_button = RoundButton(
            parent=self,
            icon_name="fa5s.stop-circle", 
            diameter=48,
            icon_size=24,
            bg_opacity=0.5
        )
        self.cancel_video_compression_button.setToolTip("Cancel Ongoing Video Compressions")
        self.cancel_video_compression_button.hide() 
        # --- END NEW --- #

        # --- NEW: Bottom Button Bar --- #
        self.bottom_button_bar = QWidget(self)
        self.bottom_button_bar.setObjectName("bottomButtonBar")
        self.bottom_button_layout = QHBoxLayout(self.bottom_button_bar)
        self.bottom_button_layout.setContentsMargins(0, 0, 0, 0)
        self.bottom_button_layout.setSpacing(10)
        self.bottom_button_layout.addStretch(1)  

        # Add buttons to layout in desired order (left to right)
        self.bottom_button_layout.addWidget(self.cancel_video_compression_button)
        self.bottom_button_layout.addWidget(self.cancel_conversion_button)
        self.bottom_button_layout.addWidget(self.douyin_button)
        self.bottom_button_layout.addWidget(self.video_compress_button)
        self.bottom_button_layout.addWidget(self.mp3_convert_button)
        self.bottom_button_layout.addWidget(self.refresh_button)
        self.bottom_button_layout.addWidget(self.oplayer_button)
        self.bottom_button_layout.addWidget(self.browse_button)
        # --- END NEW --- #

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

        # --- NEW: Connect Conversion Signals --- #
        self.mp3_convert_button.clicked.connect(self._on_mp3_convert_selected_clicked)
        self.conversion_manager.conversion_batch_started.connect(self._on_conversion_batch_started)
        self.conversion_manager.conversion_file_started.connect(self._on_conversion_file_started)
        self.conversion_manager.conversion_file_progress.connect(self._on_conversion_file_progress)
        self.conversion_manager.conversion_file_completed.connect(self._on_conversion_file_completed)
        self.conversion_manager.conversion_file_failed.connect(self._on_conversion_file_failed)
        self.conversion_manager.conversion_batch_finished.connect(self._on_conversion_batch_finished)
        # --- END NEW --- #

        # --- NEW: Connect Cancel Button --- #
        self.cancel_conversion_button.clicked.connect(self._on_cancel_conversions_clicked)
        # --- END NEW --- #

        # --- NEW: Connect Video Compression Signals --- #
        self.video_compress_button.clicked.connect(self._on_video_process_clicked)
        self.video_compression_manager.compression_batch_started.connect(self._on_video_compression_batch_started)
        self.video_compression_manager.compression_file_started.connect(self._on_video_compression_file_started)
        self.video_compression_manager.compression_file_progress.connect(self._on_video_compression_file_progress)
        self.video_compression_manager.compression_file_completed.connect(self._on_video_compression_file_completed)
        self.video_compression_manager.compression_file_failed.connect(self._on_video_compression_file_failed)
        self.video_compression_manager.compression_batch_finished.connect(self._on_video_compression_batch_finished)
        # --- END NEW --- #

        # --- NEW: Connect Douyin Processor Signals --- #
        self.douyin_processor.trim_batch_started.connect(self._on_douyin_batch_started)
        self.douyin_processor.trim_file_started.connect(self._on_douyin_file_started)
        self.douyin_processor.trim_file_progress.connect(self._on_douyin_file_progress)
        self.douyin_processor.trim_file_completed.connect(self._on_douyin_file_completed)
        self.douyin_processor.trim_file_failed.connect(self._on_douyin_file_failed)
        self.douyin_processor.trim_batch_finished.connect(self._on_douyin_batch_finished)
        # Normalization signals
        self.douyin_processor.normalize_started.connect(lambda total: (self.douyin_progress_overlay.show_normalization_started(total), self._update_douyin_progress_position()))
        self.douyin_processor.normalize_file_started.connect(lambda task_id, filename, idx, total: (self.douyin_progress_overlay.show_file_progress(task_id, os.path.basename(filename), idx, total, 0.0), self._update_douyin_progress_position()))
        self.douyin_processor.normalize_file_progress.connect(lambda task_id, percent: self.douyin_progress_overlay.update_current_file_progress(task_id, percent))
        self.douyin_processor.normalize_file_completed.connect(lambda task_id, filename: (self.douyin_progress_overlay.show_file_completed(os.path.basename(filename), os.path.basename(filename)), self._update_douyin_progress_position()))
        self.douyin_processor.normalize_file_failed.connect(lambda task_id, filename, err: (self.douyin_progress_overlay.show_file_failed(os.path.basename(filename), err), self._update_douyin_progress_position()))
        self.douyin_processor.merge_started.connect(self._on_douyin_merge_started)
        self.douyin_processor.merge_progress.connect(self._on_douyin_merge_progress)
        self.douyin_processor.merge_completed.connect(self._on_douyin_merge_completed)
        self.douyin_processor.merge_failed.connect(self._on_douyin_merge_failed)
        self.douyin_processor.process_finished.connect(self._on_douyin_process_finished)
        # --- END NEW --- #

        # --- NEW: Connect Cancel Video Compression Button --- #
        self.cancel_video_compression_button.clicked.connect(self._on_cancel_video_compressions_clicked)
        # --- END NEW --- #

        # --- NEW: Connect Douyin Button --- #
        self.douyin_button.clicked.connect(self._on_douyin_process_clicked)
        # --- END NEW --- #

    # ... [Keep navigation/display logic, add new methods below] ...
    
    # --- New Methods for Navigation and Deletion ---
    def _get_adjacent_file(self, current_path, direction='next') -> str | None:
        """Finds the next or previous file in the sorted view."""
        if not current_path: return None
        
        model = self.file_table.model()
        if not model: return None
        
        target_row = -1
        current_row = -1
        
        # Find current row
        for row in range(model.rowCount()):
            idx = model.index(row, 0)
            item_data = model.data(idx, Qt.ItemDataRole.UserRole)
            if isinstance(item_data, dict) and item_data.get('path') == current_path:
                current_row = row
                break
                
        if current_row == -1: return None
        
        if direction == 'next':
            target_row = current_row + 1
        elif direction == 'prev':
            target_row = current_row - 1
            
        if 0 <= target_row < model.rowCount():
            idx = model.index(target_row, 0)
            item_data = model.data(idx, Qt.ItemDataRole.UserRole)
            if isinstance(item_data, dict):
                return item_data.get('path')
        
        return None

    @pyqtSlot(str)
    def handle_browser_nav_request(self, direction):
        """Handles navigation requests from MainPlayer (hotkeys)."""
        if not self.persistent_player: return
        
        current_path = self.persistent_player.get_current_media_path()
        next_file = self._get_adjacent_file(current_path, direction)
        
        if next_file:
            Logger.instance().debug(caller="BrowserPage", msg=f"[BrowserPage] Hotkey Nav: Playing {next_file}")
            self.play_single_file_requested.emit(next_file)
            filename = os.path.basename(next_file)
            self._select_file_by_name(filename)

    @pyqtSlot(str)
    def handle_browser_delete_request(self, file_path):
        """Handles delete request from MainPlayer (hotkey)."""
        Logger.instance().debug(caller="BrowserPage", msg=f"[BrowserPage] Delete requested for: {file_path}")
        
        # 1. Identify next file to play
        next_file = self._get_adjacent_file(file_path, 'next')
        if not next_file:
             next_file = self._get_adjacent_file(file_path, 'prev')

        # 2. Confirm
        dialog = SilentConfirmDialog(self, os.path.basename(file_path))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 3. Stop Playback to release lock
            self.request_stop_playback.emit()
            
            # Delay to ensure lock release
            QTimer.singleShot(200, lambda: self._execute_delete(file_path, next_file))

    def _execute_delete(self, file_path, next_file_to_play):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                Logger.instance().info(caller="BrowserPage", msg=f"[BrowserPage] Deleted file: {file_path}")
                
                # Setup pending selection for the refresh
                if next_file_to_play:
                    self._pending_selection_dir = self._current_directory
                    self._pending_selection_filename = os.path.basename(next_file_to_play)
                
                self._refresh_view()
                
                if next_file_to_play and os.path.exists(next_file_to_play):
                     self.play_single_file_requested.emit(next_file_to_play)
            else:
                Logger.instance().warning(caller="BrowserPage", msg="[BrowserPage] File not found for deletion.")
        except Exception as e:
            Logger.instance().error(caller="BrowserPage", msg=f"[BrowserPage] Delete failed: {e}")
            QMessageBox.critical(self, "Delete Failed", f"Could not delete file:\n{e}")

    # ... [Rest of existing methods: _browse_folder, _navigate_to_directory, _refresh_view, etc.] ...
    def _browse_folder(self):
        last_dir = self.settings.get('browser/last_browse_dir', str(Path.home()), SettingType.PATH)
        directory = QFileDialog.getExistingDirectory(self, "Select Folder to Browse", str(last_dir), QFileDialog.Option.ShowDirsOnly)
        if directory: self._navigate_to_directory(Path(directory))
        else: self._update_empty_message()
             
    def _navigate_to_directory(self, directory_path):
        if not directory_path or not directory_path.is_dir():
            Logger.instance().debug(caller="BrowserPage", msg=f"[BrowserPage] Cannot navigate: Invalid directory path: {directory_path}")
            return False
        self.settings.set('browser/last_browse_dir', str(directory_path), SettingType.PATH)
        self.settings.sync()
        if self._current_directory != directory_path:
            self._current_directory = directory_path
            self._populate_table(self._current_directory)
            return True
        else:
            Logger.instance().debug(caller="BrowserPage", msg=f"[BrowserPage] Already in directory: {directory_path}")
            return True

    def _refresh_view(self):
        if self._current_directory and self._current_directory.is_dir():
            Logger.instance().debug(caller="BrowserPage", msg=f"[BrowserPage] Refreshing view for: {self._current_directory}")
            self._populate_table(self._current_directory)
        else:
            Logger.instance().debug(caller="BrowserPage", msg="[BrowserPage] Cannot refresh: No valid directory selected.")

    def _populate_table(self, directory_path: Path):
        if self.current_directory_worker: self.current_directory_worker.cancel()
        self.empty_label.setText(f"Loading {directory_path.name}...")
        self.empty_label.show()
        self.file_table.hide()
        self.loading_animation_step = 0
        self.loading_timer.start()
        worker = DirectoryWorker(directory_path)
        worker.signals.progress.connect(self._on_directory_loading_progress)
        worker.signals.finished.connect(lambda files_data: self._on_directory_loading_finished(files_data, directory_path))
        worker.signals.error.connect(self._on_directory_loading_error)
        self.current_directory_worker = worker
        self.thread_pool.start(worker)

    def _on_directory_loading_progress(self, current, total):
        if total > 0:
            percent = (current / total) * 100
            self.empty_label.setText(f"Loading {self._current_directory.name}... {current}/{total} ({percent:.0f}%)")
    
    def _on_directory_loading_finished(self, files_data, directory_path):
        self.loading_timer.stop()
        self.current_directory_worker = None
        if self._current_directory != directory_path: return
        if not files_data:
            self._update_empty_message(is_empty=True)
            return
        self.empty_label.hide()
        self.file_table.show()
        self.model = BaseTableModel(source_objects=files_data, column_definitions=browser_col_defs)
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.file_table.setModel(self.proxy_model)
        self.file_table.resizeRowsToContents()
        if directory_path == self._pending_selection_dir and self._pending_selection_filename:
            self._select_file_by_name(self._pending_selection_filename)
        self._pending_selection_dir = None
        self._pending_selection_filename = None

    def _on_directory_loading_error(self, error_msg):
        self.loading_timer.stop()
        self.current_directory_worker = None
        Logger.instance().error(caller="BrowserPage", msg=f"[BrowserPage] Directory loading error: {error_msg}")
        self.empty_label.setText(f"Error: {error_msg}")
        self.empty_label.show()
        self.file_table.hide()
        
    def _update_loading_animation(self):
        if not self._current_directory: return
        char = self.loading_animation_chars[self.loading_animation_step % len(self.loading_animation_chars)]
        self.empty_label.setText(f"Loading {self._current_directory.name}... {char}")
        self.loading_animation_step += 1

    def _update_empty_message(self, is_empty: bool = False):
        if self._current_directory and is_empty:
            self.empty_label.setText(f"Directory is empty: {self._current_directory.name}")
            self.file_table.hide()
            self.empty_label.show()
        elif not self._current_directory:
            self.empty_label.setText("Select a folder to browse its contents.")
            self.file_table.hide()
            self.empty_label.show()
        else:
            self.empty_label.hide()
            self.file_table.show()

    def _on_file_double_clicked(self, filepath):
        self.play_single_file_requested.emit(filepath)

    def _on_directory_double_clicked(self, dirpath):
        if dirpath and os.path.isdir(dirpath):
            self._navigate_to_directory(Path(dirpath))

    def _on_items_deleted_from_disk(self, deleted_count, error_messages):
        if deleted_count > 0:
            message = f"Deleted {deleted_count} item(s)."
            if error_messages: message += f"\n({len(error_messages)} errors occurred)"
            self._show_temporary_message(message)
        elif error_messages:
            message = f"Failed to delete selected items.\n{error_messages[0]}"
            if len(error_messages) > 1: message += " (and others)"
            self._show_temporary_message(message, is_error=True)

    def _on_oplayer_upload_selected_clicked(self):
        selected_objects = self.file_table.get_selected_items_data()
        self._files_to_upload = []
        if not selected_objects:
            QMessageBox.warning(self, "No Selection", "Please select one or more files to upload.")
            return
        for obj in selected_objects:
            path = obj.get('path')
            is_dir = obj.get('is_dir', False)
            if path and not is_dir and os.path.exists(path):
                if path not in self._files_to_upload:
                    self._files_to_upload.append(path)
        if not self._files_to_upload:
            QMessageBox.warning(self, "No Files Selected", "The current selection contains only directories or invalid files.")
            return
        if not self.oplayer_service.test_connection():
            QMessageBox.critical(self, "Connection Error", "Could not connect to OPlayer device.")
            return
        self._current_upload_index = 0
        self._total_files_to_upload = len(self._files_to_upload)
        self._start_next_upload()
        
    def _start_next_upload(self):
        if self._current_upload_index < self._total_files_to_upload:
            file_path = self._files_to_upload[self._current_upload_index]
            if not self.oplayer_service.upload_file(file_path):
                 self._on_upload_failed(f"Could not start upload for {os.path.basename(file_path)}")

    @pyqtSlot(str)
    def _on_upload_started(self, filename):
        status_text = f"Uploading {self._current_upload_index + 1}/{self._total_files_to_upload}: {filename}"
        self.upload_status.show_upload_started(status_text)
        self._update_upload_status_position()
        
    @pyqtSlot(int)
    def _on_upload_progress(self, percentage):
        self.upload_status.show_upload_progress(percentage)
        
    @pyqtSlot(str)
    def _on_upload_completed(self, filename):
        status_text = f"Completed {self._current_upload_index + 1}/{self._total_files_to_upload}: {filename}"
        self.upload_status.show_upload_completed(status_text) 
        self._current_upload_index += 1
        QTimer.singleShot(1000, self._start_next_upload) 

    @pyqtSlot(str)
    def _on_upload_failed(self, error_msg):
        filename = "Unknown File"
        if self._current_upload_index < self._total_files_to_upload:
             filename = os.path.basename(self._files_to_upload[self._current_upload_index])
        status_text = f"Failed {self._current_upload_index + 1}/{self._total_files_to_upload}: {filename}"
        self.upload_status.show_upload_failed(f"{status_text}\n{error_msg}") 
        self._current_upload_index += 1
        QTimer.singleShot(2500, self._start_next_upload) 

    def resizeEvent(self, event):
        super().resizeEvent(event)
        margin = 20
        button_y = self.height() - self.browse_button.height() - margin  
        current_x = self.width() - margin
        self.overlay_buttons = [
            self.browse_button, self.oplayer_button, self.refresh_button,
            self.mp3_convert_button, self.video_compress_button, self.douyin_button,
            self.cancel_conversion_button, self.cancel_video_compression_button
        ]
        for button in reversed(self.overlay_buttons):  
            if button.isVisible():
                button.move(current_x - button.width(), button_y)
                button.raise_()
                current_x -= button.width() + 10
        self._update_upload_status_position()
        self._update_temp_message_position()
        self._update_conversion_progress_position()
        self._update_video_compression_progress_position()
        self._update_douyin_progress_position()
        margin = 20
        bar_width = self.width() - 2 * margin
        bar_height = self.browse_button.height() 
        bar_y = self.height() - bar_height - margin
        self.bottom_button_bar.setGeometry(margin, bar_y, bar_width, bar_height)
        self.bottom_button_bar.raise_()

    def _update_upload_status_position(self):
        status_x = (self.width() - self.upload_status.width()) // 2
        status_y = 60  
        self.upload_status.move(status_x, status_y)
        self.upload_status.raise_()

    def _update_temp_message_position(self):
        if self.temp_message_label.isVisible():
            self.temp_message_label.adjustSize()
            page_center_x = self.width() // 2
            page_center_y = self.height() // 2
            label_width = self.temp_message_label.width()
            label_height = self.temp_message_label.height()
            label_x = page_center_x - label_width // 2
            label_y = page_center_y - label_height // 2
            self.temp_message_label.move(label_x, label_y)
            self.temp_message_label.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        ftp_host = self.settings.get('oplayer/ftp_host', OPlayerService.DEFAULT_HOST, SettingType.STRING)
        ftp_port = self.settings.get('oplayer/ftp_port', OPlayerService.DEFAULT_PORT, SettingType.INT)
        self.ftp_host_edit.setText(ftp_host)
        self.ftp_port_spinbox.setValue(ftp_port)
        self.oplayer_service.update_connection_settings(host=ftp_host, port=ftp_port)
        
        if self._navigation_in_progress: return
        last_dir_str = self.settings.get('browser/last_browse_dir', None, SettingType.PATH)
        if last_dir_str:
            last_dir_path = Path(last_dir_str)
            if last_dir_path.is_dir() and last_dir_path != self._current_directory:
                self._navigate_to_directory(last_dir_path)
            elif not last_dir_path.is_dir() and self._current_directory is None:
                 self._update_empty_message()
        elif self._current_directory is None:
            self._update_empty_message()
        
    def _handle_oplayer_setting_changed(self):
        host = self.ftp_host_edit.text().strip()
        port = self.ftp_port_spinbox.value()
        if not host: return
        current_host = self.oplayer_service.host
        current_port = self.oplayer_service.ftp_port
        if host == current_host and port == current_port: return
        self.settings.set('oplayer/ftp_host', host, SettingType.STRING)
        self.settings.set('oplayer/ftp_port', port, SettingType.INT)
        self.settings.sync()
        self.oplayer_service.update_connection_settings(host=host, port=port)

    def _show_temporary_message(self, message: str, is_error: bool = False):
        self.temp_message_label.setText(message)
        self.temp_message_label.show()
        self.temp_message_label.adjustSize()
        self._update_temp_message_position()
        self.temp_message_label.raise_()
        self.temp_message_timer.start() 
        if is_error:
             style = f"background-color: {self.theme.get_color('status', 'error')}; color: {self.theme.get_color('text', 'on_error')};"
        else:
             style = f"background-color: {self.theme.get_color('status', 'success')}; color: {self.theme.get_color('text', 'on_success')};"
        self.temp_message_label.setStyleSheet(f"QLabel#tempMessageLabel {{ {style} padding: 8px 15px; border-radius: 5px; font-size: 9pt; }}") 

    def set_navigation_in_progress(self, in_progress=True):
        self._navigation_in_progress = in_progress

    def navigate_to_file(self, directory_path, filename=None):
        if not directory_path: return False
        if not isinstance(directory_path, Path):
            try: target_dir = Path(directory_path)
            except Exception: return False
        else: target_dir = directory_path

        needs_load = False
        if self._current_directory == target_dir:
            if filename and self._is_file_in_table(filename):
                self._select_file_by_name(filename)
                self._pending_selection_dir = None
                self._pending_selection_filename = None
                return True 
            elif filename:
                needs_load = True
                self._pending_selection_dir = target_dir
                self._pending_selection_filename = filename
                self._refresh_view() 
            else:
                 self._pending_selection_dir = None
                 self._pending_selection_filename = None
                 return True 
        else:
            needs_load = True
            self._pending_selection_dir = target_dir
            self._pending_selection_filename = filename 
            self._navigate_to_directory(target_dir) 
        
        return needs_load 

    def _is_file_in_table(self, filename: str) -> bool:
        if not filename: return False
        try:
            proxy_model = self.file_table.model()
            if not proxy_model: return False
            for row in range(proxy_model.rowCount()):
                index = proxy_model.index(row, self.COL_FILENAME) 
                data = proxy_model.data(index, Qt.ItemDataRole.DisplayRole)
                item_data = proxy_model.data(index, Qt.ItemDataRole.UserRole)
                if (data == filename or (isinstance(item_data, dict) and item_data.get('filename') == filename)):
                    return True
            return False
        except Exception: return False

    def _select_file_by_name(self, filename: str) -> bool:
        if not filename: return False
        try:
            proxy_model = self.file_table.model()
            if not proxy_model: return False
            selected_indices = self.file_table.selectedIndexes()
            if selected_indices:
                for index in selected_indices:
                    if index.column() == self.COL_FILENAME:
                        if proxy_model.data(index, Qt.ItemDataRole.DisplayRole) == filename:
                            self.file_table.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)
                            return True
            for row in range(proxy_model.rowCount()):
                index = proxy_model.index(row, self.COL_FILENAME) 
                data = proxy_model.data(index, Qt.ItemDataRole.DisplayRole)
                item_data = proxy_model.data(index, Qt.ItemDataRole.UserRole)
                if (data == filename or (isinstance(item_data, dict) and item_data.get('filename') == filename)):
                    self.file_table.selectRow(row)
                    self.file_table.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)
                    return True
            return False
        except Exception: return False

    # ... [Keep MP3/Video/Douyin handlers] ...
    def _on_mp3_convert_selected_clicked(self):
        selected_objects = self.file_table.get_selected_items_data()
        files_to_convert = []
        if not selected_objects:
            QMessageBox.warning(self, "No Selection", "Please select one or more files to convert to MP3.")
            return
        for obj in selected_objects:
            path_str = obj.get('path')
            is_dir = obj.get('is_dir', False)
            if path_str and not is_dir and os.path.exists(path_str):
                if any(path_str.lower().endswith(ext) for ext in ['.wav', '.mp4', '.mkv', '.avi', '.flac', '.ogg', '.mov']):
                    if path_str not in [f['path'] for f in files_to_convert]: 
                        files_to_convert.append(obj) 
        if not files_to_convert:
            QMessageBox.information(self, "No Convertible Files", "The current selection contains no files suitable for MP3 conversion.")
            return
        if not self._current_directory or not self._current_directory.is_dir():
            QMessageBox.critical(self, "Error", "Cannot determine output directory. Please select a valid folder first.")
            return
        output_directory = str(self._current_directory)
        self.conversion_manager.start_conversions(files_to_convert, output_directory)

    def _on_conversion_batch_started(self, total_files: int):
        self.conversion_progress_overlay.show_conversion_started(total_files)
        self._update_conversion_progress_position()
        self.cancel_conversion_button.show() 

    def _on_conversion_file_started(self, task_id: str, original_filename: str, file_index: int, total_files: int):
        self.conversion_progress_overlay.show_file_progress(task_id, os.path.basename(original_filename), file_index, total_files, 0.0)
        self._update_conversion_progress_position() 

    def _on_conversion_file_progress(self, task_id: str, percentage: float):
        self.conversion_progress_overlay.update_current_file_progress(task_id, percentage)

    def _on_conversion_file_completed(self, task_id: str, original_filename: str, output_filepath: str):
        self.conversion_progress_overlay.show_file_completed(os.path.basename(original_filename))
        self._update_conversion_progress_position()

    def _on_conversion_file_failed(self, task_id: str, original_filename: str, error_message: str):
        self.conversion_progress_overlay.show_file_failed(os.path.basename(original_filename), error_message)
        self._update_conversion_progress_position()

    def _on_conversion_batch_finished(self):
        self.conversion_progress_overlay.show_batch_finished()
        self.cancel_conversion_button.hide() 
        self._update_conversion_progress_position() 
        QTimer.singleShot(500, self._refresh_view) 

    def _on_cancel_conversions_clicked(self):
        if self.conversion_manager: self.conversion_manager.cancel_all_conversions()

    def _on_video_process_clicked(self):
        selected_objects = self.file_table.get_selected_items_data()
        items_to_process = []
        if not selected_objects:
            QMessageBox.warning(self, "No Selection", "Please select one or more files or directories to process.")
            return
        for obj in selected_objects:
            path_str = obj.get('path')
            is_dir = obj.get('is_dir', False)
            if path_str and os.path.exists(path_str):
                if is_dir: items_to_process.append(obj)
                else:
                    if any(path_str.lower().endswith(ext) for ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.flv', '.wmv', '.mpg', '.mpeg']):
                        items_to_process.append(obj)
        if not items_to_process:
            QMessageBox.information(self, "No Video Files or Directories", "The current selection contains no video files or directories suitable for processing.")
            return
        if not self._current_directory or not self._current_directory.is_dir():
            QMessageBox.critical(self, "Error", "Cannot determine output directory. Please select a valid folder first.")
            return
        dialog = VideoProcessOptionsDialog(self)
        if not dialog.exec(): return
        opts = dialog.get_options()
        do_compress = opts.get('compress', True)
        rotate = opts.get('rotate') 
        if rotate and not do_compress:
            self._rotate_videos_async(items_to_process, rotate)
            return
        output_directory = str(self._current_directory)
        if do_compress: self.video_compression_manager.start_compressions(items_to_process, output_directory, rotate_direction=rotate)
        else: QMessageBox.information(self, "No Action", "No processing option selected.")

    def _rotate_videos_async(self, selected_objects, direction: str):
        from music_player.models.video_file_utils import discover_video_files
        from music_player.models.video_rotation_manager import VideoRotationManager
        paths = []
        for obj in selected_objects:
            path_str = obj.get('path')
            if path_str: paths.append(path_str)
        video_files = discover_video_files(paths)
        if not video_files:
            QMessageBox.information(self, "No Videos", "No video files found in selection.")
            return
        self._rotation_manager = VideoRotationManager(self)
        self.video_compression_progress_overlay.show_rotation_started(len(video_files))
        self._update_video_compression_progress_position()
        self._rotation_manager.rotation_file_started.connect(lambda filename, idx, total: self.video_compression_progress_overlay.show_rotation_file_progress(filename, idx, total, 0.0))
        self._rotation_manager.rotation_file_progress.connect(lambda filename, prog: self.video_compression_progress_overlay.show_rotation_file_progress(filename, 0, 0, prog))
        self._rotation_manager.rotation_file_completed.connect(lambda filename: self.video_compression_progress_overlay.show_rotation_file_completed(filename))
        self._rotation_manager.rotation_file_failed.connect(lambda filename, err: self.video_compression_progress_overlay.show_rotation_file_failed(filename, err))
        self._rotation_manager.rotation_batch_finished.connect(lambda: (self.video_compression_progress_overlay.show_batch_finished(), QTimer.singleShot(500, self._refresh_view)))
        self._rotation_manager.start_rotations(video_files, direction)

    def _on_video_compression_batch_started(self, total_files: int):
        self.video_compression_progress_overlay.show_compression_started(total_files)
        self._update_video_compression_progress_position()
        self.cancel_video_compression_button.show() 

    def _on_video_compression_file_started(self, task_id: str, original_filename: str, file_index: int, total_files: int):
        self.video_compression_progress_overlay.show_file_progress(task_id, os.path.basename(original_filename), file_index, total_files, 0.0)
        self._update_video_compression_progress_position() 

    def _on_video_compression_file_progress(self, task_id: str, percentage: float):
        self.video_compression_progress_overlay.update_current_file_progress(task_id, percentage)

    def _on_video_compression_file_completed(self, task_id: str, original_filename: str, compressed_filename: str):
        self.video_compression_progress_overlay.show_file_completed(os.path.basename(original_filename), os.path.basename(compressed_filename))
        self._update_video_compression_progress_position()

    def _on_video_compression_file_failed(self, task_id: str, original_filename: str, error_message: str):
        self.video_compression_progress_overlay.show_file_failed(os.path.basename(original_filename), error_message)
        self._update_video_compression_progress_position()

    def _on_video_compression_batch_finished(self):
        self.video_compression_progress_overlay.show_batch_finished()
        self.cancel_video_compression_button.hide() 
        self._update_video_compression_progress_position() 
        QTimer.singleShot(500, self._refresh_view) 

    def _on_cancel_video_compressions_clicked(self):
        if self.video_compression_manager: self.video_compression_manager.cancel_all_compressions()

    def _on_douyin_process_clicked(self):
        if not self.file_table.model():
            QMessageBox.warning(self, "No Selection", "No files selected or directory not loaded.")
            return
        selected_objects = self.file_table.get_selected_items_data()
        if not selected_objects:
            QMessageBox.warning(self, "No Selection", "Please select files or directories to process.")
            return
        dialog = DouyinOptionsDialog(self)
        if dialog.exec():
            options = dialog.get_options()
            do_trim = options["do_trim"]
            do_merge = options["do_merge"]
            if not do_trim and not do_merge:
                QMessageBox.information(self, "No Operation", "No operation selected.")
                return
            video_files = []
            for obj in selected_objects:
                path_str = obj.get('path') if isinstance(obj, dict) else str(obj)
                p = Path(path_str)
                if p.is_dir(): video_files.extend(get_all_video_files(str(p)))
                elif p.is_file() and is_video_file(p.name): video_files.append(str(p))
            if not video_files:
                QMessageBox.information(self, "No Videos", "No video files found in selection.")
                return
            output_directory = str(self._current_directory)
            self.douyin_processor.start_processing(video_files, output_directory, do_trim, do_merge)

    def _on_douyin_batch_started(self, total_files: int):
        self.douyin_progress_overlay.show_trimming_started(total_files)
        self._update_douyin_progress_position()

    def _on_douyin_file_started(self, task_id: str, original_filename: str, file_index: int, total_files: int):
        self.douyin_progress_overlay.show_file_progress(task_id, os.path.basename(original_filename), file_index, total_files, 0.0)
        self._update_douyin_progress_position()

    def _on_douyin_file_progress(self, task_id: str, percentage: float):
        self.douyin_progress_overlay.update_current_file_progress(task_id, percentage)

    def _on_douyin_file_completed(self, task_id: str, original_filename: str):
        self.douyin_progress_overlay.show_file_completed(os.path.basename(original_filename), os.path.basename(original_filename))
        self._update_douyin_progress_position()

    def _on_douyin_file_failed(self, task_id: str, original_filename: str, error_message: str):
        self.douyin_progress_overlay.show_file_failed(os.path.basename(original_filename), error_message)
        self._update_douyin_progress_position()

    def _on_douyin_batch_finished(self):
        self.douyin_progress_overlay.show_batch_finished()

    def _on_douyin_merge_started(self):
        self.douyin_progress_overlay.show_merge_started()
        self._update_douyin_progress_position()

    def _on_douyin_merge_progress(self, percent):
        self.douyin_progress_overlay.show_merge_progress(percent)
        self._update_douyin_progress_position()

    def _on_douyin_merge_completed(self, output_filename):
        self.douyin_progress_overlay.show_merge_completed(os.path.basename(output_filename))
        self._update_douyin_progress_position()

    def _on_douyin_merge_failed(self, error):
        self.douyin_progress_overlay.show_merge_failed(error)
        self._update_douyin_progress_position()

    def _on_douyin_process_finished(self):
        self.douyin_progress_overlay.show_process_finished()
        QTimer.singleShot(500, self._refresh_view)

    def _update_douyin_progress_position(self):
        if self.douyin_progress_overlay.isVisible():
            self.douyin_progress_overlay.adjustSize()
            overlay_width = self.douyin_progress_overlay.width()
            overlay_height = self.douyin_progress_overlay.height()
            overlay_x = (self.width() - overlay_width) // 2
            overlay_y = 60
            if self.upload_status.isVisible():
                overlay_y = self.upload_status.y() + self.upload_status.height() + 10
            if self.conversion_progress_overlay.isVisible():
                overlay_y = self.conversion_progress_overlay.y() + self.conversion_progress_overlay.height() + 10
            if self.video_compression_progress_overlay.isVisible():
                overlay_y = self.video_compression_progress_overlay.y() + self.video_compression_progress_overlay.height() + 10
            self.douyin_progress_overlay.move(overlay_x, overlay_y)
            self.douyin_progress_overlay.raise_()

    def _update_conversion_progress_position(self):
        if self.conversion_progress_overlay.isVisible():
            self.conversion_progress_overlay.adjustSize()
            overlay_width = self.conversion_progress_overlay.width()
            overlay_height = self.conversion_progress_overlay.height()
            overlay_x = (self.width() - overlay_width) // 2
            overlay_y = 60 
            if self.upload_status.isVisible():
                overlay_y = self.upload_status.y() + self.upload_status.height() + 10
            self.conversion_progress_overlay.move(overlay_x, overlay_y)
            self.conversion_progress_overlay.raise_()

    def _update_video_compression_progress_position(self):
        if self.video_compression_progress_overlay.isVisible():
            self.video_compression_progress_overlay.adjustSize()
            overlay_width = self.video_compression_progress_overlay.width()
            overlay_height = self.video_compression_progress_overlay.height()
            overlay_x = (self.width() - overlay_width) // 2
            overlay_y = 60 
            if self.upload_status.isVisible():
                overlay_y = self.upload_status.y() + self.upload_status.height() + 10
            if self.conversion_progress_overlay.isVisible():
                overlay_y = self.conversion_progress_overlay.y() + self.conversion_progress_overlay.height() + 10
            self.video_compression_progress_overlay.move(overlay_x, overlay_y)
            self.video_compression_progress_overlay.raise_()
