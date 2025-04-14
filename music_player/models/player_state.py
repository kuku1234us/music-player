"""
Shared state module for the Music Player application.
Stores global references and state that needs to be accessed by multiple components.
"""
from typing import Optional
from music_player.models.playlist import Playlist

# Global variable to store the current playlist being played
current_playing_playlist: Optional[Playlist] = None

def set_current_playlist(playlist: Optional[Playlist]) -> None:
    """Set the current global playlist reference"""
    global current_playing_playlist
    current_playing_playlist = playlist

def get_current_playlist() -> Optional[Playlist]:
    """Get the current global playlist reference"""
    global current_playing_playlist
    return current_playing_playlist 