"""
Main dashboard window for the Music Player application.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, QSize, pyqtSlot, QTimer, QSettings, QEvent, pyqtSignal, QObject
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
    VidProcessingPage,
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
        vid_processing_page = VidProcessingPage()
        
        # Store pages to prevent garbage collection
        self.pages['dashboard'] = dashboard_page
        self.pages['player'] = player_page
        self.pages['playlists'] = playlists_page
        self.pages['preferences'] = preferences_page
        self.pages['browser'] = browser_page
        self.pages['youtube_downloader'] = youtube_page
        self.pages['vid_processing'] = vid_processing_page
        
        # Add pages to the window
        self.add_page('dashboard', dashboard_page)
        self.add_page('player', player_page)
        self.add_page('playlists', playlists_page)
        self.add_page('preferences', preferences_page)
        self.add_page('browser', browser_page)
        self.add_page('youtube_downloader', youtube_page)
        self.add_page('vid_processing', vid_processing_page)
        
        # Connect signals from sidebar to our handler
        self.sidebar.item_clicked.connect(self.on_sidebar_item_clicked)
        
        # Connect player signals to pages
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
        if hasattr(playlists_page.play_mode_widget.selection_pool_widget, 'play_single_file_requested'):
            playlists_page.play_mode_widget.selection_pool_widget.play_single_file_requested.connect(
                lambda filepath: self.player.load_media_unified(filepath, "selection_pool")
            )
        
        # Connect signals from DashboardPage for recently played items
        if hasattr(dashboard_page, 'play_single_file_requested'):
            # Use the new comprehensive unified loading method for consistent behavior
            dashboard_page.play_single_file_requested.connect(
                lambda filepath: self.player.load_media_unified(filepath, "dashboard_recent_files")
            )
            
        if hasattr(dashboard_page, 'play_playlist_requested'):
            dashboard_page.play_playlist_requested.connect(self._handle_play_playlist_from_dashboard)
        
        # Connect YoutubePage's navigate_to_file signal to our handler method
        if hasattr(youtube_page, 'navigate_to_file'):
            youtube_page.navigate_to_file.connect(self._handle_navigate_to_downloaded_file)
            
        # Connect YoutubePage's play_file signal to handle playback of files
        if hasattr(youtube_page, 'play_file'):
            youtube_page.play_file.connect(self._handle_single_file_request)
        
        # Connect BrowserPage to the new unified loading method
        if hasattr(browser_page, 'play_single_file_requested'):
            browser_page.play_single_file_requested.connect(
                lambda filepath: self.player.load_media_unified(filepath, "browser_files")
            )
        
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
            Logger.instance().error(caller="Dashboard", msg="[Dashboard] Error: Could not find PlaylistsPage or _enter_play_mode method.")
    
    @pyqtSlot()
    def _navigate_to_player_page(self):
        """Navigates to the PlayerPage when video media is detected."""
        # No need to check is_video anymore, the signal only fires for video.
        
        if self.player and hasattr(self.player, '_video_widget') and self.player._video_widget:
                self.player._video_widget.setVisible(True)
                video_widget_was_hidden = False

        # Determine the current page ID
        current_widget = self.content_stack.currentWidget()
        current_page_id = None
        for page_id, page_widget in self.pages.items():
            if page_widget == current_widget:
                current_page_id = page_id
                break

        # Navigate only if not already on the player page
        if current_page_id != 'player':
            self.show_page('player')
            self.sidebar.set_selected_item('player')

    @pyqtSlot(str)
    def _handle_single_file_request(self, filepath: str):
        """
        Handles request to play a single file, ensuring consistent behavior.
        Uses the new unified loading approach to ensure position restoration works correctly.
        """
        self.logger.info(self.__class__.__name__, f"Handling single file request: {filepath}")

        # Check if player is available
        if not self.player or not hasattr(self.player, 'load_media_unified'):
            self.logger.error(self.__class__.__name__, "Player instance not available or missing unified loading method.")
            return

        # Use the new comprehensive unified loading method
        # This handles all video widget state, position restoration, and error handling internally
        try:
            success = self.player.load_media_unified(filepath, "youtube_downloader")
            if success:
                self.logger.info(self.__class__.__name__, "Unified media loading completed successfully.")
            else:
                self.logger.warning(self.__class__.__name__, "Unified media loading reported failure.")
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Error during unified media loading: {e}")

    def _on_playback_state_changed(self, state):
        """Handle playback state change events"""
        # Update UI elements based on state
        pass
        
    def _on_media_changed(self, metadata: dict, is_video: bool):
        """Handle media change events from the player"""
        # Extract info from metadata
        title = metadata.get('title', 'Unknown Track')
        artist = metadata.get('artist', 'Unknown Artist')
        
        # Update window title
        self.setWindowTitle(f"{title} - {artist} | Music Player")

        if is_video:
            self._navigate_to_player_page()

    def closeEvent(self, event: QCloseEvent):
        """Handle the main window closing event."""
        log_prefix = self.__class__.__name__ # Use class name for caller context
        
        self.logger.info(log_prefix, "Main window close event triggered.")

        # --- NEW: Save current playback position and subtitle state before exit ---
        if self.player and self.player.current_media_path:
            current_pos = self.player.backend.get_current_position()
            current_duration = self.player.backend.get_duration()
            current_rate = self.player.backend.get_rate()
            if current_pos and current_duration and current_pos > 5000:
                self.logger.info(log_prefix, f"Saving position {current_pos}ms at {current_rate}x rate before app exit")
                try:
                    # Get current subtitle state
                    subtitle_enabled, subtitle_track_id, subtitle_language = self.player._get_current_subtitle_state()
                    success = self.player.position_manager.save_position(
                        self.player.current_media_path, current_pos, current_duration, current_rate,
                        subtitle_enabled, subtitle_track_id, subtitle_language)
                    if success:
                        # Update tracking variables for consistency
                        self.player.last_saved_position = current_pos
                        self.logger.info(log_prefix, "Position, rate, and subtitle state saved successfully on app exit")
                    else:
                        self.logger.warning(log_prefix, "Failed to save position, rate, and subtitle state on app exit")
                except Exception as e:
                    self.logger.error(log_prefix, f"Error saving position, rate, and subtitle state on app exit: {e}")
        # ------------------------------------------------------------------------

        # Gracefully shut down the download manager threads
        if hasattr(self, 'pages') and 'youtube_downloader' in self.pages:
             youtube_page = self.pages['youtube_downloader']
             if hasattr(youtube_page, 'download_manager'):
                 self.logger.info(log_prefix, "Shutting down Download Manager...")
                 youtube_page.download_manager.shutdown()
                 self.logger.info(log_prefix, "Download Manager shutdown complete.")
             else:
                 # Use logger for warning
                 self.logger.warning(log_prefix, "Download Manager not found on YoutubePage.")
        else:
            # Use logger for warning
            self.logger.warning(log_prefix, "YoutubePage not found.")

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

    @pyqtSlot(str, str)
    def _handle_navigate_to_downloaded_file(self, output_path, filename):
        """
        Handle request to navigate to a downloaded file in the browser page.
        
        Args:
            output_path (str): The directory path where the file is located
            filename (str): The name of the file to select
        """
        self.logger.info(self.__class__.__name__, f"Navigating to downloaded file: {output_path}/{filename}")
        
        # Get the browser page instance
        browser_page = self.pages.get('browser')
        if not browser_page:
            self.logger.error(self.__class__.__name__, "Browser page not found")
            return
        
        # Set flag to indicate navigation is in progress
        # This will prevent showEvent from loading the last directory
        if hasattr(browser_page, "set_navigation_in_progress"):
            browser_page.set_navigation_in_progress(True)
        
        # Navigate to the browser page first
        self.show_page('browser')
        self.sidebar.set_selected_item('browser')
        
        # Now delegate the navigation and file selection to the BrowserPage
        if hasattr(browser_page, "navigate_to_file"):
            # The BrowserPage will handle file navigation and selection internally
            success = browser_page.navigate_to_file(output_path, filename)
            if not success:
                self.logger.warning(self.__class__.__name__, f"BrowserPage navigation failed for: {output_path}/{filename}")
        else:
            self.logger.error(self.__class__.__name__, "BrowserPage doesn't have navigate_to_file method")
