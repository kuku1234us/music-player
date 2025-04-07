"""
Domain models and business logic for the Music Player application.

This package contains the core backend implementations for media playback:
- VLCBackend: Handles media playback using the VLC library, providing a robust
             interface for controlling playback, managing playlists, and 
             handling media metadata.
"""
from music_player.models.vlc_backend import VLCBackend

__all__ = ['VLCBackend']
