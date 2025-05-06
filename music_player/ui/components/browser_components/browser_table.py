# music_player/ui/components/browser_components/browser_table.py
import os
import shutil
from pathlib import Path
from typing import List, Optional, Any

from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QApplication, QWidget
from PyQt6.QtGui import QPainter, QIcon
from PyQt6.QtCore import Qt, pyqtSignal, QModelIndex, QObject, QSize, QSortFilterProxyModel, QTimer

import qtawesome as qta

from music_player.ui.components.base_table import BaseTableView, BaseTableModel
from qt_base_app.theme.theme_manager import ThemeManager

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
                print(f"[BrowserTable] Directory double-clicked: {path_str}")
                self.directoryDoubleClicked.emit(path_str)
            else:
                # Verify it's actually a file on disk before emitting play signal
                if Path(path_str).is_file():
                    print(f"[BrowserTable] File double-clicked: {path_str}")
                    self.fileDoubleClicked.emit(path_str)
                else:
                     print(f"[BrowserTable] Double-clicked non-file/non-existent path: {path_str}")
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
            print("[BrowserTableView] No model set on the view.")
            return
            
        # --- Access the Source Model --- 
        source_model = None
        if isinstance(proxy_model, QSortFilterProxyModel):
            source_model = proxy_model.sourceModel()
        elif isinstance(proxy_model, BaseTableModel): # Handle case where maybe proxy isn't used
            source_model = proxy_model 
        else:
             print(f"[BrowserTableView] Unexpected model type ({type(proxy_model)}). Cannot determine source model.")
             return

        if not source_model:
             print("[BrowserTableView] Could not retrieve source model.")
             return
        # -------------------------------

        # Check if the SOURCE model supports our expected deletion method
        if not (hasattr(source_model, 'remove_rows_by_objects') and callable(source_model.remove_rows_by_objects)):
            print(f"[BrowserTableView] Source model ({type(source_model)}) does not support 'remove_rows_by_objects'. Cannot perform deletion.")
            return

        selected_objects = self.get_selected_items_data() # This should get data from source model via proxy
        if not selected_objects:
            return

        print(f"[BrowserTableView] Delete requested for {len(selected_objects)} item(s). Performing disk deletion...")
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
                     print(f"[BrowserTableView] Warning: Item not found on disk: {path_str}")
                     # Assume it's already gone, mark for removal from model view
                     successfully_deleted_objects.append(obj)
                     continue

                if is_dir:
                    print(f"[BrowserTableView] Deleting directory from disk: {path_str}")
                    shutil.rmtree(p)
                    deleted_count += 1
                    successfully_deleted_objects.append(obj) # Add to list for model removal
                else:
                    print(f"[BrowserTableView] Deleting file from disk: {path_str}")
                    os.remove(p)
                    deleted_count += 1
                    successfully_deleted_objects.append(obj) # Add to list for model removal
            except OSError as e:
                err = f"OS Error deleting {p.name}: {e.strerror}"
                print(f"[BrowserTableView] {err}")
                error_messages.append(err)
            except Exception as e:
                err = f"Unexpected error deleting {p.name}: {e}"
                print(f"[BrowserTableView] {err}")
                error_messages.append(err)
        # --- End Disk Deletion ---

        # --- Update Model --- 
        # Ask the SOURCE model to remove only the rows corresponding to successfully deleted objects
        if successfully_deleted_objects:
             print(f"[BrowserTableView] Requesting source model ({type(source_model)}) to remove {len(successfully_deleted_objects)} rows from view.")
             source_model.remove_rows_by_objects(successfully_deleted_objects) # <-- Call on source_model

        # --- Emit Signal --- 
        # Emit signal regardless of model update success, reporting disk operation results
        self.itemsDeletedFromDisk.emit(deleted_count, error_messages)

        # Note: We do NOT call super()._on_delete_items() here...

    # Removed navigate_to_file, _is_file_in_table, _select_file_by_name
    # These are now handled by BrowserPage due to asynchronous loading

