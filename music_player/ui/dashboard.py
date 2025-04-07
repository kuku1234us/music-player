"""
Dashboard UI component with collapsible sidebar using QtAwesome.
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
    QLabel, QPushButton, QStackedWidget, QScrollArea, QSizePolicy, QApplication, QFrame
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QFont, QFontDatabase, QColor, QPalette
import qtawesome as qta
import os
import sys

from music_player.ui.config_loader import config
from music_player.ui.pages import DashboardPage, PlayerPage, PreferencesPage, PlaylistsPage
from music_player.ui.components.sidebar import SidebarWidget


class PageManager:
    """
    Manages the creation and caching of pages in the dashboard.
    """
    def __init__(self, content_stack):
        self.content_stack = content_stack
        self.pages = {}
        self.current_page = None
    
    def get_page(self, page_id, page_class_name):
        """
        Get or create a page by its ID and class name.
        
        Args:
            page_id: ID of the page
            page_class_name: Name of the page class
            
        Returns:
            Created or cached page widget
        """
        if page_id in self.pages:
            return self.pages[page_id]
        
        # Create the page based on class name
        if page_class_name == "DashboardPage":
            page = DashboardPage()
        elif page_class_name == "PlayerPage":
            page = PlayerPage()
        elif page_class_name == "PreferencesPage":
            page = PreferencesPage()
        elif page_class_name == "PlaylistsPage":
            page = PlaylistsPage()
        else:
            # Create a placeholder for other pages
            page = QWidget()
            page.setStyleSheet("background-color: #09090b;")
            layout = QVBoxLayout(page)
            label = QLabel(f"Page '{page_class_name}' not implemented yet")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: #a1a1aa; font-size: 18px;")
            layout.addWidget(label)
        
        # Store the page in cache
        self.pages[page_id] = page
        self.content_stack.addWidget(page)
        
        return page
    
    def show_page(self, page_id, page_class_name):
        """
        Show a page by its ID and class name.
        
        Args:
            page_id: ID of the page
            page_class_name: Name of the page class
        """
        page = self.get_page(page_id, page_class_name)
        self.content_stack.setCurrentWidget(page)
        self.current_page = page_id


class DashboardWindow(QMainWindow):
    """
    Main dashboard window with a collapsible sidebar and content area.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music Player Dashboard")
        self.resize(1200, 800)
        
        # Set app icon
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                               "music_player", "resources", "play.png")
        app_icon = QIcon(icon_path)
        self.setWindowIcon(app_icon)
        
        # Force background color
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(palette.ColorRole.Window, QColor("#09090b"))
        self.setPalette(palette)
        
        # Setup fonts
        self.setup_fonts()
        
        # Main layout with sidebar and content area
        self.central_widget = QWidget()
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Create sidebar
        self.sidebar = SidebarWidget(self)
        self.sidebar.item_clicked.connect(self.on_sidebar_item_clicked)
        self.sidebar.toggled.connect(self.on_sidebar_toggled)
        self.sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        
        # Create content area
        self.content_widget = QWidget()
        self.content_widget.setObjectName("contentArea")
        self.content_widget.setStyleSheet("""
            #contentArea {
                background-color: #09090b !important;
            }
        """)
        self.content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        
        # Add header with breadcrumb and page title
        # Use QWidget instead of QFrame
        self.header = QWidget()
        self.header.setObjectName("contentHeader")
        self.header.setMinimumHeight(50)
        self.header.setMaximumHeight(50)
        
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(16, 0, 16, 0)
        
        # Create toggle button for sidebar
        self.toggle_btn = QPushButton()
        self.toggle_btn.setObjectName("toggleButton")
        # Use antialiasing for better icon quality
        self.toggle_btn.setIcon(qta.icon("fa5s.bars", color="#fafafa", options=[{'antialiasing': True}]))
        self.toggle_btn.setIconSize(QSize(16, 16))
        self.toggle_btn.setFixedSize(32, 32)
        self.toggle_btn.setToolTip("Toggle Sidebar")
        self.toggle_btn.clicked.connect(self.toggle_sidebar)
        self.toggle_btn.setStyleSheet("""
            #toggleButton {
                background-color: transparent;
                border: none;
            }
            #toggleButton:hover {
                background-color: #27272a;
                border-radius: 4px;
            }
        """)

        self.breadcrumb_label = QLabel("Dashboard")
        self.breadcrumb_label.setObjectName("breadcrumbLabel")
        self.breadcrumb_label.setStyleSheet("""
            #breadcrumbLabel {
                font-family: 'ICA Rubrik Black';
                font-size: 22px;
                font-weight: 900; /* Black weight */
                color: #fafafa;
            }
        """)

        # Add toggle button first, then breadcrumb
        self.header_layout.addWidget(self.toggle_btn)
        self.header_layout.addWidget(self.breadcrumb_label)
        self.header_layout.addStretch()
        
        # Content stack widget to hold different pages
        self.content_stack = QStackedWidget()
        
        # Initialize page manager
        self.page_manager = PageManager(self.content_stack)
        
        self.content_layout.addWidget(self.header)
        self.content_layout.addWidget(self.content_stack)
        
        # Add sidebar and content to main layout
        self.main_layout.addWidget(self.sidebar)
        self.main_layout.addWidget(self.content_widget)
        
        # Set central widget
        self.setCentralWidget(self.central_widget)
        
        # Apply theme
        self.apply_theme()
        
        # Show default page (Dashboard)
        self.on_sidebar_item_clicked("dashboard", "DashboardPage")
    
    def on_sidebar_item_clicked(self, item_id, page_class):
        """Handle sidebar item click."""
        print(f"Dashboard: Item clicked - {item_id}, {page_class}")
        
        # Show the selected page
        self.page_manager.show_page(item_id, page_class)
        
        # Update breadcrumb title based on page class
        if page_class == "DashboardPage":
            self.breadcrumb_label.setText("Dashboard")
        elif page_class == "PlayerPage":
            self.breadcrumb_label.setText("Audio Player")
        else:
            # Generic title from page class for other pages
            page_title = page_class.replace("Page", "")
            self.breadcrumb_label.setText(page_title)
    
    def on_sidebar_toggled(self, is_expanded):
        """Handle sidebar toggle event."""
        # Update layout as needed
        self.main_layout.update()

    def toggle_sidebar(self):
        """Toggle the sidebar through the sidebar widget."""
        self.sidebar.toggle_sidebar()

    def apply_theme(self):
        """Apply theme to the application."""
        # Don't use qt_material
        self.setStyleSheet("""
            QMainWindow {
                background-color: #09090b !important;
            }
            
            QScrollBar:vertical {
                background: #18181b !important;
                width: 6px;
                margin: 0px;
            }
            
            QScrollBar::handle:vertical {
                background: #27272a !important;
                min-height: 20px;
                border-radius: 3px;
            }
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            
            QScrollBar:horizontal {
                background: #18181b !important;
                height: 6px;
                margin: 0px;
            }
            
            QScrollBar::handle:horizontal {
                background: #27272a !important;
                min-width: 20px;
                border-radius: 3px;
            }
            
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
        """)

    def setup_fonts(self):
        """Load and apply custom fonts (Geist Sans & Mono)."""
        # Construct the absolute path to the fonts directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(script_dir, '..', '..')) # Go up two levels from ui
        font_dir = os.path.join(project_root, 'music_player', 'fonts')
        
        # Fonts to load (adjust list as needed)
        fonts_to_load = [
            "Geist-Regular.ttf", "Geist-Medium.ttf", "Geist-SemiBold.ttf", "Geist-Bold.ttf",
            "GeistMono-Regular.ttf", "GeistMono-Medium.ttf", "GeistMono-SemiBold.ttf", "GeistMono-Bold.ttf",
            "ICARubrikBlack.ttf"
        ]
        
        loaded_font_ids = []
        # Don't instantiate QFontDatabase, use static methods
        for font_file in fonts_to_load:
            font_path = os.path.join(font_dir, font_file)
            if os.path.exists(font_path):
                font_id = QFontDatabase.addApplicationFont(font_path)
                if font_id != -1:
                    loaded_font_ids.append(font_id)
                    # Check families associated with this specific loaded font ID
                    families = QFontDatabase.applicationFontFamilies(font_id)
            
        # After loading all, check the complete list of families available to the application
        available_families = QFontDatabase.families()
        
        default_font_family = "Geist"
        mono_font_family = "Geist Mono"
        header_font_family = "ICA Rubrik Black"
        
        # Check if the specific families are now available
        geist_sans_found = default_font_family in available_families
        geist_mono_found = mono_font_family in available_families
        header_font_found = header_font_family in available_families
        
        if geist_sans_found:
            app_font = QFont(default_font_family, 10)
        else:
            # Fallback logic
            app_font = QFont("Segoe UI", 10)
            if not app_font.exactMatch():
                app_font = QFont("Arial", 10)
                
        QApplication.setFont(app_font)


def create_dashboard():
    """Create and return the dashboard window."""
    dashboard = DashboardWindow()
    return dashboard 