#!/usr/bin/env python
"""
Entry point script to run the Music Player application.
"""
import sys
import os
from pathlib import Path

# Add the project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon, QFont, QFontDatabase

# Import from our base app framework
from qt_base_app.app import setup_dark_title_bar

# Import music player dashboard
from music_player.ui.dashboard import MusicPlayerDashboard


def load_custom_fonts():
    """Load custom fonts and return font family names."""
    # Get the fonts directory
    fonts_dir = Path(__file__).parent / "music_player" / "fonts"
    
    # Font information to track
    font_families = {
        "default": None,      # Default UI font (Geist)
        "monospace": None,    # Monospace font (GeistMono)
        "title": None         # Title font (ICA Rubrik)
    }
    
    # Font files to load with their target categories
    font_mappings = {
        "Geist-Regular.ttf": "default",
        "GeistMono-Regular.ttf": "monospace",
        "ICARubrikBlack.ttf": "title"
    }
    
    # Add custom fonts if available
    if fonts_dir.exists():
        print("Loading fonts from:", fonts_dir)
        for font_file, category in font_mappings.items():
            font_path = fonts_dir / font_file
            if font_path.exists():
                font_id = QFontDatabase.addApplicationFont(str(font_path))
                if font_id >= 0:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        font_families[category] = families[0]
                        print(f"Loaded font: {font_file} as {families[0]}")
    
    return font_families


def apply_application_styles(app, font_families):
    """Apply global application styles and fonts."""
    # Set application-wide font to the default font if available
    if font_families["default"]:
        app_font = QFont(font_families["default"])
        app_font.setPointSize(10)  # Set a reasonable default size
        app.setFont(app_font)
        print(f"Set application-wide font to {font_families['default']}")
        
        # Create stylesheet for specific components
        stylesheet = f"""
            * {{
                font-family: '{font_families["default"]}';
            }}
            
            QLabel#pageTitle {{
                font-family: '{font_families["title"] or font_families["default"]}';
                font-size: 20px;
                font-weight: bold;
            }}
            
            QLabel[objectName^="timeLabel"] {{
                font-family: '{font_families["monospace"] or font_families["default"]}';
            }}
        """
        
        # Apply stylesheet to application
        app.setStyleSheet(app.styleSheet() + stylesheet)


def main():
    """Main entry point for the Music Player application."""
    # Set the path to the music player config
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                          "music_player", "resources", "music_player_config.yaml")
    
    # Create QApplication
    app = QApplication(sys.argv)
    
    # Setup dark title bar for Windows
    setup_dark_title_bar(app)
    
    # Load custom fonts and apply application styles
    font_families = load_custom_fonts()
    apply_application_styles(app, font_families)
    
    # Initialize our custom music player dashboard
    window = MusicPlayerDashboard(config_path)
    
    # Set app icon
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                         "music_player", "resources", "play.png")
    if os.path.exists(icon_path):
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)
        window.setWindowIcon(app_icon)
    else:
        print(f"Warning: App icon not found at {icon_path}")
    
    # Show the window
    window.show()
    
    # Run the application
    sys.exit(app.exec())


if __name__ == "__main__":
    main() 