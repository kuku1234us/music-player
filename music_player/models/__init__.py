"""
Domain models and business logic for the Music Player application.

This package contains the core backend implementations for media playback:
- VLCBackend: Handles media playback using the VLC library, providing a robust
             interface for controlling playback, managing playlists, and 
             handling media metadata.
"""
from music_player.models.vlc_backend import VLCBackend
from .file_pool_model import FilePoolModel
from .playlist import Playlist
from .recently_played import RecentlyPlayedModel

# Models migrated from youtube-master
from .SiteModel import SiteModel
from .YoutubeModel import YoutubeModel
from .BilibiliModel import BilibiliModel
from .Yt_DlpModel import YtDlpModel # Assuming class name is YtDlpModel
from .DownloadManager import DownloadManager
from .CLIDownloadWorker import CLIDownloadWorker


__all__ = [
    'VLCBackend',
    'FilePoolModel',
    'Playlist',
    'RecentlyPlayedModel',
    # Migrated models
    'SiteModel',
    'YoutubeModel',
    'BilibiliModel',
    'YtDlpModel',
    'DownloadManager',
    'CLIDownloadWorker',
]
