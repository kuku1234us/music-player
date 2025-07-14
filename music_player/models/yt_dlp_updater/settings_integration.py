"""
Settings integration for yt-dlp updater.

This module defines all settings keys, defaults, and types for the yt-dlp
automatic updater functionality. These settings are stored in QSettings
for user preferences, while update tracking data is stored in the database.
"""
from qt_base_app.models.settings_manager import SettingType


# --- Settings Keys ---
YT_DLP_UPDATER_ENABLED_KEY = 'yt_dlp_updater/enabled'
YT_DLP_UPDATER_AUTO_UPDATE_KEY = 'yt_dlp_updater/auto_update'
YT_DLP_UPDATER_CHECK_INTERVAL_KEY = 'yt_dlp_updater/check_interval_hours'
YT_DLP_UPDATER_INSTALL_PATH_KEY = 'yt_dlp_updater/install_path'
YT_DLP_UPDATER_BACKUP_PATH_KEY = 'yt_dlp_updater/backup_path'
YT_DLP_UPDATER_TIMEOUT_KEY = 'yt_dlp_updater/timeout_seconds'
YT_DLP_UPDATER_MAX_RETRIES_KEY = 'yt_dlp_updater/max_retries'
YT_DLP_UPDATER_VERIFY_CHECKSUMS_KEY = 'yt_dlp_updater/verify_checksums'
YT_DLP_UPDATER_KEEP_BACKUPS_KEY = 'yt_dlp_updater/keep_backups'
YT_DLP_UPDATER_NOTIFICATION_LEVEL_KEY = 'yt_dlp_updater/notification_level'

# --- Default Values ---
DEFAULT_YT_DLP_UPDATER_ENABLED = True
DEFAULT_YT_DLP_UPDATER_AUTO_UPDATE = True
DEFAULT_YT_DLP_UPDATER_CHECK_INTERVAL = 24  # hours
DEFAULT_YT_DLP_UPDATER_INSTALL_PATH = r'C:\yt-dlp\yt-dlp.exe'
DEFAULT_YT_DLP_UPDATER_BACKUP_PATH = r'C:\yt-dlp\yt-dlp.exe.backup'
DEFAULT_YT_DLP_UPDATER_TIMEOUT = 30  # seconds
DEFAULT_YT_DLP_UPDATER_MAX_RETRIES = 3
DEFAULT_YT_DLP_UPDATER_VERIFY_CHECKSUMS = True
DEFAULT_YT_DLP_UPDATER_KEEP_BACKUPS = 3  # number of backup files to keep
DEFAULT_YT_DLP_UPDATER_NOTIFICATION_LEVEL = 'normal'  # 'minimal', 'normal', 'verbose'

# --- Settings Dictionary for Registration ---
YT_DLP_UPDATER_SETTINGS = {
    # Core update behavior
    YT_DLP_UPDATER_ENABLED_KEY: (DEFAULT_YT_DLP_UPDATER_ENABLED, SettingType.BOOL),
    YT_DLP_UPDATER_AUTO_UPDATE_KEY: (DEFAULT_YT_DLP_UPDATER_AUTO_UPDATE, SettingType.BOOL),
    YT_DLP_UPDATER_CHECK_INTERVAL_KEY: (DEFAULT_YT_DLP_UPDATER_CHECK_INTERVAL, SettingType.INT),
    
    # File paths
    YT_DLP_UPDATER_INSTALL_PATH_KEY: (DEFAULT_YT_DLP_UPDATER_INSTALL_PATH, SettingType.PATH),
    YT_DLP_UPDATER_BACKUP_PATH_KEY: (DEFAULT_YT_DLP_UPDATER_BACKUP_PATH, SettingType.PATH),
    
    # Network settings
    YT_DLP_UPDATER_TIMEOUT_KEY: (DEFAULT_YT_DLP_UPDATER_TIMEOUT, SettingType.INT),
    YT_DLP_UPDATER_MAX_RETRIES_KEY: (DEFAULT_YT_DLP_UPDATER_MAX_RETRIES, SettingType.INT),
    
    # Security and backup settings
    YT_DLP_UPDATER_VERIFY_CHECKSUMS_KEY: (DEFAULT_YT_DLP_UPDATER_VERIFY_CHECKSUMS, SettingType.BOOL),
    YT_DLP_UPDATER_KEEP_BACKUPS_KEY: (DEFAULT_YT_DLP_UPDATER_KEEP_BACKUPS, SettingType.INT),
    
    # User interface settings
    YT_DLP_UPDATER_NOTIFICATION_LEVEL_KEY: (DEFAULT_YT_DLP_UPDATER_NOTIFICATION_LEVEL, SettingType.STRING),
}


class UpdaterSettingsHelper:
    """
    Helper class for updater settings operations.
    Provides convenience methods for accessing updater settings.
    """
    
    @staticmethod
    def get_all_settings_keys():
        """Get list of all updater setting keys."""
        return list(YT_DLP_UPDATER_SETTINGS.keys())
    
    @staticmethod
    def get_default_value(key: str):
        """Get default value for a setting key."""
        if key in YT_DLP_UPDATER_SETTINGS:
            return YT_DLP_UPDATER_SETTINGS[key][0]
        return None
    
    @staticmethod
    def get_setting_type(key: str):
        """Get setting type for a setting key."""
        if key in YT_DLP_UPDATER_SETTINGS:
            return YT_DLP_UPDATER_SETTINGS[key][1]
        return None
    
    @staticmethod
    def validate_notification_level(level: str) -> bool:
        """Validate notification level value."""
        return level in ['minimal', 'normal', 'verbose']
    
    @staticmethod
    def validate_check_interval(hours: int) -> bool:
        """Validate check interval (should be reasonable)."""
        return 1 <= hours <= 168  # 1 hour to 1 week
    
    @staticmethod
    def validate_timeout(seconds: int) -> bool:
        """Validate network timeout (should be reasonable)."""
        return 5 <= seconds <= 300  # 5 seconds to 5 minutes
    
    @staticmethod
    def validate_max_retries(retries: int) -> bool:
        """Validate max retries (should be reasonable)."""
        return 0 <= retries <= 10
    
    @staticmethod
    def validate_keep_backups(count: int) -> bool:
        """Validate backup count (should be reasonable)."""
        return 0 <= count <= 20  # 0 to 20 backup files 