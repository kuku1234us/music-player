from qt_base_app.models.logger import Logger
# music_player/models/file_pool_model.py
import os
from typing import List, Optional, Any, Set

from PyQt6.QtCore import QModelIndex

# Import BaseTableModel - adjust path if necessary based on actual location
from music_player.ui.components.base_table import BaseTableModel, ColumnDefinition
from qt_base_app.models.logger import Logger # Import Logger

class FilePoolModel(BaseTableModel):
    """
    A base table model for managing items representing files.
    Maintains the list of source objects and a synchronized internal set of paths
    for efficient checking. Includes optional path-based filtering.
    Assumes source objects are dictionaries containing at least a 'path' key.
    """
    def __init__(self,
                 source_objects: Optional[List[Any]] = None,
                 column_definitions: Optional[List[ColumnDefinition]] = None,
                 parent: Optional[Any] = None):
        
        logger = Logger.instance() # Get logger
        # Initialize the internal path set before calling super()
        self._pool_paths: Set[str] = set()
        # --- Add Filtering State --- 
        self._is_path_filtered: bool = False
        self._allowed_paths: Set[str] = set()
        self._filtered_indices_map: List[int] = []
        # -------------------------
        
        logger.debug(self.__class__.__name__, f"[FilePoolModel.__init__] Initializing. Provided source_objects count: {len(source_objects) if source_objects else 0}")
        # Note: super().__init__ will call our overridden set_source_objects if source_objects is provided
        #       Correction: BaseTableModel.__init__ does NOT call set_source_objects.
        super().__init__(source_objects, column_definitions, parent)
        logger.debug(self.__class__.__name__, f"[FilePoolModel.__init__] After super().__init__. _source_objects count: {len(self._source_objects)}")
        
        # --- Explicitly rebuild path set AFTER super() sets _source_objects --- 
        if self._source_objects: # Only rebuild if super() actually set objects
            logger.debug(self.__class__.__name__, "[FilePoolModel.__init__] Calling _rebuild_path_set from __init__.")
            self._rebuild_path_set(self._source_objects)
            logger.debug(self.__class__.__name__, f"[FilePoolModel.__init__] Path set rebuilt. Size: {len(self._pool_paths)}")
        # ---------------------------------------------------------------------
        
        # Initialize map *after* super() has potentially set source_objects
        # AND after path set is rebuilt (if needed)
        if not self._is_path_filtered:
            self._filtered_indices_map = list(range(len(self._source_objects)))

    def _get_path_from_obj(self, obj: Any) -> Optional[str]:
        """Safely gets the normalized path from a source object."""
        if isinstance(obj, dict):
            path = obj.get('path')
            if path:
                return os.path.normpath(str(path))
        return None

    def _rebuild_path_set(self, objects_list: List[Any]):
        """Helper to rebuild the internal path set from a list of objects."""
        logger = Logger.instance()
        logger.debug(self.__class__.__name__, f"[FilePoolModel._rebuild_path_set] Rebuilding path set from {len(objects_list)} objects.")
        self._pool_paths.clear()
        added_count = 0
        for obj in objects_list:
            norm_path = self._get_path_from_obj(obj)
            if norm_path:
                self._pool_paths.add(norm_path)
                added_count += 1
        logger.debug(self.__class__.__name__, f"[FilePoolModel._rebuild_path_set] Finished rebuilding. Added {added_count} unique paths. Set size: {len(self._pool_paths)}")

    def _rebuild_filter_map(self):
        """Rebuilds the mapping from filtered rows to source rows."""
        self._filtered_indices_map.clear()
        if not self._is_path_filtered:
            self._filtered_indices_map = list(range(len(self._source_objects)))
        else:
            for i, obj in enumerate(self._source_objects):
                norm_path = self._get_path_from_obj(obj)
                if norm_path and norm_path in self._allowed_paths:
                    self._filtered_indices_map.append(i)

    # --- Overridden Methods to sync _pool_paths AND handle filtering ---

    def set_source_objects(self, source_objects: List[Any]):
        """Replaces the entire dataset, rebuilds the path set, and clears any active filter."""
        self.beginResetModel() # Reset model at the start
        self._rebuild_path_set(source_objects)
        # Assign directly to internal list
        self._source_objects = source_objects if source_objects is not None else []
        # Clear filter state
        self._is_path_filtered = False
        self._allowed_paths.clear()
        self._rebuild_filter_map() # Rebuild map for new unfiltered data
        self.endResetModel()

    def insert_rows(self, row: int, objects_to_insert: List[Any], parent=QModelIndex()) -> bool:
        """Inserts rows, updates path set, and resets model if filtered."""
        # Determine insertion point in source list
        source_insert_row = self.map_to_source_row(row) if self._is_path_filtered else row
        source_insert_row = max(0, min(source_insert_row, len(self._source_objects)))

        paths_added_to_set = set()
        valid_objects_to_insert = []
        for obj in objects_to_insert:
            norm_path = self._get_path_from_obj(obj)
            if norm_path and norm_path not in self._pool_paths:
                paths_added_to_set.add(norm_path)
                valid_objects_to_insert.append(obj)
        
        if not valid_objects_to_insert:
            return False

        # === Call Parent First to emit correct signals ===
        # BaseTableModel handles list insertion and begin/endInsertRows
        success = super().insert_rows(source_insert_row, valid_objects_to_insert, parent)
        # ================================================

        if success:
            # Update our path set to match
            self._pool_paths.update(paths_added_to_set)
            # If filtered, the structure changed, so reset is needed for the map
            if self._is_path_filtered:
                self.beginResetModel()
                self._rebuild_filter_map()
                self.endResetModel()
        # else: If parent failed, set is not updated, signals not emitted by parent.
            
        return success

    def remove_rows_by_objects(self, objects_to_remove: List[Any]):
        """Removes rows corresponding to the given objects, syncing path set and filter."""
        logger = Logger.instance()
        logger.debug(self.__class__.__name__, f"[FilePoolModel] remove_rows_by_objects called with {len(objects_to_remove)} objects.")

        if not objects_to_remove:
            logger.debug(self.__class__.__name__, "[FilePoolModel] No objects provided for removal.")
            return
            
        # --- Identify paths to remove BEFORE calling super() --- 
        # We need this *before* the objects are removed from the source list
        paths_to_remove_from_set = set()
        valid_objects_for_super = [] # Store objects confirmed to be in the model
        current_objects_map = {id(obj): i for i, obj in enumerate(self._source_objects)}
        
        for obj_to_remove in objects_to_remove:
            if id(obj_to_remove) in current_objects_map: # Check if object exists in source
                norm_path = self._get_path_from_obj(obj_to_remove)
                if norm_path:
                    paths_to_remove_from_set.add(norm_path)
                valid_objects_for_super.append(obj_to_remove) # Add to list for super()
            else:
                logger.warning(self.__class__.__name__, f"[FilePoolModel] Attempted to remove object ID {id(obj_to_remove)} which is not in _source_objects.")
                
        if not valid_objects_for_super:
            logger.debug(self.__class__.__name__, "[FilePoolModel] No valid objects found to pass to super().remove_rows_by_objects.")
            return
        # ------------------------------------------------------

        logger.debug(self.__class__.__name__, f"[FilePoolModel] Calling super().remove_rows_by_objects with {len(valid_objects_for_super)} valid objects.")
        try:
            # Let the parent handle the actual removal from _source_objects and signals
            super().remove_rows_by_objects(valid_objects_for_super)
            logger.debug(self.__class__.__name__, "[FilePoolModel] super().remove_rows_by_objects finished.")
        except Exception as e:
            logger.exception(self.__class__.__name__, f"[FilePoolModel] EXCEPTION during super().remove_rows_by_objects: %s", e)
            return # Don't proceed with path/filter updates if super failed

        # --- Sync path set and filter map AFTER successful removal --- 
        logger.debug(self.__class__.__name__, f"[FilePoolModel] _source_objects size AFTER super(): {len(self._source_objects)}")
        logger.debug(self.__class__.__name__, f"[FilePoolModel] _pool_paths size BEFORE sync: {len(self._pool_paths)}. Removing {len(paths_to_remove_from_set)} paths.")
        self._pool_paths -= paths_to_remove_from_set # Remove identified paths
        logger.debug(self.__class__.__name__, f"[FilePoolModel] _pool_paths size AFTER sync: {len(self._pool_paths)}")
        
        # Rebuild filter map if filter is active
        if self._is_path_filtered:
            logger.debug(self.__class__.__name__, "[FilePoolModel] Filter active, resetting model after removal.")
            self.beginResetModel() # Filter map change requires full reset
            logger.debug(self.__class__.__name__, f"[FilePoolModel] _filtered_indices_map size BEFORE rebuild: {len(self._filtered_indices_map)}")
            self._rebuild_filter_map()
            logger.debug(self.__class__.__name__, f"[FilePoolModel] _filtered_indices_map size AFTER rebuild: {len(self._filtered_indices_map)}")
            self.endResetModel()
        else: 
            logger.debug(self.__class__.__name__, "[FilePoolModel] Not filtered, relying on parent signals for removal update.")
        # ----------------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        """Returns the number of rows, considering the filter."""
        if parent.isValid():
            return 0
        return len(self._filtered_indices_map) if self._is_path_filtered else len(self._source_objects)

    def map_to_source_row(self, view_row: int) -> int:
        """Maps a visible row index (when filtered) to the source list index."""
        if self._is_path_filtered:
            if 0 <= view_row < len(self._filtered_indices_map):
                return self._filtered_indices_map[view_row]
            else:
                return -1 # Invalid view row
        else:
            return view_row # 1:1 mapping when not filtered

    def data(self, index: QModelIndex, role: int = ...) -> Any:
        """Returns data for the given index, mapping row if filtered."""
        if not index.isValid(): return None
        source_row = self.map_to_source_row(index.row())
        if source_row == -1: return None
        # Create index for the source row to pass to super()
        source_index = self.createIndex(source_row, index.column(), index.internalPointer())
        return super().data(source_index, role)

    # --- Path Filtering Methods --- 

    def apply_path_filter(self, allowed_paths: Set[str]):
        """Filters the model to only show items whose paths are in allowed_paths."""
        # Normalize the input paths immediately
        normalized_allowed = {os.path.normpath(p) for p in allowed_paths}
        Logger.instance().debug(caller="FilePoolModel", msg=f"[FilePoolModel] Applying path filter with {len(normalized_allowed)} allowed paths.")
        self.beginResetModel()
        self._is_path_filtered = True
        self._allowed_paths = normalized_allowed
        self._rebuild_filter_map()
        self.endResetModel()
        Logger.instance().debug(caller="FilePoolModel", msg=f"[FilePoolModel] Path filter applied. Filtered row count: {self.rowCount()}")

    def clear_path_filter(self):
        """Removes the path filter, showing all items."""
        if not self._is_path_filtered:
            return # Nothing to clear
        Logger.instance().debug(caller="FilePoolModel", msg="[FilePoolModel] Clearing path filter.")
        self.beginResetModel()
        self._is_path_filtered = False
        self._allowed_paths.clear()
        self._rebuild_filter_map() # Rebuilds to 1:1 map
        self.endResetModel()
        Logger.instance().debug(caller="FilePoolModel", msg=f"[FilePoolModel] Path filter cleared. Row count: {self.rowCount()}")

    def is_path_filtered(self) -> bool:
        """Returns True if a path filter is currently active."""
        return self._is_path_filtered

    # --- Existing Helper Methods ---

    def contains_path(self, path_str: str) -> bool:
        """Checks if a normalized path exists in the internal set."""
        return os.path.normpath(path_str) in self._pool_paths

    def get_all_paths(self) -> List[str]:
        """Returns a list of all unique normalized paths currently in the model."""
        return list(self._pool_paths) 