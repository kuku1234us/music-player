from pathlib import Path
from qt_base_app.models.settings_manager import SettingType

# --- Define Keys ---
# Player settings
PLAYER_VOLUME_KEY = 'player/volume'
# Preferences
PREF_SEEK_INTERVAL_KEY = 'preferences/seek_interval'
PREF_WORKING_DIR_KEY = 'preferences/working_dir'
# Recent items
RECENT_FILES_KEY = 'recent/files'
RECENT_PLAYLISTS_KEY = 'recent/playlists'

# Youtube Downloader settings
YT_DOWNLOAD_DIR_KEY = 'youtube_downloader/download_dir' # Key for output directory
YT_ACTIVE_RESOLUTION_KEY = 'youtube_downloader/active_resolution'
YT_HTTPS_ENABLED_KEY = 'youtube_downloader/https_enabled'
YT_M4A_ENABLED_KEY = 'youtube_downloader/m4a_enabled'
YT_SUBTITLES_ENABLED_KEY = 'youtube_downloader/subtitles/enabled'
YT_SUBTITLES_LANG_KEY = 'youtube_downloader/subtitles/language'
YT_COOKIES_ENABLED_KEY = 'youtube_downloader/cookies/enabled'
YTDLP_USE_CLI_KEY = 'youtube_downloader/ytdlp/use_cli'
# Restore QSettings key for YouTube API
YT_API_QSETTINGS_KEY = 'youtube/api_key' 
# Add QSettings key for Groq API
GROQ_API_QSETTINGS_KEY = 'ai/groq/api_key' 
# Add key for max concurrent downloads
YT_MAX_CONCURRENT_KEY = 'youtube_downloader/max_concurrent'

# --- NEW: Conversion Settings ---
CONVERSION_MP3_BITRATE_KEY = 'conversion/mp3_bitrate_kbps'

# --- Environment Variable Keys (For .env fallback) ---
# Only YT needed if hybrid approach was kept, remove otherwise.
# Assuming QSettings only now, remove both:
# YT_API_ENV_KEY = 'YOUTUBE_API_KEY'
# GROQ_API_ENV_KEY = 'GROQ_API_KEY'

# --- Define Default Values ---
DEFAULT_PLAYER_VOLUME = 100
DEFAULT_SEEK_INTERVAL = 3
# Default from old settings manager was Path.home()
DEFAULT_WORKING_DIR = str(Path.home())
DEFAULT_RECENT_FILES = []
DEFAULT_RECENT_PLAYLISTS = []
# Youtube defaults
DEFAULT_YT_DOWNLOAD_DIR = str(Path.home() / "Downloads")
DEFAULT_YT_ACTIVE_RESOLUTION = "720p"
DEFAULT_YT_HTTPS_ENABLED = True
DEFAULT_YT_M4A_ENABLED = True
DEFAULT_YT_SUBTITLES_ENABLED = True
DEFAULT_YT_SUBTITLES_LANG = "en"
DEFAULT_YT_COOKIES_ENABLED = False
DEFAULT_YTDLP_USE_CLI = True # Defaulting to CLI as per migration design note
# Restore API Key Defaults
DEFAULT_YT_API_KEY = "" 
DEFAULT_GROQ_API_KEY = "" 
# Add default for max concurrent downloads
DEFAULT_YT_MAX_CONCURRENT = 3

# --- NEW: Conversion Defaults ---
DEFAULT_CONVERSION_MP3_BITRATE = 128 # Stored as integer (e.g., 128 for 128kbps)

# --- Define Defaults Dictionary for Persistent Settings ---
# This dictionary maps the setting keys to their default values and types.
# The SettingsManager uses this when set_defaults() is called to initialize
# persistent settings (like those stored in QSettings/Registry) only if
# they don't already exist in the user's stored settings.
MUSIC_PLAYER_DEFAULTS = {
    # Map Key Constant -> (Default Value, SettingType)
    PLAYER_VOLUME_KEY: (DEFAULT_PLAYER_VOLUME, SettingType.INT),
    PREF_SEEK_INTERVAL_KEY: (DEFAULT_SEEK_INTERVAL, SettingType.INT),
    PREF_WORKING_DIR_KEY: (DEFAULT_WORKING_DIR, SettingType.PATH),
    RECENT_FILES_KEY: (DEFAULT_RECENT_FILES, SettingType.LIST),
    RECENT_PLAYLISTS_KEY: (DEFAULT_RECENT_PLAYLISTS, SettingType.LIST),
    # Youtube Downloader defaults
    YT_DOWNLOAD_DIR_KEY: (DEFAULT_YT_DOWNLOAD_DIR, SettingType.PATH),
    YT_ACTIVE_RESOLUTION_KEY: (DEFAULT_YT_ACTIVE_RESOLUTION, SettingType.STRING),
    YT_HTTPS_ENABLED_KEY: (DEFAULT_YT_HTTPS_ENABLED, SettingType.BOOL),
    YT_M4A_ENABLED_KEY: (DEFAULT_YT_M4A_ENABLED, SettingType.BOOL),
    YT_SUBTITLES_ENABLED_KEY: (DEFAULT_YT_SUBTITLES_ENABLED, SettingType.BOOL),
    YT_SUBTITLES_LANG_KEY: (DEFAULT_YT_SUBTITLES_LANG, SettingType.STRING),
    YT_COOKIES_ENABLED_KEY: (DEFAULT_YT_COOKIES_ENABLED, SettingType.BOOL),
    YTDLP_USE_CLI_KEY: (DEFAULT_YTDLP_USE_CLI, SettingType.BOOL),
    # Add API Keys back to QSettings defaults
    YT_API_QSETTINGS_KEY: (DEFAULT_YT_API_KEY, SettingType.STRING),
    GROQ_API_QSETTINGS_KEY: (DEFAULT_GROQ_API_KEY, SettingType.STRING),
    # Add max concurrent downloads to defaults
    YT_MAX_CONCURRENT_KEY: (DEFAULT_YT_MAX_CONCURRENT, SettingType.INT),
    # --- NEW: Conversion Settings Default ---
    CONVERSION_MP3_BITRATE_KEY: (DEFAULT_CONVERSION_MP3_BITRATE, SettingType.INT),
} 