"""
Main dashboard window for the Music Player application.
"""
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFontDatabase, QFont
import os
from pathlib import Path

# Import page classes
from music_player.ui.pages import (
    DashboardPage,
    PlayerPage,
    PlaylistsPage,
    PreferencesPage,
)


class MusicPlayerDashboard:
    """
    Main dashboard window for the Music Player application.
    Uses the BaseWindow from our framework.
    """
    def __init__(self, base_window):
        """
        Initialize the dashboard.
        
        Args:
            base_window: The BaseWindow instance from the framework
        """
        self.window = base_window
        self.window.setWindowTitle("Music Player")
        
        # Store page instances to prevent garbage collection
        self.pages = {}
        
        # Set up fonts
        self.setup_fonts()
        
        # Initialize and add pages
        self.initialize_pages()
    
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
        self.window.add_page('dashboard', dashboard_page)
        self.window.add_page('player', player_page)
        self.window.add_page('playlists', playlists_page)
        self.window.add_page('preferences', preferences_page)
        
        # Connect signals from sidebar to our handler
        self.window.sidebar.item_clicked.connect(self.on_sidebar_item_clicked)
        
        # Show the dashboard page initially
        self.window.show_page('dashboard')
        
        # Set dashboard as initially selected in sidebar
        self.window.sidebar.set_selected_item('dashboard')
    
    def on_sidebar_item_clicked(self, item_id, page_class):
        """
        Handle sidebar item click.
        
        Args:
            item_id: ID of the sidebar item
            page_class: Class of the page to show
        """
        # Show the corresponding page
        self.window.show_page(item_id)
        
        # Update the page title (optional, the framework should handle this)
        page_titles = {
            'dashboard': 'Dashboard',
            'player': 'Player',
            'playlists': 'Playlists',
            'preferences': 'Preferences'
        }
        
        if item_id in page_titles:
            self.window.page_title.setText(page_titles[item_id])
    
    def setup_fonts(self):
        """Set up custom fonts for the application."""
        # Get the fonts directory
        fonts_dir = Path(__file__).parent.parent / "fonts"
        
        # Add custom fonts if available
        if fonts_dir.exists():
            font_files = {
                "Inter": ["Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-Bold.ttf"],
            }
            
            for font_family, files in font_files.items():
                for file in files:
                    font_path = fonts_dir / file
                    if font_path.exists():
                        font_id = QFontDatabase.addApplicationFont(str(font_path))
                        if font_id >= 0:
                            print(f"Added font: {file}")
