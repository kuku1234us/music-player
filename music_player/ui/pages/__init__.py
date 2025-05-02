"""
This module contains UI pages for the music player application.
"""
from music_player.ui.pages.dashboard_page import DashboardPage
from music_player.ui.pages.player_page import PlayerPage
from music_player.ui.pages.preference_page import PreferencePage as PreferencesPage
from music_player.ui.pages.playlists_page import PlaylistsPage
from music_player.ui.pages.browser_page import BrowserPage
from .youtube_page import YoutubePage

__all__ = [
    'DashboardPage', 
    'PlayerPage', 
    'PreferencesPage', 
    'PlaylistsPage',
    'BrowserPage',
    'YoutubePage'
] 