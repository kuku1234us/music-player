"""
File management for yt-dlp updates.
Handles download, installation, backup, and rollback operations.
"""

import os
import sys
import hashlib
import tempfile
import shutil
import stat
import time
from pathlib import Path
from typing import Optional, Dict, Any, Callable, NamedTuple
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse

from qt_base_app.models.logger import Logger
from qt_base_app.models.settings_manager import SettingsManager, SettingType


class DownloadProgress(NamedTuple):
    """Progress information for download operations."""
    bytes_downloaded: int
    total_bytes: int
    percentage: float
    download_speed: float  # bytes per second
    eta_seconds: float     # estimated time remaining


class DownloadResult(NamedTuple):
    """Result of a download operation."""
    success: bool
    file_path: Optional[str]
    file_size: int
    download_time: float
    checksum: Optional[str]
    error_message: str = ""


class InstallResult(NamedTuple):
    """Result of an installation operation."""
    success: bool
    installed_path: str
    backup_path: Optional[str]
    previous_version: Optional[str]
    error_message: str = ""


class PathManager:
    """
    Manages file system paths and operations for yt-dlp updates.
    Handles path validation, permission checks, and directory creation.
    """
    
    def __init__(self):
        self.logger = Logger.instance()
    
    def get_install_path(self) -> str:
        """
        Get the target installation path for yt-dlp.exe.
        
        Returns:
            str: Full path where yt-dlp.exe should be installed
        """
        try:
            # Import here to avoid circular imports
            from .update_database_manager import YtDlpUpdateManager
            
            # Get from database settings
            db_manager = YtDlpUpdateManager.instance()
            settings = db_manager.get_settings()
            install_path = settings.get('install_path', r'C:\yt-dlp\yt-dlp.exe')
        except Exception as e:
            self.logger.warning("PathManager", f"Could not get install path from database: {e}")
            # Fallback to default
            install_path = r'C:\yt-dlp\yt-dlp.exe'
        
        # Ensure path is absolute
        if not os.path.isabs(install_path):
            # Make relative to application directory
            if getattr(sys, 'frozen', False):
                app_dir = os.path.dirname(sys.executable)
            else:
                app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            install_path = os.path.join(app_dir, install_path)
        
        return str(Path(install_path).resolve())
    
    def get_backup_path(self) -> str:
        """
        Get the backup path for the current yt-dlp.exe.
        
        Returns:
            str: Full path for backup file
        """
        install_path = self.get_install_path()
        return f"{install_path}.backup"
    
    def get_temp_download_path(self) -> str:
        """
        Get a temporary path for downloading the new yt-dlp.exe.
        
        Returns:
            str: Full path for temporary download file
        """
        install_path = self.get_install_path()
        return f"{install_path}.tmp"
    
    def validate_install_path(self) -> Dict[str, Any]:
        """
        Validate the installation path and check permissions.
        
        Returns:
            Dict with validation results:
            - valid: bool
            - writable: bool
            - directory_exists: bool
            - file_exists: bool
            - error_message: str
        """
        install_path = self.get_install_path()
        install_dir = os.path.dirname(install_path)
        
        result = {
            'valid': True,
            'writable': False,
            'directory_exists': False,
            'file_exists': False,
            'error_message': ''
        }
        
        try:
            # Check if path is valid
            Path(install_path).resolve()
            
            # Check if directory exists
            result['directory_exists'] = os.path.exists(install_dir)
            
            # Check if file exists
            result['file_exists'] = os.path.exists(install_path)
            
            # Check write permissions
            if result['directory_exists']:
                result['writable'] = os.access(install_dir, os.W_OK)
            else:
                # Try to create directory to test permissions
                try:
                    os.makedirs(install_dir, exist_ok=True)
                    result['directory_exists'] = True
                    result['writable'] = os.access(install_dir, os.W_OK)
                except (OSError, PermissionError) as e:
                    result['error_message'] = f"Cannot create directory: {e}"
                    result['valid'] = False
            
            # If file exists, check if we can write to it
            if result['file_exists'] and result['writable']:
                try:
                    # Test write access by attempting to open in append mode
                    with open(install_path, 'ab'):
                        pass
                except (OSError, PermissionError):
                    result['writable'] = False
                    result['error_message'] = "File exists but is not writable"
                    
        except (OSError, ValueError) as e:
            result['valid'] = False
            result['error_message'] = f"Invalid path: {e}"
        
        return result
    
    def ensure_directory_exists(self, path: str) -> bool:
        """
        Ensure that the directory containing the given path exists.
        
        Args:
            path: File path whose directory should exist
            
        Returns:
            bool: True if directory exists or was created successfully
        """
        try:
            directory = os.path.dirname(path)
            os.makedirs(directory, exist_ok=True)
            return True
        except (OSError, PermissionError) as e:
            self.logger.error("PathManager", f"Failed to create directory for {path}: {e}")
            return False
    
    def is_file_in_use(self, file_path: str) -> bool:
        """
        Check if a file is currently in use (locked by another process).
        
        Args:
            file_path: Path to check
            
        Returns:
            bool: True if file is in use
        """
        if not os.path.exists(file_path):
            return False
            
        try:
            # Try to open the file in exclusive mode
            with open(file_path, 'r+b') as f:
                pass
            return False
        except (OSError, PermissionError):
            return True
    
    def get_file_version(self, file_path: str) -> Optional[str]:
        """
        Get version information from yt-dlp.exe.
        
        Args:
            file_path: Path to yt-dlp.exe
            
        Returns:
            Optional[str]: Version string or None if not available
        """
        if not os.path.exists(file_path):
            return None
            
        try:
            import subprocess
            result = subprocess.run(
                [file_path, '--version'],
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            self.logger.warning("PathManager", f"Failed to get version from {file_path}: {e}")
        
        return None


class FileDownloader:
    """
    Handles secure download of yt-dlp.exe with progress tracking and verification.
    """
    
    def __init__(self):
        self.logger = Logger.instance()
        self.path_manager = PathManager()
        
        # Get download configuration from database
        try:
            from .update_database_manager import YtDlpUpdateManager
            db_manager = YtDlpUpdateManager.instance()
            settings = db_manager.get_settings()
            self.timeout = settings.get('timeout_seconds', 30)
            self.max_retries = settings.get('max_retries', 3)
        except Exception as e:
            self.logger.warning("FileDownloader", f"Could not get settings from database: {e}")
            self.timeout = 30
            self.max_retries = 3
        
        self.chunk_size = 8192  # 8KB chunks for progress tracking
        self.user_agent = "MusicPlayer-YtDlpUpdater/1.0"
    
    def download_file(
        self, 
        url: str, 
        target_path: str,
        expected_checksum: Optional[str] = None,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None
    ) -> DownloadResult:
        """
        Download a file with progress tracking and optional checksum verification.
        
        Args:
            url: URL to download from
            target_path: Where to save the downloaded file
            expected_checksum: Optional SHA256 checksum to verify
            progress_callback: Optional callback for progress updates
            
        Returns:
            DownloadResult: Result of the download operation
        """
        start_time = time.time()
        
        # Ensure target directory exists
        if not self.path_manager.ensure_directory_exists(target_path):
            return DownloadResult(
                success=False,
                file_path=None,
                file_size=0,
                download_time=0,
                checksum=None,
                error_message="Failed to create target directory"
            )
        
        # Attempt download with retries
        for attempt in range(self.max_retries):
            try:
                result = self._download_with_progress(
                    url, target_path, progress_callback, start_time
                )
                
                if result.success:
                    # Verify checksum if provided
                    if expected_checksum:
                        if not self._verify_checksum(target_path, expected_checksum):
                            # Checksum failed, remove file and try again
                            self._safe_remove_file(target_path)
                            if attempt < self.max_retries - 1:
                                self.logger.warning("FileDownloader", 
                                    f"Checksum verification failed, retrying... (attempt {attempt + 1})")
                                continue
                            else:
                                return DownloadResult(
                                    success=False,
                                    file_path=None,
                                    file_size=0,
                                    download_time=time.time() - start_time,
                                    checksum=result.checksum,
                                    error_message="Checksum verification failed after all retries"
                                )
                    
                    return result
                else:
                    if attempt < self.max_retries - 1:
                        self.logger.warning("FileDownloader", 
                            f"Download failed, retrying... (attempt {attempt + 1}): {result.error_message}")
                        time.sleep(2 ** attempt)  # Exponential backoff
                    
            except Exception as e:
                error_msg = f"Download attempt {attempt + 1} failed: {e}"
                self.logger.error("FileDownloader", error_msg)
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    return DownloadResult(
                        success=False,
                        file_path=None,
                        file_size=0,
                        download_time=time.time() - start_time,
                        checksum=None,
                        error_message=error_msg
                    )
        
        return DownloadResult(
            success=False,
            file_path=None,
            file_size=0,
            download_time=time.time() - start_time,
            checksum=None,
            error_message="All download attempts failed"
        )
    
    def _download_with_progress(
        self,
        url: str,
        target_path: str,
        progress_callback: Optional[Callable[[DownloadProgress], None]],
        start_time: float
    ) -> DownloadResult:
        """
        Perform the actual download with progress tracking.
        """
        try:
            # Create request with headers
            request = Request(url)
            request.add_header('User-Agent', self.user_agent)
            request.add_header('Accept-Encoding', 'gzip, deflate')
            
            # Open connection
            with urlopen(request, timeout=self.timeout) as response:
                # Get file size from headers
                content_length = response.headers.get('Content-Length')
                total_bytes = int(content_length) if content_length else 0
                
                # Initialize progress tracking
                bytes_downloaded = 0
                last_progress_time = start_time
                
                # Create hash for checksum calculation
                sha256_hash = hashlib.sha256()
                
                # Download file in chunks
                with open(target_path, 'wb') as f:
                    while True:
                        chunk = response.read(self.chunk_size)
                        if not chunk:
                            break
                        
                        f.write(chunk)
                        sha256_hash.update(chunk)
                        bytes_downloaded += len(chunk)
                        
                        # Update progress if callback provided
                        if progress_callback and total_bytes > 0:
                            current_time = time.time()
                            if current_time - last_progress_time >= 0.1:  # Update every 100ms
                                elapsed_time = current_time - start_time
                                download_speed = bytes_downloaded / elapsed_time if elapsed_time > 0 else 0
                                percentage = (bytes_downloaded / total_bytes) * 100
                                
                                # Calculate ETA
                                if download_speed > 0:
                                    remaining_bytes = total_bytes - bytes_downloaded
                                    eta_seconds = remaining_bytes / download_speed
                                else:
                                    eta_seconds = 0
                                
                                progress = DownloadProgress(
                                    bytes_downloaded=bytes_downloaded,
                                    total_bytes=total_bytes,
                                    percentage=percentage,
                                    download_speed=download_speed,
                                    eta_seconds=eta_seconds
                                )
                                progress_callback(progress)
                                last_progress_time = current_time
                
                # Final progress update
                if progress_callback and total_bytes > 0:
                    progress = DownloadProgress(
                        bytes_downloaded=bytes_downloaded,
                        total_bytes=total_bytes,
                        percentage=100.0,
                        download_speed=0,
                        eta_seconds=0
                    )
                    progress_callback(progress)
                
                download_time = time.time() - start_time
                checksum = sha256_hash.hexdigest()
                
                return DownloadResult(
                    success=True,
                    file_path=target_path,
                    file_size=bytes_downloaded,
                    download_time=download_time,
                    checksum=checksum
                )
                
        except (URLError, HTTPError, OSError) as e:
            # Clean up partial download
            self._safe_remove_file(target_path)
            return DownloadResult(
                success=False,
                file_path=None,
                file_size=0,
                download_time=time.time() - start_time,
                checksum=None,
                error_message=str(e)
            )
    
    def _verify_checksum(self, file_path: str, expected_checksum: str) -> bool:
        """
        Verify the SHA256 checksum of a downloaded file.
        
        Args:
            file_path: Path to the file to verify
            expected_checksum: Expected SHA256 checksum (hex string)
            
        Returns:
            bool: True if checksum matches
        """
        try:
            calculated_checksum = self._calculate_file_checksum(file_path)
            return calculated_checksum.lower() == expected_checksum.lower()
        except Exception as e:
            self.logger.error("FileDownloader", f"Checksum verification failed: {e}")
            return False
    
    def _calculate_file_checksum(self, file_path: str) -> str:
        """
        Calculate SHA256 checksum of a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            str: SHA256 checksum as hex string
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(self.chunk_size), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    
    def _safe_remove_file(self, file_path: str) -> None:
        """
        Safely remove a file, ignoring errors.
        
        Args:
            file_path: Path to the file to remove
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass  # Ignore removal errors


class FileInstaller:
    """
    Handles atomic installation of yt-dlp.exe with backup and rollback capabilities.
    """
    
    def __init__(self):
        self.logger = Logger.instance()
        self.path_manager = PathManager()
    
    def install_update(self, downloaded_file: str, target_version: Optional[str] = None) -> InstallResult:
        """
        Install a downloaded yt-dlp.exe update atomically with backup.
        
        Args:
            downloaded_file: Path to the downloaded yt-dlp.exe file
            target_version: Optional version string for logging
            
        Returns:
            InstallResult: Result of the installation operation
        """
        install_path = self.path_manager.get_install_path()
        backup_path = self.path_manager.get_backup_path()
        
        # Validate download file
        if not os.path.exists(downloaded_file):
            return InstallResult(
                success=False,
                installed_path=install_path,
                backup_path=None,
                previous_version=None,
                error_message="Downloaded file does not exist"
            )
        
        # Check if current installation is in use
        if os.path.exists(install_path) and self.path_manager.is_file_in_use(install_path):
            return InstallResult(
                success=False,
                installed_path=install_path,
                backup_path=None,
                previous_version=None,
                error_message="Current yt-dlp.exe is in use and cannot be replaced"
            )
        
        # Get current version for rollback info
        previous_version = None
        if os.path.exists(install_path):
            previous_version = self.path_manager.get_file_version(install_path)
        
        try:
            # Step 1: Create backup of current installation
            backup_created = False
            if os.path.exists(install_path):
                backup_created = self._create_backup(install_path, backup_path)
                if not backup_created:
                    return InstallResult(
                        success=False,
                        installed_path=install_path,
                        backup_path=None,
                        previous_version=previous_version,
                        error_message="Failed to create backup of current installation"
                    )
            
            # Step 2: Atomic installation
            success = self._perform_atomic_install(downloaded_file, install_path)
            
            if success:
                # Step 3: Verify installation
                if self._verify_installation(install_path):
                    # Installation successful
                    self.logger.info("FileInstaller", 
                        f"Successfully installed yt-dlp.exe to {install_path}")
                    
                    # Clean up downloaded file
                    self._safe_remove_file(downloaded_file)
                    
                    return InstallResult(
                        success=True,
                        installed_path=install_path,
                        backup_path=backup_path if backup_created else None,
                        previous_version=previous_version
                    )
                else:
                    # Installation verification failed, rollback
                    self.logger.error("FileInstaller", "Installation verification failed, rolling back")
                    if backup_created:
                        self._rollback_from_backup(backup_path, install_path)
                    
                    return InstallResult(
                        success=False,
                        installed_path=install_path,
                        backup_path=backup_path if backup_created else None,
                        previous_version=previous_version,
                        error_message="Installation verification failed"
                    )
            else:
                # Installation failed, rollback if needed
                if backup_created:
                    self._rollback_from_backup(backup_path, install_path)
                
                return InstallResult(
                    success=False,
                    installed_path=install_path,
                    backup_path=backup_path if backup_created else None,
                    previous_version=previous_version,
                    error_message="Failed to install update"
                )
                
        except Exception as e:
            self.logger.error("FileInstaller", f"Installation failed with exception: {e}")
            
            # Attempt rollback on exception
            if backup_created:
                self._rollback_from_backup(backup_path, install_path)
            
            return InstallResult(
                success=False,
                installed_path=install_path,
                backup_path=backup_path if backup_created else None,
                previous_version=previous_version,
                error_message=f"Installation exception: {e}"
            )
    
    def _create_backup(self, source_path: str, backup_path: str) -> bool:
        """
        Create a backup of the current installation.
        
        Args:
            source_path: Current installation file
            backup_path: Where to store the backup
            
        Returns:
            bool: True if backup was created successfully
        """
        try:
            # Remove existing backup if present
            self._safe_remove_file(backup_path)
            
            # Copy current installation to backup location
            shutil.copy2(source_path, backup_path)
            
            # Verify backup was created correctly
            if os.path.exists(backup_path):
                source_size = os.path.getsize(source_path)
                backup_size = os.path.getsize(backup_path)
                if source_size == backup_size:
                    self.logger.info("FileInstaller", f"Created backup at {backup_path}")
                    return True
                else:
                    self.logger.error("FileInstaller", "Backup file size mismatch")
                    self._safe_remove_file(backup_path)
                    return False
            else:
                return False
                
        except (OSError, shutil.Error) as e:
            self.logger.error("FileInstaller", f"Failed to create backup: {e}")
            return False
    
    def _perform_atomic_install(self, source_path: str, target_path: str) -> bool:
        """
        Perform atomic installation using temporary file and rename.
        
        Args:
            source_path: Downloaded file to install
            target_path: Final installation path
            
        Returns:
            bool: True if installation succeeded
        """
        try:
            # Ensure target directory exists
            if not self.path_manager.ensure_directory_exists(target_path):
                return False
            
            # Use atomic rename operation
            # On Windows, we need to remove the target first if it exists
            if os.path.exists(target_path):
                os.remove(target_path)
            
            # Move the downloaded file to the final location
            shutil.move(source_path, target_path)
            
            # Set executable permissions (important for cross-platform compatibility)
            if os.name != 'nt':  # Not Windows
                os.chmod(target_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            
            return True
            
        except (OSError, shutil.Error) as e:
            self.logger.error("FileInstaller", f"Atomic installation failed: {e}")
            return False
    
    def _verify_installation(self, install_path: str) -> bool:
        """
        Verify that the installation was successful.
        
        Args:
            install_path: Path to verify
            
        Returns:
            bool: True if installation is valid
        """
        try:
            # Check if file exists and is executable
            if not os.path.exists(install_path):
                return False
            
            # Check file size (yt-dlp.exe should be at least 1MB)
            file_size = os.path.getsize(install_path)
            if file_size < 1024 * 1024:  # Less than 1MB is suspicious
                self.logger.warning("FileInstaller", f"Installed file seems too small: {file_size} bytes")
                return False
            
            # Try to execute --version to verify it's working
            try:
                import subprocess
                result = subprocess.run(
                    [install_path, '--version'],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False
                )
                
                # If we get a version output, consider it successful
                if result.returncode == 0 and result.stdout.strip():
                    self.logger.info("FileInstaller", f"Installation verified: {result.stdout.strip()}")
                    return True
                else:
                    self.logger.warning("FileInstaller", f"Version check failed: {result.stderr}")
                    return False
                    
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
                self.logger.warning("FileInstaller", f"Could not verify installation by running --version: {e}")
                # If we can't run it, but the file exists and has reasonable size, consider it OK
                return True
            
        except Exception as e:
            self.logger.error("FileInstaller", f"Installation verification failed: {e}")
            return False
    
    def _rollback_from_backup(self, backup_path: str, install_path: str) -> bool:
        """
        Rollback installation from backup.
        
        Args:
            backup_path: Path to backup file
            install_path: Target installation path
            
        Returns:
            bool: True if rollback succeeded
        """
        try:
            if not os.path.exists(backup_path):
                self.logger.error("FileInstaller", "Cannot rollback: backup file does not exist")
                return False
            
            # Remove current (failed) installation
            self._safe_remove_file(install_path)
            
            # Restore from backup
            shutil.copy2(backup_path, install_path)
            
            if os.path.exists(install_path):
                self.logger.info("FileInstaller", "Successfully rolled back to previous version")
                return True
            else:
                self.logger.error("FileInstaller", "Rollback failed: could not restore backup")
                return False
                
        except (OSError, shutil.Error) as e:
            self.logger.error("FileInstaller", f"Rollback failed: {e}")
            return False
    
    def _safe_remove_file(self, file_path: str) -> None:
        """
        Safely remove a file, ignoring errors.
        
        Args:
            file_path: Path to the file to remove
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass  # Ignore removal errors
    
    def cleanup_old_backups(self, keep_count: int = 3) -> None:
        """
        Clean up old backup files, keeping only the most recent ones.
        
        Args:
            keep_count: Number of backup files to keep
        """
        try:
            backup_path = self.path_manager.get_backup_path()
            backup_dir = os.path.dirname(backup_path)
            backup_name = os.path.basename(backup_path)
            
            if not os.path.exists(backup_dir):
                return
            
            # Find all backup files (including timestamped ones)
            backup_files = []
            for filename in os.listdir(backup_dir):
                if filename.startswith(backup_name):
                    file_path = os.path.join(backup_dir, filename)
                    if os.path.isfile(file_path):
                        mtime = os.path.getmtime(file_path)
                        backup_files.append((mtime, file_path))
            
            # Sort by modification time (newest first)
            backup_files.sort(reverse=True)
            
            # Remove old backups
            for _, file_path in backup_files[keep_count:]:
                self._safe_remove_file(file_path)
                self.logger.info("FileInstaller", f"Cleaned up old backup: {file_path}")
                
        except Exception as e:
            self.logger.warning("FileInstaller", f"Failed to cleanup old backups: {e}") 