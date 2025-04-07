"""
VLC Player UI components for the music player application.
"""
from .player_widget import PlayerWidget
from .player_controls import PlayerControls
from .player_timeline import PlayerTimeline
from .album_art_display import AlbumArtDisplay
from .main_player import MainPlayer

__all__ = [
    'PlayerWidget',
    'PlayerControls',
    'PlayerTimeline',
    'AlbumArtDisplay',
    'MainPlayer'
] 