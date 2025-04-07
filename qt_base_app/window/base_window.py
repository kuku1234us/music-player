"""
Base window implementation for Qt applications.
"""
import os
from pathlib import Path
import yaml
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QColor
import qtawesome as qta

from ..theme.theme_manager import ThemeManager
from ..components.sidebar import SidebarWidget


class BaseWindow(QMainWindow):
    """
    Base window class that implements a standard layout with sidebar and content area.
    Can be extended for specific applications.
    """
    def __init__(self, config_path: str = None):
        super().__init__()
        self.theme = ThemeManager.instance()
        
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Set window properties
        self._setup_window()
        
        # Create and setup UI
        self._setup_ui()
        
        # Apply theme
        self._apply_theme()
    
    def _load_config(self, config_path: str = None) -> dict:
        """Load application configuration from YAML file."""
        if not config_path:
            config_path = Path(__file__).parent.parent / 'config' / 'app_config.yaml'
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return {}
    
    def _setup_window(self):
        """Set up window properties."""
        # Set window title
        self.setWindowTitle(self.config.get('app', {}).get('title', 'Qt Application'))
        
        # Set window size
        window_config = self.config.get('app', {}).get('window', {})
        self.resize(
            window_config.get('width', 1200),
            window_config.get('height', 800)
        )
        self.setMinimumSize(
            window_config.get('min_width', 800),
            window_config.get('min_height', 600)
        )
        
        # Set window icon
        self._setup_window_icon()
        
        # Force background color
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(palette.ColorRole.Window, 
                        QColor(self.theme.get_color('background', 'primary')))
        self.setPalette(palette)
    
    def _setup_window_icon(self):
        """Set up the window icon from file or qtawesome."""
        app_config = self.config.get('app', {})
        icon_path = app_config.get('icon_path')
        
        if icon_path and os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            # Use qtawesome icon as fallback
            icon_name = app_config.get('icon', 'fa5s.window-maximize')
            self.setWindowIcon(qta.icon(icon_name))
    
    def _setup_ui(self):
        """Set up the main UI layout."""
        # Main layout setup
        self.central_widget = QWidget()
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Create sidebar
        self.sidebar = SidebarWidget(self)
        self.sidebar.item_clicked.connect(self._on_sidebar_item_clicked)
        
        # Create content area
        self._setup_content_area()
        
        # Set central widget
        self.setCentralWidget(self.central_widget)
    
    def _setup_content_area(self):
        """Set up the main content area."""
        self.content_widget = QWidget()
        self.content_widget.setObjectName("contentArea")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        
        # Header with sidebar trigger
        self._setup_header()
        
        # Content stack
        self.content_stack = QStackedWidget()
        self.content_layout.addWidget(self.content_stack)
        
        # Add to main layout
        self.main_layout.addWidget(self.sidebar)
        self.main_layout.addWidget(self.content_widget)
    
    def _setup_header(self):
        """Set up the header area with sidebar toggle and page title."""
        self.header = QWidget()
        self.header.setObjectName("contentHeader")
        self.header.setFixedHeight(self.theme.get_dimension('header', 'height'))
        
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(16, 0, 16, 0)
        
        # Toggle button
        self.toggle_btn = self._create_sidebar_toggle()
        
        # Page title
        typography = self.theme.get_typography('title')
        self.page_title = QLabel()
        self.page_title.setObjectName("pageTitle")
        self.page_title.setStyleSheet(f"""
            color: {self.theme.get_color('text', 'primary')};
            font-size: {typography['size']}px;
            font-weight: {typography['weight']};
        """)
        
        self.header_layout.addWidget(self.toggle_btn)
        self.header_layout.addWidget(self.page_title)
        self.header_layout.addStretch()
        
        self.content_layout.addWidget(self.header)
    
    def _create_sidebar_toggle(self) -> QPushButton:
        """Create the sidebar toggle button."""
        toggle_btn = QPushButton()
        toggle_btn.setObjectName("toggleButton")
        toggle_btn.setIcon(qta.icon(
            "fa5s.bars",
            color=self.theme.get_color('text', 'primary'),
            options=[{'antialiasing': True}]
        ))
        toggle_btn.setIconSize(QSize(16, 16))
        toggle_btn.setFixedSize(32, 32)
        toggle_btn.setToolTip("Toggle Sidebar")
        toggle_btn.clicked.connect(self._toggle_sidebar)
        
        toggle_btn.setStyleSheet(f"""
            #toggleButton {{
                background-color: transparent;
                border: none;
            }}
            #toggleButton:hover {{
                background-color: {self.theme.get_color('background', 'tertiary')};
                border-radius: 4px;
            }}
        """)
        
        return toggle_btn
    
    def _toggle_sidebar(self):
        """Toggle the sidebar visibility."""
        self.sidebar.toggle_sidebar()
    
    def _on_sidebar_item_clicked(self, item_id: str, page_class: str):
        """
        Handle sidebar item click.
        Should be overridden by subclasses to implement specific page loading.
        """
        # Update the page title
        if page_class:
            title = page_class.replace('Page', '')
            self.page_title.setText(title)
        
        # Show the corresponding page if found
        self.show_page(item_id)
    
    def _apply_theme(self):
        """Apply theme to the window."""
        self.setStyleSheet(self.theme.get_stylesheet('window'))
    
    def add_page(self, page_id: str, page_widget: QWidget):
        """
        Add a page to the content stack.
        
        Args:
            page_id: Unique identifier for the page
            page_widget: The page widget to add
        """
        # Set the page_id as a property on the widget for later retrieval
        page_widget.setProperty('page_id', page_id)
        
        # Add to the content stack
        self.content_stack.addWidget(page_widget)
    
    def show_page(self, page_id: str):
        """
        Show a specific page.
        
        Args:
            page_id: ID of the page to show
        """
        # Find the page widget by ID and show it
        page_found = False
        for i in range(self.content_stack.count()):
            widget = self.content_stack.widget(i)
            if widget.property('page_id') == page_id:
                self.content_stack.setCurrentWidget(widget)
                page_found = True
                
                # Set the page title based on various methods
                title = ""
                
                # Check sidebar configuration for matching page title
                sidebar_config = self.config.get('sidebar', {}).get('sections', [])
                for section in sidebar_config:
                    for item in section.get('items', []):
                        if item.get('id') == page_id:
                            title = item.get('title', '')
                            break
                    if title:
                        break
                
                # If no title from config, use object name
                if not title and hasattr(widget, 'objectName') and widget.objectName():
                    obj_name = widget.objectName()
                    title = obj_name.replace('Page', '').replace('page', '')
                
                # If still no title, use page_id
                if not title:
                    title = page_id.capitalize()
                
                # Set the page title
                self.page_title.setText(title)
                break
        
        # If page wasn't found, log an error
        if not page_found:
            print(f"Error: Page with ID '{page_id}' not found") 