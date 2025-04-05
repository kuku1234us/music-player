"""
Main window for the Music Player application.
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSlider, QListWidget, QFileDialog
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPalette, QColor


class MainWindow(QMainWindow):
    """Main window for the Music Player application."""
    
    def __init__(self):
        super().__init__()
        
        # Set window properties
        self.setWindowTitle("Music Player")
        self.setMinimumSize(800, 600)
        
        # Apply dark theme
        self.apply_dark_theme()
        
        # Set up the UI
        self.setup_ui()
    
    def apply_dark_theme(self):
        """Apply dark theme to the application."""
        dark_palette = QPalette()
        
        # Set color groups
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        
        # Apply the palette
        self.setPalette(dark_palette)
    
    def setup_ui(self):
        """Set up the user interface."""
        # Create central widget and main layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        # Create playlist section
        playlist_label = QLabel("Playlist")
        playlist_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        playlist = QListWidget()
        
        # Create control buttons
        controls_layout = QHBoxLayout()
        
        play_button = QPushButton("Play")
        pause_button = QPushButton("Pause")
        stop_button = QPushButton("Stop")
        open_button = QPushButton("Open")
        
        controls_layout.addWidget(play_button)
        controls_layout.addWidget(pause_button)
        controls_layout.addWidget(stop_button)
        controls_layout.addWidget(open_button)
        
        # Create progress slider
        progress_layout = QHBoxLayout()
        progress_slider = QSlider(Qt.Orientation.Horizontal)
        time_label = QLabel("00:00 / 00:00")
        
        progress_layout.addWidget(progress_slider)
        progress_layout.addWidget(time_label)
        
        # Add all widgets to main layout
        main_layout.addWidget(playlist_label)
        main_layout.addWidget(playlist)
        main_layout.addLayout(controls_layout)
        main_layout.addLayout(progress_layout)
        
        # Set the central widget
        self.setCentralWidget(central_widget)
        
        # Connect signals
        open_button.clicked.connect(self.open_file)
    
    def open_file(self):
        """Open a music file."""
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        file_dialog.setNameFilter("Audio Files (*.mp3 *.wav *.ogg *.flac)")
        
        if file_dialog.exec():
            filenames = file_dialog.selectedFiles()
            # TODO: Add files to playlist 