"""
Main dashboard window for the Music Player application.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFontDatabase, QFont
import os
from pathlib import Path

# Import BaseWindow from framework
from qt_base_app.window.base_window import BaseWindow

# Import page classes
from music_player.ui.pages import (
    DashboardPage,
    PlayerPage,
    PlaylistsPage,
    PreferencesPage,
)

# Import player components
from music_player.ui.vlc_player import MainPlayer


class MusicPlayerDashboard(BaseWindow):
    """
    Main dashboard window for the Music Player application.
    Inherits from BaseWindow and customizes the layout to include a player at the bottom.
    """
    def __init__(self, config_path=None):
        """
        Initialize the music player dashboard.
        
        Args:
            config_path: Path to configuration file
        """
        # Create a persistent player for the dashboard
        self.player = MainPlayer(persistent_mode=True)
        
        # Store page instances to prevent garbage collection
        self.pages = {}
        
        # Initialize base window
        super().__init__(config_path)
        
        # Set up the application structure after base initialization
        self.initialize_pages()
        
        # Fix the player height
        self.player.setFixedHeight(130)
        
        # Style the player
        self.player.setStyleSheet("""
            QWidget#mainPlayer {
                background-color: #1a1a1a;
                border-top: 1px solid #333333;
            }
        """)
        
        # Set minimum window dimensions
        self.setMinimumWidth(900)
        self.setMinimumHeight(600)
        
        # Set window title
        self.setWindowTitle("Music Player")
        
        # Apply additional styling to fix sidebar margins
        self.setStyleSheet("""
            QMainWindow {
                margin: 0;
                padding: 0;
                border: none;
            }
            #sidebar {
                margin: 0;
                padding: 0;
                border: none;
            }
        """)
    
    def _assemble_layout(self):
        """
        Override the BaseWindow's layout assembly to include the player at the bottom.
        This is called during BaseWindow initialization.
        """
        # Main vertical layout for the central widget
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Top container for sidebar and content
        top_container = QWidget()
        top_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        # Horizontal layout for top section (sidebar + content)
        top_layout = QHBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        
        # Setup content layout
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.content_layout.addWidget(self.header)
        self.content_layout.addWidget(self.content_stack, 1)
        
        # Add sidebar and content to top section
        top_layout.addWidget(self.sidebar, 0)  # No stretch
        top_layout.addWidget(self.content_widget, 1)  # Give content stretch
        
        # Add top container to main layout with stretch
        self.main_layout.addWidget(top_container, 1)
        
        # Add player to bottom of main layout
        self.main_layout.addWidget(self.player, 0)  # No stretch
    
    def initialize_pages(self):
        """Initialize and add all pages to the window."""
        # Create pages
        dashboard_page = DashboardPage()
        player_page = PlayerPage()
        playlists_page = PlaylistsPage()
        preferences_page = PreferencesPage()
        
        # Store pages to prevent garbage collection
        self.pages['dashboard'] = dashboard_page
        self.pages['player'] = player_page
        self.pages['playlists'] = playlists_page
        self.pages['preferences'] = preferences_page
        
        # Add pages to the window
        self.add_page('dashboard', dashboard_page)
        self.add_page('player', player_page)
        self.add_page('playlists', playlists_page)
        self.add_page('preferences', preferences_page)
        
        # Connect signals from sidebar to our handler
        self.sidebar.item_clicked.connect(self.on_sidebar_item_clicked)
        
        # Connect player signals to pages
        if hasattr(self.player, 'track_changed'):
            self.player.track_changed.connect(self._on_track_changed)
        if hasattr(self.player, 'playback_state_changed'):
            self.player.playback_state_changed.connect(self._on_playback_state_changed)
        if hasattr(self.player, 'media_changed'):
            self.player.media_changed.connect(self._on_media_changed)
        
        # Connect PlayerPage to the persistent player
        if hasattr(player_page, 'set_persistent_player'):
            player_page.set_persistent_player(self.player)
            
        # Connect PlaylistsPage to the player
        if hasattr(playlists_page, 'playlist_selected_for_playback') and hasattr(self.player, 'load_playlist'):
            playlists_page.playlist_selected_for_playback.connect(self.player.load_playlist)
            
        # Connect the new track selection signal from PlayModeWidget to MainPlayer's slot
        if hasattr(playlists_page.play_mode_widget, 'track_selected_for_playback') and hasattr(self.player, 'play_track_from_playlist'):
            playlists_page.play_mode_widget.track_selected_for_playback.connect(self.player.play_track_from_playlist)
        
        # Show the dashboard page initially
        self.show_page('dashboard')
        
        # Set dashboard as initially selected in sidebar
        self.sidebar.set_selected_item('dashboard')
    
    def on_sidebar_item_clicked(self, item_id, page_class):
        """
        Handle sidebar item click.
        
        Args:
            item_id: ID of the sidebar item
            page_class: Class of the page to show
        """
        # Show the corresponding page
        self.show_page(item_id)
        
        # Update the page title (optional, the framework should handle this)
        page_titles = {
            'dashboard': 'Dashboard',
            'player': 'Player',
            'playlists': 'Playlists',
            'preferences': 'Preferences'
        }
        
        if item_id in page_titles:
            # Set the title text
            self.page_title.setText(page_titles[item_id])
    
    def _on_track_changed(self, metadata):
        """Handle track change events"""
        # Update window title with song info
        title = metadata.get('title', 'Unknown Track')
        artist = metadata.get('artist', 'Unknown Artist')
        self.setWindowTitle(f"{title} - {artist} | Music Player")
        
        # Update pages with track info
        if hasattr(self.pages.get('dashboard'), 'update_now_playing'):
            self.pages['dashboard'].update_now_playing(metadata)
            
    def _on_playback_state_changed(self, state):
        """Handle playback state change events"""
        # Update UI elements based on state
        pass
        
    def _on_media_changed(self, title, artist, album, artwork_path):
        """Handle media change events from the player"""
        # Update window title
        self.setWindowTitle(f"{title} - {artist} | Music Player")
        
        # Update dashboard
        if hasattr(self.pages.get('dashboard'), 'update_now_playing'):
            metadata = {
                'title': title,
                'artist': artist,
                'album': album,
                'artwork_path': artwork_path
            }
            self.pages['dashboard'].update_now_playing(metadata)
