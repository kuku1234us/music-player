"""
Dialog to choose video processing options: compression and/or rotation.
"""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QDialogButtonBox, QWidget
from PyQt6.QtCore import Qt


class VideoProcessOptionsDialog(QDialog):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setWindowTitle("Video Processing Options")
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.compress_checkbox = QCheckBox("Compress to 720p (H.264)")
        self.compress_checkbox.setChecked(True)  # Default option

        self.rotate_cw_checkbox = QCheckBox("Rotate ↻")
        self.rotate_ccw_checkbox = QCheckBox("Rotate ↺")

        # Ensure CW and CCW are mutually exclusive
        self.rotate_cw_checkbox.stateChanged.connect(self._on_cw_changed)
        self.rotate_ccw_checkbox.stateChanged.connect(self._on_ccw_changed)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose actions to perform:"))
        layout.addWidget(self.compress_checkbox)
        layout.addWidget(self.rotate_cw_checkbox)
        layout.addWidget(self.rotate_ccw_checkbox)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_cw_changed(self, state: int):
        if state == Qt.CheckState.Checked.value:
            self.rotate_ccw_checkbox.setChecked(False)

    def _on_ccw_changed(self, state: int):
        if state == Qt.CheckState.Checked.value:
            self.rotate_cw_checkbox.setChecked(False)

    def get_options(self) -> dict:
        rotate = None
        if self.rotate_cw_checkbox.isChecked():
            rotate = 'cw'
        elif self.rotate_ccw_checkbox.isChecked():
            rotate = 'ccw'
        return {
            'compress': self.compress_checkbox.isChecked(),
            'rotate': rotate,
        }


