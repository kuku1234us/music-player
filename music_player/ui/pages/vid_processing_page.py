from pathlib import Path
import os
import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, 
    QHeaderView, QMessageBox, QProgressBar, QCheckBox, QComboBox
)
from PyQt6.QtCore import Qt, QSize, pyqtSlot, QRect, QTimer
from PyQt6.QtGui import QImage

from music_player.ui.components.base_table import BaseTableView
from music_player.ui.components.round_button import RoundButton
from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.models.settings_manager import SettingsManager
from qt_base_app.components.base_progress_overlay import BaseProgressOverlay

from music_player.models.vid_proc_model import VidProcTableModel, VidProcItem, calculate_default_tile_index
from music_player.models.vid_proc_manager import VidProcManager
from music_player.ui.delegates.vid_proc_delegates import ThumbDelegate, ControlGroupDelegate, TitleInfoDelegate

class VidProcessingPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = ThemeManager.instance()
        self.settings = SettingsManager.instance()
        self.manager = VidProcManager()
        
        # Internal state for preview progress
        self._previews_pending = 0
        self._total_previews = 0
        
        # Internal state for processing progress
        self._processing_total = 0
        self._processing_current = 0
        self._is_processing = False # New flag to track state
        
        self._current_directory = None  # Track current directory to avoid re-scanning
        
        self._setup_ui()
        self._apply_theme_styles() # Apply custom styles
        self._connect_signals()

    def _apply_theme_styles(self):
        """Apply theme-specific styles, particularly for widgets that don't pick it up automatically."""
        # Use orange accent color for the checkbox indicator
        orange_color = "#ff8c00" # DarkOrange / rgb(255, 140, 0)
        
        # Checkbox style
        self.chk_merge.setStyleSheet(f"""
            QCheckBox {{
                color: #e0e0e0;
                spacing: 5px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1px solid #666;
                border-radius: 3px;
                background: #333;
            }}
            QCheckBox::indicator:unchecked:hover {{
                border: 1px solid {orange_color};
            }}
            QCheckBox::indicator:checked {{
                background: {orange_color};
                border: 1px solid {orange_color};
                image: url(:/icons/check.svg);
            }}
            QCheckBox::indicator:disabled {{
                background: #2a2a2a;
                border: 1px solid #444;
            }}
        """)
        # Apply same style to cleanup checkbox
        self.chk_cleanup.setStyleSheet(self.chk_merge.styleSheet())
        
        # ComboBox style
        self.combo_res.setStyleSheet(f"""
            QComboBox {{
                background-color: #333;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #aaa;
                margin-right: 5px;
            }}
        """)

    def _setup_ui(self):
        # Main Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(16)

        # --- Top Controls Row (Merge & Resolution) ---
        top_controls_layout = QHBoxLayout()
        top_controls_layout.setSpacing(20)
        
        # Merge Output Checkbox
        self.chk_merge = QCheckBox("Merge Output")
        self.chk_merge.setToolTip("Merge all processed videos into a single file")
        self.chk_merge.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Cleanup Singles Checkbox (dependent on Merge)
        self.chk_cleanup = QCheckBox("Cleanup Singles")
        self.chk_cleanup.setToolTip("Delete individual processed files after successful merge")
        self.chk_cleanup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_cleanup.setChecked(True) # Default to checked
        self.chk_cleanup.hide() # Initially hidden until Merge is checked
        
        self.chk_merge.stateChanged.connect(lambda s: self.chk_cleanup.setVisible(s == Qt.CheckState.Checked.value))

        # Resolution ComboBox
        self.combo_res = QComboBox()
        self.combo_res.addItems(["720p", "Original", "1080p"])
        self.combo_res.setCurrentText("720p") # Default
        self.combo_res.setToolTip("Output resolution height (width auto-scaled)")
        self.combo_res.setCursor(Qt.CursorShape.PointingHandCursor)
        
        lbl_res = QLabel("Output Resolution:")
        lbl_res.setBuddy(self.combo_res)
        lbl_res.setStyleSheet("color: #aaa;") # Subtle label color
        
        top_controls_layout.addWidget(self.chk_merge)
        top_controls_layout.addWidget(self.chk_cleanup)
        top_controls_layout.addStretch() # Spacer
        top_controls_layout.addWidget(lbl_res)
        top_controls_layout.addWidget(self.combo_res)
        
        self.main_layout.addLayout(top_controls_layout)
        # ---------------------------------------------

        # Table
        self.model = VidProcTableModel(self)
        self.table = BaseTableView("vid_proc_table", self)
        self.table.setModel(self.model)
        
        # Set Delegates
        self.table.setItemDelegateForColumn(1, ThumbDelegate(VidProcTableModel.RoleThumbIn, self.table, manager=self.manager)) # Pass manager
        self.table.setItemDelegateForColumn(2, TitleInfoDelegate(self.table)) # New Delegate
        self.table.setItemDelegateForColumn(3, ControlGroupDelegate(self.table))
        self.table.setItemDelegateForColumn(4, ThumbDelegate(VidProcTableModel.RoleThumbOut, self.table, manager=self.manager)) # Pass manager
        
        # Open persistent editors
        self.model.rowsInserted.connect(self._on_rows_inserted)

        # Table styling adjustments
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch) # Title & Timeline
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed) # Controls
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed) # Preview
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed) # Status
        
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 140) # Thumb
        self.table.setColumnWidth(3, 200) # Controls
        self.table.setColumnWidth(4, 140) # Preview
        self.table.setColumnWidth(5, 100)
        
        self.table.verticalHeader().setDefaultSectionSize(100) # Height for thumbs

        self.main_layout.addWidget(self.table)

        # --- Progress Overlay ---
        self.progress_overlay = BaseProgressOverlay(self)
        self.progress_overlay.hide() # Initially hidden

        # --- Create Overlay Buttons (No Layout) ---
        # They will be positioned in resizeEvent
        
        # Removed btn_stop as btn_process now handles stop

        self.btn_folder = RoundButton(self, icon_name="fa5s.folder", diameter=48)
        self.btn_folder.setToolTip("Select Input Folder")
        
        self.btn_scan = RoundButton(self, icon_name="fa5s.sync-alt", diameter=48)
        self.btn_scan.setToolTip("Scan Folder")

        self.btn_process = RoundButton(self, icon_name="fa5s.play", diameter=48)
        self.btn_process.setToolTip("Start Processing")
        
        self.btn_open = RoundButton(self, icon_name="fa5s.external-link-alt", diameter=48)
        self.btn_open.setToolTip("Open Output Folder")

        # Store buttons list for easier positioning
        self.overlay_buttons = [
            self.btn_open,
            self.btn_process,
            self.btn_scan,
            self.btn_folder
        ]

    def _connect_signals(self):
        self.btn_folder.clicked.connect(self._on_folder_clicked)
        self.btn_scan.clicked.connect(self._on_scan_clicked)
        self.btn_process.clicked.connect(self._on_process_clicked)
        self.btn_open.clicked.connect(self._on_open_clicked)
        
        self.manager.item_probed.connect(self._on_item_probed)
        self.manager.scan_started.connect(self._on_scan_started)
        self.manager.scan_progress.connect(self._on_scan_progress)
        self.manager.scan_finished.connect(self._on_scan_finished)
        # preview_ready now includes a version integer so we can ignore stale previews
        self.manager.preview_ready.connect(self._on_preview_ready)
        self.manager.process_finished.connect(self._on_process_finished)
        self.manager.merge_finished.connect(self._on_merge_finished)
        
        self.model.dataChanged.connect(self._on_data_changed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_overlay_positions()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_overlay_positions()
        
        # Auto-load last directory
        last_dir = self.settings.get('vidproc.last_dir')
        if last_dir:
            path = Path(last_dir)
            if path.exists() and path.is_dir() and path != self._current_directory:
                self._current_directory = path
                self.model.clear()
                self.manager.scan_folder(path)

    def _update_overlay_positions(self):
        # Position Progress Overlay (Centered)
        if hasattr(self, 'progress_overlay') and self.progress_overlay.isVisible():
            self.progress_overlay.adjustSize()
            overlay_w = self.progress_overlay.width()
            overlay_h = self.progress_overlay.height()
            x = (self.width() - overlay_w) // 2
            y = 60 # Similar to BrowserPage logic
            self.progress_overlay.move(x, y)
            self.progress_overlay.raise_()

        if not hasattr(self, 'overlay_buttons'):
            return

        # Position overlay buttons at bottom-right
        margin = 20
        spacing = 10
        
        # Use a reference button for height if possible, or fallback
        if self.overlay_buttons:
            btn_h = 48 # Fixed size or get from button if visible
        else:
            btn_h = 48
        
        # Start from bottom-right
        curr_x = self.width() - margin
        curr_y = self.height() - margin - btn_h
        
        for btn in self.overlay_buttons:
            if btn.isVisible():
                btn.move(curr_x - btn.width(), curr_y)
                btn.raise_()
                curr_x -= (btn.width() + spacing)

    def _on_scan_started(self, total_files: int):
        self.progress_overlay.show_progress("Scanning files...", f"Found {total_files} files", 0)
        self._update_overlay_positions()

    def _on_scan_progress(self, current: int, total: int):
        percent = int((current / total) * 100) if total > 0 else 0
        self.progress_overlay.show_progress(f"Scanning... {percent}%", f"{current}/{total}", percent)

    def _on_scan_finished(self):
        self.progress_overlay.show_complete("Scan Finished", auto_hide_delay=1000)

    def _on_folder_clicked(self):
        # Use current directory or last saved as starting point
        start_dir = str(Path.home())
        if self._current_directory and self._current_directory.exists():
            start_dir = str(self._current_directory)
        else:
            saved_dir = self.settings.get('vidproc.last_dir')
            if saved_dir and Path(saved_dir).exists():
                start_dir = saved_dir

        folder = QFileDialog.getExistingDirectory(self, "Select Video Folder", start_dir)
        if folder:
            path = Path(folder)
            self.settings.set('vidproc.last_dir', folder)
            self._current_directory = path
            # Progress shown by _on_scan_started
            self.manager.scan_folder(path)
            self.model.clear()

    def _on_scan_clicked(self):
        last_dir = self.settings.get('vidproc.last_dir')
        if last_dir:
            path = Path(last_dir)
            self._current_directory = path
            # Progress shown by _on_scan_started
            self.model.clear()
            self.manager.scan_folder(path)
        else:
            self._on_folder_clicked()

    def _update_preview_progress(self):
        """Update progress overlay when a preview is ready."""
        if self.progress_overlay.isVisible():
            if self._previews_pending > 0:
                self._previews_pending -= 1
                done = self._total_previews - self._previews_pending
                percent = int((done / self._total_previews) * 100) if self._total_previews > 0 else 0
                self.progress_overlay.show_progress(f"Updating Previews... {percent}%", f"{done}/{self._total_previews}", percent)
                
                if self._previews_pending == 0:
                    self.progress_overlay.show_complete("Previews Updated", auto_hide_delay=1000)

    def _on_item_probed(self, info: dict):
        default_split = 3
        default_idx = calculate_default_tile_index(default_split)
        
        item: VidProcItem = {
            'path': info['path'],
            'title': info['path'].name,
            'size_in': info['size'],
            'fps': info['fps'],
            'duration': info['duration'],
            'codec_v': info['codec_v'],
            'codec_a': None, 
            'split': default_split,
            'tile_index': default_idx,
            'x_offset': 0,
            'width_delta': 0,
            'preview_time': min(5.0, info['duration'] * 0.2), # Initialize with default time logic
            'crop_rect': None, # Let model calculate
            'out_size': QSize(1080, 1920), # Default
            'included': True,
            'status': 'pending',
            'out_path': None,
            'log_tail': '',
            'thumb_in': None,
            'thumb_out': None
        }
        
        self.model.add_items([item])
        
        # Trigger preview gen
        self.manager.generate_preview(item)

    def _on_preview_ready(self, path: Path, type_: str, version: int):
        """Handle preview readiness."""
        # Ignore stale previews for cropped output
        if type_ == 'out':
            latest = self.manager.get_preview_version(path)
            if version < latest:
                return

        # Update model
        for i in range(self.model.rowCount()):
            item = self.model.get_item(i)
            if item['path'] == path:
                suffix = "in" if type_ == 'in' else "out"
                img_path = self.manager.temp_dir / f"{path.stem}_{suffix}.jpg"
                if img_path.exists():
                    img = QImage(str(img_path))
                    
                    if type_ == 'in':
                        self.model.update_item(i, thumb_in=img)
                    else:
                        self.model.update_item(i, thumb_out=img)
                    
                break
                
        # Update progress if it's an 'out' preview (preview regen)
        if type_ == 'out' and self.progress_overlay.isVisible():
            self._update_preview_progress()

    def _on_rows_inserted(self, parent, first, last):
        for row in range(first, last + 1):
            self.table.openPersistentEditor(self.model.index(row, 2)) # Title & Timeline
            self.table.openPersistentEditor(self.model.index(row, 3)) # Controls

    def _on_data_changed(self, top, bottom, roles):
        row = top.row()
        item = self.model.get_item(row)
        
        # If roles is empty (all changed) or includes RoleControls (structural change or preview_time change)
        # This happens when Split/X/Delta/PreviewTime changes.
        if not roles or VidProcTableModel.RoleControls in roles:
            self.manager.generate_preview(item)

    def _reset_process_button(self):
        """Resets the process button to its initial state."""
        self.btn_process.set_icon("fa5s.play")
        self.btn_process.setToolTip("Start Processing")
        self._is_processing = False

    def _on_process_clicked(self):
        # --- Toggle State Logic ---
        if self._is_processing:
            # User clicked Stop
            self.manager.cancel_all_processing()
            self.progress_overlay.show_error("Cancelled", "Processing stopped by user.", auto_hide_delay=2000)
            self._reset_process_button()
            return
        # ---------------------------

        items = [self.model.get_item(i) for i in range(self.model.rowCount())]
        included = [i for i in items if i['included']]
        
        if not included:
            QMessageBox.warning(self, "No Videos", "Please select at least one video to process.")
            return
            
        first_path = included[0]['path']
        default_out = first_path.parent / "processed"
        
        saved_out = self.settings.get('vidproc.out_dir')
        if saved_out:
            out_dir = Path(saved_out)
        else:
            out_dir = default_out
            
        if not out_dir.exists():
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not create output directory:\n{e}")
                return
                
        self.settings.set('vidproc.out_dir', str(out_dir))
        
        # Determine target height based on combo selection
        res_text = self.combo_res.currentText()
        if res_text == "720p":
            target_h = 1280
        elif res_text == "1080p":
            target_h = 1920
        else: # "Original"
            target_h = 0 # Signal to manager to not force scale (or just mod 2)
        
        # Count actually pending items (not already 'ok')
        pending_items = included
        self._processing_total = len(pending_items)
        self._processing_current = 0
        
        if self._processing_total == 0:
             QMessageBox.information(self, "No Pending Items", "All selected items have already been processed successfully.")
             return

        # --- Start Processing ---
        self._is_processing = True
        self.btn_process.set_icon("fa5s.stop")
        self.btn_process.setToolTip("Stop Processing")
        
        # Show Overlay
        self.progress_overlay.show_progress(
            "Processing Videos...", 
            f"0/{self._processing_total}", 
            0
        )
        self._update_overlay_positions()
        
        for i, item in enumerate(items):
            if item['included']:
                self.model.update_item(i, status='processing')
                
        self.manager.process_items(items, out_dir, target_height=target_h)
        
    def _on_process_finished(self, path_str: str, success: bool, msg: str):
        path = Path(path_str)
        for i in range(self.model.rowCount()):
            item = self.model.get_item(i)
            if item['path'] == path:
                new_status = 'ok' if success else 'error'
                out_path = Path(msg) if success else None
                self.model.update_item(i, status=new_status, out_path=out_path)
                if not success:
                    from qt_base_app.models.logger import Logger
                    Logger.instance().error("VidProcessingPage", f"Error processing {path.name}: {msg}")
                break
        
        # Update Overlay Progress
        self._processing_current += 1
        percent = int((self._processing_current / self._processing_total) * 100) if self._processing_total > 0 else 0
        
        if self.progress_overlay.isVisible():
            self.progress_overlay.show_progress(
                f"Processing... {percent}%", 
                f"{self._processing_current}/{self._processing_total}", 
                percent
            )
            
            if self._processing_current >= self._processing_total:
                # Check if Merge is requested
                if self.chk_merge.isChecked():
                    self._start_merge()
                else:
                    self.progress_overlay.show_complete("Processing Complete!", auto_hide_delay=2000)
                    self._reset_process_button() # Reset button when done

    def _start_merge(self):
        """Collect successful outputs and start merge."""
        output_files = []
        for i in range(self.model.rowCount()):
            item = self.model.get_item(i)
            if item['included'] and item['status'] == 'ok' and item['out_path']:
                output_files.append(item['out_path'])
        
        if len(output_files) < 2:
            self.progress_overlay.show_complete("Processing Complete (Skipped Merge: < 2 files)", auto_hide_delay=3000)
            self._reset_process_button()
            return

        # Store pending files for potential cleanup
        self._pending_merge_files = output_files

        self.progress_overlay.show_progress("Merging Videos...", "Concatenating outputs...", 100)
        
        # Create merged filename based on folder + timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
        if self._current_directory:
            folder_name = self._current_directory.name
        else:
            folder_name = "merged"
            
        out_name = f"{folder_name}_merged_{timestamp}.mp4"
        # Save in the same output directory as individual clips
        first_out_dir = output_files[0].parent
        merge_out_path = first_out_dir / out_name
        
        self.manager.merge_videos(output_files, merge_out_path)

    def _on_merge_finished(self, success: bool, msg: str):
        if success:
            self.progress_overlay.show_complete(f"Merge Complete!\n{Path(msg).name}", auto_hide_delay=4000)
            
            # Cleanup logic
            if self.chk_cleanup.isChecked() and hasattr(self, '_pending_merge_files'):
                from qt_base_app.models.logger import Logger
                count = 0
                for f_path in self._pending_merge_files:
                    try:
                        if f_path.exists():
                            f_path.unlink()
                            count += 1
                    except Exception as e:
                        Logger.instance().error("VidProcessingPage", f"Failed to cleanup {f_path.name}: {e}")
                
                if count > 0:
                    # Optionally log or notify, but overlay is already showing complete
                    Logger.instance().info("VidProcessingPage", f"Cleaned up {count} individual files.")
        else:
            self.progress_overlay.show_error("Merge Failed", msg)
            
        # Clear pending files ref
        self._pending_merge_files = []
        self._reset_process_button() # Reset button after merge

    def _on_open_clicked(self):
        out_dir = self.settings.get('vidproc.out_dir')
        if out_dir and Path(out_dir).exists():
            os.startfile(out_dir)
        else:
            last_dir = self.settings.get('vidproc.last_dir')
            if last_dir and Path(last_dir).exists():
                os.startfile(last_dir)
