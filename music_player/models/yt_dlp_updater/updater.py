"""
Main yt-dlp updater class.

This module provides the main YtDlpUpdater class that orchestrates
the entire update checking and installation process.
"""
import os
from typing import Optional, Dict, Any, NamedTuple
from datetime import datetime, timedelta
from pathlib import Path

from qt_base_app.models.logger import Logger

from .update_database_manager import YtDlpUpdateManager
from .github_client import GitHubClient
from .version_manager import VersionManager
from .file_manager import FileDownloader, FileInstaller, PathManager, DownloadResult, InstallResult


class UpdateResult(NamedTuple):
    """Result of an update check or installation operation."""
    success: bool
    updated: bool
    current_url: str
    latest_url: str
    current_version: str
    latest_version: str
    error_message: str = ""


class YtDlpUpdater:
    """
    Main yt-dlp updater class.
    
    Coordinates update checking, downloading, and installation of yt-dlp.exe.
    Uses download URLs as version identifiers for future-proof operation.
    """
    
    _instance = None
    
    def __init__(self):
        """Initialize the updater."""
        self.logger = Logger.instance()
        self.db_manager = YtDlpUpdateManager.instance()
        self.version_manager = VersionManager()
        
        # Initialize file management components
        self.path_manager = PathManager()
        self.file_downloader = FileDownloader()
        self.file_installer = FileInstaller()
        
        # Initialize GitHub client with database settings
        settings = self.db_manager.get_settings()
        timeout = settings.get('timeout_seconds', 30)
        max_retries = settings.get('max_retries', 3)
        self.github_client = GitHubClient(timeout=timeout, max_retries=max_retries)
    
    @classmethod
    def instance(cls):
        """Get singleton instance of YtDlpUpdater."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def should_check_for_update(self) -> bool:
        """
        Determine if an update check is needed based on settings and timing.
        
        Returns:
            bool: True if update check should be performed
        """
        # Get all settings from database
        settings = self.db_manager.get_settings()
        
        # Check if updates are enabled
        if not settings.get('enabled', True):
            self.logger.debug(self.__class__.__name__, "Updates disabled in settings")
            return False
        
        # Get time since last check
        last_check_time = self.db_manager.get_last_check_time()
        if last_check_time is None:
            self.logger.info(self.__class__.__name__, "No previous update check found, check needed")
            return True
        
        # Check if enough time has passed
        check_interval_hours = settings.get('check_interval_hours', 24)
        
        time_since_check = datetime.now() - last_check_time
        interval_timedelta = timedelta(hours=check_interval_hours)
        
        if time_since_check >= interval_timedelta:
            self.logger.info(self.__class__.__name__, 
                           f"Update check needed: {time_since_check} >= {interval_timedelta}")
            return True
        else:
            self.logger.debug(self.__class__.__name__, 
                            f"Update check not needed: {time_since_check} < {interval_timedelta}")
            return False
    
    def check_and_update_async(self, force_check: bool = False) -> UpdateResult:
        """
        Check for updates and install if needed (main entry point).
        
        Args:
            force_check (bool): Force check regardless of timing
            
        Returns:
            UpdateResult: Result of the operation
        """
        try:
            # Check if we should perform update check
            if not force_check and not self.should_check_for_update():
                return self._get_current_status()
            
            self.logger.info(self.__class__.__name__, "Starting yt-dlp update check")
            
            # Get current installation info using PathManager
            install_path = self.path_manager.get_install_path()
            
            current_version_info = self._get_current_version_info(install_path)
            current_url = current_version_info.get('download_url', '')
            current_version = current_version_info.get('version_string', '')
            
            # Check for latest version from GitHub
            latest_release = self.github_client.get_latest_release()
            if not latest_release:
                error_msg = "Failed to fetch latest release information from GitHub"
                self.db_manager.record_update_error(error_msg)
                return UpdateResult(
                    success=False,
                    updated=False,
                    current_url=current_url,
                    latest_url="",
                    current_version=current_version,
                    latest_version="",
                    error_message=error_msg
                )
            
            latest_url = latest_release['download_url']
            latest_version = latest_release.get('version', '')
            
            # Record the check attempt
            self.db_manager.record_check_attempt(
                latest_url=latest_url,
                latest_version_string=latest_version,
                current_url=current_url,
                current_version_string=current_version,
                install_path=install_path
            )
            
            # Check if update is needed
            if not self.version_manager.is_newer_version(current_url, latest_url):
                self.logger.info(self.__class__.__name__, "yt-dlp is already up to date")
                return UpdateResult(
                    success=True,
                    updated=False,
                    current_url=current_url,
                    latest_url=latest_url,
                    current_version=current_version,
                    latest_version=latest_version
                )
            
            # Check if auto-update is enabled
            settings = self.db_manager.get_settings()
            auto_update = settings.get('auto_update', True)
            
            if not auto_update:
                self.logger.info(self.__class__.__name__, "Update available but auto-update disabled")
                return UpdateResult(
                    success=True,
                    updated=False,
                    current_url=current_url,
                    latest_url=latest_url,
                    current_version=current_version,
                    latest_version=latest_version,
                    error_message="Auto-update disabled"
                )
            
            # Perform the update
            self.logger.info(self.__class__.__name__, 
                           f"Update needed: {self.version_manager.format_version_for_display(current_url)} -> {self.version_manager.format_version_for_display(latest_url)}")
            
            update_success = self._perform_update(latest_release, install_path)
            
            if update_success:
                # Get new version info after update
                new_version_info = self._get_current_version_info(install_path)
                new_version = new_version_info.get('version_string', latest_version)
                
                # Record successful update
                backup_path = self.version_manager.get_backup_path(install_path)
                self.db_manager.record_update_success(
                    new_download_url=latest_url,
                    new_version_string=new_version,
                    install_path=install_path,
                    backup_path=backup_path
                )
                
                self.logger.info(self.__class__.__name__, f"Successfully updated yt-dlp to {self.version_manager.format_version_for_display(latest_url)}")
                
                return UpdateResult(
                    success=True,
                    updated=True,
                    current_url=latest_url,
                    latest_url=latest_url,
                    current_version=new_version,
                    latest_version=latest_version
                )
            else:
                error_msg = "Failed to install yt-dlp update"
                self.db_manager.record_update_error(error_msg)
                return UpdateResult(
                    success=False,
                    updated=False,
                    current_url=current_url,
                    latest_url=latest_url,
                    current_version=current_version,
                    latest_version=latest_version,
                    error_message=error_msg
                )
                
        except Exception as e:
            error_msg = f"Unexpected error during update: {str(e)}"
            self.logger.error(self.__class__.__name__, error_msg)
            self.db_manager.record_update_error(error_msg)
            
            return UpdateResult(
                success=False,
                updated=False,
                current_url="",
                latest_url="",
                current_version="",
                latest_version="",
                error_message=error_msg
            )
    
    def _get_current_status(self) -> UpdateResult:
        """
        Get current status without performing any checks.
        
        Returns:
            UpdateResult: Current status information
        """
        try:
            # Get current installation info using PathManager
            install_path = self.path_manager.get_install_path()
            current_version_info = self._get_current_version_info(install_path)
            
            return UpdateResult(
                success=True,
                updated=False,
                current_url=current_version_info.get('download_url', ''),
                latest_url='',  # No check performed
                current_version=current_version_info.get('version_string', ''),
                latest_version='',  # No check performed
                error_message="No update check performed"
            )
            
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Error getting current status: {e}")
            return UpdateResult(
                success=False,
                updated=False,
                current_url="",
                latest_url="",
                current_version="",
                latest_version="",
                error_message=str(e)
            )
    
    def _get_current_version_info(self, install_path: str) -> Dict[str, str]:
        """
        Get current version information combining database and file system.
        
        Args:
            install_path (str): Path to yt-dlp.exe
            
        Returns:
            Dict: Version information with 'download_url' and 'version_string'
        """
        # Try to get info from database first
        db_info = self.db_manager.get_current_version_info()
        
        # Get current version from file system using PathManager
        current_version_string = self.path_manager.get_file_version(install_path)
        
        if db_info:
            # Use database info but update version string if available from file
            return {
                'download_url': db_info['download_url'],
                'version_string': current_version_string or db_info['version_string'] or 'unknown'
            }
        else:
            # No database info, try to find yt-dlp and create initial info
            if not os.path.exists(install_path):
                # Try to find in PATH
                path_version = self.version_manager.find_yt_dlp_in_path()
                if path_version:
                    current_version_string = self.path_manager.get_file_version(path_version)
            
            return {
                'download_url': 'unknown',
                'version_string': current_version_string or 'unknown'
            }
    
    def _perform_update(self, release_info: Dict[str, Any], install_path: str) -> bool:
        """
        Perform the actual download and installation of yt-dlp using new file management.
        
        Args:
            release_info (Dict): Release information from GitHub
            install_path (str): Target installation path
            
        Returns:
            bool: True if update was successful
        """
        try:
            download_url = release_info['download_url']
            checksum_url = release_info.get('checksum_url')
            version_string = release_info.get('version', 'unknown')
            
            self.logger.info(self.__class__.__name__, f"Starting update: downloading from {download_url}")
            
            # Validate installation path first
            path_validation = self.path_manager.validate_install_path()
            if not path_validation['valid']:
                error_msg = f"Invalid install path: {path_validation['error_message']}"
                self.logger.error(self.__class__.__name__, error_msg)
                self.db_manager.record_update_error(error_msg)
                return False
            
            if not path_validation['writable']:
                error_msg = f"Install path not writable: {install_path}"
                self.logger.error(self.__class__.__name__, error_msg)
                self.db_manager.record_update_error(error_msg)
                return False
            
            # Check if current installation is in use
            if self.path_manager.is_file_in_use(install_path):
                error_msg = "yt-dlp.exe is currently in use and cannot be updated"
                self.logger.error(self.__class__.__name__, error_msg)
                self.db_manager.record_update_error(error_msg)
                return False
            
            # Get expected checksum if available
            expected_checksum = None
            if checksum_url:
                expected_checksum = self.github_client.download_checksum_file(checksum_url)
                if expected_checksum:
                    self.logger.info(self.__class__.__name__, f"Will verify checksum: {expected_checksum}")
            
            # Download to temporary location
            temp_download_path = self.path_manager.get_temp_download_path()
            
            # Record download start
            self.db_manager.record_download_start(download_url, temp_download_path)
            
            # Progress callback for logging
            def log_progress(progress):
                if progress.percentage % 20 == 0:  # Log every 20%
                    speed_mb = progress.download_speed / (1024 * 1024)
                    self.logger.info(self.__class__.__name__, 
                        f"Download progress: {progress.percentage:.1f}% ({speed_mb:.1f} MB/s)")
            
            # Perform download with progress tracking and checksum verification
            download_result: DownloadResult = self.file_downloader.download_file(
                url=download_url,
                target_path=temp_download_path,
                expected_checksum=expected_checksum,
                progress_callback=log_progress
            )
            
            if not download_result.success:
                error_msg = f"Download failed: {download_result.error_message}"
                self.logger.error(self.__class__.__name__, error_msg)
                self.db_manager.record_update_error(error_msg)
                return False
            
            # Record successful download
            self.db_manager.record_download_complete(
                download_url=download_url,
                file_size=download_result.file_size,
                download_time=download_result.download_time,
                checksum=download_result.checksum
            )
            
            # Log successful download
            size_mb = download_result.file_size / (1024 * 1024)
            self.logger.info(self.__class__.__name__, 
                f"Downloaded {size_mb:.1f} MB in {download_result.download_time:.1f}s")
            
            if download_result.checksum and expected_checksum:
                self.logger.info(self.__class__.__name__, "Checksum verification passed")
            
            # Record installation start
            self.db_manager.record_installation_start(temp_download_path, install_path)
            
            # Install the downloaded file
            install_result: InstallResult = self.file_installer.install_update(
                downloaded_file=temp_download_path,
                target_version=version_string
            )
            
            if install_result.success:
                # Get the actual installed version
                installed_version = self.path_manager.get_file_version(install_result.installed_path)
                
                # Record successful installation
                self.db_manager.record_installation_complete(
                    installed_path=install_result.installed_path,
                    backup_path=install_result.backup_path,
                    previous_version=install_result.previous_version,
                    new_version=installed_version or version_string
                )
                
                # Record successful update in database
                self.db_manager.record_update_success(
                    new_download_url=download_url,
                    new_version_string=installed_version or version_string,
                    install_path=install_result.installed_path,
                    backup_path=install_result.backup_path
                )
                
                self.logger.info(self.__class__.__name__, 
                    f"Update completed successfully: {installed_version or version_string}")
                
                # Clean up old backups (keep last 3)
                self.file_installer.cleanup_old_backups(keep_count=3)
                
                return True
            else:
                error_msg = f"Installation failed: {install_result.error_message}"
                self.logger.error(self.__class__.__name__, error_msg)
                self.db_manager.record_update_error(error_msg)
                return False
                
        except Exception as e:
            error_msg = f"Update process failed with exception: {e}"
            self.logger.error(self.__class__.__name__, error_msg)
            self.db_manager.record_update_error(error_msg)
            return False
    
    def get_update_status(self) -> Dict[str, Any]:
        """
        Get comprehensive update status information.
        
        Returns:
            Dict: Status information including versions, timing, etc.
        """
        try:
            # Get database stats
            db_stats = self.db_manager.get_database_stats()
            
            # Get current version info using PathManager
            install_path = self.path_manager.get_install_path()
            
            current_version_info = self._get_current_version_info(install_path)
            
            # Get settings
            settings = self.db_manager.get_settings()
            enabled = settings.get('enabled', True)
            auto_update = settings.get('auto_update', True)
            check_interval = settings.get('check_interval_hours', 24)
            
            # Get path validation info
            path_validation = self.path_manager.validate_install_path()
            
            status = {
                'enabled': enabled,
                'auto_update': auto_update,
                'check_interval_hours': check_interval,
                'install_path': install_path,
                'path_valid': path_validation['valid'],
                'path_writable': path_validation['writable'],
                'directory_exists': path_validation['directory_exists'],
                'current_url': current_version_info.get('download_url'),
                'current_version': current_version_info.get('version_string'),
                'last_check_time': db_stats.get('last_check_time'),
                'last_update_time': db_stats.get('last_update_time'),
                'total_checks': db_stats.get('total_checks', 0),
                'total_updates': db_stats.get('total_updates', 0),
                'last_error': db_stats.get('last_error'),
                'file_exists': os.path.exists(install_path),
                'file_in_use': self.path_manager.is_file_in_use(install_path) if os.path.exists(install_path) else False,
                'should_check': self.should_check_for_update()
            }
            
            return status
            
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Error getting update status: {e}")
            return {'error': str(e)} 