from PyQt6.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QPushButton, QLabel, QDialogButtonBox


class DouyinOptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Douyin Process Options")
        
        self.layout = QVBoxLayout(self)
        
        self.label = QLabel("Select the operations to perform:")
        self.layout.addWidget(self.label)
        
        self.trim_checkbox = QCheckBox("Trim last 3.03 seconds from each video")
        self.trim_checkbox.setChecked(True)
        self.layout.addWidget(self.trim_checkbox)
        
        self.merge_checkbox = QCheckBox("Merge videos into a single output file")
        self.merge_checkbox.setChecked(True)
        self.layout.addWidget(self.merge_checkbox)
        
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

    def get_options(self):
        return {
            "do_trim": self.trim_checkbox.isChecked(),
            "do_merge": self.merge_checkbox.isChecked()
        } 