"""
Video site detection and platform-specific handling.
Supports different video platforms like YouTube and Bilibili.
"""
import re
from urllib.parse import urlparse
from PyQt6.QtGui import QPixmap

class SiteModel:
    """
    Detects and manages different video platforms.
    Provides methods to identify video platforms and process URLs.
    Acts as a facade for all site-specific operations.
    """
    
    # Site identifiers
    SITE_YOUTUBE = "youtube"
    SITE_BILIBILI = "bilibili"
    SITE_UNKNOWN = "unknown"
    
    @staticmethod
    def detect_site(url):
        """
        Detect which video platform the URL belongs to.
        
        Args:
            url (str): The video URL or ID
            
        Returns:
            str: Site identifier (youtube, bilibili, unknown)
        """
        if not url:
            return SiteModel.SITE_UNKNOWN
            
        # Handle protocol URLs from Chrome extension
        if url.startswith('youtubemaster://'):
            # Extract the actual URL from the protocol URL
            protocol_path = url.replace('youtubemaster://', '')
            
            # Check if it's the format with format type
            if '/' in protocol_path and protocol_path.split('/', 1)[0] in ['video', 'audio']:
                _, protocol_url = protocol_path.split('/', 1)
                url = protocol_url  # Use the clean URL for detection
            else:
                # Legacy format - just the URL after the protocol
                url = protocol_path
        
        # Parse the URL
        try:
            parsed_url = urlparse(url)
            
            # Check for direct video IDs without domain
            if not parsed_url.netloc:
                # Try to detect format
                if re.match(r'^[A-Za-z0-9_-]{11}$', url):
                    return SiteModel.SITE_YOUTUBE  # Looks like a YouTube ID
                elif re.match(r'^BV[a-zA-Z0-9]{10}$', url):
                    return SiteModel.SITE_BILIBILI  # Looks like a Bilibili BV ID
                return SiteModel.SITE_UNKNOWN
            
            # Check domains
            domain = parsed_url.netloc.lower()
            
            if 'youtube.com' in domain or 'youtu.be' in domain:
                return SiteModel.SITE_YOUTUBE
                
            if 'bilibili.com' in domain:
                return SiteModel.SITE_BILIBILI
                
            return SiteModel.SITE_UNKNOWN
            
        except Exception as e:
            print(f"Error detecting site: {e}")
            return SiteModel.SITE_UNKNOWN
    
    @staticmethod
    def extract_video_id(url):
        """
        Extract video ID from any supported platform URL.
        
        Args:
            url (str): The video URL
            
        Returns:
            str: The video ID or None if not found
        """
        site = SiteModel.detect_site(url)
        
        if site == SiteModel.SITE_YOUTUBE:
            from .YoutubeModel import YoutubeModel
            return YoutubeModel.extract_video_id(url)
            
        elif site == SiteModel.SITE_BILIBILI:
            from .BilibiliModel import BilibiliModel
            return BilibiliModel.extract_video_id(url)
            
        return None
    
    @staticmethod
    def get_clean_url(url):
        """
        Normalize a URL based on the detected site.
        
        Args:
            url (str): The video URL
            
        Returns:
            str: Normalized URL for the detected site
        """
        # Handle protocol URLs from Chrome extension
        if url.startswith('youtubemaster://'):
            # Extract the actual URL from the protocol URL
            protocol_path = url.replace('youtubemaster://', '')
            
            # Check if it's the format with format type
            if '/' in protocol_path and protocol_path.split('/', 1)[0] in ['video', 'audio']:
                _, protocol_url = protocol_path.split('/', 1)
                url = protocol_url  # Use the clean URL for normalization
            else:
                # Legacy format - just the URL after the protocol
                url = protocol_path
        
        site = SiteModel.detect_site(url)
        
        if site == SiteModel.SITE_YOUTUBE:
            from .YoutubeModel import YoutubeModel
            return YoutubeModel.clean_url(url)
            
        elif site == SiteModel.SITE_BILIBILI:
            from .BilibiliModel import BilibiliModel
            return BilibiliModel.clean_url(url)
            
        # Return original URL for unknown sites
        return url
        
    @staticmethod
    def get_video_metadata(url):
        """
        Get title and thumbnail for a video from any supported platform.
        
        Args:
            url (str): The video URL
            
        Returns:
            tuple: (title, pixmap) where title is a string and pixmap is a QPixmap
        """
        site = SiteModel.detect_site(url)
        
        if site == SiteModel.SITE_YOUTUBE:
            from .YoutubeModel import YoutubeModel
            return YoutubeModel.get_video_metadata(url)
            
        elif site == SiteModel.SITE_BILIBILI:
            from .BilibiliModel import BilibiliModel
            return BilibiliModel.get_video_metadata(url)
            
        # Return placeholder for unknown sites
        return "Unknown Video", None
        
    @staticmethod
    def get_thumbnail(url, quality='default'):
        """
        Get thumbnail image for a video from any supported platform.
        
        Args:
            url (str): The video URL
            quality (str): Quality level (used by some platforms)
            
        Returns:
            QPixmap: Thumbnail image or None if not found
        """
        site = SiteModel.detect_site(url)
        
        if site == SiteModel.SITE_YOUTUBE:
            from .YoutubeModel import YoutubeModel
            return YoutubeModel.get_thumbnail(url, quality)
            
        elif site == SiteModel.SITE_BILIBILI:
            from .BilibiliModel import BilibiliModel
            return BilibiliModel.get_thumbnail(url)
            
        return None

    @staticmethod
    def is_supported_site(url):
        """
        Check if a URL is from a supported video platform.
        
        Args:
            url (str): The URL to check
            
        Returns:
            bool: True if the URL is from a supported platform
        """
        site = SiteModel.detect_site(url)
        return site != SiteModel.SITE_UNKNOWN

    @staticmethod
    def extract_bilibili_id(url):
        """
        Extract the BV ID from a Bilibili URL.
        
        Args:
            url (str): The Bilibili URL
            
        Returns:
            str: The BV ID or None if not found
        """
        # Handle direct BV ID input
        if re.match(r'^BV[a-zA-Z0-9]{10}$', url):
            return url
            
        # Parse the URL
        try:
            parsed_url = urlparse(url)
            
            # Extract BV ID from path
            path = parsed_url.path
            match = re.search(r'BV([a-zA-Z0-9]{10})', path)
            if match:
                return f"BV{match.group(1)}"
                
            return None
            
        except Exception as e:
            print(f"Error extracting Bilibili ID: {e}")
            return None
    
    @staticmethod
    def normalize_bilibili_url(url):
        """
        Clean a Bilibili URL to the standard format.
        
        Args:
            url (str): The Bilibili URL or BV ID
            
        Returns:
            str: Normalized URL or original URL if normalization fails
        """
        # Handle direct BV ID input
        if re.match(r'^BV[a-zA-Z0-9]{10}$', url):
            return f"https://www.bilibili.com/video/{url}"
            
        # Extract the BV ID and create a clean URL
        bv_id = SiteModel.extract_bilibili_id(url)
        if bv_id:
            return f"https://www.bilibili.com/video/{bv_id}"
            
        # Return original URL if we can't normalize it
        return url 