"""
Bilibili data model for the application.
"""
import re
import requests
from urllib.parse import urlparse
from PyQt6.QtGui import QPixmap
from qt_base_app.models.logger import Logger

class BilibiliModel:
    """Model for Bilibili data and operations."""
    
    @staticmethod
    def extract_video_id(url):
        """
        Extract BV ID from a Bilibili URL.
        
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
            Logger.instance().error(caller="BilibiliModel", msg=f"Error extracting Bilibili ID: {e}")
            return None
    
    @staticmethod
    def clean_url(url):
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
        bv_id = BilibiliModel.extract_video_id(url)
        if bv_id:
            return f"https://www.bilibili.com/video/{bv_id}"
            
        # Return original URL if we can't normalize it
        return url
    
    @staticmethod
    def get_video_metadata(url):
        """
        Get title and thumbnail for a Bilibili video.
        
        Args:
            url (str): The Bilibili URL
            
        Returns:
            tuple: (title, pixmap) or ("Unknown Video", None) if not found
        """
        video_id = BilibiliModel.extract_video_id(url)
        if not video_id:
            return "Unknown Video", None
        
        title = None
        pixmap = None
        
        try:
            # Build API URL for Bilibili
            api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={video_id}"
            
            # Set up user agent header to mimic browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://www.bilibili.com'
            }
            
            # Make API request with timeout
            response = requests.get(api_url, headers=headers, timeout=15.0)
            data = response.json()
            
            # Check if the API call was successful
            if data['code'] == 0 and 'data' in data:
                # Extract title
                title = data['data'].get('title', 'Unknown Bilibili Video')
                
                # Extract thumbnail URL
                thumbnail_url = data['data'].get('pic')
                
                if thumbnail_url:
                    # Download thumbnail with timeout
                    img_response = requests.get(thumbnail_url, timeout=15.0)
                    if img_response.status_code == 200:
                        pixmap = QPixmap()
                        pixmap.loadFromData(img_response.content)
        
        except Exception as e:
            Logger.instance().error(caller="BilibiliModel", msg=f"Error fetching Bilibili metadata: {e}")
            # If we failed to get metadata, just return the video ID as a title
            title = f"Bilibili Video: {video_id}"
        
        return title, pixmap
    
    @staticmethod
    def get_thumbnail(url, quality='default'):
        """
        Get thumbnail image from Bilibili video URL.
        
        Args:
            url (str): The Bilibili URL
            quality (str): Quality level (ignored, Bilibili API provides one size)
            
        Returns:
            QPixmap: Thumbnail image or None if not found
        """
        _, pixmap = BilibiliModel.get_video_metadata(url)
        return pixmap