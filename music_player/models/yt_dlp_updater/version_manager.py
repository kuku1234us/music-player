"""
Version manager for yt-dlp version comparison and validation.

This module handles version comparison using download URLs as version identifiers,
making it future-proof regardless of yt-dlp's versioning scheme changes.
"""
import subprocess
import os
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path
import urllib.parse

from qt_base_app.models.logger import Logger


def _windows_no_window_kwargs() -> dict:
    """
    Return subprocess kwargs that suppress console windows on Windows.

    This is important when our GUI app launches helper console programs
    (like yt-dlp.exe). Without these flags, Windows may briefly flash a
    console window (often titled with the executable path).
    """
    if os.name != "nt":
        return {}

    kwargs: dict = {
        # Use the constant if available; fallback is the documented value.
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
    }

    # Best-effort: also request hidden show window via STARTUPINFO.
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
        si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = si
    except Exception:
        pass

    return kwargs


class VersionManager:
    """
    Manager for yt-dlp version operations.
    Uses download URLs as version identifiers for future-proof comparison.
    """
    
    def __init__(self):
        """Initialize version manager."""
        self.logger = Logger.instance()
    
    def compare_versions(self, current_url: str, latest_url: str) -> int:
        """
        Compare two yt-dlp versions using their download URLs.
        
        Args:
            current_url (str): Current version's download URL
            latest_url (str): Latest version's download URL
            
        Returns:
            int: -1 if current != latest (update needed), 0 if equal, -2 if invalid URLs
        """
        try:
            if not current_url or not latest_url:
                self.logger.error(self.__class__.__name__, 
                                f"Invalid URLs: current='{current_url}', latest='{latest_url}'")
                return -2
            
            # Normalize URLs for comparison
            current_normalized = self._normalize_url(current_url)
            latest_normalized = self._normalize_url(latest_url)
            
            if current_normalized == latest_normalized:
                return 0  # Same version
            else:
                return -1  # Different version, assume update needed
                
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Error comparing versions: {e}")
            return -2
    
    def is_newer_version(self, current_url: str, latest_url: str) -> bool:
        """
        Check if latest version URL is different from current version URL.
        
        Args:
            current_url (str): Current version's download URL
            latest_url (str): Latest version's download URL
            
        Returns:
            bool: True if URLs are different (update needed)
        """
        comparison = self.compare_versions(current_url, latest_url)
        return comparison == -1
    
    def _normalize_url(self, url: str) -> str:
        """
        Normalize URL for consistent comparison.
        
        Args:
            url (str): URL to normalize
            
        Returns:
            str: Normalized URL
        """
        if not url:
            return ""
        
        # Parse and reconstruct to normalize
        parsed = urllib.parse.urlparse(url.strip())
        
        # Reconstruct with normalized components
        normalized = urllib.parse.urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.params,
            parsed.query,
            ""  # Remove fragment
        ))
        
        return normalized
    
    def extract_version_from_url(self, url: str) -> str:
        """
        Extract version identifier from GitHub download URL.
        
        Args:
            url (str): Download URL (e.g., ".../download/2025.06.30/yt-dlp.exe")
            
        Returns:
            str: Version identifier extracted from URL path, or URL hash if extraction fails
        """
        if not url:
            return "unknown"
        
        try:
            parsed = urllib.parse.urlparse(url)
            path_parts = parsed.path.split('/')
            
            # Look for pattern: /download/{version}/yt-dlp.exe
            if 'download' in path_parts:
                download_index = path_parts.index('download')
                if download_index + 1 < len(path_parts):
                    version_candidate = path_parts[download_index + 1]
                    if version_candidate and version_candidate != 'yt-dlp.exe':
                        return version_candidate
            
            # Fallback: use hash of the URL
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            self.logger.debug(self.__class__.__name__, f"Using URL hash as version: {url_hash}")
            return f"url-{url_hash}"
            
        except Exception as e:
            self.logger.warning(self.__class__.__name__, f"Error extracting version from URL: {e}")
            return "unknown"
    
    def validate_version_url(self, url: str) -> bool:
        """
        Validate if a URL looks like a valid yt-dlp download URL.
        
        Args:
            url (str): URL to validate
            
        Returns:
            bool: True if URL appears valid
        """
        if not url:
            return False
        
        try:
            parsed = urllib.parse.urlparse(url)
            
            # Check basic URL structure
            if not parsed.scheme or not parsed.netloc:
                return False
            
            # Check if it's a GitHub URL
            if 'github.com' not in parsed.netloc.lower():
                return False
            
            # Check if it contains yt-dlp.exe
            if 'yt-dlp.exe' not in parsed.path:
                return False
            
            return True
            
        except Exception:
            return False
    
    def get_current_installed_version(self, yt_dlp_path: str) -> Optional[str]:
        """
        Get version information from currently installed yt-dlp.exe.
        
        Args:
            yt_dlp_path (str): Path to yt-dlp.exe
            
        Returns:
            str: Version string from --version output, or None if unable to determine
        """
        if not yt_dlp_path or not os.path.exists(yt_dlp_path):
            self.logger.warning(self.__class__.__name__, f"yt-dlp.exe not found at: {yt_dlp_path}")
            return None
        
        try:
            # Run yt-dlp --version to get version info
            result = subprocess.run(
                [yt_dlp_path, '--version'],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                **_windows_no_window_kwargs(),
            )
            
            if result.returncode == 0:
                version_output = result.stdout.strip()
                self.logger.debug(self.__class__.__name__, f"yt-dlp version output: {version_output}")
                
                if version_output:
                    self.logger.info(self.__class__.__name__, f"Detected yt-dlp version: {version_output}")
                    return version_output
                else:
                    self.logger.warning(self.__class__.__name__, "Empty version output")
            else:
                self.logger.warning(self.__class__.__name__, 
                                  f"yt-dlp --version failed: {result.stderr.strip()}")
                
        except subprocess.TimeoutExpired:
            self.logger.error(self.__class__.__name__, "Timeout getting yt-dlp version")
        except FileNotFoundError:
            self.logger.error(self.__class__.__name__, f"yt-dlp.exe not found at: {yt_dlp_path}")
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Error getting yt-dlp version: {e}")
        
        return None
    
    def format_version_for_display(self, version_info: str) -> str:
        """
        Format version information for user display.
        
        Args:
            version_info (str): Version string or URL
            
        Returns:
            str: Formatted version string
        """
        if not version_info:
            return "Unknown"
        
        # If it looks like a URL, extract version from it
        if version_info.startswith('http'):
            extracted = self.extract_version_from_url(version_info)
            return f"v{extracted}" if not extracted.startswith('url-') else extracted
        
        # If it's already a version string, return as-is
        return version_info
    
    def create_version_record(self, download_url: str, version_string: str = None) -> Dict[str, Any]:
        """
        Create a comprehensive version record for database storage.
        
        Args:
            download_url (str): Download URL used as primary version identifier
            version_string (str): Optional version string from yt-dlp --version
            
        Returns:
            Dict: Version record with all relevant information
        """
        record = {
            'download_url': download_url,
            'url_version': self.extract_version_from_url(download_url),
            'version_string': version_string,
            'display_version': self.format_version_for_display(version_string or download_url),
            'timestamp': datetime.now().isoformat(),
            'url_hash': hashlib.md5(download_url.encode()).hexdigest() if download_url else None
        }
        
        return record
    
    def get_file_hash(self, file_path: str) -> Optional[str]:
        """
        Calculate SHA256 hash of a file for integrity verification.
        
        Args:
            file_path (str): Path to file
            
        Returns:
            str: SHA256 hash, or None if error
        """
        if not os.path.exists(file_path):
            return None
        
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            
            file_hash = hash_sha256.hexdigest()
            self.logger.debug(self.__class__.__name__, f"File hash for {file_path}: {file_hash}")
            return file_hash
            
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Error calculating file hash: {e}")
            return None
    
    def get_default_install_path(self) -> str:
        """
        Get the default yt-dlp installation path for Windows.
        
        Returns:
            str: Default installation path
        """
        return r"C:\yt-dlp\yt-dlp.exe"
    
    def find_yt_dlp_in_path(self) -> Optional[str]:
        """
        Try to find yt-dlp.exe in the system PATH.
        
        Returns:
            str: Path to yt-dlp.exe if found, None otherwise
        """
        try:
            # Try to find yt-dlp in PATH
            result = subprocess.run(
                ['where', 'yt-dlp.exe'],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                **_windows_no_window_kwargs(),
            )
            
            if result.returncode == 0:
                path = result.stdout.strip().split('\n')[0]  # Get first result
                if os.path.exists(path):
                    self.logger.info(self.__class__.__name__, f"Found yt-dlp in PATH: {path}")
                    return path
            
        except Exception as e:
            self.logger.debug(self.__class__.__name__, f"Error searching PATH for yt-dlp: {e}")
        
        return None
    
    def get_backup_path(self, install_path: str) -> str:
        """
        Generate backup file path for the given installation path.
        
        Args:
            install_path (str): Original installation path
            
        Returns:
            str: Backup file path
        """
        if not install_path:
            return ""
        
        path_obj = Path(install_path)
        backup_path = path_obj.parent / f"{path_obj.stem}.backup{path_obj.suffix}"
        return str(backup_path) 