from PyQt6.QtWidgets import (
    QStyledItemDelegate, QWidget, QHBoxLayout, QVBoxLayout, QSpinBox, QLabel, 
    QStyleOptionViewItem, QDialog, QApplication, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QRect, QEvent, QPersistentModelIndex, QThread
from PyQt6.QtGui import QPainter, QImage, QColor, QPixmap
from PyQt6.QtWidgets import QStyle
import subprocess
from pathlib import Path

from music_player.models.vid_proc_model import VidProcTableModel, VidProcItem
from music_player.ui.components.video_timeline import VideoTimeline

from qt_base_app.models.logger import Logger

# --- Worker for High-Res Image Generation ---
class HighResImageWorker(QThread):
    result_ready = pyqtSignal(QImage)
    
    def __init__(self, item, type_, temp_dir):
        super().__init__()
        self.item = item
        self.type_ = type_
        self.temp_dir = temp_dir
        self.logger = Logger.instance()
        
    def run(self):
        try:
            file_path = self.item['path']
            # Use existing preview time or 0
            ts = float(self.item.get('preview_time', 0.0))
            
            # Determine output path
            suffix = "in_full" if self.type_ == 'in' else "out_full"
            out_path = self.temp_dir / f"{file_path.stem}_{suffix}_{int(ts*100)}.jpg"
            
            # FFmpeg command - NO SCALING, just extraction (and cropping if 'out')
            # Note: Put -ss before -i for fast seek
            cmd = ["ffmpeg", "-y", "-ss", str(ts), "-i", str(file_path), "-frames:v", "1"]
            
            if self.type_ == 'out' and self.item.get('crop_rect'):
                r = self.item['crop_rect']
                cmd.extend(["-vf", f"crop={r.width()}:{r.height()}:{r.x()}:{r.y()}"])
            
            # No scaling filter added -> Original resolution
            # Use -q:v 2 for high quality jpeg
            cmd.extend(["-q:v", "2", str(out_path)])
            
            # Run FFmpeg
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if out_path.exists():
                img = QImage(str(out_path))
                if not img.isNull():
                    self.result_ready.emit(img)
                else:
                    self.result_ready.emit(QImage())
            else:
                self.logger.error("HighResImageWorker", f"Output file not found: {out_path}")
                
        except Exception as e:
            self.logger.error("HighResImageWorker", f"Error: {e}")
            self.result_ready.emit(QImage()) # Emit empty on error

class ImagePopup(QDialog):
    """Popup window to display image in full scale (fit to screen)."""
    def __init__(self, low_res_image: QImage, item: dict, type_: str, temp_dir: Path, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: #1a1a1a;") # Dark gray background, opaque
        self.logger = Logger.instance()
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        # Remove alignment on layout to allow label to expand
        
        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Remove Ignored SizePolicy to let label use pixmap sizeHint
        self.lbl_image.setStyleSheet("background-color: transparent;") 
        
        self.layout.addWidget(self.lbl_image)
        
        # Initial display with low-res image
        if low_res_image and not low_res_image.isNull():
            self.update_display(low_res_image)
        else:
            self.resize(400, 300)
            self.lbl_image.setText("Loading preview...")
            self.lbl_image.setStyleSheet("color: white;")
            
        # Start fetching high-res image
        self.worker = HighResImageWorker(item, type_, temp_dir)
        self.worker.result_ready.connect(self.on_high_res_ready)
        self.worker.start()

    def update_display(self, image):
        # Get screen size
        if self.parentWidget() and self.parentWidget().windowHandle():
            screen = self.parentWidget().windowHandle().screen()
        else:
            screen = QApplication.primaryScreen()
            
        screen_rect = screen.availableGeometry()
        max_w = int(screen_rect.width() * 0.95)
        max_h = int(screen_rect.height() * 0.95)
        
        target_w = image.width()
        target_h = image.height()

        # Scale down ONLY if larger than screen
        if target_w > max_w or target_h > max_h:
            scaled_img = image.scaled(
                max_w, max_h, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.lbl_image.setPixmap(QPixmap.fromImage(scaled_img))
            target_w = scaled_img.width()
            target_h = scaled_img.height()
        else:
            self.lbl_image.setPixmap(QPixmap.fromImage(image))
            
        self.resize(target_w, target_h)
        
        # Re-center
        geo = self.geometry()
        geo.moveCenter(screen_rect.center())
        self.setGeometry(geo)

    def on_high_res_ready(self, img):
        if not img.isNull():
            self.update_display(img)
        else:
            self.logger.error("ImagePopup", "HighResImageWorker returned null image")
    
    def mouseReleaseEvent(self, event):
        self.accept()

class ThumbDelegate(QStyledItemDelegate):
    def __init__(self, role, parent=None, manager=None):
        super().__init__(parent)
        self.role = role
        self.manager = manager # Need manager to access temp_dir

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        
        # Draw background
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        
        img: QImage = index.data(self.role)
        
        if img and not img.isNull():
            # Scale image to fit height, maintain aspect ratio
            h = option.rect.height() - 4
            if h > 0:
                scaled = img.scaledToHeight(h, Qt.TransformationMode.SmoothTransformation)
                
                # Center horizontally
                x = option.rect.left() + (option.rect.width() - scaled.width()) // 2
                y = option.rect.top() + 2
                
                painter.drawImage(x, y, scaled)
        else:
            # Draw placeholder or text
            painter.setPen(option.palette.text().color())
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, "No Preview")
            
        painter.restore()
        
    def sizeHint(self, option, index):
        return QSize(120, 90) # Default size

    def editorEvent(self, event, model, option, index):
        # Handle click to show popup
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            img: QImage = index.data(self.role)
            
            # Get full item data to pass to popup
            # Use RoleObject because RoleControls is not available for thumbnail columns
            item = index.data(VidProcTableModel.RoleObject)
            
            if img and not img.isNull() and item and self.manager:
                type_ = 'in' if self.role == VidProcTableModel.RoleThumbIn else 'out'
                
                parent_widget = option.widget.window() if option.widget else None
                popup = ImagePopup(img, item, type_, self.manager.temp_dir, parent_widget)
                popup.exec()
                return True 
        
        return super().editorEvent(event, model, option, index)

class ControlGroupWidget(QWidget):
    """Widget containing the 4 spinboxes for the table cell."""
    valuesChanged = pyqtSignal(int, int, int, int) # split, idx, x, width_delta

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(2, 2, 2, 2)
        self.layout.setSpacing(8)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter) # Center controls vertically/horizontally
        
        # Helper to create labeled spinbox (label above control)
        def create_labeled_spinbox(label_text, min_val, max_val):
            container = QWidget()
            v_layout = QVBoxLayout(container)
            v_layout.setContentsMargins(0, 0, 0, 0)
            v_layout.setSpacing(0) # Remove gap between label and spinbox
            
            lbl = QLabel(label_text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v_layout.addWidget(lbl)
            
            sb = QSpinBox()
            sb.setRange(min_val, max_val)
            v_layout.addWidget(sb)
            
            return container, sb

        # Split
        self.container_split, self.sb_split = create_labeled_spinbox("Split", 1, 10)
        # Change connection to _on_split_changed for auto-update of idx
        self.sb_split.valueChanged.connect(self._on_split_changed)
        self.layout.addWidget(self.container_split)
        
        # Idx
        self.container_idx, self.sb_idx = create_labeled_spinbox("Idx", 0, 9) # Max depends on split
        self.sb_idx.valueChanged.connect(lambda v: self._emit_change(idx=v))
        self.layout.addWidget(self.container_idx)

        # X Offset
        self.container_x, self.sb_x = create_labeled_spinbox("X", -9999, 9999)
        self.sb_x.valueChanged.connect(lambda v: self._emit_change(x=v))
        self.layout.addWidget(self.container_x)
        
        # Width Delta
        self.container_delta, self.sb_delta = create_labeled_spinbox("+", -9999, 9999)
        self.sb_delta.valueChanged.connect(lambda v: self._emit_change(delta=v))
        self.layout.addWidget(self.container_delta)
        
        self._block_signals = False

    def set_values(self, split, idx, x, delta):
        self._block_signals = True
        self.sb_split.setValue(split)
        
        # Update idx range based on split
        self.sb_idx.setRange(0, max(0, split - 1))
        self.sb_idx.setValue(idx)
        
        self.sb_x.setValue(x)
        self.sb_delta.setValue(delta)
        self._block_signals = False

    def _on_split_changed(self, val):
        if self._block_signals:
            return

        # Logic: Calculate new default idx
        # split 1 -> 0
        # split 2 -> 1 (right of mid)
        # split 3 -> 1 (mid)
        # split 4 -> 2 (right of mid)
        # Formula: val // 2
        new_idx = val // 2
        
        # Update UI state without triggering another emission loop
        self.sb_idx.blockSignals(True)
        self.sb_idx.setRange(0, max(0, val - 1))
        self.sb_idx.setValue(new_idx)
        self.sb_idx.blockSignals(False)
        
        # Emit change with BOTH new values
        self._emit_change(split=val, idx=new_idx)

    def _emit_change(self, split=None, idx=None, x=None, delta=None):
        if not self._block_signals:
            s = split if split is not None else self.sb_split.value()
            i_val = idx if idx is not None else self.sb_idx.value()
            x_val = x if x is not None else self.sb_x.value()
            d = delta if delta is not None else self.sb_delta.value()
            
            # Range clamp just in case (though _on_split_changed handles it)
            if split is not None:
                 self.sb_idx.setRange(0, max(0, s - 1))

            self.valuesChanged.emit(s, i_val, x_val, d)

class ControlGroupDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def createEditor(self, parent, option, index):
        editor = ControlGroupWidget(parent)
        # Capture persistent index to safe-guard against row moves
        p_index = QPersistentModelIndex(index)
        # Accept the values from the signal
        editor.valuesChanged.connect(lambda s, i, x, d: self._on_editor_changed(editor, p_index, s, i, x, d))
        return editor

    def _on_editor_changed(self, editor, p_index, split, idx, x, delta):
        if p_index.isValid():
            model = p_index.model()
            # Pass values directly to avoid reading stale editor state if any
            self.setModelData(editor, model, p_index, val_split=split, val_idx=idx, val_x=x, val_delta=delta)

    def setEditorData(self, editor, index):
        item = index.data(VidProcTableModel.RoleControls)
        if item:
            if isinstance(editor, ControlGroupWidget):
                editor.set_values(item['split'], item.get('tile_index', 0), item['x_offset'], item['width_delta'])

    def setModelData(self, editor, model, index, val_split=None, val_idx=None, val_x=None, val_delta=None):
        if isinstance(editor, ControlGroupWidget):
            # Use provided values if available, else read from editor
            split = val_split if val_split is not None else editor.sb_split.value()
            idx = val_idx if val_idx is not None else editor.sb_idx.value()
            x = val_x if val_x is not None else editor.sb_x.value()
            delta = val_delta if val_delta is not None else editor.sb_delta.value()
            
            if hasattr(model, 'update_item'):
                # Use index.row() which works for both QModelIndex and QPersistentModelIndex
                model.update_item(index.row(), split=split, tile_index=idx, x_offset=x, width_delta=delta)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

class TitleInfoWidget(QWidget):
    previewTimeChanged = pyqtSignal(float)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # --- MODIFIED: Set layout margins to 0 to fill cell ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2) # Reduced vertical margins
        layout.setSpacing(2) # Reduced spacing
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_title = QLabel()
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.lbl_title.font()
        font.setBold(True)
        self.lbl_title.setFont(font)
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred) # Expand width
        
        self.lbl_info = QLabel()
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_info.setStyleSheet("color: #888;")
        self.lbl_info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred) # Expand width
        
        self.timeline = VideoTimeline()
        self.timeline.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed) # Ensure timeline expands
        self.timeline.position_changed.connect(self.previewTimeChanged)
        
        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_info)
        layout.addWidget(self.timeline)
        # -------------------------------------------------------
        
    def set_data(self, title, info_text, duration, preview_time):
        self.lbl_title.setText(title)
        self.lbl_info.setText(info_text)
        self.timeline.set_duration(duration)
        self.timeline.set_position(preview_time)

class TitleInfoDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def createEditor(self, parent, option, index):
        editor = TitleInfoWidget(parent)
        p_index = QPersistentModelIndex(index)
        editor.previewTimeChanged.connect(lambda t: self._on_time_changed(p_index, t))
        return editor

    def _on_time_changed(self, p_index, time):
        if p_index.isValid():
            model = p_index.model()
            if hasattr(model, 'update_item'):
                model.update_item(p_index.row(), preview_time=time)

    def setEditorData(self, editor, index):
        item = index.data(VidProcTableModel.RoleControls) # Use RoleControls to get full item
        if item and isinstance(editor, TitleInfoWidget):
            info_text = f"{item['size_in'].width()}x{item['size_in'].height()} • {item['fps']:.2f} fps"
            editor.set_data(item['title'], info_text, item['duration'], item.get('preview_time', 0.0))

    def setModelData(self, editor, model, index):
        pass
        
    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)
