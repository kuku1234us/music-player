# qt_base_app/models/resource_locator.py
import sys
import os
import platform # Keep platform import if needed elsewhere, or remove if not

# REMOVED: Import Logger
# from .logger import Logger 

class ResourceLocator:
    """
    Provides a reliable way to locate resource files both when running
    from source and when running as a bundled application (PyInstaller).
    """

    @staticmethod
    def get_path(relative_path: str) -> str:
        """
        Get the absolute path to a resource file.

        Args:
            relative_path: The path to the resource relative to the
                           application root (source) or the bundle root (_MEIPASS).

        Returns:
            The absolute path to the resource.
        """
        # REMOVED: Get logger instance 
        # logger = Logger.instance()
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
            # REMOVED: logger.debug(f"[ResourceLocator] Running bundled, _MEIPASS: {base_path}")
        except AttributeError:
            # Running from source. Use the directory of the main script.
            base_path = os.path.abspath(os.path.dirname(sys.argv[0]))
            # Fallback if sys.argv[0] is not reliable 
            if not os.path.isdir(base_path):
                 base_path = os.path.abspath(".") # Use CWD as last resort
            # REMOVED: logger.debug(f"[ResourceLocator] Running from source, base_path: {base_path}")

        # Ensure base_path exists
        if not os.path.isdir(base_path):
             # Use print to stderr for warnings
             print(f"[ResourceLocator] Warning: Determined base_path does not exist: {base_path}", file=sys.stderr)
             # REMOVED: logger.warning(...)
             # raise FileNotFoundError(...) # Keep commented out or decide on error handling

        # Use os.path.normpath to handle potential mixed slashes
        resource_abs_path = os.path.normpath(os.path.join(base_path, relative_path))
        # REMOVED: logger.debug(f"[ResourceLocator] Resolved '{relative_path}' to: {resource_abs_path}")

        return resource_abs_path
