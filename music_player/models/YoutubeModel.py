"""
YouTube data model for the application.
"""
import os
import re
import requests
from urllib.parse import urlparse, parse_qs
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QUrl
from qt_base_app.models.logger import Logger

# Added import for SettingsManager
from qt_base_app.models.settings_manager import SettingsManager, SettingType
# TODO: Define YT_API_KEY_KEY in music_player.models.settings_defs.py later
YT_API_KEY_KEY = 'youtube/api_key' # Placeholder definition for now

# Import the QSettings key constant
from music_player.models.settings_defs import YT_API_QSETTINGS_KEY 

# REMOVE ENV Key Import
# from music_player.models.settings_defs import YT_API_ENV_KEY 

class YoutubeModel:
    """Model for YouTube data and operations."""
    
    @staticmethod
    def extract_video_id(url):
        """Extract video ID from a YouTube URL."""
        # Handle protocol URLs from Chrome extension / custom protocol invocations
        # (Legacy: youtubemaster://, Current: musicplayerdl://)
        if url and url.startswith(('musicplayerdl://', 'youtubemaster://')):
            protocol_path = url.split('://', 1)[1]

            # Check if it's the format with format type
            if '/' in protocol_path and protocol_path.split('/', 1)[0] in ['video', 'audio', 'best']:
                _, protocol_url = protocol_path.split('/', 1)
                url = protocol_url  # Use the actual YouTube URL for extraction
            else:
                # Legacy format - just the YouTube URL after the protocol
                url = protocol_path
        
        # Try to parse the URL
        parsed_url = urlparse(url)
        
        # Different YouTube URL formats
        if parsed_url.netloc in ('youtube.com', 'www.youtube.com'):
            # Standard youtube.com/watch?v=VIDEO_ID
            if parsed_url.path == '/watch':
                query_params = parse_qs(parsed_url.query)
                if 'v' in query_params:
                    return query_params['v'][0]
            
            # YouTube Shorts format youtube.com/shorts/VIDEO_ID
            elif parsed_url.path.startswith('/shorts/'):
                # Extract video ID from the path
                return parsed_url.path[8:]
            
            # Short youtube.com/v/VIDEO_ID
            elif parsed_url.path.startswith('/v/'):
                return parsed_url.path[3:]
            
            # Embedded youtube.com/embed/VIDEO_ID
            elif parsed_url.path.startswith('/embed/'):
                return parsed_url.path[7:]
                
        # Short URLs youtu.be/VIDEO_ID
        elif parsed_url.netloc == 'youtu.be':
            return parsed_url.path[1:]
        
        # Try regex pattern as fallback
        pattern = r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/|youtube\.com\/shorts\/)([^"&?\/\s]{11})'
        match = re.search(pattern, url)
        if match:
            return match.group(1)
            
        return None
        
    @staticmethod
    def get_thumbnail_url(video_id, quality='high'):
        """
        Get the thumbnail URL for a YouTube video.
        
        Quality options:
        - default: Default thumbnail (120x90)
        - high: High quality (480x360)
        - medium: Medium quality (320x180)
        - maxres: Maximum resolution (1280x720)
        """
        if not video_id:
            return None
            
        quality_map = {
            'default': f"http://img.youtube.com/vi/{video_id}/default.jpg",
            'medium': f"http://img.youtube.com/vi/{video_id}/mqdefault.jpg",
            'high': f"http://img.youtube.com/vi/{video_id}/hqdefault.jpg",
            'maxres': f"http://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        }
        
        return quality_map.get(quality, quality_map['high'])
    
    @staticmethod
    def get_thumbnail(url, quality='default'):
        """Get thumbnail image from YouTube video URL."""
        video_id = YoutubeModel.extract_video_id(url)
        if not video_id:
            return None
            
        thumbnail_url = YoutubeModel.get_thumbnail_url(video_id, quality)
        
        # Use SettingsManager.get with QSettings key
        api_key = SettingsManager.instance().get(YT_API_QSETTINGS_KEY, '', SettingType.STRING) 
        if api_key:
            try:
                api_url = f"https://www.googleapis.com/youtube/v3/videos?id={video_id}&key={api_key}&part=snippet"
                # Add timeout to prevent blocking for too long
                response = requests.get(api_url, timeout=15.0)
                data = response.json()
                
                if 'items' in data and len(data['items']) > 0:
                    thumbnails = data['items'][0]['snippet']['thumbnails']
                    if 'maxres' in thumbnails and quality == 'maxres':
                        thumbnail_url = thumbnails['maxres']['url']
                    elif 'high' in thumbnails and quality in ['high', 'maxres']:
                        thumbnail_url = thumbnails['high']['url']
                    elif 'medium' in thumbnails and quality in ['medium', 'high', 'maxres']:
                        thumbnail_url = thumbnails['medium']['url']
                    elif 'default' in thumbnails:
                        thumbnail_url = thumbnails['default']['url']
            except Exception as e:
                Logger.instance().error(caller="YoutubeModel", msg=f"Error fetching thumbnail via API: {e}")
                # Fall back to direct thumbnail URL
        
        # Download the thumbnail
        try:
            # Add timeout to prevent blocking for too long
            response = requests.get(thumbnail_url, timeout=15.0)
            if response.status_code == 200:
                pixmap = QPixmap()
                pixmap.loadFromData(response.content)
                return pixmap
        except Exception as e:
            Logger.instance().error(caller="YoutubeModel", msg=f"Error downloading thumbnail: {e}")
        
        return None 

    @staticmethod
    def get_video_metadata(url):
        """Get both title and thumbnail for a YouTube video."""
        # Clean the URL if it has a protocol prefix
        original_url = url
        if url and url.startswith(('musicplayerdl://', 'youtubemaster://')):
            protocol_path = url.split('://', 1)[1]
            if '/' in protocol_path and protocol_path.split('/', 1)[0] in ['video', 'audio', 'best']:
                _, url = protocol_path.split('/', 1)
            else:
                url = protocol_path
        
        video_id = YoutubeModel.extract_video_id(url)
        if not video_id:
            return "Unknown Video", None
        
        # Use SettingsManager.get with QSettings key
        api_key = SettingsManager.instance().get(YT_API_QSETTINGS_KEY, '', SettingType.STRING) 
        title = None
        pixmap = None
        
        if api_key:
            try:
                api_url = f"https://www.googleapis.com/youtube/v3/videos?id={video_id}&key={api_key}&part=snippet"
                
                # Add timeout to prevent blocking for too long
                response = requests.get(api_url, timeout=15.0)
                data = response.json()
                
                if 'items' in data and len(data['items']) > 0:
                    snippet = data['items'][0]['snippet']
                    title = snippet.get('title', None)
                    
                    # Get thumbnail URL
                    thumbnails = snippet.get('thumbnails', {})
                    thumbnail_url = None
                    
                    # Prefer smaller thumbnails
                    for size in ['default', 'medium', 'high']:
                        if size in thumbnails:
                            thumbnail_url = thumbnails[size]['url']
                            break
                    
                    # Download the thumbnail
                    if thumbnail_url:
                        # Add timeout to prevent blocking for too long
                        response = requests.get(thumbnail_url, timeout=15.0)
                        if response.status_code == 200:
                            pixmap = QPixmap()
                            pixmap.loadFromData(response.content)
            except Exception as e:
                Logger.instance().error(caller="YoutubeModel", msg=f"Error fetching data via YouTube API: {str(e)}")
        
        # Fallback for title and thumbnail if needed
        if not title:
            # Create a better loading title that includes video ID
            youtube_url = YoutubeModel.clean_url(url)
            if "watch?v=" in youtube_url:
                title = f"Loading YouTube video: {video_id}"
            else:
                title = f"Loading YouTube video"
        
        if not pixmap:
            pixmap = YoutubeModel.get_thumbnail(url, 'medium')
        
        return title, pixmap

    @staticmethod
    def clean_url(url):
        """
        Clean a YouTube URL to remove unnecessary parameters.
        Returns a standardized YouTube URL with only the video ID.
        """
        # If it's a video ID, convert to full URL
        if url and not url.startswith(('http://', 'https://', 'www.')):
            # Assume it's a video ID
            return f"https://www.youtube.com/watch?v={url}"
        
        # Extract video ID using the existing method
        video_id = YoutubeModel.extract_video_id(url)
        
        # If we found a valid video ID, return standard format
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
        
        # If we couldn't extract a video ID, return the original URL
        return url 