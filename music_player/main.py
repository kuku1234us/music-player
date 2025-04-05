#!/usr/bin/env python
"""
Main entry point for the Music Player application.
"""
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication, Qt

from .ui.main_window import MainWindow


def main():
    """Initialize and run the application."""
    # Set application information
    QCoreApplication.setApplicationName("Music Player")
    QCoreApplication.setOrganizationName("Music Player")
    QCoreApplication.setApplicationVersion("0.1.0")

    # Create the application
    app = QApplication(sys.argv)
    
    # Set the style to Fusion, which allows us to customize colors
    app.setStyle("Fusion")
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    # Run the application
    sys.exit(app.exec())


if __name__ == "__main__":
    main() 