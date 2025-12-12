from qt_base_app.models.logger import Logger
# music_player/ui/components/browser_components/browser_table.py
import os
import shutil
from pathlib import Path
from typing import List, Optional, Any, Dict

from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QApplication, QWidget, QToolTip
from PyQt6.QtGui import QPainter, QIcon, QHelpEvent
from PyQt6.QtCore import Qt, pyqtSignal, QModelIndex, QObject, QSize, QSortFilterProxyModel, QTimer, QEvent, QPoint, QThreadPool, QRunnable

import qtawesome as qta

from music_player.ui.components.base_table import BaseTableView, BaseTableModel
from qt_base_app.theme.theme_manager import ThemeManager
from music_player.models.file_metadata_utils import (
    get_video_metadata, get_audio_metadata, get_image_metadata,
    is_video_file, is_audio_file, is_image_file
)
from ..custom_tooltip import CustomToolTip

# --- Metadata Worker ---

class MetadataWorker(QRunnable):
    """Worker for fetching file metadata in background."""
    
    def __init__(self, file_path: str, filename: str, callback):
        super().__init__()
        self.file_path = file_path
        self.filename = filename
        self.callback = callback
    
    def run(self):
        """Fetch metadata and call callback with result."""
        try:
            tooltip = None
            if is_video_file(self.filename):
                metadata = get_video_metadata(self.file_path)
                tooltip = f"Dimensions: {metadata.get('dimensions', 'N/A')}\n" \
                          f"Bitrate: {metadata.get('bitrate', 'N/A')}\n" \
                          f"Frame Rate: {metadata.get('frame_rate', 'N/A')}\n" \
                          f"Audio Bitrate: {metadata.get('audio_bitrate', 'N/A')}"
            elif is_audio_file(self.filename):
                metadata = get_audio_metadata(self.file_path)
                tooltip = f"Bitrate: {metadata.get('bitrate', 'N/A')}\n" \
                          f"Audio Bitrate: {metadata.get('audio_bitrate', 'N/A')}"
            elif is_image_file(self.filename):
                metadata = get_image_metadata(self.file_path)
                tooltip = f"Dimensions: {metadata.get('dimensions', 'N/A')}"
            
            # Call callback on main thread
            self.callback(self.file_path, tooltip)
        except Exception as e:
            Logger.instance().error(caller="MetadataWorker", msg=f"[MetadataWorker] Error fetching metadata for {self.file_path}: {e}")
            self.callback(self.file_path, None)

# --- Icon Delegate ---

