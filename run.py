#!/usr/bin/env python
"""
Entry point script to run the Music Player application.
"""
import sys
import os
from pathlib import Path

# Add the project root directory to Python path
# sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))) # Usually not needed if running via module/poetry

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon, QFont, QFontDatabase

# Import from our base app framework
from qt_base_app.app import setup_dark_title_bar
from qt_base_app.models.resource_locator import ResourceLocator # Import the helper

# Import music player dashboard
from music_player.ui.dashboard import MusicPlayerDashboard


def load_custom_fonts():
    """Load custom fonts and return font family names."""
    # Define relative path to fonts dir (relative to project/bundle root)
    fonts_dir_relative = os.path.join("music_player", "fonts")
    # Get absolute path using the helper
    fonts_dir_abs = ResourceLocator.get_path(fonts_dir_relative)

    font_families = {
        "default": None,      # Default UI font (Geist)
        "monospace": None,    # Monospace font (GeistMono)
        "title": None         # Title font (ICA Rubrik)
    }
    font_mappings = {
        "Geist-Regular.ttf": "default",
        "GeistMono-Regular.ttf": "monospace",
        "ICARubrikBlack.ttf": "title"
    }

    # Add custom fonts if available using the absolute path
    if os.path.isdir(fonts_dir_abs):
        print(f"Loading fonts from: {fonts_dir_abs}") # Debug print
        for font_file, category in font_mappings.items():
            font_path = os.path.join(fonts_dir_abs, font_file)
            if os.path.exists(font_path):
                font_id = QFontDatabase.addApplicationFont(str(font_path))
                if font_id >= 0:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        font_families[category] = families[0]
                else:
                    print(f"Warning: Failed to load font: {font_path}")
            # else: # Optional: Debug missing font files
            #     print(f"Debug: Font file not found: {font_path}")
    else:
         print(f"Warning: Fonts directory not found at {fonts_dir_abs}")

    return font_families


def apply_application_styles(app, font_families):
    """Apply global application styles and fonts."""
    # Set application-wide font to the default font if available
    if font_families["default"]:
        app_font = QFont(font_families["default"])
        app_font.setPointSize(10)  # Set a reasonable default size
        app.setFont(app_font)

        # Create stylesheet for specific components
        # Ensure fonts are quoted correctly in CSS
        default_font_css = f"'{font_families['default']}'" if font_families['default'] else 'sans-serif'
        title_font_css = f"'{font_families['title']}'" if font_families['title'] else default_font_css
        mono_font_css = f"'{font_families['monospace']}'" if font_families['monospace'] else 'monospace'

        stylesheet = f"""
            * {{
                font-family: {default_font_css};
            }}

            QLabel#pageTitle {{
                font-family: {title_font_css};
                font-size: 20px;
                font-weight: bold;
            }}
        """

        # Apply stylesheet to application
        # Append carefully if needed, otherwise replace
        app.setStyleSheet(stylesheet) # Use this if it's the main stylesheet
        # app.setStyleSheet(app.styleSheet() + stylesheet) # Use this to append


def main():
    """Main entry point for the Music Player application."""
    # Set the path to the music player config using the helper
    # Path relative to project/bundle root
    config_path_relative = os.path.join("music_player", "resources", "music_player_config.yaml")
    config_path_abs = ResourceLocator.get_path(config_path_relative)

    # Create QApplication
    app = QApplication(sys.argv)

    # Setup dark title bar for Windows
    setup_dark_title_bar(app)

    # Load custom fonts and apply application styles
    font_families = load_custom_fonts()
    apply_application_styles(app, font_families)

    # Initialize our custom music player dashboard
    # Pass the absolute path obtained from ResourceLocator
    window = MusicPlayerDashboard(config_path_abs)

    # Set app icon using the helper
    # Path relative to project/bundle root
    icon_path_relative = os.path.join("music_player", "resources", "play.png")
    icon_path_abs = ResourceLocator.get_path(icon_path_relative)
    if os.path.exists(icon_path_abs):
        app_icon = QIcon(icon_path_abs)
        app.setWindowIcon(app_icon)
        # BaseWindow likely sets its own icon, this might be redundant unless BaseWindow fails
        # window.setWindowIcon(app_icon)
    else:
        print(f"Warning: App icon not found at {icon_path_abs}")

    # Show the window
    window.show()

    # Run the application
    sys.exit(app.exec())


if __name__ == "__main__":
    # Changing directory might not be necessary when using ResourceLocator correctly,
    # but can sometimes help with relative imports if structure is complex.
    # os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main() 