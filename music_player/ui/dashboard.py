"""
Main dashboard window for the Music Player application.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, QSize, pyqtSlot
from PyQt6.QtGui import QFontDatabase, QFont, QCloseEvent
import os
from pathlib import Path
import sys

# Import BaseWindow from framework
from qt_base_app.window.base_window import BaseWindow
# Import Logger
from qt_base_app.models.logger import Logger

# Import page classes
from music_player.ui.pages import (
    DashboardPage,
    PlayerPage,
    PlaylistsPage,
    PreferencesPage,
    BrowserPage,
    YoutubePage,
)

# Import player components
from music_player.ui.vlc_player import MainPlayer

# Import Playlist for type hint
from music_player.models.playlist import Playlist


class MusicPlayerDashboard(BaseWindow):
    """
    Main dashboard window for the Music Player application.
    Inherits from BaseWindow and customizes the layout to include a player at the bottom.
    """
    def __init__(self, **kwargs):
        """
        Initialize the music player dashboard.
        
        Args:
            config_path: Path to configuration file
        """
        # Create a persistent player for the dashboard
        self.player = MainPlayer(persistent_mode=True)
        
        # Store page instances to prevent garbage collection
        self.pages = {}
        
        # Initialize base window (config is loaded by create_application)
        super().__init__(**kwargs)
        
        # --- Initialize Logger AFTER base init (which loads YAML config) ---
        self.logger = Logger.instance()
        self.logger.info(self.__class__.__name__, "MusicPlayerDashboard initializing...")
        # -----------------------------------------------------------------
        
        # Set up the application structure after base initialization
        # Now self.config is available
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
        # Create pages (no longer pass ai_config to PlaylistsPage)
        dashboard_page = DashboardPage()
        player_page = PlayerPage()
        playlists_page = PlaylistsPage(parent=self) # Removed ai_config
        preferences_page = PreferencesPage()
        browser_page = BrowserPage()
        youtube_page = YoutubePage()
        
        # Store pages to prevent garbage collection
        self.pages['dashboard'] = dashboard_page
        self.pages['player'] = player_page
        self.pages['playlists'] = playlists_page
        self.pages['preferences'] = preferences_page
        self.pages['browser'] = browser_page
        self.pages['youtube_downloader'] = youtube_page
        
        # Add pages to the window
        self.add_page('dashboard', dashboard_page)
        self.add_page('player', player_page)
        self.add_page('playlists', playlists_page)
        self.add_page('preferences', preferences_page)
        self.add_page('browser', browser_page)
        self.add_page('youtube_downloader', youtube_page)
        
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
        
        # Connect the signal to play the entire playlist (from breadcrumb button)
        if hasattr(playlists_page, 'playlist_play_requested') and hasattr(self.player, 'load_playlist'):
            playlists_page.playlist_play_requested.connect(self.player.load_playlist)
        
        # Connect double-click signals for single file playback
        if hasattr(playlists_page.play_mode_widget.selection_pool_widget, 'play_single_file_requested') and hasattr(self.player, 'play_single_file'):
            playlists_page.play_mode_widget.selection_pool_widget.play_single_file_requested.connect(self.player.play_single_file)
            
        if hasattr(browser_page, 'play_single_file_requested') and hasattr(self.player, 'play_single_file'):
            browser_page.play_single_file_requested.connect(self.player.play_single_file)
        
        # Connect signals from DashboardPage for recently played items
        if hasattr(dashboard_page, 'play_single_file_requested'):
            dashboard_page.play_single_file_requested.connect(self._handle_play_single_from_dashboard)
            
        if hasattr(dashboard_page, 'play_playlist_requested'):
            dashboard_page.play_playlist_requested.connect(self._handle_play_playlist_from_dashboard)
        
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
            'preferences': 'Preferences',
            'browser': 'File Browser',
            'youtube_downloader': 'Youtube Downloader',
        }
        
        if item_id in page_titles:
            # Set the title text
            self.page_title.setText(page_titles[item_id])
    
    def _handle_play_single_from_dashboard(self, filepath: str):
        """Handles request from dashboard to play a single file and navigate."""
        if self.player and hasattr(self.player, 'play_single_file'):
            self.player.play_single_file(filepath)
            self.show_page('player')
            self.sidebar.set_selected_item('player')
            
    def _handle_play_playlist_from_dashboard(self, playlist: Playlist):
        """Handles request from dashboard to play a playlist and navigate."""
        # Get the playlists page instance
        pl_page = self.pages.get('playlists')
        if pl_page and hasattr(pl_page, '_enter_play_mode'):
            # Tell the playlists page to enter play mode for this playlist
            # This will trigger the necessary state changes and player loading internally
            pl_page._enter_play_mode(playlist)
            # Navigate to the playlists page (which will now show the play mode)
            self.show_page('playlists')
            self.sidebar.set_selected_item('playlists')
        else:
            print("[Dashboard] Error: Could not find PlaylistsPage or _enter_play_mode method.")
    
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

    def closeEvent(self, event: QCloseEvent):
        """Handle the main window closing event."""
        log_prefix = self.__class__.__name__ # Use class name for caller context
        
        self.logger.info(log_prefix, "Main window close event triggered.")

        # Gracefully shut down the download manager threads
        if hasattr(self, 'pages') and 'youtube_downloader' in self.pages:
             youtube_page = self.pages['youtube_downloader']
             if hasattr(youtube_page, 'download_manager'):
                 self.logger.info(log_prefix, "Shutting down Download Manager...")
                 youtube_page.download_manager.shutdown()
                 self.logger.info(log_prefix, "Download Manager shutdown complete.")
             else:
                 # Use logger for warning
                 self.logger.warn(log_prefix, "Download Manager not found on YoutubePage.")
        else:
            # Use logger for warning
            self.logger.warn(log_prefix, "YoutubePage not found.")

        # Accept the close event to allow the window to close
        event.accept()
        # Optionally call the base class closeEvent if needed
        # super().closeEvent(event)

    @pyqtSlot(str, str)
    def handle_protocol_url(self, url: str, format_type: str):
        """Handles incoming URLs from the custom protocol handler."""
        self.logger.info(self.__class__.__name__, f"Protocol URL received: {url} (Type: {format_type})")
        
        # Find the YoutubePage instance
        youtube_page: YoutubePage | None = self.pages.get('youtube_downloader')
        
        if youtube_page and isinstance(youtube_page, YoutubePage): # Check type too
            if hasattr(youtube_page, 'auto_add_download') and callable(youtube_page.auto_add_download):
                try:
                    # Delegate to the YoutubePage
                    youtube_page.auto_add_download(url, format_type)
                    
                    # Switch UI to show the download page
                    self.show_page('youtube_downloader')
                    self.sidebar.set_selected_item('youtube_downloader')
                    self.logger.info(self.__class__.__name__, "Switched to Youtube Downloader page.")
                except Exception as e:
                     # Log the error using the logger
                     self.logger.error(self.__class__.__name__, f"Error calling auto_add_download: {e}")
            else:
                # Log the error using the logger
                self.logger.error(self.__class__.__name__, "YoutubePage instance found, but missing 'auto_add_download' method.")
        else:
            # Log the error using the logger
            self.logger.error(self.__class__.__name__, "Could not find YoutubePage instance in self.pages.")