class IconDelegate(QStyledItemDelegate):
    """
    A delegate to draw file/folder icons in the first column.
    Expects the source object (UserRole) to have an 'is_dir' attribute/key.
    """
    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self.theme = ThemeManager.instance()
        self.folder_icon = qta.icon('fa5s.folder', color=self.theme.get_color('text', 'secondary'))
        self.file_icon = qta.icon('fa5s.file-alt', color=self.theme.get_color('text', 'secondary')) # Use file-alt for regular files
        self.icon_size = 16 # Standard icon size

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        # Ensure we only process the first column (Filename)
        if index.column() == 0:
            painter.save()

            # Get the source object - assumes BaseTableModel provides it via UserRole
            source_object = index.data(Qt.ItemDataRole.UserRole)
            is_dir = False
            if isinstance(source_object, dict):
                is_dir = source_object.get('is_dir', False)
            elif hasattr(source_object, 'is_dir'):
                is_dir = getattr(source_object, 'is_dir', False)
            elif hasattr(source_object, 'is_dir()'): # Handle cases like pathlib.Path
                 try:
                      is_dir = source_object.is_dir()
                 except: pass # Ignore errors if it's not a path-like object

            icon_to_draw = self.folder_icon if is_dir else self.file_icon

            # Calculate icon position (vertically centered, left-aligned with padding)
            icon_rect = option.rect
            icon_x = icon_rect.left() + 5 # Add some padding
            icon_y = icon_rect.top() + (icon_rect.height() - self.icon_size) // 2
            
            # Draw the icon
            icon_to_draw.paint(painter, icon_x, icon_y, self.icon_size, self.icon_size)

            # Adjust the option rect for the text to avoid drawing over the icon
            # Use style primitive to get accurate text margin
            text_margin = QApplication.style().pixelMetric(
                QApplication.style().PixelMetric.PM_FocusFrameHMargin, option, option.widget) + 1
            
            original_text_rect = option.rect.adjusted(self.icon_size + text_margin + 5, 0, 0, 0)
            
            # Temporarily modify the option's rect for the base class painting
            original_option_rect = option.rect
            option.rect = original_text_rect

            # Call the base class paint method to draw the text and handle selection etc.
            # Important: Do this *after* drawing the icon and adjusting the rect
            super().paint(painter, option, index)

            # Restore the original rect if needed elsewhere (though usually not necessary)
            option.rect = original_option_rect

            painter.restore()
        else:
            # For other columns, just use the default painting
            super().paint(painter, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        # Optionally adjust size hint if needed, e.g., to ensure space for icon
        size = super().sizeHint(option, index)
        if index.column() == 0:
            size.setWidth(size.width() + self.icon_size + 5) # Add space for icon and padding
        return size

# --- Browser Table View ---

class BrowserTableView(BaseTableView):
    """
    Subclass of BaseTableView specifically for the file browser.
    Adds icon display, specific double-click handling, and disk deletion logic.
    """
    fileDoubleClicked = pyqtSignal(str) # Emits absolute file path
    directoryDoubleClicked = pyqtSignal(str) # Emits absolute directory path
    # Signal emitted after attempting deletion (count deleted, list of error strings)
    itemsDeletedFromDisk = pyqtSignal(int, list)

    def __init__(self, table_name: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__(table_name=table_name, parent=parent)

        # Set the custom delegate for the first column (Filename)
        self.icon_delegate = IconDelegate(self)
        self.setItemDelegateForColumn(0, self.icon_delegate)
        self.setMouseTracking(True)
        self.viewport().installEventFilter(self)
        self._metadata_cache: Dict[str, Optional[str]] = {}  # Cache formatted tooltips by file path
        self._tooltip_widget = CustomToolTip(self)
        
        # Async metadata handling
        self._thread_pool = QThreadPool()
        self._thread_pool.setMaxThreadCount(2)  # Limit concurrent metadata fetches
        self._pending_requests: Dict[str, bool] = {}  # Track files being processed
        self._prefetch_timer = QTimer()
        self._prefetch_timer.setSingleShot(True)
        self._prefetch_timer.timeout.connect(self._prefetch_visible_metadata)

    # Override mouseDoubleClickEvent for specific actions
    def mouseDoubleClickEvent(self, event):
        index = self.indexAt(event.pos())
        if not index.isValid():
            super().mouseDoubleClickEvent(event) # Allow default handling if click is not on an item
            return

        model = self.model()
        # Ensure it's a model we can get UserRole data from
        if not model:
            super().mouseDoubleClickEvent(event)
            return
            
        source_object = model.data(model.index(index.row(), 0), Qt.ItemDataRole.UserRole)
        if source_object is None:
            super().mouseDoubleClickEvent(event)
            return

        path_str = None
        is_dir = False

        # Extract path and is_dir flag (adapt based on expected source_object type)
        if isinstance(source_object, dict):
            path_str = source_object.get('path')
            is_dir = source_object.get('is_dir', False)
        elif isinstance(source_object, Path): # Handle Path objects directly
             path_str = str(source_object)
             is_dir = source_object.is_dir()
        elif hasattr(source_object, 'path') and hasattr(source_object, 'is_dir'): # Handle objects with attributes
            path_str = getattr(source_object, 'path')
            is_dir = getattr(source_object, 'is_dir', False)
        
        # Check if we got a valid path
        if path_str:
            if is_dir:
                Logger.instance().debug(caller="BrowserTable", msg=f"[BrowserTable] Directory double-clicked: {path_str}")
                self.directoryDoubleClicked.emit(path_str)
            else:
                # Verify it's actually a file on disk before emitting play signal
                if Path(path_str).is_file():
                    Logger.instance().debug(caller="BrowserTable", msg=f"[BrowserTable] File double-clicked: {path_str}")
                    self.fileDoubleClicked.emit(path_str)
                else:
                     Logger.instance().debug(caller="BrowserTable", msg=f"[BrowserTable] Double-clicked non-file/non-existent path: {path_str}")
                     super().mouseDoubleClickEvent(event) # Fallback
            event.accept() # We handled it
        else:
            # If path couldn't be determined, let the base class handle it
             super().mouseDoubleClickEvent(event)


    # Override _on_delete_items to add disk deletion
    def _on_delete_items(self):
        """Handles Delete key press: Deletes from disk first, then asks model to remove rows."""
        proxy_model = self.model() # Get the model assigned to the view (likely the proxy)
        if not proxy_model:
            Logger.instance().debug(caller="BrowserTableView", msg="[BrowserTableView] No model set on the view.")
            return
            
        # --- Access the Source Model --- 
        source_model = None
        if isinstance(proxy_model, QSortFilterProxyModel):
            source_model = proxy_model.sourceModel()
        elif isinstance(proxy_model, BaseTableModel): # Handle case where maybe proxy isn't used
            source_model = proxy_model 
        else:
             Logger.instance().debug(caller="BrowserTableView", msg=f"[BrowserTableView] Unexpected model type ({type(proxy_model)}). Cannot determine source model.")
             return

        if not source_model:
             Logger.instance().debug(caller="BrowserTableView", msg="[BrowserTableView] Could not retrieve source model.")
             return
        # -------------------------------

        # Check if the SOURCE model supports our expected deletion method
        if not (hasattr(source_model, 'remove_rows_by_objects') and callable(source_model.remove_rows_by_objects)):
            Logger.instance().debug(caller="BrowserTableView", msg=f"[BrowserTableView] Source model ({type(source_model)}) does not support 'remove_rows_by_objects'. Cannot perform deletion.")
            return

        selected_objects = self.get_selected_items_data() # This should get data from source model via proxy
        if not selected_objects:
            return

        Logger.instance().debug(caller="BrowserTableView", msg=f"[BrowserTableView] Delete requested for {len(selected_objects)} item(s). Performing disk deletion...")
        deleted_count = 0
        successfully_deleted_objects = []
        error_messages = []

        # --- Perform Disk Deletion --- (Existing logic)
        for obj in selected_objects:
            path_str = None
            is_dir = False
            # Extract path and is_dir flag (consistent with double-click logic)
            if isinstance(obj, dict):
                 path_str = obj.get('path')
                 is_dir = obj.get('is_dir', False)
            elif isinstance(obj, Path):
                 path_str = str(obj)
                 is_dir = obj.is_dir()
            elif hasattr(obj, 'path') and hasattr(obj, 'is_dir'):
                path_str = getattr(obj, 'path')
                is_dir = getattr(obj, 'is_dir', False)

            if not path_str:
                error_messages.append(f"Could not determine path for object: {obj}")
                continue # Skip if path is missing

            try:
                p = Path(path_str)
                if not p.exists():
                     Logger.instance().warning(caller="BrowserTableView", msg=f"[BrowserTableView] Warning: Item not found on disk: {path_str}")
                     # Assume it's already gone, mark for removal from model view
                     successfully_deleted_objects.append(obj)
                     continue

                if is_dir:
                    Logger.instance().debug(caller="BrowserTableView", msg=f"[BrowserTableView] Deleting directory from disk: {path_str}")
                    shutil.rmtree(p)
                    deleted_count += 1
                    successfully_deleted_objects.append(obj) # Add to list for model removal
                else:
                    Logger.instance().debug(caller="BrowserTableView", msg=f"[BrowserTableView] Deleting file from disk: {path_str}")
                    os.remove(p)
                    deleted_count += 1
                    successfully_deleted_objects.append(obj) # Add to list for model removal
            except OSError as e:
                err = f"OS Error deleting {p.name}: {e.strerror}"
                Logger.instance().debug(caller="BrowserTableView", msg=f"[BrowserTableView] {err}")
                error_messages.append(err)
            except Exception as e:
                err = f"Unexpected error deleting {p.name}: {e}"
                Logger.instance().debug(caller="BrowserTableView", msg=f"[BrowserTableView] {err}")
                error_messages.append(err)
        # --- End Disk Deletion ---

        # --- Update Model --- 
        # Ask the SOURCE model to remove only the rows corresponding to successfully deleted objects
        if successfully_deleted_objects:
             Logger.instance().debug(caller="BrowserTableView", msg=f"[BrowserTableView] Requesting source model ({type(source_model)}) to remove {len(successfully_deleted_objects)} rows from view.")
             source_model.remove_rows_by_objects(successfully_deleted_objects) # <-- Call on source_model

        # --- Emit Signal --- 
        # Emit signal regardless of model update success, reporting disk operation results
        self.itemsDeletedFromDisk.emit(deleted_count, error_messages)

        # Note: We do NOT call super()._on_delete_items() here...

    # Removed navigate_to_file, _is_file_in_table, _select_file_by_name
    # These are now handled by BrowserPage due to asynchronous loading

    def scrollContentsBy(self, dx: int, dy: int):
        """Override to trigger metadata prefetching when scrolling."""
        super().scrollContentsBy(dx, dy)
        # Start/restart timer to prefetch metadata after scrolling stops
        self._prefetch_timer.start(100)  # 100ms delay after scroll stops

    def _prefetch_visible_metadata(self):
        """Prefetch metadata for visible rows in the background."""
        # Metadata prefetching disabled to prevent UI blocking
        return

    def _should_fetch_metadata(self, file_path: str, filename: str) -> bool:
        """Check if metadata should be fetched for this file."""
        # Skip if already cached or being processed
        if file_path in self._metadata_cache or file_path in self._pending_requests:
            return False
            
        # Only fetch for supported media files
        return is_video_file(filename) or is_audio_file(filename) or is_image_file(filename)

    def _fetch_metadata_async(self, file_path: str, filename: str):
        """Start async metadata fetch for a file."""
        if file_path in self._pending_requests:
            return
            
        self._pending_requests[file_path] = True
        worker = MetadataWorker(file_path, filename, self._on_metadata_fetched)
        self._thread_pool.start(worker)

    def _on_metadata_fetched(self, file_path: str, tooltip: Optional[str]):
        """Callback when metadata fetch completes."""
        # Remove from pending requests
        self._pending_requests.pop(file_path, None)
        
        # Store in cache
        self._metadata_cache[file_path] = tooltip
        
        # If tooltip widget is currently showing this file, update it
        if hasattr(self, '_current_tooltip_path') and self._current_tooltip_path == file_path:
            if tooltip:
                self._tooltip_widget.setText(tooltip)
                self._tooltip_widget.adjustSize()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Event filter for handling tooltip events on the viewport."""
        # Tooltip functionality disabled to prevent UI blocking
        if obj == self.viewport() and event.type() == QEvent.Type.ToolTip:
            # Hide any existing tooltip and consume the event
            self._tooltip_widget.hide()
            if hasattr(self, '_current_tooltip_path'):
                delattr(self, '_current_tooltip_path')
            return True  # We handled the event (by ignoring it)
        return super().eventFilter(obj, event)

    def _should_show_tooltip(self, filename: str) -> bool:
        """Check if tooltip should be shown for this file type."""
        return is_video_file(filename) or is_audio_file(filename) or is_image_file(filename)

    def _get_formatted_tooltip(self, file_path: str, filename: str) -> Optional[str]:
        """Get the formatted tooltip string for the file."""
        # Return cached value if available
        if file_path in self._metadata_cache:
            return self._metadata_cache[file_path]
        
        # For unsupported file types, return None immediately
        if not self._should_show_tooltip(filename):
            self._metadata_cache[file_path] = None
            return None
            
        # If not cached and is supported type, metadata will be fetched async
        return None

