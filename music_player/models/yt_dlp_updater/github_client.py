"""
GitHub client for yt-dlp release information.

This module handles interaction with GitHub's API and releases page
to fetch the latest yt-dlp version and download URLs.
"""
import json
import re
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import time

from qt_base_app.models.logger import Logger


class GitHubClient:
    """
    Client for fetching yt-dlp release information from GitHub.
    Supports both API and HTML fallback methods.
    """
    
    REPO_OWNER = "yt-dlp"
    REPO_NAME = "yt-dlp"
    API_BASE_URL = "https://api.github.com"
    RELEASES_PAGE_URL = "https://github.com/yt-dlp/yt-dlp/releases"
    
    def __init__(self, timeout: int = 30, max_retries: int = 3):
        """
        Initialize GitHub client.
        
        Args:
            timeout (int): Request timeout in seconds
            max_retries (int): Maximum number of retry attempts
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = Logger.instance()
        
        # User agent to identify our application
        self.user_agent = "MusicPlayer-YtDlpUpdater/1.0"
    
    def get_latest_release(self) -> Optional[Dict[str, Any]]:
        """
        Get the latest yt-dlp release information.
        
        Tries GitHub API first, falls back to HTML parsing if API fails.
        
        Returns:
            Dict containing release information:
            {
                'version': '2025.06.30',
                'download_url': 'https://github.com/yt-dlp/yt-dlp/releases/download/2025.06.30/yt-dlp.exe',
                'checksum_url': 'https://github.com/yt-dlp/yt-dlp/releases/download/2025.06.30/SHA2-256SUMS',
                'published_at': '2025-06-30T12:00:00Z',
                'release_notes': 'Release notes text...',
                'source': 'api'  # or 'html'
            }
            Returns None if both methods fail.
        """
        # Try API first
        self.logger.info(self.__class__.__name__, "Fetching latest release via GitHub API")
        api_result = self._get_release_via_api()
        if api_result:
            api_result['source'] = 'api'
            return api_result
        
        # Fallback to HTML parsing
        self.logger.warning(self.__class__.__name__, "GitHub API failed, falling back to HTML parsing")
        html_result = self._get_release_via_html()
        if html_result:
            html_result['source'] = 'html'
            return html_result
        
        self.logger.error(self.__class__.__name__, "Both API and HTML methods failed to get release info")
        return None
    
    def _get_release_via_api(self) -> Optional[Dict[str, Any]]:
        """
        Get release information via GitHub API.
        
        Returns:
            Dict: Release information or None if failed
        """
        api_url = f"{self.API_BASE_URL}/repos/{self.REPO_OWNER}/{self.REPO_NAME}/releases/latest"
        
        try:
            data = self._make_request(api_url, "GitHub API")
            if not data:
                return None
            
            # Parse JSON response
            response_data = json.loads(data)
            
            # Extract version from tag_name (e.g., "2025.06.30")
            version = response_data.get('tag_name', '').strip()
            if not version:
                self.logger.error(self.__class__.__name__, "No tag_name found in API response")
                return None
            
            # Find yt-dlp.exe asset
            assets = response_data.get('assets', [])
            download_url = None
            checksum_url = None
            
            for asset in assets:
                asset_name = asset.get('name', '')
                if asset_name == 'yt-dlp.exe':
                    download_url = asset.get('browser_download_url')
                elif asset_name == 'SHA2-256SUMS':
                    checksum_url = asset.get('browser_download_url')
            
            if not download_url:
                self.logger.error(self.__class__.__name__, "yt-dlp.exe asset not found in API response")
                return None
            
            result = {
                'version': version,
                'download_url': download_url,
                'checksum_url': checksum_url,
                'published_at': response_data.get('published_at'),
                'release_notes': response_data.get('body', '').strip()
            }
            
            self.logger.info(self.__class__.__name__, f"Successfully fetched release via API: {version}")
            return result
            
        except json.JSONDecodeError as e:
            self.logger.error(self.__class__.__name__, f"Failed to parse API JSON response: {e}")
            return None
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Unexpected error in API method: {e}")
            return None
    
    def _get_release_via_html(self) -> Optional[Dict[str, Any]]:
        """
        Get release information by parsing GitHub releases HTML page.
        
        Returns:
            Dict: Release information or None if failed
        """
        try:
            data = self._make_request(self.RELEASES_PAGE_URL, "GitHub releases page")
            if not data:
                return None
            
            # Parse HTML to find latest release
            result = self._parse_releases_html(data)
            if result:
                self.logger.info(self.__class__.__name__, f"Successfully fetched release via HTML: {result['version']}")
            
            return result
            
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Unexpected error in HTML method: {e}")
            return None
    
    def _parse_releases_html(self, html_content: str) -> Optional[Dict[str, Any]]:
        """
        Parse GitHub releases HTML to extract latest release information.
        
        Args:
            html_content (str): HTML content from releases page
            
        Returns:
            Dict: Parsed release information or None if failed
        """
        try:
            # Look for the first release section (latest release)
            # Pattern for release version/tag (e.g., "2025.06.30")
            version_pattern = r'<h2[^>]*>\s*<a[^>]*href="[^"]*tag/([^"]+)"[^>]*>'
            version_match = re.search(version_pattern, html_content)
            
            if not version_match:
                self.logger.error(self.__class__.__name__, "Could not find version pattern in HTML")
                return None
            
            version = version_match.group(1).strip()
            
            # Look for yt-dlp.exe download link
            # Pattern: href="...download/{version}/yt-dlp.exe"
            exe_pattern = rf'href="([^"]*download/{re.escape(version)}/yt-dlp\.exe)"'
            exe_match = re.search(exe_pattern, html_content)
            
            if not exe_match:
                self.logger.error(self.__class__.__name__, f"Could not find yt-dlp.exe download link for version {version}")
                return None
            
            download_url = exe_match.group(1)
            # Ensure it's a full URL
            if download_url.startswith('/'):
                download_url = 'https://github.com' + download_url
            elif not download_url.startswith('http'):
                download_url = 'https://github.com/' + download_url
            
            # Look for checksum file
            checksum_pattern = rf'href="([^"]*download/{re.escape(version)}/SHA2-256SUMS)"'
            checksum_match = re.search(checksum_pattern, html_content)
            checksum_url = None
            
            if checksum_match:
                checksum_url = checksum_match.group(1)
                if checksum_url.startswith('/'):
                    checksum_url = 'https://github.com' + checksum_url
                elif not checksum_url.startswith('http'):
                    checksum_url = 'https://github.com/' + checksum_url
            
            # Try to extract publish date (optional, HTML parsing is less reliable for this)
            date_pattern = r'<relative-time[^>]*datetime="([^"]+)"'
            date_match = re.search(date_pattern, html_content)
            published_at = date_match.group(1) if date_match else None
            
            result = {
                'version': version,
                'download_url': download_url,
                'checksum_url': checksum_url,
                'published_at': published_at,
                'release_notes': ''  # Not easily extractable from HTML
            }
            
            return result
            
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Error parsing HTML: {e}")
            return None
    
    def _make_request(self, url: str, description: str) -> Optional[str]:
        """
        Make HTTP request with retry logic.
        
        Args:
            url (str): URL to request
            description (str): Description for logging
            
        Returns:
            str: Response content or None if failed
        """
        for attempt in range(self.max_retries):
            try:
                self.logger.debug(self.__class__.__name__, f"Requesting {description}: {url} (attempt {attempt + 1})")
                
                # Create request with proper headers
                request = urllib.request.Request(url)
                request.add_header('User-Agent', self.user_agent)
                request.add_header('Accept', 'application/vnd.github.v3+json' if 'api.github' in url else 'text/html')
                
                # Make request
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    if response.status == 200:
                        content = response.read().decode('utf-8')
                        self.logger.debug(self.__class__.__name__, f"Successfully fetched {description}")
                        return content
                    else:
                        self.logger.warning(self.__class__.__name__, 
                                          f"HTTP {response.status} for {description}")
                        
            except urllib.error.HTTPError as e:
                if e.code == 403 and 'api.github' in url:
                    self.logger.warning(self.__class__.__name__, 
                                      f"GitHub API rate limit exceeded (HTTP 403), will retry with HTML fallback")
                    return None  # Don't retry API requests on rate limit
                else:
                    self.logger.warning(self.__class__.__name__, 
                                      f"HTTP error {e.code} for {description}: {e.reason}")
                    
            except urllib.error.URLError as e:
                self.logger.warning(self.__class__.__name__, f"URL error for {description}: {e.reason}")
                
            except Exception as e:
                self.logger.warning(self.__class__.__name__, f"Request error for {description}: {e}")
            
            # Wait before retry (exponential backoff)
            if attempt < self.max_retries - 1:
                wait_time = (2 ** attempt) + 0.5  # 0.5s, 2.5s, 4.5s
                self.logger.debug(self.__class__.__name__, f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
        
        self.logger.error(self.__class__.__name__, f"Failed to fetch {description} after {self.max_retries} attempts")
        return None
    
    def download_checksum_file(self, checksum_url: str) -> Optional[str]:
        """
        Download and parse SHA256 checksum file.
        
        Args:
            checksum_url (str): URL to SHA2-256SUMS file
            
        Returns:
            str: SHA256 hash for yt-dlp.exe, or None if not found
        """
        if not checksum_url:
            self.logger.warning(self.__class__.__name__, "No checksum URL provided")
            return None
        
        try:
            content = self._make_request(checksum_url, "checksum file")
            if not content:
                return None
            
            # Parse checksum file format: "hash filename"
            # Look for line containing yt-dlp.exe
            for line in content.splitlines():
                line = line.strip()
                if 'yt-dlp.exe' in line:
                    # Extract hash (first part before space)
                    parts = line.split()
                    if len(parts) >= 2:
                        hash_value = parts[0]
                        self.logger.debug(self.__class__.__name__, f"Found SHA256 for yt-dlp.exe: {hash_value}")
                        return hash_value
            
            self.logger.warning(self.__class__.__name__, "yt-dlp.exe not found in checksum file")
            return None
            
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Error downloading checksum: {e}")
            return None
    
    def verify_connectivity(self) -> bool:
        """
        Verify connectivity to GitHub.
        
        Returns:
            bool: True if GitHub is accessible
        """
        try:
            # Simple connectivity test
            test_url = "https://github.com"
            request = urllib.request.Request(test_url)
            request.add_header('User-Agent', self.user_agent)
            
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status == 200
                
        except Exception as e:
            self.logger.warning(self.__class__.__name__, f"GitHub connectivity test failed: {e}")
            return False 