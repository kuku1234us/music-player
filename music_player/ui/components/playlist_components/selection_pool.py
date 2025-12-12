from qt_base_app.models.logger import Logger
# ./music_player/ui/components/playlist_components/selection_pool.py
import os
import time # Import time for throttling
import datetime
from pathlib import Path
from typing import List, Optional, Any # Added Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFileDialog, QAbstractItemView, QMenu, QApplication,
    QComboBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QObject, QThread, QSortFilterProxyModel, QModelIndex
from PyQt6.QtGui import QCursor, QIcon, QMovie # Added QMovie for spinner
import qtawesome as qta

from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.models.settings_manager import SettingsManager, SettingType
from music_player.ui.components.search_field import SearchField
from music_player.ui.components.icon_button import IconButton
from music_player.ai.groq_music_model import GroqMusicModel

# Import BaseTable components
from music_player.ui.components.base_table import BaseTableView, ColumnDefinition
from music_player.models.file_pool_model import FilePoolModel # <-- ADD

# Define common audio file extensions
AUDIO_EXTENSIONS = {
    '.mp3', '.flac', '.wav', '.ogg', '.aac', '.m4a', '.wma', 
    '.opus', '.aiff', '.ape', '.mpc'
}

def format_file_size(size_bytes):
    """Format file size from bytes to human-readable format"""
    if size_bytes is None: return "Unknown"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes/(1024*1024):.1f} MB"
    else:
        return f"{size_bytes/(1024*1024*1024):.1f} GB"

def format_modified_time(mod_time):
    """Format modified time to human-readable format"""
    if not mod_time: return "Unknown"
    try:
      dt = datetime.datetime.fromtimestamp(mod_time)
      return dt.strftime("%Y-%m-%d %H:%M")
    except Exception: return "Invalid Date"

# --- Update Column Definitions ---
pool_col_defs = [
    ColumnDefinition(
        header="Filename",
        data_key=lambda td: Path(td.get('path', '')).name,
        sort_key=lambda td: Path(td.get('path', '')).name.lower(),
        width=300, stretch=1,
        tooltip_key='path'
    ),
    ColumnDefinition(
        header="Size",
        data_key='size_bytes', # Use stored key
        display_formatter=format_file_size,
        sort_key='size_bytes', # Sort by stored key
        width=100,
        alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        sort_role=Qt.ItemDataRole.EditRole
    ),
    ColumnDefinition(
        header="Modified",
        data_key='mod_stamp', # Use stored key
        display_formatter=format_modified_time,
        sort_key='mod_stamp', # Sort by stored key
        width=150,
        sort_role=Qt.ItemDataRole.EditRole
    ),
]

class ClassificationWorker(QObject):
    """Worker object to run AI classification in a separate thread."""
    finished = pyqtSignal(list) # Emits list of matching file paths
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int) # Emits current_processed, total_files

    def __init__(self, model, filenames, config):
        super().__init__()
        self.groq_model = model
        self.filenames = filenames
        self.prompt_config = config
        self.is_cancelled = False # Flag to signal cancellation

    def run(self):
        """Runs the classification task."""
        results = [] # Initialize results
        try:
            # Callback for progress
            def progress_handler(current, total):
                if total > 0:
                    percent = int((current / total) * 100)
                    self.progress.emit(percent, total)

            # Function for the model to check cancellation
            def cancellation_check():
                return self.is_cancelled

            # Call classify_filenames, passing the necessary callbacks
            results = self.groq_model.classify_filenames(
                self.filenames, 
                self.prompt_config,
                worker_cancelled_check=cancellation_check,
                progress_callback=progress_handler,
                # Pass the worker's main error signal directly as the callback for CRITICAL errors
                error_callback=self.error.emit 
            )
            
            # Check cancellation *after* the main call returns
            if self.is_cancelled:
                Logger.instance().debug(caller="Worker", msg="[Worker] Task cancelled after completion.")
                self.finished.emit([]) # Emit empty list if cancelled
            else:
                self.finished.emit(results)
                
        except Exception as e:
            # Catch any other unhandled exception in the worker itself
            Logger.instance().error(caller="Worker", msg=f"[Worker] Unhandled exception: {e}")
            self.error.emit(f"Worker thread error: {e}")
            # Ensure finished is emitted even on unhandled exception, potentially with empty results
            self.finished.emit([]) # Emit empty list on major error

