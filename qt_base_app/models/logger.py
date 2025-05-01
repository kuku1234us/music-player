import logging
import sys
import re
from pathlib import Path
from typing import Optional, Any, Dict

# Import SettingsManager to access YAML config
from .settings_manager import SettingsManager

def _sanitize_filename(name: str) -> str:
    """Removes invalid characters for filenames."""
    # Remove characters not allowed in common filesystems
    # Use raw string and single backslash for literal backslash in character class
    sanitized = re.sub(r'[\/*?:"<>|]', "", name)
    # Replace potential leading/trailing dots or spaces
    sanitized = sanitized.strip(". ")
    if not sanitized: # Handle case where name becomes empty
        sanitized = "app" # Default if title is invalid/empty
    return sanitized

class Logger:
    """
    Singleton class for application-wide logging.

    Reads configuration from the YAML file loaded via SettingsManager:
    - logging.level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL). Default: INFO.
    - logging.log_to_file: Boolean, whether to log to a file. Default: True.
    - logging.log_to_console: Boolean, whether to print logs to stdout. Default: True.
    - logging.clear_on_startup: Boolean, whether to clear the log file on app start. Default: True.
    - app.title: Used for the log filename. Default: 'Application'.

    Log file is created in the project root (dev) or executable directory (built).
    Filename format: [app_title].log
    """
    _instance: Optional['Logger'] = None
    _logger: Optional[logging.Logger] = None # Store the configured logger instance

    _log_levels = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }

    @classmethod
    def instance(cls) -> 'Logger':
        """Get the singleton instance of Logger."""
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            cls._instance._configure() # Configure on first instance creation
        return cls._instance

    def __init__(self):
        """Prevent direct instantiation after singleton is created."""
        if Logger._instance is not None and self._logger is not None:
            raise RuntimeError("Use Logger.instance() to get the logger")
        # Initial call from instance() allows configuration

    def _configure(self):
        """Configures the logger based on settings."""
        if self._logger is not None: # Prevent reconfiguration
            return
        try:
            settings = SettingsManager.instance()

            # Read Configuration
            log_level_str = settings.get_yaml_config('logging.level', 'INFO').upper()
            log_to_file = settings.get_yaml_config('logging.log_to_file', True)
            log_to_console = settings.get_yaml_config('logging.log_to_console', True)
            clear_on_startup = settings.get_yaml_config('logging.clear_on_startup', True)
            app_title = settings.get_yaml_config('app.title', 'Application')

            # Determine Log Level
            log_level = self._log_levels.get(log_level_str, logging.INFO)

            # Setup Logger instance for this singleton
            logger_instance = logging.getLogger(app_title)
            logger_instance.setLevel(log_level)
            logger_instance.propagate = False

            # Prevent adding handlers multiple times (redundant due to singleton check, but safe)
            if logger_instance.hasHandlers():
                 print("Logger already configured, skipping handler setup.")
                 self._logger = logger_instance # Ensure self._logger is set
                 return

            # Define Formatter
            log_format = '%(asctime)s - %(levelname)-8s - %(name)s - %(message)s'
            formatter = logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S')

            # Configure File Handler
            if log_to_file:
                try:
                    if getattr(sys, 'frozen', False):
                        log_dir = Path(sys.executable).parent
                    else:
                        log_dir = Path.cwd()

                    log_filename = f"{_sanitize_filename(app_title)}.log"
                    log_file_path = log_dir / log_filename
                    filemode = 'w' if clear_on_startup else 'a'

                    file_handler = logging.FileHandler(log_file_path, mode=filemode, encoding='utf-8')
                    file_handler.setFormatter(formatter)
                    file_handler.setLevel(log_level)
                    logger_instance.addHandler(file_handler)
                    print(f"Logging to file: {log_file_path} (Level: {log_level_str}, Clear: {clear_on_startup})")
                except Exception as e:
                    print(f"Error setting up file logger: {e}", file=sys.stderr)

            # Configure Console Handler
            if log_to_console:
                try:
                    console_handler = logging.StreamHandler(sys.stdout)
                    console_handler.setFormatter(formatter)
                    console_handler.setLevel(log_level)
                    logger_instance.addHandler(console_handler)
                    print(f"Logging to console enabled (Level: {log_level_str})")
                except Exception as e:
                    print(f"Error setting up console logger: {e}", file=sys.stderr)

            # Store the configured logger
            self._logger = logger_instance
            self._logger.info(f"--- Logger Initialized (Level: {log_level_str}) ---")

        except Exception as e:
            print(f"FATAL ERROR configuring logger: {e}", file=sys.stderr)
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
            self._logger = logging.getLogger("FallbackLogger")
            self._logger.error(f"Logger configuration failed: {e}", exc_info=True)

    # --- Public Logging Methods ---
    def _log(self, level, msg: str, *args, **kwargs):
        # Helper to ensure logger is configured before use
        if self._logger is None:
            print(f"Logger not configured. Message: {msg}", file=sys.stderr)
            return
        log_method = getattr(self._logger, level)
        log_method(msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs):
        self._log('debug', msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        self._log('info', msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        self._log('warning', msg, *args, **kwargs)

    def error(self, msg: str, *args, exc_info=False, **kwargs):
        # Pass exc_info explicitly to logger method
        if self._logger is None:
            print(f"Logger not configured. Error: {msg}", file=sys.stderr)
            return
        self._logger.error(msg, *args, exc_info=exc_info, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        self._log('critical', msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs):
        # Use logger's exception method which automatically adds exc_info
        if self._logger is None:
            print(f"Logger not configured. Exception: {msg}", file=sys.stderr)
            return
        self._logger.exception(msg, *args, **kwargs) 