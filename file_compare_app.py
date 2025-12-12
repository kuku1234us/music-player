#!/usr/bin/env python3
"""
File Comparison and Deletion App
A PyQt6 application for comparing two directories and removing duplicate files.
"""

import sys
import os
import shutil
from pathlib import Path
from typing import List, Set, Dict
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QFrame, QSplitter, QGroupBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIcon, QPixmap
import qtawesome as qta

from qt_base_app.models.logger import Logger

class FileComparisonWorker(QThread):
    """Worker thread for file comparison to avoid blocking UI."""
    progress = pyqtSignal(int)
    comparison_complete = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, old_dir: str, target_dir: str):
        super().__init__()
        self.old_dir = old_dir
        self.target_dir = target_dir

    def run(self):
        try:
            # Get all files from both directories
            old_files = self._get_files_in_directory(self.old_dir)
            target_files = self._get_files_in_directory(self.target_dir)
            
            Logger.instance().debug(caller="file_compare_app", msg=f"Old directory has {len(old_files)} unique filenames")
            Logger.instance().debug(caller="file_compare_app", msg=f"Target directory has {len(target_files)} unique filenames")
            
            # Find files in OLD directory that also exist in TARGET directory
            # These are the files we want to mark as duplicates in the target
            duplicates = []
            total_files = len(old_files)
            
            for i, old_file in enumerate(old_files):
                self.progress.emit(int((i / total_files) * 100))
                
                # If this file from old directory exists in target directory, mark it as duplicate
                if old_file in target_files:
                    duplicates.append(old_file)
            
            Logger.instance().debug(caller="file_compare_app", msg=f"Found {len(duplicates)} files from old directory that exist in target")
            Logger.instance().debug(caller="file_compare_app", msg=f"This should be <= {len(old_files)} (number of files in old directory)")
            
            self.comparison_complete.emit(duplicates)
            
        except Exception as e:
            self.error.emit(str(e))

    def _get_files_in_directory(self, directory: str) -> Set[str]:
        """Get filenames from the root directory only (no subdirectories)."""
        files = set()
        try:
            # Only get files from the root directory, not subdirectories
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                if os.path.isfile(item_path):
                    files.add(item)
        except Exception as e:
            Logger.instance().error(caller="file_compare_app", msg=f"Error reading directory {directory}: {e}", exc_info=True)
        return files


class FileDeletionWorker(QThread):
    """Worker thread for file deletion to avoid blocking UI."""
    progress = pyqtSignal(int)
    deletion_complete = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, target_dir: str, files_to_delete: List[str]):
        super().__init__()
        self.target_dir = target_dir
        self.files_to_delete = files_to_delete

    def run(self):
        try:
            deleted_count = 0
            total_files = len(self.files_to_delete)
            
            Logger.instance().debug(caller="file_compare_app", msg=f"Starting deletion of {total_files} files from {self.target_dir}")
            
            for i, filename in enumerate(self.files_to_delete):
                self.progress.emit(int((i / total_files) * 100))
                
                # Find the file in the target directory (root only)
                file_path = self._find_file_in_directory(self.target_dir, filename)
                if file_path and os.path.exists(file_path):
                    try:
                        Logger.instance().debug(caller="file_compare_app", msg=f"Deleting {file_path}")
                        os.remove(file_path)
                        deleted_count += 1
                    except Exception as e:
                        Logger.instance().error(caller="file_compare_app", msg=f"Error deleting {file_path}: {e}", exc_info=True)
                else:
                    Logger.instance().debug(caller="file_compare_app", msg=f"File not found in root directory: {filename}")
            
            Logger.instance().debug(caller="file_compare_app", msg=f"Successfully deleted {deleted_count} out of {total_files} files")
            self.deletion_complete.emit(deleted_count)
            
        except Exception as e:
            self.error.emit(str(e))

    def _find_file_in_directory(self, directory: str, filename: str) -> str:
        """Find the full path of a file in the root directory only (no subdirectories)."""
        try:
            # Only search in the root directory, not subdirectories
            file_path = os.path.join(directory, filename)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                return file_path
        except Exception as e:
            Logger.instance().error(caller="file_compare_app", msg=f"Error searching for {filename} in {directory}: {e}", exc_info=True)
        return ""


