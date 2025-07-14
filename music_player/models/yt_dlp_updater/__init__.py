"""
yt-dlp automatic updater module.

This module provides automatic update functionality for yt-dlp.exe on Windows systems.
It handles GitHub API integration, version comparison, file downloads, and database tracking.
"""

from .updater import YtDlpUpdater
from .update_database_manager import YtDlpUpdateManager
from .github_client import GitHubClient
from .version_manager import VersionManager
from .settings_integration import YT_DLP_UPDATER_SETTINGS

__all__ = [
    'YtDlpUpdater',
    'YtDlpUpdateManager', 
    'GitHubClient',
    'VersionManager',
    'YT_DLP_UPDATER_SETTINGS'
] 