class SelectionPoolWidget(QWidget):
    """
    Widget representing the Selection Pool area in Play Mode.
    Allows staging tracks via DND, Browse, or deletion from playlist.
    """
    # Signal to request adding selected tracks to the main playlist
    add_selected_requested = pyqtSignal(list) # Emits list of track paths
    # Signal to request playing a single file
    play_single_file_requested = pyqtSignal(str) # Emits filepath
    
    def __init__(self, parent=None):
        """
        Initializes the SelectionPoolWidget.

        Args:
            parent (QWidget, optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.setObjectName("selectionPoolWidget")
        
        self.theme = ThemeManager.instance()
        # Remove SettingsManager instance - no longer needed here

        # AI Model Initialization
        self.groq_model: Optional[GroqMusicModel] = None
        self.ai_enabled: bool = False
        self._initialize_ai_model()

        # Threading attributes
        self.classification_thread: Optional[QThread] = None
        self.classification_worker: Optional[ClassificationWorker] = None

        # Model references - Type hint changed
        self.model: Optional[FilePoolModel] = None # <-- Use FilePoolModel type hint
        self.proxy_model: Optional[QSortFilterProxyModel] = None
        
        self._setup_ui()
        self._connect_signals()
        self._populate_ai_prompts() # Populate combo after UI setup
        
    def _initialize_ai_model(self):
        """Initializes the Groq Music Model and checks readiness."""
        try:
            # GroqMusicModel now reads config internally from SettingsManager
            self.groq_model = GroqMusicModel() # No longer pass config
            self.ai_enabled = self.groq_model.api_ready
            if not self.ai_enabled:
                Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] AI features disabled (Groq API not ready).")
        except Exception as e:
            Logger.instance().error(caller="SelectionPool", msg=f"[SelectionPool] Error initializing AI Model: {e}")
            self.ai_enabled = False
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0) # Add some top margin
        layout.setSpacing(8)
        
        # --- Header --- 
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        
        title_label = QLabel("Selection Pool")
        title_label.setStyleSheet(f"""
            color: {self.theme.get_color('text', 'secondary')};
            font-weight: bold;
            font-size: 10pt;
        """)
        
        # Add the SearchField component
        self.search_field = SearchField(placeholder="Filter pool...")
        # Set a maximum width or flexible sizing as needed
        # self.search_field.setMaximumWidth(250) 
        
        # --- AI Controls --- 
        self.ai_prompt_combo = QComboBox()
        self.ai_prompt_combo.setToolTip("Select AI prompt to filter pool")
        self.ai_prompt_combo.setMinimumWidth(150) # Give it some minimum width
        self.ai_prompt_combo.setEnabled(self.ai_enabled)
        header_layout.addWidget(self.ai_prompt_combo)

        self.ai_run_button = IconButton(
            icon_name='fa5s.magic', 
            tooltip='Classify pool using selected AI prompt',
            icon_color_key=('text', 'secondary'), 
            parent=self
        )
        self.ai_run_button.setEnabled(self.ai_enabled)
        header_layout.addWidget(self.ai_run_button)

        self.ai_clear_filter_button = IconButton(
            icon_name='fa5s.times-circle', 
            tooltip='Clear AI filter',
            icon_color_key=('text', 'secondary'),
            parent=self
        )
        self.ai_clear_filter_button.setEnabled(self.ai_enabled) # Enable based on AI readiness
        self.ai_clear_filter_button.hide() # Hide initially
        header_layout.addWidget(self.ai_clear_filter_button)
        # ---------------------

        # Use IconButton for Browse button
        self.browse_button = IconButton(
            icon_name='fa5s.folder-open',
            tooltip="Browse folder to add tracks",
            icon_color_key=('text', 'secondary'), # Match original style
            parent=self
        )
        # Remove old styling for browse_button
        # self.browse_button = QPushButton()
        # self.browse_button.setIcon(qta.icon('fa5s.folder-open'))
        # self.browse_button.setToolTip("Browse folder to add tracks")
        # self.browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        # self.browse_button.setFlat(True)
        # self.browse_button.setIconSize(self.browse_button.sizeHint() / 1.5)
        # self.browse_button.setStyleSheet(f"""
        #     QPushButton {{ border: none; padding: 2px; color: {self.theme.get_color('text', 'secondary')}; }}
        #     QPushButton:hover {{ background-color: {self.theme.get_color('background', 'secondary')}40; border-radius: 3px; }}
        # """)
        
        # Use IconButton for Add button
        self.add_selected_button = IconButton(
            icon_name='fa5s.plus',
            tooltip="Add selected tracks to current playlist",
            icon_color_key=('text', 'secondary'), # Match original style
            parent=self
        )
        # Remove old styling for add_selected_button
        # self.add_selected_button = QPushButton() # Removed text
        # self.add_selected_button.setIcon(qta.icon('fa5s.plus', color=self.theme.get_color('text', 'secondary'))) # Added icon
        # self.add_selected_button.setToolTip("Add selected tracks to current playlist")
        # self.add_selected_button.setFlat(True) # Make flat like browse button
        # self.add_selected_button.setIconSize(self.browse_button.sizeHint() / 1.5) # Use similar icon size
        # self.add_selected_button.setStyleSheet(f""" 
        #     QPushButton {{ border: none; padding: 2px; color: {self.theme.get_color('text', 'secondary')}; }}
        #     QPushButton:hover {{ background-color: {self.theme.get_color('background', 'secondary')}40; border-radius: 3px; }}
        # """) # Applied similar styling
        # self.add_selected_button.setCursor(Qt.CursorShape.PointingHandCursor)

        header_layout.addWidget(title_label)
        # Add the search field next to the title - WITH stretch factor
        header_layout.addWidget(self.search_field, 1) # Re-added stretch factor , 1
        # Add stretch AFTER the search field to push buttons right - REMOVED
        # header_layout.addStretch(1) 
        # header_layout.addStretch(1) # Remove or adjust stretch if needed - Already removed
        header_layout.addWidget(self.browse_button)
        header_layout.addWidget(self.add_selected_button)
        
        # --- Pool Table --- 
        self.pool_table = BaseTableView(table_name="selection_pool_table", parent=self)
        self.pool_table.setObjectName("poolTable") # Use different object name if needed
        # Set context menu policy here if re-enabling later
        self.pool_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pool_table.setMinimumHeight(100) # Give it some initial size
        
        # Add components to main layout
        layout.addLayout(header_layout)
        layout.addWidget(self.pool_table)
        
        # --- Progress Overlay (Re-added for folder scanning) --- 
        self.progress_overlay = QWidget(self.pool_table) # Child of table
        self.progress_overlay.setObjectName("progressOverlay")
        overlay_layout = QVBoxLayout(self.progress_overlay)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_label = QLabel("Processing...")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_label.setStyleSheet("color: white; font-weight: bold;")
        # Optional: Add spinner icon here if needed
        overlay_layout.addWidget(self.progress_label)
        self.progress_overlay.setStyleSheet("background-color: rgba(0, 0, 0, 0.7); border-radius: 4px;")
        self.progress_overlay.hide() # Initially hidden
        
    def _connect_signals(self):
        self.browse_button.clicked.connect(self._browse_folder)
        self.add_selected_button.clicked.connect(self._emit_add_selected)
        self.pool_table.customContextMenuRequested.connect(self._show_context_menu)
        # Connect the search field signal
        self.search_field.textChanged.connect(self._filter_pool_table_proxy)
        # Connect double-click signal
        self.pool_table.doubleClicked.connect(self._on_item_double_clicked)
        # --- Connect AI signals if enabled --- 
        if self.ai_enabled:
             self.ai_run_button.clicked.connect(self._on_classify_requested)
             self.ai_clear_filter_button.clicked.connect(self._clear_ai_filter)

    def _populate_ai_prompts(self):
        """Populates the AI prompt dropdown."""
        if not self.ai_enabled or not self.groq_model:
            self.ai_prompt_combo.addItem("AI Disabled")
            return

        prompt_labels = self.groq_model.get_available_prompts()
        self.ai_prompt_combo.clear()
        self.ai_prompt_combo.addItem("-- Select AI Filter --") # Default/placeholder item
        if prompt_labels:
            self.ai_prompt_combo.addItems(prompt_labels)
        else:
            self.ai_prompt_combo.addItem("No Prompts Found")
            self.ai_prompt_combo.setEnabled(False)
            self.ai_run_button.setEnabled(False)
        
    def _show_context_menu(self, position):
        """Display context menu for selection pool items"""
        if not self.pool_table.model() or self.pool_table.model().rowCount() == 0:
            return
            
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {self.theme.get_color('background', 'primary')};
                color: {self.theme.get_color('text', 'primary')};
                border: 1px solid {self.theme.get_color('border', 'primary')};
                border-radius: 4px;
                padding: 5px;
            }}
            QMenu::item {{
                padding: 5px 15px;
                border-radius: 3px;
            }}
            QMenu::item:selected {{
                background-color: {self.theme.get_color('background', 'secondary')};
            }}
        """)
        
        selected_items = self.pool_table.selectedItems()
        if selected_items:
            # Copy to clipboard action
            copy_action = menu.addAction("Copy Path")
            copy_action.triggered.connect(lambda: self._copy_selected_paths_to_clipboard())
            
            # Remove from selection pool action
            remove_action = menu.addAction("Remove from Selection Pool")
            remove_action.triggered.connect(lambda: self._remove_selected_items())
            
            # Add to playlist action (same as add selected button)
            add_to_playlist_action = menu.addAction("Add to Current Playlist")
            add_to_playlist_action.triggered.connect(self._emit_add_selected)
            
            # Select all action
            menu.addSeparator()
            select_all_action = menu.addAction("Select All")
            select_all_action.triggered.connect(self.pool_table.selectAll)
            
            # Clear selection action
            clear_selection_action = menu.addAction("Clear Selection")
            clear_selection_action.triggered.connect(self.pool_table.clearSelection)
            
            menu.addSeparator()
            # Clear pool action
            clear_pool_action = menu.addAction("Clear Pool")
            clear_pool_action.triggered.connect(self.clear_pool)
        
        menu.exec(QCursor.pos())
        
    def _copy_selected_paths_to_clipboard(self):
        """Copy selected file paths to clipboard"""
        selected_paths = self.get_selected_tracks()
        if selected_paths:
            clipboard = QApplication.clipboard()
            clipboard.setText("\n".join(selected_paths))
            
    def _remove_selected_items(self):
        """Remove selected items from the selection pool"""
        if hasattr(self.pool_table, '_on_delete_items') and callable(self.pool_table._on_delete_items):
            Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] Context menu: Triggering table's delete handler.")
            self.pool_table._on_delete_items()
        else:
            Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] Context menu: Cannot find table's delete handler.")
            # Fallback: Manually remove via model (less ideal as it duplicates logic)
            # selected_paths = self.get_selected_tracks()
            # if selected_paths:
            #     self.remove_tracks(selected_paths)

    def _on_item_double_clicked(self, index: QModelIndex):
        """Handle double-click on an item in the pool table."""
        if not self.proxy_model or not index.isValid():
            return
        # Get source object via proxy model
        source_object = self.proxy_model.data(index, Qt.ItemDataRole.UserRole)
        if isinstance(source_object, dict):
            filepath = source_object.get('path')
            if filepath and os.path.isfile(filepath): # Ensure it's a file
                Logger.instance().debug(caller="SelectionPool", msg=f"[SelectionPool] Double-click detected, requesting single play: {filepath}")
                self.play_single_file_requested.emit(filepath)

    def resizeEvent(self, event):
        """Handle resize to keep overlay positioned correctly."""
        super().resizeEvent(event)
        # Resize overlay to match the table geometry within the widget
        if hasattr(self, 'progress_overlay') and self.progress_overlay.isVisible():
            self.progress_overlay.setGeometry(self.pool_table.geometry())

    # --- AI Classification Methods --- 

    def _on_classify_requested(self):
        """Starts the AI classification process in a background thread."""
        # --- Strict Check: Prevent starting if a thread is already running/cleaning up --- 
        if self.classification_thread is not None:
            Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] Cannot start classification: Previous thread is still active or cleaning up.")
            QMessageBox.warning(self, "Busy", "Please wait for the previous AI task to fully complete.")
            return
        # ------------------------------------------------------------------------------
        
        if not self.ai_enabled or not self.groq_model:
            QMessageBox.warning(self, "AI Feature Disabled", "Groq API is not available or not configured correctly.")
            return

        # Check if a valid prompt is selected
        if self.ai_prompt_combo.currentIndex() == 0:
            QMessageBox.information(self, "Select Prompt", "Please select an AI filter prompt from the dropdown first.")
            return
            
        selected_label = self.ai_prompt_combo.currentText()
        prompt_config = self.groq_model.get_prompt_config_by_label(selected_label)
        if not prompt_config:
            QMessageBox.warning(self, "Prompt Error", f"Could not find configuration for prompt: {selected_label}")
            return
            
        # Get paths from ALL objects in the source model
        all_pool_paths = self.model.get_all_paths() if self.model else []
        if not all_pool_paths:
            QMessageBox.information(self, "Empty Pool", "The selection pool contains no valid paths.")
            return
            
        # --- Change Button State (Start) --- 
        try:
            self.ai_run_button.clicked.disconnect(self._on_classify_requested)
        except TypeError: # Signal not connected
            pass 
        self.ai_run_button.setIcon(qta.icon('fa5s.stop'))
        self.ai_run_button.setToolTip('Stop AI classification')
        try:
            self.ai_run_button.clicked.connect(self._on_stop_classification_requested)
        except TypeError: # Already connected?
            pass
        self.ai_run_button.setEnabled(True) # Keep enabled to allow stopping
        self.ai_prompt_combo.setEnabled(False) # Disable combo during processing
        self.ai_clear_filter_button.setEnabled(False) # Disable clear during processing
        self.search_field.setEnabled(False) # Disable search during processing
        # ------------------------------------
        
        # --- Show Overlay --- 
        self.progress_overlay.setGeometry(self.pool_table.geometry())
        self.progress_label.setText("Starting...") # Initial progress text
        self.progress_overlay.raise_()
        self.progress_overlay.show()
        # --------------------
        
        # --- Start Thread --- 
        self.classification_worker = ClassificationWorker(self.groq_model, all_pool_paths, prompt_config)
        self.classification_thread = QThread()
        self.classification_worker.moveToThread(self.classification_thread)

        # --- Add the missing started signal connection --- 
        self.classification_thread.started.connect(self.classification_worker.run)
        # -------------------------------------------------

        # Connect worker signals to UI slots
        self.classification_worker.finished.connect(self._on_classification_finished)
        self.classification_worker.error.connect(self._on_classification_error)
        self.classification_worker.progress.connect(self._update_progress_text)
        
        # --- Explicitly quit thread when worker is done --- 
        self.classification_worker.finished.connect(self.classification_thread.quit)
        self.classification_worker.error.connect(self.classification_thread.quit)
        # -------------------------------------------------
        
        # Clean up worker and thread AFTER thread finishes
        self.classification_thread.finished.connect(self.classification_worker.deleteLater) 
        # self.classification_thread.finished.connect(self.classification_thread.quit) # Already connected above
        self.classification_thread.finished.connect(self.classification_thread.deleteLater) 
        # Connect thread finished signal to _clear_thread_references (for UI reset and clearing refs)
        self.classification_thread.finished.connect(self._clear_thread_references)

        # Start the thread AFTER storing the reference and connecting signals
        self.classification_thread.start()
        Logger.instance().info(caller="SelectionPool", msg=f"[SelectionPool] Started classification thread for '{selected_label}'.")

    def _on_stop_classification_requested(self):
        """Signals the background worker thread to stop."""
        if hasattr(self, 'classification_thread') and self.classification_thread and self.classification_thread.isRunning():
            if hasattr(self, 'classification_worker') and self.classification_worker:
                Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] Stop requested. Signalling worker...")
                self.classification_worker.is_cancelled = True
                
                # Change button state immediately to indicate request received
                self.ai_run_button.setEnabled(False) # Disable until worker confirms stop
                self.ai_run_button.setToolTip('Stopping...')
            else:
                Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] Stop requested but worker reference is missing.")
        else:
            Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] Stop requested but classification thread is not running.")
            # Might need to reset button state here if thread died unexpectedly?
            self._reset_ai_button_state()

    def _on_classification_finished(self, matching_paths: list):
        """Handles the results when the classification worker finishes."""
        Logger.instance().info(caller="SelectionPool", msg=f"[SelectionPool] Classification finished. Received {len(matching_paths)} matching paths.")
        self.progress_overlay.hide()
        
        if not self.model:
             Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] Model not available to apply filter.")
             self._clear_thread_references() # Ensure UI reset even if model gone
             return
             
        # If worker was cancelled, matching_paths should be empty
        cancelled = False
        if hasattr(self.classification_worker, 'is_cancelled') and self.classification_worker.is_cancelled:
            cancelled = True
            Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] Classification was cancelled by user.")
            # Don't apply filter if cancelled
            self._clear_thread_references() # Reset UI
            return # Stop here

        # Filter the stored unfiltered list based on results
        # matching_paths_set = {os.path.normpath(p) for p in matching_paths}
        # filtered_objects = [obj for obj in all_objects 
        #                     if isinstance(obj, dict) and os.path.normpath(obj.get('path','')) in matching_paths_set]

        # Reset the source model with the filtered list
        if self.model:
            # === Simply call the model's filter method === 
            self.model.apply_path_filter(set(matching_paths))
            # ============================================
            # The model's override handles the path set update
            # View updates automatically because apply_path_filter calls begin/endResetModel
            # Need to check row count *after* filtering
            filtered_row_count = self.model.rowCount() # Get count after filter
            total_row_count = len(self.model.get_all_paths()) # Get total from source
            if filtered_row_count < total_row_count:
                 self.ai_clear_filter_button.show()
            else:
                 self.ai_clear_filter_button.hide()
        else:
             Logger.instance().error(caller="SelectionPool", msg="[SelectionPool] Error: Model is None, cannot apply filter results.")

        # Show clear button if filter resulted in fewer items or none
        # if len(filtered_objects) < len(all_objects):
        #     self.ai_clear_filter_button.show()
        # else:
        #     self.ai_clear_filter_button.hide()
        
        # Clear the stored unfiltered list
        # self._unfiltered_pool_objects = None 
        # UI reset is handled by _clear_thread_references

    def _on_classification_error(self, error_message: str):
        """Handles errors reported by the classification worker."""
        Logger.instance().error(caller="SelectionPool", msg=f"[SelectionPool] Classification error signal received: {error_message}")
        self.progress_overlay.hide()
        QMessageBox.critical(self, "AI Classification Error", error_message)
        # Ensure filter is cleared on error (existing logic)
        if self.model:
            self.model.clear_path_filter()
        self._clear_ai_filter(show_message=False) # Keep this to hide button maybe? Or remove?
                                                   # Let's remove it, model.clear_path_filter handles state.
        # UI reset is handled by _clear_thread_references

    def _update_progress_text(self, percent: int, total: int):
        """Updates the progress label on the overlay."""
        if hasattr(self, 'progress_label'):
            self.progress_label.setText(f"Processing... {percent}% ({total} files)")
            
    def _clear_ai_filter(self, show_message=True): 
        if show_message:
            Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] Clearing AI filter.")
        # === Simply call the model's clear method ===
        if self.model:
             self.model.clear_path_filter()
        # ==========================================
        # Use the stored unfiltered list if available
        # objects_to_restore = self._unfiltered_pool_objects
        # if objects_to_restore is None:
        #      # ... (Fallback logic removed) ...
        # else:
        #      # ... (Restoration logic removed) ...
        
        # Clear the stored list and hide button
        # self._unfiltered_pool_objects = None
        self.ai_clear_filter_button.hide() # Hide button when filter cleared

    def _reset_ai_button_state(self):
        """Resets the Run/Stop AI button to its initial state."""
        if not hasattr(self, 'ai_run_button'): return
        try:
            self.ai_run_button.clicked.disconnect(self._on_stop_classification_requested)
        except TypeError:
            pass # Not connected or already disconnected
        self.ai_run_button.setIcon(qta.icon('fa5s.magic'))
        self.ai_run_button.setToolTip('Classify pool using selected AI prompt')
        try:
            # Only reconnect if not already connected (prevents multiple connections)
            self.ai_run_button.clicked.disconnect(self._on_classify_requested)
        except TypeError:
             pass # Assume it might be disconnected, proceed to connect
        finally: 
             try:
                 self.ai_run_button.clicked.connect(self._on_classify_requested)
             except TypeError:
                 Logger.instance().warning(caller="SelectionPool", msg="[SelectionPool] Warning: Could not reconnect run button signal.")
                 pass # Avoid error if somehow still connected
                 
        self.ai_run_button.setEnabled(self.ai_enabled) 

    def _clear_thread_references(self):
        """Callback solely to clear worker/thread references AND RESET UI after QThread finishes."""
        Logger.instance().info(caller="SelectionPool", msg="[SelectionPool] QThread finished signal received. Clearing references and resetting UI.")
        self.classification_worker = None
        self.classification_thread = None
        # REMOVED: self._unfiltered_pool_objects = None # Clear stored list here too
        # --- Reset UI controls HERE --- 
        self._reset_ai_button_state() # Reset the run/stop button appearance/connections
        self.ai_prompt_combo.setEnabled(self.ai_enabled) # Re-enable combo based on AI status
        self.search_field.setEnabled(True) # Re-enable search field
        # Re-enable clear button only if it's visible
        if not self.ai_clear_filter_button.isHidden():
             self.ai_clear_filter_button.setEnabled(True)

    def add_tracks(self, track_paths: List[str]):
        """
        Adds a list of track file paths to the selection pool, avoiding duplicates.
        
        Args:
            track_paths (List[str]): A list of absolute paths to track files.
        """
        # Determine which paths are genuinely new (not in the model's set)
        new_paths_normalized = []
        if self.model:
             for path_str in track_paths:
                 norm_path = os.path.normpath(path_str)
                 if not self.model.contains_path(norm_path):
                     new_paths_normalized.append(norm_path)
        else:
             # If model doesn't exist, all non-empty paths are potentially new
             new_paths_normalized = [os.path.normpath(p) for p in track_paths if p]
             # We rely on SelectionPoolModel.__init__ to build the initial set
        
        if not new_paths_normalized:
            Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] add_tracks: No new paths to add.")
            return # Nothing new to add

        # Create objects only for the new paths
        new_track_objects = []
        for norm_path in new_paths_normalized:
             # --- Pre-fetch stats --- 
             size_bytes: Optional[int] = None
             mod_stamp: Optional[float] = None
             try:
                 # Check existence before statting
                 p = Path(norm_path)
                 if p.exists():
                     stats = p.stat()
                     size_bytes = stats.st_size
                     mod_stamp = stats.st_mtime
                 else:
                      Logger.instance().warning(caller="SelectionPool", msg=f"[SelectionPool] Warning: File not found when adding to pool: {norm_path}")
             except Exception as e:
                 Logger.instance().error(caller="SelectionPool", msg=f"[SelectionPool] Error stating file {norm_path} on add: {e}")
             # -----------------------
             new_track_objects.append({
                 'path': norm_path,
                 'size_bytes': size_bytes, # Store fetched size (or None)
                 'mod_stamp': mod_stamp    # Store fetched timestamp (or None)
             })

        if not new_track_objects:
             # This case should not happen if new_paths_normalized was non-empty
             Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] add_tracks: No track objects created despite new paths.")
             return 

        if self.model is None:
            # First time adding: Create FilePoolModel
            Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] First tracks added, creating FilePoolModel.")
            self.model = FilePoolModel(source_objects=new_track_objects, column_definitions=pool_col_defs)
            self.proxy_model = QSortFilterProxyModel()
            self.proxy_model.setSourceModel(self.model)
            self.pool_table.setModel(self.proxy_model)
            self.pool_table.resizeRowsToContents()
        else:
            # Model exists: Insert rows using FilePoolModel's insert_rows
            Logger.instance().debug(caller="SelectionPool", msg=f"[SelectionPool] Adding {len(new_track_objects)} tracks to existing model.")
            insert_row_index = self.model.rowCount() # Get row count from potentially filtered model
            if not self.model.insert_rows(insert_row_index, new_track_objects):
                 Logger.instance().error(caller="SelectionPool", msg="[SelectionPool] Error inserting rows into model.")

    def get_selected_tracks(self) -> List[str]:
        """
        Returns a list of full file paths for the currently selected items in the pool.
        """
        if not self.model: # Check if model exists
            return []
        selected_objects = self.pool_table.get_selected_items_data()
        return [obj.get('path', '') for obj in selected_objects if isinstance(obj, dict) and obj.get('path')]
        
    def remove_tracks(self, track_paths: List[str]):
        """
        Removes tracks from the pool based on a list of full file paths.
        """
        if not self.model or not track_paths:
            return
            
        # Find corresponding objects in the model
        paths_to_remove_set = {os.path.normpath(p) for p in track_paths}
        objects_to_remove = []
        all_current_objects = self.model.get_all_objects()
        for obj in all_current_objects:
             if isinstance(obj, dict):
                 obj_path = obj.get('path')
                 if obj_path and os.path.normpath(obj_path) in paths_to_remove_set:
                      objects_to_remove.append(obj)
        
        if objects_to_remove:
            Logger.instance().debug(caller="SelectionPool", msg=f"[SelectionPool] Requesting model remove {len(objects_to_remove)} objects (remove_tracks).")
            # Call the model's method, which now handles the path set
            self.model.remove_rows_by_objects(objects_to_remove)
        else:
            Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] remove_tracks: No matching objects found in model.")

    def clear_pool(self):
        """
        Removes all items from the selection pool table and internal set.
        """
        if self.model:
            Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] Clearing model.")
            self.model.set_source_objects([])
            # Model's override handles clearing the path set
        else:
             Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] Clearing pool (model was already None).")

    def _browse_folder(self):
        """
        Opens a directory dialog and scans the selected folder for media files.
        The last used directory is remembered for future sessions.
        """
        # Get settings instance here
        settings = SettingsManager.instance()
        # Get the last used directory from settings, or default to user's home
        last_dir = settings.get('playlists/last_browse_dir', str(Path.home()), SettingType.PATH)
        
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Folder to Scan",
            str(last_dir),  # Convert Path to string for QFileDialog
            QFileDialog.Option.ShowDirsOnly
        )
        
        if directory:
            # --- Show Overlay --- 
            self.progress_label.setText(f"Scanning {os.path.basename(directory)}...")
            self.progress_overlay.setGeometry(self.pool_table.geometry())
            self.progress_overlay.raise_()
            self.progress_overlay.show()
            QApplication.processEvents() # Allow UI update
            # ------------------
            try:
                # Save the selected directory for next time
                settings.set('playlists/last_browse_dir', directory, SettingType.PATH)
                settings.sync()  # Ensure settings are saved immediately
                
                # --- Get current playlist tracks (if available) --- 
                current_playlist_tracks_set = set()
                try:
                    playlist_playmode_widget = self.parentWidget().parentWidget()
                    if hasattr(playlist_playmode_widget, 'current_playlist') and playlist_playmode_widget.current_playlist:
                        current_playlist_tracks_set = set(os.path.normpath(p.get('path','')) for p in playlist_playmode_widget.current_playlist.tracks if p.get('path'))
                except AttributeError:
                    pass # Ignore if parent cannot be accessed

                found_files_initial = []
                try:
                    for root, _, files in os.walk(directory):
                        for filename in files:
                            if Path(filename).suffix.lower() in AUDIO_EXTENSIONS:
                                full_path = os.path.join(root, filename)
                                found_files_initial.append(full_path)
                except Exception as e:
                    Logger.instance().error(caller="selection_pool", msg=f"Error scanning directory '{directory}': {e}")
                    QMessageBox.warning(self, "Scan Error", f"Could not fully scan directory:\n{e}")
                    # Don't return yet, hide overlay in finally

                # --- Filter and Delete Hidden/Small Files ---
                files_to_add_to_pool = []
                deleted_count = 0
                KB_SIZE = 1024
                # --- Update Overlay Text for Processing --- 
                self.progress_label.setText(f"Processing {len(found_files_initial)} found items...")
                QApplication.processEvents() # Allow UI update
                # -----------------------------------------
                for file_path_str in found_files_initial:
                    try:
                        p = Path(file_path_str)
                        filename = p.name
                        norm_path = os.path.normpath(file_path_str)
                        if norm_path in current_playlist_tracks_set:
                            continue
                        file_size = p.stat().st_size
                        if filename.startswith('._') and file_size < KB_SIZE:
                            try:
                                os.remove(file_path_str)
                                deleted_count += 1
                            except OSError: pass
                        else:
                            files_to_add_to_pool.append(file_path_str)
                    except Exception: pass # Ignore errors for individual files

                if deleted_count > 0:
                    Logger.instance().info(caller="SelectionPool", msg=f"[SelectionPool] Finished cleanup. Deleted {deleted_count} hidden/small files.")
                    
                # Add the filtered list to the pool
                if files_to_add_to_pool:
                    self.add_tracks(files_to_add_to_pool)
                elif not found_files_initial:
                    Logger.instance().debug(caller="selection_pool", msg=f"No audio files found in '{directory}'")
            finally:
                # --- Hide Overlay --- 
                self.progress_overlay.hide()
                # ------------------
                
    def _emit_add_selected(self):
        """
        Emits the signal to add the selected tracks to the main playlist.
        Optionally removes them from the pool after emitting.
        """
        selected_paths = self.get_selected_tracks()
        if selected_paths:
            self.add_selected_requested.emit(selected_paths)

    def _filter_pool_table_proxy(self, text: str):
        """Filters the pool table using the proxy model."""
        if self.proxy_model:
            search_text = text.strip() # No need for lower here if case-insensitive
            # Use setFilterRegularExpression for more flexibility, though setFilterFixedString is simpler
            # For basic contains, regex is fine. Escape special chars if needed.
            # Using regex allows multiple terms maybe? Let's stick to simple contains for now.
            # QSortFilterProxyModel uses QRegularExpression which handles basic patterns well.
            self.proxy_model.setFilterRegularExpression(search_text)
        else:
             Logger.instance().debug(caller="SelectionPool", msg="[SelectionPool] Cannot filter: Proxy model not available.")

