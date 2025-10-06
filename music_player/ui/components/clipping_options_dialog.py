"""
Dialog for clipping options: force keyframe snapping and optional resize to 720p.
"""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QCheckBox, QDialogButtonBox, QWidget
from PyQt6.QtCore import Qt


class ClippingOptionsDialog(QDialog):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setWindowTitle("Clipping Options")
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.snap_checkbox = QCheckBox("Snap Keyframe (stream copy, no re-encode)")
        self.resize_checkbox = QCheckBox("Resize to 720p (keep aspect ratio)")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select additional options:"))
        layout.addWidget(self.snap_checkbox)
        layout.addWidget(self.resize_checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_options(self) -> dict:
        return {
            'snap_keyframe': self.snap_checkbox.isChecked(),
            'resize_720p': self.resize_checkbox.isChecked(),
        }


