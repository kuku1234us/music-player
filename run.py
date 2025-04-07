#!/usr/bin/env python
"""
Entry point script to run the Music Player application.
"""
import sys
import os
from ctypes import windll, byref, c_int, sizeof

# Add the project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtGui import QIcon
from music_player.ui.dashboard import create_dashboard

def setup_dark_title_bar(app):
    """Set dark title bar on Windows if available."""
    if sys.platform == "win32":
        try:
            # Windows 11 and Windows 10 after 1903
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            # Windows 10 before 1903
            DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19
            
            # Ensure Qt running with dark mode support
            app.setStyle("Fusion")
            
            # This will be applied to all top-level windows
            def apply_dark_title_to_window(window):
                try:
                    hwnd = int(window.winId())
                    # Try both attributes for compatibility
                    windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 
                        byref(c_int(1)), sizeof(c_int)
                    )
                    windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1, 
                        byref(c_int(1)), sizeof(c_int)
                    )
                    print(f"Dark title bar applied to window {hwnd}")
                except Exception as e:
                    print(f"Failed to apply dark title bar to window: {e}")
            
            # Store the original show method
            original_widget_show = QWidget.show
            
            # Create a patched show method that applies dark title bar
            def patched_show(self):
                result = original_widget_show(self)
                if self.isWindow():
                    apply_dark_title_to_window(self)
                return result
            
            # Monkey patch QWidget.show method
            QWidget.show = patched_show
            
            print("Dark title bar setup complete")
        except Exception as e:
            print(f"Failed to set up dark title bar: {e}")


if __name__ == "__main__":
    # Create application
    app = QApplication(sys.argv)
    
    # Set app icon
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                         "music_player", "resources", "play.png")
    if os.path.exists(icon_path):
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)
    else:
        print(f"Warning: App icon not found at {icon_path}")
    
    # Apply dark title bar
    setup_dark_title_bar(app)
    
    # Set Fusion style for consistent appearance
    app.setStyle("Fusion")
    
    # Create and show dashboard
    dashboard = create_dashboard()
    dashboard.show()
    
    sys.exit(app.exec()) 