"""
Main entry point for Qt base applications.
"""
import sys
import platform
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from .window.base_window import BaseWindow
from .theme.theme_manager import ThemeManager


def setup_dark_title_bar(app):
    """Set up dark title bar for Windows applications."""
    if platform.system() == "Windows":
        import ctypes
        app.setStyle("Fusion")
        
        # Tell Windows to use dark title bar
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        set_window_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
        get_parent = ctypes.windll.user32.GetParent
        
        def apply_dark_title_bar(window_id):
            """Apply dark title bar to a specific window."""
            if window_id:
                try:
                    # Convert window id to int for Windows API
                    hwnd = int(window_id)
                    value = 0x01  # True
                    value_ptr = ctypes.byref(ctypes.c_int(value))
                    value_size = ctypes.sizeof(ctypes.c_int)
                    
                    # Apply to parent window (the actual window frame)
                    parent_hwnd = get_parent(hwnd)
                    if parent_hwnd:
                        set_window_attribute(
                            parent_hwnd,
                            DWMWA_USE_IMMERSIVE_DARK_MODE,
                            value_ptr,
                            value_size
                        )
                    else:
                        # If no parent, try applying to the window itself
                        set_window_attribute(
                            hwnd,
                            DWMWA_USE_IMMERSIVE_DARK_MODE,
                            value_ptr,
                            value_size
                        )
                except Exception as e:
                    print(f"Failed to apply dark title bar: {e}")
        
        # Apply to all new windows
        app.focusWindowChanged.connect(
            lambda window: apply_dark_title_bar(window.winId()) if window else None
        )


def create_app(config_path: str = None) -> tuple[QApplication, BaseWindow]:
    """
    Create and configure the application and main window.
    
    Args:
        config_path: Optional path to the application configuration file.
                    If not provided, uses the default config.
    
    Returns:
        tuple: (QApplication instance, BaseWindow instance)
    """
    # Create application
    app = QApplication(sys.argv)
    
    # Initialize theme manager
    theme = ThemeManager.instance()
    
    # Set up dark title bar for Windows
    setup_dark_title_bar(app)
    
    # Create main window
    window = BaseWindow(config_path)
    window.show()
    
    return app, window


def run_app(app: QApplication, window: BaseWindow) -> int:
    """
    Run the application.
    
    Args:
        app: QApplication instance
        window: BaseWindow instance
    
    Returns:
        int: Application exit code
    """
    return app.exec() 