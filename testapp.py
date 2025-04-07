"""
Test application using the qt_base_app framework.
"""
import sys
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGridLayout
from qt_base_app.app import create_app, run_app
from qt_base_app.components.base_card import BaseCard
from qt_base_app.theme.theme_manager import ThemeManager


class DashboardPage(QWidget):
    """Dashboard page with some example cards."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = ThemeManager.instance()
        self.setObjectName("dashboardPage")
        self.setProperty('page_id', 'dashboard')  # Set explicit page_id
        print(f"Dashboard page created with objectName: {self.objectName()}")
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the dashboard UI."""
        # Main layout with some padding
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)
        
        # Grid layout for cards
        grid = QGridLayout()
        grid.setSpacing(24)
        
        # Create some example cards
        welcome_card = BaseCard("Welcome")
        welcome_label = QLabel("Welcome to the Test Application!")
        welcome_label.setStyleSheet(f"""
            color: {self.theme.get_color('text', 'primary')};
            font-size: {self.theme.get_typography('text')['size']}px;
        """)
        welcome_card.add_widget(welcome_label)
        
        stats_card = BaseCard("Statistics")
        stats_label = QLabel("This is where statistics would go")
        stats_label.setStyleSheet(f"""
            color: {self.theme.get_color('text', 'secondary')};
            font-size: {self.theme.get_typography('text')['size']}px;
        """)
        stats_card.add_widget(stats_label)
        
        info_card = BaseCard("Information")
        info_label = QLabel("This is an example of the base app framework")
        info_label.setStyleSheet(f"""
            color: {self.theme.get_color('text', 'secondary')};
            font-size: {self.theme.get_typography('text')['size']}px;
        """)
        info_card.add_widget(info_label)
        
        # Add cards to grid
        grid.addWidget(welcome_card, 0, 0)
        grid.addWidget(stats_card, 0, 1)
        grid.addWidget(info_card, 1, 0, 1, 2)  # Span 2 columns
        
        # Add grid to main layout
        layout.addLayout(grid)
        layout.addStretch()  # Push everything to the top


class PreferencesPage(QWidget):
    """Preferences page with some example settings."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = ThemeManager.instance()
        self.setObjectName("preferencesPage")
        self.setProperty('page_id', 'preferences')  # Set explicit page_id
        print(f"Preferences page created with objectName: {self.objectName()}")
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the preferences UI."""
        # Main layout with some padding
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)
        
        # Create a settings card
        settings_card = BaseCard("Settings")
        settings_label = QLabel("This is where settings would go")
        settings_label.setStyleSheet(f"""
            color: {self.theme.get_color('text', 'secondary')};
            font-size: {self.theme.get_typography('text')['size']}px;
        """)
        settings_card.add_widget(settings_label)
        
        # Add card to layout
        layout.addWidget(settings_card)
        layout.addStretch()  # Push everything to the top


def main():
    """Main entry point for the test application."""
    # Create application and window
    app, window = create_app()
    
    # Create pages
    dashboard = DashboardPage()
    preferences = PreferencesPage()
    
    # Add pages to window
    window.add_page("dashboard", dashboard)
    window.add_page("preferences", preferences)
    
    print("Pages added to window. About to show dashboard page...")
    
    # Show initial page
    window.show_page("dashboard")
    
    print(f"Dashboard page shown. Current page title: '{window.page_title.text()}'")
    
    # Log sidebar configuration to help debugging
    print("Sidebar configuration:")
    for section in window.config.get('sidebar', {}).get('sections', []):
        print(f"  Section: {section.get('title')}")
        for item in section.get('items', []):
            print(f"    Item: {item.get('id')} -> {item.get('title')}")
    
    # Run application
    return run_app(app, window)


if __name__ == "__main__":
    sys.exit(main()) 