#!/usr/bin/env python
"""
Entry point script to run the Music Player application.
"""
import sys
import os

# Add the project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

# Import from our base app framework
from qt_base_app.app import create_app, run_app, setup_dark_title_bar

# Import music player dashboard
from music_player.ui.dashboard import MusicPlayerDashboard


def main():
    """Main entry point for the Music Player application."""
    # Set the path to the music player config
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                          "music_player", "resources", "music_player_config.yaml")
    
    # Create application and base window using our framework
    app, base_window = create_app(config_path)
    
    # Set app icon
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                         "music_player", "resources", "play.png")
    if os.path.exists(icon_path):
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)
        base_window.setWindowIcon(app_icon)
    else:
        print(f"Warning: App icon not found at {icon_path}")
    
    # Initialize music player dashboard with the base window
    music_player = MusicPlayerDashboard(base_window)
    
    # Run the application
    sys.exit(run_app(app, base_window))


if __name__ == "__main__":
    main() 