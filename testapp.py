"""
Test application using the qt_base_app framework.
"""
import sys
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGridLayout, QHBoxLayout, QSizePolicy
from qt_base_app.app import create_app, run_app
from qt_base_app.components.base_card import BaseCard
from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.window.base_window import BaseWindow
from PyQt6.QtWidgets import QApplication


class CustomPlayerWindow(BaseWindow):
    """
    Custom window implementation with a player area at the bottom.
    Demonstrates the new layout customization capabilities.
    """
    def _assemble_layout(self):
        """
        Override to create a custom layout with a player at the bottom.
        This demonstrates how to create a totally different layout
        while keeping all the original widget functionality.
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
        
        # Create player placeholder
        self.player_placeholder = QWidget()
        self.player_placeholder.setObjectName("playerPlaceholder")
        self.player_placeholder.setFixedHeight(70)
        self.player_placeholder.setStyleSheet("""
            QWidget#playerPlaceholder {
                background-color: #1a1a1a;
                border-top: 1px solid #333333;
            }
        """)
        
        # Add player placeholder to bottom of main layout
        self.main_layout.addWidget(self.player_placeholder, 0)  # No stretch


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
    """
    Main entry point for the test application.
    
    If 'custom' is passed as a command line argument, it will test the custom layout.
    Otherwise, it will test the default layout.
    """
    # Check command line arguments
    use_custom_layout = len(sys.argv) > 1 and sys.argv[1].lower() == 'custom'
    
    if use_custom_layout:
        print("Testing custom layout with player at bottom...")
        return test_custom_layout()
    else:
        print("Testing default layout...")
        return test_default_layout()


def test_default_layout():
    """Test the application with the default layout."""
    # Create application with default window
    print("Creating application with default BaseWindow layout:")
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
    
    print("\nDefault layout window created!")
    
    # Run application
    return run_app(app, window)


def test_custom_layout():
    """Test the custom layout window."""
    print("\nTesting with CustomPlayerWindow layout:")
    
    # Create application
    app = QApplication(sys.argv)
    from qt_base_app.app import setup_dark_title_bar
    setup_dark_title_bar(app)
    
    # Get the config path
    config_path = None  # Use default config
    
    # Create custom window
    window = CustomPlayerWindow(config_path)
    
    # Create pages
    dashboard = DashboardPage()
    preferences = PreferencesPage()
    
    # Add pages to window
    window.add_page("dashboard", dashboard)
    window.add_page("preferences", preferences)
    
    # Show initial page
    window.show_page("dashboard")
    
    # Show the window
    window.show()
    
    print("Custom layout window created with player placeholder at the bottom!")
    
    # Run application
    return app.exec()


if __name__ == "__main__":
    sys.exit(main()) 