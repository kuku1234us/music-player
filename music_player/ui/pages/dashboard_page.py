"""
Dashboard page for the Music Player application.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QIcon

# Try to import qtawesome for icons
try:
    import qtawesome as qta
    HAS_QTAWESOME = True
except ImportError:
    HAS_QTAWESOME = False

# Import BaseCard from the framework
from qt_base_app.components.base_card import BaseCard
from qt_base_app.theme.theme_manager import ThemeManager

# Keep import for ActivityItem which we still need
from music_player.ui.components import ActivityItem


class DashboardPage(QWidget):
    """
    Main dashboard page showing music statistics and recently played tracks.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # Set widget properties
        self.setObjectName("dashboardPage")
        self.setProperty('page_id', 'dashboard')
        
        # Get theme manager instance
        self.theme = ThemeManager.instance()
        
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
        self.welcome_label.setStyleSheet(f"""
            color: {self.theme.get_color('text', 'primary')};
            font-size: 24px;
            font-weight: bold;
        """)
        self.main_layout.addWidget(self.welcome_label)
        
        self.description_label = QLabel("Enjoy your favorite music with this feature-rich audio player.")
        self.description_label.setStyleSheet(f"""
            color: {self.theme.get_color('text', 'secondary')};
            font-size: 16px;
            margin-bottom: 16px;
        """)
        self.main_layout.addWidget(self.description_label)
        
        # Stats section
        self.stats_section = QWidget()
        self.stats_grid = QGridLayout(self.stats_section)
        self.stats_grid.setContentsMargins(0, 0, 0, 0)
        self.stats_grid.setSpacing(16)
        
        # Create stats cards using BaseCard
        self.songs_card = self._create_stats_card("Total Songs", "1,254", "fa5s.music", "#4f46e5")
        self.albums_card = self._create_stats_card("Albums", "87", "fa5s.compact-disc", "#ec4899")
        self.playlists_card = self._create_stats_card("Playlists", "12", "fa5s.list", "#f59e0b")
        
        # Add stats cards to grid
        self.stats_grid.addWidget(self.songs_card, 0, 0)
        self.stats_grid.addWidget(self.albums_card, 0, 1)
        self.stats_grid.addWidget(self.playlists_card, 0, 2)
        
        self.main_layout.addWidget(self.stats_section)
        
        # Recent Activity section using BaseCard
        self.recent_activity = BaseCard("Recent Activity")
        
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
        
        # Recommended content using BaseCard
        self.recommended_card = BaseCard("Recommended For You")
        
        # Add description
        description_label = QLabel("Based on your listening history, we think you might enjoy these tracks.")
        description_label.setStyleSheet(f"color: {self.theme.get_color('text', 'secondary')};")
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
    
    def _create_stats_card(self, title, value, icon_name, icon_color):
        """
        Create a statistics card with an icon and value.
        
        Args:
            title: The title of the card
            value: The value to display
            icon_name: Font Awesome icon name
            icon_color: Color for the icon
        
        Returns:
            BaseCard: A card with the statistics information
        """
        # Create card with a slightly different styling - no border and a subtle background
        card = BaseCard(
            title,
            border_style="none",
            background_style=f"{self.theme.get_color('background', 'tertiary')}"
        )
        
        # Create content widget
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)
        
        # Add icon if qtawesome is available
        if HAS_QTAWESOME:
            icon_label = QLabel()
            icon = qta.icon(icon_name, color=icon_color)
            icon_label.setPixmap(icon.pixmap(48, 48))
            content_layout.addWidget(icon_label)
        
        # Add value
        value_label = QLabel(value)
        value_label.setStyleSheet(f"""
            color: {self.theme.get_color('text', 'primary')};
            font-size: 24px;
            font-weight: bold;
        """)
        content_layout.addWidget(value_label)
        content_layout.addStretch()
        
        card.add_widget(content)
        return card 