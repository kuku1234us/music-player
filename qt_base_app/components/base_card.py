"""
Base card component for Qt applications.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt
from ..theme.theme_manager import ThemeManager


class BaseCard(QWidget):
    """
    A base card component that can be extended for specific use cases.
    Provides a standard card layout with a title and content area.
    """
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.theme = ThemeManager.instance()
        
        # Enable background styling
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        # Set object name for styling
        self.setObjectName("baseCard")
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the card UI layout."""
        # Apply card styling
        self.setStyleSheet(self.theme.get_stylesheet('card'))
        
        # Create layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(
            self.theme.get_dimension('card', 'padding'),
            self.theme.get_dimension('card', 'padding'),
            self.theme.get_dimension('card', 'padding'),
            self.theme.get_dimension('card', 'padding')
        )
        self.layout.setSpacing(self.theme.get_dimension('spacing', 'large'))
        
        # Create title
        typography = self.theme.get_typography('card_title')
        self.title_label = QLabel(self.title)
        self.title_label.setObjectName("cardTitle")
        self.title_label.setStyleSheet(f"""
            color: {self.theme.get_color('text', 'primary')};
            font-size: {typography['size']}px;
            font-weight: {typography['weight']};
        """)
        
        # Create content area
        self.content_widget = QWidget()
        self.content_widget.setObjectName("cardContent")
        self.content_widget.setStyleSheet(f"""
            color: {self.theme.get_color('text', 'primary')};
            background-color: transparent;
        """)
        
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(self.theme.get_dimension('spacing', 'medium'))
        
        # Add to layout
        self.layout.addWidget(self.title_label)
        self.layout.addWidget(self.content_widget)
    
    def add_widget(self, widget: QWidget):
        """
        Add a widget to the card's content area.
        
        Args:
            widget: The widget to add
        """
        self.content_layout.addWidget(widget)
    
    def clear_content(self):
        """Remove all widgets from the content area."""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater() 