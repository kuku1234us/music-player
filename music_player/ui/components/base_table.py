import os
import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Union, Callable
from dataclasses import dataclass, field # Import dataclass

from PyQt6.QtWidgets import (
    QTableView, QHeaderView, QAbstractItemView, QWidget
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QAbstractTableModel, QModelIndex, QObject, QSortFilterProxyModel
)
from PyQt6.QtGui import QIcon
import qtawesome as qta

from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.models.settings_manager import SettingsManager, SettingType
from qt_base_app.models.logger import Logger

# --- Removed old helper functions and classes ---
# def format_file_size(size_bytes): ...
# def format_modified_time(mod_time): ...
# class SizeAwareTableItem(QTableWidgetItem): ...
# class DateAwareTableItem(QTableWidgetItem): ...

# --- Column Definition ---
@dataclass
class ColumnDefinition:
    """Defines how a column in BaseTable should be displayed and behave."""
    header: str
    # Data key: Attribute/dict key string, or function(object) -> value
    data_key: Union[str, Callable[[Any], Any]]
    # Display formatter: Optional function(value) -> string
    display_formatter: Optional[Callable[[Any], str]] = None
    # Sort key: Optional Attribute/dict key string, or function(object) -> sortable_value
    sort_key: Optional[Union[str, Callable[[Any], Any]]] = None
    # Role to use for sorting data (default: EditRole)
    sort_role: int = Qt.ItemDataRole.EditRole
    # Initial width (optional)
    width: Optional[int] = None
    # Alignment for the text within the cell (default: AlignLeft)
    alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    # Role to use for ToolTip data (default: None, meaning no tooltip from model)
    tooltip_key: Optional[Union[str, Callable[[Any], Any]]] = None
    tooltip_role: int = Qt.ItemDataRole.ToolTipRole
    # Stretch factor (optional) - used by BaseTableView
    stretch: int = 0

