"""
Dashboard page for the Music Player application.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout
from PyQt6.QtCore import Qt
import qtawesome as qta

# Import all needed components from card.py
from music_player.ui.components import DashboardCard, StatsCard, ActivityItem


class DashboardPage(QWidget):
    """
    Main dashboard page showing music statistics and recently played tracks.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # Set widget properties
        self.setObjectName("dashboardPage")
        
        # Update to use modern styles
        self.setStyleSheet("""
            #dashboardPage {
                background-color: #09090b !important;
            }
        """)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the UI for the dashboard page."""
        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 24, 24, 24)
        self.main_layout.setSpacing(24)
        
        # Welcome message
        self.welcome_label = QLabel("Welcome to your Music Player")
        self.welcome_label.setObjectName("welcomeLabel")
        self.welcome_label.setStyleSheet("""
            color: #fafafa;
            font-size: 24px;
            font-weight: bold;
        """)
        self.main_layout.addWidget(self.welcome_label)
        
        self.description_label = QLabel("The quick brown fox jumps over the lazy dog. 1234567890")
        self.description_label.setStyleSheet("""
            color: #a1a1aa;
            font-size: 16px;
            margin-bottom: 16px;
        """)
        self.main_layout.addWidget(self.description_label)
        
        # Stats section
        self.stats_section = QWidget()
        self.stats_grid = QGridLayout(self.stats_section)
        self.stats_grid.setContentsMargins(0, 0, 0, 0)
        self.stats_grid.setSpacing(16)
        
        # Replace custom stats cards with StatsCard from card.py
        self.songs_card = StatsCard("Total Songs", "1,254", "fa5s.music", color="#4f46e5")
        self.albums_card = StatsCard("Albums", "87", "fa5s.compact-disc", color="#ec4899")
        self.playlists_card = StatsCard("Playlists", 12, "fa5s.list", color="#f59e0b")
        
        # Add stats cards to grid
        self.stats_grid.addWidget(self.songs_card, 0, 0)
        self.stats_grid.addWidget(self.albums_card, 0, 1)
        self.stats_grid.addWidget(self.playlists_card, 0, 2)
        
        self.main_layout.addWidget(self.stats_section)
        
        # Replace custom section cards with DashboardCard
        # Recent Activity section
        self.recent_activity = DashboardCard("Recent Activity")
        
        # Add activity items
        self.recent_activity.add_widget(
            ActivityItem("New album added to library", "2 hours ago", "fa5s.compact-disc", "#4f46e5")
        )
        
        self.recent_activity.add_widget(
            ActivityItem("Listened to 'Summer Playlist'", "5 hours ago", "fa5s.play", "#ec4899")
        )
        
        self.recent_activity.add_widget(
            ActivityItem("Added 3 songs to favorites", "Yesterday", "fa5s.heart", "#f59e0b")
        )
        
        self.main_layout.addWidget(self.recent_activity)
        
        # Recommended content
        self.recommended_card = DashboardCard("Recommended For You")
        
        # Add description
        description_label = QLabel("Based on your listening history, we think you might enjoy these tracks.")
        description_label.setStyleSheet("color: #a1a1aa;")
        self.recommended_card.add_widget(description_label)
        
        # Add recommended tracks
        self.recommended_card.add_widget(
            ActivityItem("Midnight Sonata - Classical Vibes", "Classical", "fa5s.music", "#10b981")
        )
        
        self.recommended_card.add_widget(
            ActivityItem("Summer Nights - Beach Boys", "Rock", "fa5s.music", "#f59e0b")
        )
        
        self.main_layout.addWidget(self.recommended_card)
        
        # Add a stretch to push everything up
        self.main_layout.addStretch() 