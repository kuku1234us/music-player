from typing import TypedDict, List, Optional, Literal, Any
from pathlib import Path
from PyQt6.QtCore import QRect, QSize, Qt, QAbstractTableModel, QModelIndex, pyqtSignal
from PyQt6.QtGui import QImage

from music_player.ui.components.base_table import BaseTableView
from music_player.ui.components.base_table import BaseTableModel

class VidProcItem(TypedDict):
    path: Path
    title: str            # display name
    size_in: QSize        # W×H from ffprobe
    fps: float
    duration: float
    codec_v: str
    codec_a: Optional[str]
    
    # User controls
    split: int            # e.g., 3 (required)
    tile_index: int       # 0-based index of selected tile
    x_offset: int         # pixels relative to selected tile's left
    width_delta: int      # pixels added to the tile width
    preview_time: float   # timestamp for preview generation (seconds)
    
    # Derived
    crop_rect: QRect      # computed from split/tile_index/x/width_delta
    out_size: QSize       # final portrait size
    
    included: bool
    status: Literal['pending', 'processing', 'ok', 'error', 'skipped']
    out_path: Optional[Path]
    log_tail: str
    
    # Cache for images
    thumb_in: Optional[QImage]
    thumb_out: Optional[QImage]

def calculate_default_tile_index(split: int) -> int:
    """Calculate default tile index based on split value."""
    split = max(1, split)
    # If split is odd (e.g. 3), pick middle (1).
    # If split is even (e.g. 2), pick right of middle (1).
    # split 1 -> idx 0
    # split 2 -> idx 1
    # split 3 -> idx 1
    # split 4 -> idx 2
    # Formula: split // 2
    return split // 2

def calculate_crop_rect(item: VidProcItem) -> QRect:
    """Calculate the crop rectangle based on item fields."""
    W = item['size_in'].width()
    H = item['size_in'].height()
    S = max(1, item['split'])
    Tw = int(W / S)
    
    # Clamp index to valid range
    idx = max(0, min(item['tile_index'], S - 1))
        
    # Effective tile width
    Wtile = Tw + item['width_delta']
    
    # Tile X
    base_x = Tw * idx
    x = base_x + item['x_offset']
    
    # Portrait lock 9:16
    out_w = min(Wtile, int(H * 9 / 16))
    out_h = min(H, int(Wtile * 16 / 9))
    
    # Center within the tile
    x2 = x + (Wtile - out_w) // 2
    y2 = (H - out_h) // 2
    
    return QRect(int(x2), int(y2), int(out_w), int(out_h))

class VidProcTableModel(BaseTableModel):
    # Custom roles
    RoleThumbIn = Qt.ItemDataRole.UserRole + 1
    RoleThumbOut = Qt.ItemDataRole.UserRole + 2
    RoleControls = Qt.ItemDataRole.UserRole + 3
    RoleStatus = Qt.ItemDataRole.UserRole + 4
    RoleObject = Qt.ItemDataRole.UserRole + 5 # For accessing the full item

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[VidProcItem] = []
        
        # Define columns
        self.columns = [
            "Include", 
            "Original", 
            "Title & Info", 
            "Controls", 
            "Preview", 
            "Status"
        ]

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._items)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
            
        item = self._items[index.row()]
        col = index.column()

        if role == self.RoleObject:
            return item

        # Include Column (Checkbox)
        if col == 0:
            if role == Qt.ItemDataRole.CheckStateRole:
                return Qt.CheckState.Checked if item['included'] else Qt.CheckState.Unchecked
            return None

        # Original Thumb
        if col == 1:
            if role == self.RoleThumbIn:
                return item.get('thumb_in')
            return None

        # Title & Info
        if col == 2:
            # --- MODIFIED: Return None for DisplayRole to avoid duplicate text rendering ---
            if role == Qt.ItemDataRole.DisplayRole:
                return None 
            # -----------------------------------------------------------------------------
            # Add RoleControls here to allow Delegate to access item data (e.g. duration, preview_time)
            if role == self.RoleControls: 
                return item
            return None

        # Controls (handled by delegate)
        if col == 3:
            if role == self.RoleControls:
                return item # Delegate needs the whole item to bind spinboxes
            return None

        # Preview Thumb
        if col == 4:
            if role == self.RoleThumbOut:
                return item.get('thumb_out')
            return None
            
        # Status
        if col == 5:
            if role == Qt.ItemDataRole.DisplayRole:
                return item['status']
            if role == self.RoleStatus:
                return item['status']
            return None

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
            
        flags = super().flags(index)
        
        if index.column() == 0:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
            flags |= Qt.ItemFlag.ItemIsEnabled
            
        return flags

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid():
            return False
            
        row = index.row()
        col = index.column()
        
        if col == 0 and role == Qt.ItemDataRole.CheckStateRole:
            # value is Qt.CheckState enum value (0 or 2)
            self._items[row]['included'] = (value == Qt.CheckState.Checked.value)
            self.dataChanged.emit(index, index, [role])
            return True
            
        return False

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.columns):
                return self.columns[section]
        return super().headerData(section, orientation, role)

    def add_items(self, new_items: List[VidProcItem]):
        # Ensure crop_rect is calculated for new items
        for item in new_items:
            if 'crop_rect' not in item or item['crop_rect'] is None:
                item['crop_rect'] = calculate_crop_rect(item)
            # Ensure preview_time is set
            if 'preview_time' not in item:
                item['preview_time'] = 0.0 # Default to start or logic in manager

        self.beginInsertRows(QModelIndex(), len(self._items), len(self._items) + len(new_items) - 1)
        self._items.extend(new_items)
        self.endInsertRows()
        
    def clear(self):
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()

    def get_item(self, row: int) -> Optional[VidProcItem]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None
        
    def update_item(self, row: int, **kwargs):
        """Update fields of an item and emit dataChanged."""
        if 0 <= row < len(self._items):
            item = self._items[row]
            changed = False
            roles = []
            
            # Check for structural changes that affect crop
            structural_keys = {'split', 'tile_index', 'x_offset', 'width_delta'}
            structural_changed = False
            
            # Special handling: if 'split' is changing but 'tile_index' is NOT provided,
            # we should update 'tile_index' to default for new split.
            if 'split' in kwargs and 'tile_index' not in kwargs:
                 new_split = kwargs['split']
                 if new_split != item['split']:
                     kwargs['tile_index'] = calculate_default_tile_index(new_split)

            for k, v in kwargs.items():
                if item.get(k) != v:
                    item[k] = v
                    changed = True
                    if k in structural_keys:
                        structural_changed = True
                    
                    if k == 'preview_time':
                        # If preview_time changes, we must trigger regeneration.
                        # We reuse RoleControls to signal "input parameters changed".
                        roles.append(self.RoleControls)

                    # Map keys to roles for optimization (optional but good)
                    if k == 'thumb_in':
                        roles.append(self.RoleThumbIn)
                    elif k == 'thumb_out':
                        roles.append(self.RoleThumbOut)
                    elif k == 'status':
                        roles.append(self.RoleStatus)
            
            if structural_changed:
                # Recalculate crop immediately
                item['crop_rect'] = calculate_crop_rect(item)
                roles.append(self.RoleControls)
            
            if changed:
                # If roles is empty, emit for all roles (default)
                role_vec = roles if roles else [] 
                self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount()-1), role_vec)