# --- Base Table Model ---
class BaseTableModel(QAbstractTableModel):
    """
    A reusable table model that adapts a list of arbitrary Python objects
    for display in a QTableView using ColumnDefinition specifications.
    """

    def __init__(self,
                 source_objects: Optional[List[Any]] = None,
                 column_definitions: Optional[List[ColumnDefinition]] = None,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self._source_objects: List[Any] = source_objects if source_objects is not None else []
        self._column_definitions: List[ColumnDefinition] = column_definitions if column_definitions is not None else []
        self._headers = [cd.header for cd in self._column_definitions]

    @property
    def column_definitions(self) -> List[ColumnDefinition]:
        """Read-only access to column definitions."""
        return self._column_definitions

    def set_source_objects(self, source_objects: List[Any]):
        """Replaces the entire dataset and notifies the view."""
        self.beginResetModel()
        self._source_objects = source_objects if source_objects is not None else []
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        """Returns the number of rows (objects)."""
        return 0 if parent.isValid() else len(self._source_objects)

    def columnCount(self, parent=QModelIndex()) -> int:
        """Returns the number of columns defined."""
        return 0 if parent.isValid() else len(self._column_definitions)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Provides header labels."""
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self._headers):
                return self._headers[section]
        return super().headerData(section, orientation, role)

    def _get_value_from_key(self, obj: Any, key: Union[str, Callable[[Any], Any]]) -> Any:
        """Safely retrieves a value from an object using attribute, key, or callable."""
        try:
            if callable(key): return key(obj)
            if isinstance(key, str):
                if isinstance(obj, dict): return obj.get(key)
                else: return getattr(obj, key, None)
        except Exception as e:
            # print(f"[BaseTableModel] Error getting value for key '{key}': {e}") # Use logging
            pass
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """The core method providing data to the view for different roles."""
        if not index.isValid() or not (0 <= index.row() < len(self._source_objects)):
            return None

        row, col = index.row(), index.column()
        if not (0 <= col < len(self._column_definitions)): return None

        obj = self._source_objects[row]
        col_def = self._column_definitions[col]

        if role == Qt.ItemDataRole.DisplayRole:
            raw_value = self._get_value_from_key(obj, col_def.data_key)
            if col_def.display_formatter:
                try: return col_def.display_formatter(raw_value)
                except Exception: return "FmtErr"
            else:
                return str(raw_value if raw_value is not None else "")

        elif role == col_def.sort_role:
            sort_key = col_def.sort_key if col_def.sort_key is not None else col_def.data_key
            return self._get_value_from_key(obj, sort_key)

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return col_def.alignment

        elif role == col_def.tooltip_role and col_def.tooltip_key:
             tooltip_data = self._get_value_from_key(obj, col_def.tooltip_key)
             return str(tooltip_data) if tooltip_data is not None else None

        elif role == Qt.ItemDataRole.UserRole:
            return obj

        return None

    # --- Data Modification Methods ---
    def update_row_data(self, row: int):
        """Notify views that data for a specific row may have changed."""
        if 0 <= row < self.rowCount():
            start_index = self.index(row, 0)
            end_index = self.index(row, self.columnCount() - 1)
            self.dataChanged.emit(start_index, end_index) # Emit for all roles

    def remove_rows_by_objects(self, objects_to_remove: List[Any]):
        """Removes rows corresponding to the given objects."""
        logger = Logger.instance() # Get logger instance
        logger.debug(f"[BaseTableModel] remove_rows_by_objects called with {len(objects_to_remove)} objects.") # Corrected
        
        if not objects_to_remove: 
            logger.debug("[BaseTableModel] No objects provided for removal.") # Corrected
            return
            
        # Map object IDs to their current row indices
        current_objects_map = {id(obj): i for i, obj in enumerate(self._source_objects)}
        rows_to_remove_indices = []
        
        for obj_to_remove in objects_to_remove:
            row_index = current_objects_map.get(id(obj_to_remove))
            if row_index is not None:
                # Ensure index is still valid (list size might change if duplicates were passed)
                if 0 <= row_index < len(self._source_objects):
                    # Double check the object ID matches at that index now
                    if id(self._source_objects[row_index]) == id(obj_to_remove):
                         rows_to_remove_indices.append(row_index)
                    else:
                         logger.warning(f"[BaseTableModel] Index {row_index} found for object ID {id(obj_to_remove)}, but object ID mismatch occurred later.") # Corrected
                else:
                    logger.warning(f"[BaseTableModel] Index {row_index} found for object ID {id(obj_to_remove)}, but index became invalid.") # Corrected
            else:
                logger.warning(f"[BaseTableModel] Object ID {id(obj_to_remove)} not found in current map.") # Corrected

        if not rows_to_remove_indices:
            logger.debug("[BaseTableModel] No valid row indices found for removal after mapping.") # Corrected
            return

        # Remove duplicates and sort reversed
        unique_rows_to_remove = sorted(list(set(rows_to_remove_indices)), reverse=True)
        logger.debug(f"[BaseTableModel] Attempting to remove rows at indices: {unique_rows_to_remove}") # Corrected

        removed_count = 0
        for row_index in unique_rows_to_remove:
            # Final check before emitting signals and popping
            if 0 <= row_index < len(self._source_objects): 
                logger.debug(f"[BaseTableModel] Emitting beginRemoveRows for index {row_index}") # Corrected
                self.beginRemoveRows(QModelIndex(), row_index, row_index) # SIGNAL 1
                try:
                    removed_obj = self._source_objects.pop(row_index) # <-- THE ACTUAL REMOVAL
                    removed_count += 1
                    logger.debug(f"[BaseTableModel] Popped object from index {row_index}. List size now {len(self._source_objects)}") # Corrected
                except IndexError as e:
                    # Use %s for standard formatting of exception
                    logger.error(f"[BaseTableModel] IndexError trying to pop row {row_index}: %s", e) # Corrected
                finally:
                    self.endRemoveRows() # SIGNAL 2
            else:
                logger.warning(f"[BaseTableModel] Skipping removal for index {row_index} as it became invalid.") # Corrected
        
        logger.debug(f"[BaseTableModel] Finished remove_rows_by_objects. Actually removed {removed_count} items.") # Corrected

    def insert_rows(self, row: int, objects_to_insert: List[Any], parent=QModelIndex()) -> bool:
         """Inserts rows into the model."""
         count = len(objects_to_insert)
         if count <= 0 or row < 0 or row > len(self._source_objects):
             return False

         self.beginInsertRows(parent, row, row + count - 1)
         for i in range(count):
             self._source_objects.insert(row + i, objects_to_insert[i])
         self.endInsertRows()
         return True

    # --- Data Access ---
    def get_object(self, row: int) -> Optional[Any]:
         """Gets the source object at a given row."""
         if 0 <= row < len(self._source_objects):
             return self._source_objects[row]
         return None

    def get_all_objects(self) -> List[Any]:
        """Returns a shallow copy of the internal list of source objects."""
        return list(self._source_objects)

# --- Base Table View ---
class BaseTableView(QTableView):
    """
    A reusable QTableView optimized for use with BaseTableModel.
    Includes styling, persistence for column widths and sort order,
    and basic interaction setup (including Del key handling).
    """
    # Optional signal (could be useful for parent widgets reacting to view-initiated deletion)
    # delete_requested = pyqtSignal(list) # Emits list of source objects requested for deletion
    items_removed = pyqtSignal(list) # Emits list of source objects that were removed

    def __init__(self,
                 table_name: Optional[str] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.table_name = table_name
        self.setObjectName(table_name if table_name else "baseTableView")

        self.theme = ThemeManager.instance()
        self.settings = SettingsManager.instance()

        self._column_definitions: List[ColumnDefinition] = []

        # Internal state for persistence
        self._sort_column = 0
        self._sort_order = Qt.SortOrder.AscendingOrder

        # Sort indicator icons (needed for manual update in case header item doesn't exist yet)
        self.sort_up_icon = qta.icon('fa5s.sort-up', color=self.theme.get_color('text', 'secondary'))
        self.sort_down_icon = qta.icon('fa5s.sort-down', color=self.theme.get_color('text', 'secondary'))


        self._setup_ui()
        self._connect_signals()

    def setModel(self, model: QAbstractTableModel): # Accept any model, but check type
        """Sets the data model and performs necessary setup."""
        old_model = self.model()
        if old_model:
            try: pass # Disconnect signals if needed
            except TypeError: pass

        super().setModel(model)
        self._column_definitions = [] # Reset column definitions

        # Determine the source model and retrieve column definitions
        source_for_defs = None
        if isinstance(model, BaseTableModel):
            source_for_defs = model
            print(f"[BaseTableView] Set model is BaseTableModel: {type(model)}") # Debug
        elif isinstance(model, QSortFilterProxyModel):
            print(f"[BaseTableView] Set model is QSortFilterProxyModel: {type(model)}") # Debug
            source_model = model.sourceModel()
            if isinstance(source_model, BaseTableModel):
                source_for_defs = source_model
                print(f"[BaseTableView] Proxy source model is BaseTableModel: {type(source_model)}") # Debug
            else:
                print(f"[BaseTableView] Warning: Proxy source model is NOT BaseTableModel ({type(source_model)}). Persistence/Features limited.")
        else:
            if model is not None:
                 print(f"[BaseTableView] Warning: Using non-BaseTableModel/Proxy model ({type(model)}). Persistence/Features may be limited.")

        # Store column definitions if found
        if source_for_defs:
            self._column_definitions = source_for_defs.column_definitions
            print(f"[BaseTableView] Stored {len(self._column_definitions)} column definitions.") # Debug
        else:
             print("[BaseTableView] No column definitions stored.") # Debug

        # Load persistent state or apply defaults (now uses potentially loaded definitions)
        if self.table_name:
            self._load_table_state()
        else:
            self._apply_default_widths()

        # Apply loaded sort order to the view's header AND trigger initial sort
        if model and model.rowCount() > 0 and self.isSortingEnabled():
            self.sortByColumn(self._sort_column, self._sort_order)

        self._update_sort_indicator() # Set initial indicator

    def _apply_default_widths(self):
        """Applies initial widths defined in column definitions or a fallback."""
        if not self._column_definitions or not self.model(): return
        fallback_width = 150
        header = self.horizontalHeader()
        col_count = self.model().columnCount()
        for i in range(col_count):
             # Check if column index is valid for definitions list
             if i < len(self._column_definitions):
                 col_def = self._column_definitions[i]
                 width = col_def.width if col_def.width is not None else fallback_width
                 header.resizeSection(i, width)
                 resize_mode = QHeaderView.ResizeMode.Stretch if col_def.stretch > 0 else QHeaderView.ResizeMode.Interactive
                 header.setSectionResizeMode(i, resize_mode)
             else: # Fallback if column count from model > len(col_defs)
                 header.resizeSection(i, fallback_width)
                 header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)


    def _setup_ui(self):
        """Configure the basic appearance and behavior of the view."""
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(False)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.verticalHeader().setDefaultSectionSize(22)
        self.setSortingEnabled(True) # Enable header click sorting
        self.horizontalHeader().setSectionsClickable(True)

        # Styling (Same as documentation)
        self.setStyleSheet(f"""
            QTableView {{
                background-color: {self.theme.get_color('background', 'primary')};
                alternate-background-color: {self.theme.get_color('background', 'alternate_row')};
                border: 1px solid {self.theme.get_color('border', 'primary')};
                border-radius: 4px;
                selection-background-color: {self.theme.get_color('background', 'selected_row')};
                selection-color: {self.theme.get_color('text', 'selected_row')};
                gridline-color: transparent;
            }}
             QTableView::item {{
                 padding: 0px 8px;
                 border: none;
                 color: {self.theme.get_color('text', 'primary')};
                 background-color: transparent;
             }}
             QTableView::item:selected {{
                 background-color: {self.theme.get_color('background', 'selected_row')};
             }}
            QHeaderView::section {{
                background-color: {self.theme.get_color('background', 'tertiary')};
                color: {self.theme.get_color('text', 'secondary')};
                padding: 0px 8px; height: 24px; border: none;
                border-bottom: 1px solid {self.theme.get_color('border', 'secondary')};
                border-right: 1px solid {self.theme.get_color('border', 'secondary')};
            }}
            QHeaderView::section:last {{ border-right: none; }}
            QHeaderView::section:hover {{ background-color: {self.theme.get_color('background', 'quaternary')}; }}
        """)

    def _connect_signals(self):
        """Connect signals for resizing and sorting."""
        header = self.horizontalHeader()
        if self.table_name:
            header.sectionResized.connect(self._on_column_resized)
        header.sortIndicatorChanged.connect(self._on_sort_indicator_changed)

    def _on_column_resized(self, logicalIndex: int, oldSize: int, newSize: int):
        """Save table state when column width changes."""
        if self.table_name:
            self._save_table_state() # Save widths and current sort state

    def _on_sort_indicator_changed(self, logicalIndex: int, order: Qt.SortOrder):
        """Slot connected to header's sortIndicatorChanged signal."""
        # print(f"[{self.table_name}] Sort indicator changed: Col={logicalIndex}, Order={order}")
        self._sort_column = logicalIndex
        self._sort_order = order
        # --- ADD Persistence --- 
        # Save the new sort state immediately
        if self.table_name:
            key_base = self._get_table_state_setting_key()
            print(f"[{self.table_name}] Saving sort state: Col={self._sort_column}, Order={self._sort_order.name}")
            self.settings.set(f"{key_base}/sort_column", self._sort_column, SettingType.INT)
            self.settings.set(f"{key_base}/sort_order", self._sort_order.value, SettingType.INT) # Store enum value as int
            self.settings.sync() # Persist change immediately
        # ----------------------
        # No need to call _save_table_state() here, as that saves widths too.
        # We only need to save the sort order when it changes.

    def _update_sort_indicator(self):
         """Sets the visual sort indicator on the header."""
         self.horizontalHeader().setSortIndicator(self._sort_column, self._sort_order)


    # --- Persistence Methods ---
    def _get_table_state_setting_key(self) -> str:
        if not self.table_name: return ""
        safe_table_name = ''.join(c if c.isalnum() else '_' for c in self.table_name)
        return f'ui/tables/{safe_table_name}/state'

    def _save_table_state(self):
        """Save current table state (widths and sort order) to settings."""
        key = self._get_table_state_setting_key()
        if not key or not self.model(): return

        header = self.horizontalHeader()
        col_count = self.model().columnCount()
        # Ensure header sections match model columns before saving
        if header.count() != col_count:
             print(f"[BaseTableView] Warning: Header count ({header.count()}) != Model column count ({col_count}). Skipping state save.")
             return

        column_widths = { f'col_{i}': header.sectionSize(i) for i in range(col_count) }
        sort_state = { 'column': self._sort_column, 'order': int(self._sort_order.value) }
        table_state = { 'column_widths': column_widths, 'sort_state': sort_state }
        self.settings.set(key, table_state, SettingType.DICT)

    def _load_table_state(self):
        """Load table state (widths and sort order) from settings."""
        key = self._get_table_state_setting_key()
        # Ensure model and definitions are ready before loading
        if not key or not self.model() or not self._column_definitions:
            self._sort_column = 0
            self._sort_order = Qt.SortOrder.AscendingOrder
            self._apply_default_widths()
            return

        col_count = self.model().columnCount()
        # Check consistency
        if col_count != len(self._column_definitions):
             print(f"[BaseTableView] Warning: Model column count ({col_count}) != Column definitions ({len(self._column_definitions)}). Using default state.")
             self._sort_column = 0
             self._sort_order = Qt.SortOrder.AscendingOrder
             self._apply_default_widths()
             return

        default_widths = {f'col_{i}': cd.width if cd.width is not None else 150
                          for i, cd in enumerate(self._column_definitions)}
        default_sort_state = {'column': 0, 'order': 0}
        default_table_state = {'column_widths': default_widths, 'sort_state': default_sort_state}

        table_state = self.settings.get(key, default_table_state, SettingType.DICT)
        column_widths = table_state.get('column_widths', default_widths)
        sort_state = table_state.get('sort_state', default_sort_state)

        # Apply loaded/default widths
        header = self.horizontalHeader()
        for i in range(col_count):
            col_key = f'col_{i}'
            width = column_widths.get(col_key, default_widths.get(col_key, 150))
            header.resizeSection(i, width)

        # Load sort state into internal variables
        loaded_sort_col = sort_state.get('column', default_sort_state['column'])
        loaded_sort_order_val = sort_state.get('order', default_sort_state['order'])

        self._sort_column = loaded_sort_col if 0 <= loaded_sort_col < col_count else default_sort_state['column']
        try: self._sort_order = Qt.SortOrder(loaded_sort_order_val)
        except ValueError: self._sort_order = Qt.SortOrder(default_sort_state['order'])

        # Sort indicator is updated in setModel after loading state


    # --- Key Press Handling ---
    def keyPressEvent(self, event):
        """Handle key press events, specifically the Delete key."""
        if event.key() == Qt.Key.Key_Delete:
            # Check selection model validity before accessing
            sel_model = self.selectionModel()
            if self.hasFocus() and sel_model and sel_model.hasSelection():
                self._on_delete_items()
                event.accept()
                return
        super().keyPressEvent(event)

    def _on_delete_items(self):
        """Handles item deletion request by asking the model."""
        view_model = self.model() # This could be the source or the proxy
        if not view_model:
            print("[BaseTableView] Cannot delete: No model set.")
            return

        # Determine the actual source model where remove_rows_by_objects lives
        source_model = None
        if isinstance(view_model, QSortFilterProxyModel):
            source_model = view_model.sourceModel()
            print(f"[BaseTableView] Delete target is source model via proxy: {type(source_model)}")
        else:
            source_model = view_model # View model is the source model
            print(f"[BaseTableView] Delete target is direct model: {type(source_model)}")

        # Check if the *source* model supports the deletion method
        if not (source_model and hasattr(source_model, 'remove_rows_by_objects') and callable(source_model.remove_rows_by_objects)):
            print(f"[BaseTableView] Source model ({type(source_model)}) does not support 'remove_rows_by_objects'.")
            return

        objects_to_delete = self.get_selected_items_data() # This now handles proxy mapping
        if objects_to_delete:
            print(f"[BaseTableView] Requesting source model to delete {len(objects_to_delete)} object(s).")
            source_model.remove_rows_by_objects(objects_to_delete)
            self.items_removed.emit(objects_to_delete)

    # --- Utility methods ---
    def get_selected_items_data(self) -> List[Any]:
         """Returns a list of source objects for the selected rows."""
         view_model = self.model()
         sel_model = self.selectionModel()
         if not view_model or not sel_model: return []

         selected_data = []
         is_proxy = isinstance(view_model, QSortFilterProxyModel)
         source_model = view_model.sourceModel() if is_proxy else view_model

         if not source_model:
             print("[BaseTableView] Cannot get selected data: Source model not found.")
             return []

         # Use selectedRows() which gives indices relative to the view_model
         for view_index in sel_model.selectedRows():
             # Map view index to source index if using a proxy
             source_index = view_model.mapToSource(view_index) if is_proxy else view_index
             # Get the object from the SOURCE model using the SOURCE index
             obj = source_model.data(source_index, Qt.ItemDataRole.UserRole)
             if obj is not None:
                 # Check for duplicates just in case selectedRows gives multiple indices for same logical row sometimes
                 # Using id() might be safer if objects are mutable and hash changes
                 is_duplicate = False
                 obj_id = id(obj)
                 for existing_obj in selected_data:
                     if id(existing_obj) == obj_id:
                         is_duplicate = True
                         break
                 if not is_duplicate:
                      selected_data.append(obj)
         return selected_data

    def get_all_items_data(self) -> List[Any]:
         """Returns a list of source objects for all rows currently in the model.

           Note: This returns data in the model's internal order, which might
           differ from the view's display order if sorting/filtering is applied
           via a proxy model.
         """
         model = self.model()
         # If model has a specific method, use it
         if hasattr(model, 'get_all_objects') and callable(model.get_all_objects):
             return model.get_all_objects()
         # Fallback: iterate through model indices
         elif model:
             return [model.data(model.index(r, 0), Qt.ItemDataRole.UserRole) for r in range(model.rowCount())]
         return []

    def get_visible_items_data_in_order(self) -> List[Any]:
        """Returns a list of source objects for all rows IN THE CURRENT DISPLAY ORDER.

        This accounts for sorting/filtering applied by the view or proxy model.
        """
        model = self.model() # Could be BaseTableModel or QSortFilterProxyModel
        if not model: return []

        ordered_data = []
        for visual_row in range(model.rowCount()): # Iterate visual rows presented by model()
             # Get the index for the first column of the visual row
             visual_index = model.index(visual_row, 0)
             # Retrieve the source object using UserRole
             # The model (or proxy) handles mapping the visual index to the source if necessary
             obj = model.data(visual_index, Qt.ItemDataRole.UserRole)
             if obj is not None:
                 ordered_data.append(obj)
             # Else: row might be filtered out or UserRole not set, skip it.
        return ordered_data


# --- Remove old BaseTable(QTableWidget) class ---
# class BaseTable(QTableWidget):
#    ... (all the old implementation) ...

