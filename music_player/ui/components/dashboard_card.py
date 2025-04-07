"""
DashboardCard component for the music player application.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout
from PyQt6.QtCore import Qt
import qtawesome as qta


class DashboardCard(QWidget):
    """
    A card component for displaying information on the dashboard.
    """
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.title = title
        
        self.setAttribute(Qt.WA_StyledBackground, True)
        
        # Set object name and apply base styles with transparent background
        self.setObjectName("dashboardCard")
        self.setStyleSheet("""
            #dashboardCard {
                background-color: transparent;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        
        # Create layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(16)
        
        # Create title
        self.title_label = QLabel(self.title)
        self.title_label.setObjectName("cardTitle")
        self.title_label.setStyleSheet("""
            color: #fafafa;
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 4px;
            background-color: transparent; /* Ensure title bg is transparent */
        """)
        
        # Create content area
        self.content_widget = QWidget()
        self.content_widget.setObjectName("cardContent")
        self.content_widget.setStyleSheet("""
            color: #fafafa;
            background-color: transparent; /* Ensure content bg is transparent */
        """)
        
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 8, 0, 0)
        self.content_layout.setSpacing(12)  # Increased spacing between items
        
        # Add to layout
        self.layout.addWidget(self.title_label)
        self.layout.addWidget(self.content_widget)
    
    def add_widget(self, widget):
        """Add a widget to the card content."""
        self.content_layout.addWidget(widget)
    
    def add_layout(self, layout):
        """Add a layout to the card content."""
        self.content_layout.addLayout(layout)


class StatsCard(DashboardCard):
    """
    A card for displaying statistics with a number and icon.
    """
    def __init__(self, title, value, icon_name, parent=None, color="#6366f1"):
        super().__init__(title, parent)
        self.value = value
        self.icon_name = icon_name
        self.color = color
        
        # Explicitly set WA_StyledBackground for StatsCard too
        self.setAttribute(Qt.WA_StyledBackground, True)
        
        # Set object name to match class name
        self.setObjectName("statsCard")
        
        # Restore stylesheet for stats cards with transparent background
        self.setStyleSheet(f"""
            #statsCard {{
                background-color: transparent;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 16px;
            }}
            
            #statsCard #cardTitle {{
                color: #a1a1aa; /* Override title color */
                font-size: 14px; /* Override title size */
                font-weight: 500;
                margin-bottom: 4px;
                background-color: transparent;
            }}
            
            /* Content color is handled by the specific value/icon labels */
        """)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the UI for the stats card."""
        # Create stats layout
        stats_layout = QHBoxLayout()
        stats_layout.setContentsMargins(0, 8, 0, 0)
        
        # Create value label
        value_label = QLabel(str(self.value))
        value_label.setStyleSheet(f"""
            font-size: 32px;
            font-weight: 700;
            color: {self.color};
        """)
        
        # Create icon with antialiasing for better quality
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon(self.icon_name, color=self.color, options=[{'antialiasing': True}]).pixmap(32, 32))
        
        # Add to layout
        stats_layout.addWidget(value_label)
        stats_layout.addStretch()
        stats_layout.addWidget(icon_label)
        
        # Add to card
        self.add_layout(stats_layout)


class ActivityItem(QWidget):
    """
    An activity item with a colored indicator, title, and subtitle.
    """
    def __init__(self, title, subtitle, icon_name, color, parent=None):
        super().__init__(parent)
        self.title = title
        self.subtitle = subtitle
        self.icon_name = icon_name
        self.color = color
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the UI for the activity item."""
        # Main layout
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 4, 0, 4)
        self.layout.setSpacing(12)
        
        # Create icon indicator
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(20, 20)
        self.icon_label.setPixmap(qta.icon(self.icon_name, color=self.color, options=[{'antialiasing': True}]).pixmap(16, 16))
        self.icon_label.setStyleSheet(f"""
            background-color: {self.color.replace(')', ' / 20%)')};
            border-radius: 10px;
            padding: 2px;
        """)
        
        # Create content
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(2)
        
        # Create title and subtitle
        self.title_label = QLabel(self.title)
        self.title_label.setStyleSheet("""
            font-size: 14px;
            font-weight: 500;
            color: #fafafa;
        """)
        
        self.subtitle_label = QLabel(self.subtitle)
        self.subtitle_label.setStyleSheet("""
            font-size: 12px;
            color: #a1a1aa;
        """)
        
        # Add to layouts
        self.content_layout.addWidget(self.title_label)
        self.content_layout.addWidget(self.subtitle_label)
        
        self.layout.addWidget(self.icon_label)
        self.layout.addWidget(self.content_widget, 1)  # Stretch factor 1 