class DirectoryPane(QWidget):
    """A pane for displaying directory contents."""
    
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.directory_path = ""
        self.setup_ui(title)
    
    def setup_ui(self, title: str):
        layout = QVBoxLayout(self)
        
        # Title
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Directory selection
        dir_layout = QHBoxLayout()
        self.dir_label = QLabel("No directory selected")
        self.dir_label.setStyleSheet("QLabel { padding: 5px; border: 1px solid #ccc; background-color: #f9f9f9; }")
        dir_layout.addWidget(self.dir_label, 1)
        
        self.select_btn = QPushButton("Select Directory")
        self.select_btn.clicked.connect(self.select_directory)
        dir_layout.addWidget(self.select_btn)
        layout.addLayout(dir_layout)
        
        # File list
        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(True)
        layout.addWidget(self.file_list)
        
        # File count
        self.count_label = QLabel("0 files")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.count_label)
    
    def select_directory(self):
        directory = QFileDialog.getExistingDirectory(self, f"Select {self.windowTitle()} Directory")
        if directory:
            self.directory_path = directory
            self.dir_label.setText(directory)
            self.load_directory_contents()
    
    def load_directory_contents(self):
        """Load and display files in the selected directory."""
        self.file_list.clear()
        if not self.directory_path:
            self.count_label.setText("0 files")
            return
        
        try:
            # Get all files recursively for display
            all_files = []
            for root, dirs, filenames in os.walk(self.directory_path):
                for filename in filenames:
                    all_files.append(filename)
            
            # Get only files in the root directory for counting
            root_files = []
            try:
                for item in os.listdir(self.directory_path):
                    item_path = os.path.join(self.directory_path, item)
                    if os.path.isfile(item_path):
                        root_files.append(item)
            except Exception as e:
                Logger.instance().error(
                    caller="file_compare_app",
                    msg=f"Error reading root directory {self.directory_path}: {e}",
                    exc_info=True,
                )
            
            # Display all files (recursive)
            all_files.sort()
            for filename in all_files:
                item = QListWidgetItem(filename)
                self.file_list.addItem(item)
            
            # Count only root directory files
            self.count_label.setText(f"{len(root_files)} files")
            Logger.instance().debug(
                caller="file_compare_app",
                msg=f"Root directory has {len(root_files)} files, total files (recursive): {len(all_files)}",
            )
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error loading directory: {e}")
            self.count_label.setText("0 files")
            Logger.instance().error(
                caller="file_compare_app",
                msg=f"Error loading directory {self.directory_path}: {e}",
                exc_info=True,
            )
    
    def get_filenames(self) -> Set[str]:
        """Get all filenames in the directory."""
        filenames = set()
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            filenames.add(item.text())
        return filenames
    
    def mark_duplicates(self, duplicate_filenames: Set[str]):
        """Mark duplicate files in the list."""
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.text() in duplicate_filenames:
                item.setBackground(Qt.GlobalColor.red)
                item.setForeground(Qt.GlobalColor.white)
            else:
                item.setBackground(Qt.GlobalColor.white)
                item.setForeground(Qt.GlobalColor.black)


class FileCompareApp(QMainWindow):
    """Main application window for file comparison and deletion."""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.comparison_worker = None
        self.deletion_worker = None
    
    def setup_ui(self):
        self.setWindowTitle("File Comparison and Deletion Tool")
        self.setGeometry(100, 100, 1200, 800)
        
        # Main widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Create splitter for side-by-side panes
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left pane (Old directory)
        self.old_pane = DirectoryPane("Old")
        splitter.addWidget(self.old_pane)
        
        # Right pane (Target directory)
        self.target_pane = DirectoryPane("Target")
        splitter.addWidget(self.target_pane)
        
        # Set splitter proportions
        splitter.setSizes([600, 600])
        
        # Control buttons
        control_layout = QHBoxLayout()
        
        self.compare_btn = QPushButton("Compare Directories")
        self.compare_btn.clicked.connect(self.compare_directories)
        self.compare_btn.setEnabled(False)
        control_layout.addWidget(self.compare_btn)
        
        self.delete_btn = QPushButton("Delete Selected Files")
        self.delete_btn.clicked.connect(self.delete_selected_files)
        self.delete_btn.setEnabled(False)
        control_layout.addWidget(self.delete_btn)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        control_layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        control_layout.addWidget(self.status_label)
        
        main_layout.addLayout(control_layout)
        
        # Connect directory selection signals
        self.old_pane.select_btn.clicked.connect(self.check_compare_button)
        self.target_pane.select_btn.clicked.connect(self.check_compare_button)
    
    def check_compare_button(self):
        """Enable compare button if both directories are selected."""
        can_compare = bool(self.old_pane.directory_path and self.target_pane.directory_path)
        self.compare_btn.setEnabled(can_compare)
    
    def compare_directories(self):
        """Compare the two directories and mark duplicates."""
        if not self.old_pane.directory_path or not self.target_pane.directory_path:
            QMessageBox.warning(self, "Error", "Please select both directories first.")
            return
        
        self.status_label.setText("Comparing directories...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.compare_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        
        # Start comparison worker
        self.comparison_worker = FileComparisonWorker(
            self.old_pane.directory_path,
            self.target_pane.directory_path
        )
        self.comparison_worker.progress.connect(self.progress_bar.setValue)
        self.comparison_worker.comparison_complete.connect(self.on_comparison_complete)
        self.comparison_worker.error.connect(self.on_worker_error)
        self.comparison_worker.start()
    
    def on_comparison_complete(self, duplicate_filenames: List[str]):
        """Handle completion of directory comparison."""
        self.progress_bar.setVisible(False)
        self.compare_btn.setEnabled(True)
        
        # Get the actual number of files in each pane
        old_file_count = self.old_pane.file_list.count()
        target_file_count = self.target_pane.file_list.count()
        
        Logger.instance().debug(caller="file_compare_app", msg=f"Old pane displays {old_file_count} files")
        Logger.instance().debug(caller="file_compare_app", msg=f"Target pane displays {target_file_count} files")
        Logger.instance().debug(caller="file_compare_app", msg=f"Comparison found {len(duplicate_filenames)} duplicates")
        
        # Validate: duplicates cannot exceed the number of files in old directory
        if len(duplicate_filenames) > old_file_count:
            Logger.instance().error(
                caller="file_compare_app",
                msg=f"Found {len(duplicate_filenames)} duplicates but old directory only has {old_file_count} files!",
            )
            Logger.instance().warning(
                caller="file_compare_app",
                msg="This indicates a bug in the comparison logic. Limiting duplicates to old directory count.",
            )
            # Limit duplicates to the number of files in old directory
            duplicate_filenames = duplicate_filenames[:old_file_count]
        
        if duplicate_filenames:
            self.target_pane.mark_duplicates(set(duplicate_filenames))
            self.delete_btn.setEnabled(True)
            self.status_label.setText(f"Found {len(duplicate_filenames)} duplicate files")
        else:
            self.status_label.setText("No duplicate files found")
            self.delete_btn.setEnabled(False)
    
    def delete_selected_files(self):
        """Delete the selected duplicate files."""
        # Get duplicate filenames from target pane
        duplicate_filenames = []
        for i in range(self.target_pane.file_list.count()):
            item = self.target_pane.file_list.item(i)
            if item.background().color() == Qt.GlobalColor.red:
                duplicate_filenames.append(item.text())
        
        if not duplicate_filenames:
            QMessageBox.information(self, "Info", "No files selected for deletion.")
            return
        
        # Confirm deletion
        reply = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete {len(duplicate_filenames)} files from the target directory?\n\nThis action cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.perform_deletion(duplicate_filenames)
    
    def perform_deletion(self, filenames: List[str]):
        """Perform the actual file deletion."""
        self.status_label.setText("Deleting files...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.delete_btn.setEnabled(False)
        self.compare_btn.setEnabled(False)
        
        # Start deletion worker
        self.deletion_worker = FileDeletionWorker(
            self.target_pane.directory_path,
            filenames
        )
        self.deletion_worker.progress.connect(self.progress_bar.setValue)
        self.deletion_worker.deletion_complete.connect(self.on_deletion_complete)
        self.deletion_worker.error.connect(self.on_worker_error)
        self.deletion_worker.start()
    
    def on_deletion_complete(self, deleted_count: int):
        """Handle completion of file deletion."""
        self.progress_bar.setVisible(False)
        self.delete_btn.setEnabled(False)
        self.compare_btn.setEnabled(True)
        
        self.status_label.setText(f"Deleted {deleted_count} files")
        
        # Refresh target directory
        self.target_pane.load_directory_contents()
        
        QMessageBox.information(
            self, "Deletion Complete",
            f"Successfully deleted {deleted_count} files from the target directory."
        )
    
    def on_worker_error(self, error_message: str):
        """Handle worker thread errors."""
        self.progress_bar.setVisible(False)
        self.compare_btn.setEnabled(True)
        self.delete_btn.setEnabled(False)
        self.status_label.setText("Error occurred")
        
        QMessageBox.critical(self, "Error", f"An error occurred: {error_message}")


def main():
    """Main application entry point."""
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Create and show main window
    window = FileCompareApp()
    window.show()
    
    # Start application event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main() 