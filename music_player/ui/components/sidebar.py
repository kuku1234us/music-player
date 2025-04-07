"""
Reusable sidebar component with collapsible animation functionality.
"""
from pathlib import Path
import yaml
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QGraphicsOpacityEffect, QFrame,
    QToolButton
)
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QSize, 
    pyqtSignal, QParallelAnimationGroup, QSettings
)
from PyQt6.QtGui import QColor, QPalette
import qtawesome as qta
from music_player.models.settings_manager import SettingsManager, SettingType


def load_sidebar_config():
    """Load sidebar configuration from YAML file."""
    config_path = Path(__file__).parent.parent.parent / 'resources' / 'dashboard_config.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config['sidebar']


class MenuItem(QPushButton):
    """
    Menu item for the sidebar.
    """
    def __init__(self, item_id, title, icon_name, parent=None):
        super().__init__(parent)
        self.item_id = item_id
        self.title = title
        self.icon_name = icon_name
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the UI for the menu item."""
        # Create a layout for the button content
        self.button_layout = QHBoxLayout(self)
        # Use 16px left margin for better appearance
        self.button_layout.setContentsMargins(16, 4, 16, 4)
        # self.button_layout.setSpacing(0)  # Further reduced spacing between icon and text
        
        # Use QToolButton for icons with increased size
        self.icon_button = QToolButton()
        self.icon_button.setFixedSize(28, 28)  # Larger fixed size
        self.icon_button.setStyleSheet("""
            QToolButton {
                background-color: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
        """)
        # Connect the icon button's click to the parent button's click
        self.icon_button.clicked.connect(self.click)
        self.update_icon("#a1a1aa")
        
        # Add text label
        self.text_label = QLabel(self.title)
        self.text_label.setStyleSheet("color: #a1a1aa; font-size: 14px;")
        
        # Add the icon and text to layout
        self.button_layout.addWidget(self.icon_button)
        self.button_layout.addWidget(self.text_label)
        self.button_layout.addStretch()
        
        # Button styling
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName(f"menuItem_{self.item_id}")
        
        # Basic styling - selected state will be set in on_item_clicked
        self.setStyleSheet("""
            background-color: #18181b;
            border: none;
            border-radius: 4px;
            height: 34px;  /* Slightly taller to accommodate larger icon */
            margin: 2px 8px;
        """)
        
    def update_icon(self, color):
        """
        Update the icon with the given color.
        
        Args:
            color (str): Color for the icon in hex format (#RRGGBB)
        """
        if hasattr(self, 'icon_name'):
            icon = qta.icon(self.icon_name, color=color, options=[{'antialiasing': True, 'scale_factor': 1.0}])
            if hasattr(self, 'icon_button'):
                self.icon_button.setIcon(icon)
                # Increase icon size to fill more of the button
                self.icon_button.setIconSize(QSize(20, 20))

    def setText(self, text):
        """Override setText to update our custom label"""
        if hasattr(self, 'text_label'):
            self.text_label.setText(text)
        else:
            super().setText(text)


class MenuSection(QWidget):
    """
    Section in the sidebar menu with a title and items.
    """
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.title = title
        self.items = []
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the UI for the menu section."""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 10, 0, 10)
        self.layout.setSpacing(0)
        
        # Set background to match sidebar
        self.setStyleSheet("background-color: #18181b;")
        
        if self.title:
            section_title = QLabel(self.title.upper())
            section_title.setObjectName("sectionTitle")
            section_title.setStyleSheet("""
                #sectionTitle {
                    color: #52525b;
                    font-size: 11px;
                    font-weight: bold;
                    padding-left: 16px;
                    margin-bottom: 5px;
                    background-color: transparent;
                }
            """)
            self.layout.addWidget(section_title)
    
    def add_item(self, item):
        """Add a menu item to the section."""
        self.items.append(item)
        self.layout.addWidget(item)


class SidebarWidget(QWidget):
    """
    Collapsible sidebar widget that can be toggled between expanded and collapsed states.
    """
    # Signal emitted when a menu item is clicked
    item_clicked = pyqtSignal(str, str)  # id, page
    # Signal emitted when sidebar is toggled
    toggled = pyqtSignal(bool)  # is_expanded
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.settings = SettingsManager.instance()
        self.expanded = self.settings.get('ui/sidebar/expanded', True, SettingType.BOOL)
        self.animation = None
        self.menu_items = {}
        
        # Set fixed width when expanded
        self.expanded_width = 200
        self.collapsed_width = 48
        self.setFixedWidth(self.expanded_width if self.expanded else self.collapsed_width)
        
        # Set object name for styling
        self.setObjectName("sidebar")
        
        # Apply the correct background color
        self.setStyleSheet("background-color: #18181b;")
        
        # Set explicit background color via palette too
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(palette.ColorRole.Window, QColor("#18181b"))
        self.setPalette(palette)
        
        # Layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Create title section
        self.setup_title()
        
        # Create scrollable area for menu items
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        self.menu_widget = QWidget()
        self.menu_widget.setStyleSheet("background-color: #18181b;")
        self.menu_layout = QVBoxLayout(self.menu_widget)
        self.menu_layout.setContentsMargins(0, 10, 0, 10)
        self.menu_layout.setSpacing(0)
        
        self.scroll_area.setWidget(self.menu_widget)
        
        # Add widgets to layout
        self.layout.addWidget(self.scroll_area)
        
        # Load menu items from configuration
        self.load_menu_items()
        
        # Apply the initial collapsed state if needed
        if not self.expanded:
            # Initialize the collapsed state without animation
            self._apply_collapsed_state()

    def setup_title(self):
        """Set up the title section of the sidebar."""
        # Get title and icon from config
        config = load_sidebar_config()
        title = config['title']
        icon_name = config['icon']
        
        self.title_header = QWidget()
        self.title_header.setObjectName("titleHeader")
        self.title_header.setMinimumHeight(50)
        self.title_header.setMaximumHeight(50)
        
        self.title_layout = QHBoxLayout(self.title_header)
        self.title_layout.setContentsMargins(10, 0, 10, 0)
        
        self.title_icon = QLabel()
        # Use antialiasing for better icon quality
        icon = qta.icon(icon_name, color="#fafafa", options=[{'antialiasing': True}])
        self.title_icon.setPixmap(icon.pixmap(24, 24))
        
        self.title = QLabel(title)
        self.title.setObjectName("titleLabel")
        self.title.setStyleSheet("""
            #titleLabel {
                color: #fafafa;
                font-size: 16px;
                font-weight: 600;
            }
        """)
        
        self.title_layout.addWidget(self.title_icon)
        self.title_layout.addWidget(self.title)
        self.title_layout.addStretch()
        
        self.layout.addWidget(self.title_header)

    def load_menu_items(self):
        """Load menu items from configuration."""
        # Clear existing items
        while self.menu_layout.count():
            item = self.menu_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Load sections and items from config
        config = load_sidebar_config()
        sections = config['sections']
        for section_data in sections:
            section = MenuSection(section_data.get('title', ''))
            
            for item_data in section_data.get('items', []):
                item_id = item_data.get('id')
                title = item_data.get('title', '')
                icon = item_data.get('icon', 'fa5s.circle')
                page = item_data.get('page', '')
                
                menu_item = MenuItem(item_id, title, icon)
                menu_item.clicked.connect(
                    (lambda item_id=item_id, page=page: 
                     lambda checked=False: self.on_item_clicked(item_id, page))()
                )
                
                section.add_item(menu_item)
                self.menu_items[item_id] = menu_item
            
            self.menu_layout.addWidget(section)
        
        # Add a stretch at the end to push all items to the top
        self.menu_layout.addStretch()
        
        # Set dashboard as initially selected
        self.set_selected_item('dashboard')

    def set_selected_item(self, item_id):
        """
        Explicitly set an item as selected without emitting the clicked signal.
        
        Args:
            item_id: ID of the item to select
        """
        if item_id in self.menu_items:
            # Set this item as selected
            selected_item = self.menu_items[item_id]
            selected_item.setStyleSheet("""
                background-color: #27272a;
                border: none;
                border-radius: 4px;
                height: 34px;
                margin: 2px 8px;
            """)
            
            if hasattr(selected_item, 'text_label'):
                selected_item.text_label.setStyleSheet("color: #ffffff; font-size: 14px;")
            
            if hasattr(selected_item, 'icon_button'):
                # Update icon to white color when selected
                selected_item.update_icon("#ffffff")
                
            # Initialize all other items to normal state
            for key, item in self.menu_items.items():
                if key != item_id:
                    item.setStyleSheet("""
                        background-color: #18181b;
                        border: none;
                        border-radius: 4px;
                        height: 34px;
                        margin: 2px 8px;
                    """)
                    
                    if hasattr(item, 'text_label'):
                        item.text_label.setStyleSheet("color: #a1a1aa; font-size: 14px;")
                    
                    if hasattr(item, 'icon_button') and hasattr(item, 'icon_name'):
                        # Ensure icon is properly set with correct color
                        item.update_icon("#a1a1aa")

    def on_item_clicked(self, item_id, page):
        """Handle menu item click."""
        print(f"Item clicked: {item_id}, {page}")
        # Update selected state for all items
        for key, item in self.menu_items.items():
            if key == item_id:
                # Selected item style - no margins, just change background color
                item.setStyleSheet("""
                    background-color: #27272a;
                    border: none;
                    border-radius: 4px;
                    height: 34px;
                    margin: 2px 8px;
                """)
                if hasattr(item, 'text_label'):
                    item.text_label.setStyleSheet("color: #ffffff; font-size: 14px;")
                # Update icon to white color when selected
                item.update_icon("#ffffff")
            else:
                # Normal item style
                item.setStyleSheet("""
                    background-color: #18181b;
                    border: none;
                    border-radius: 4px;
                    height: 34px;
                    margin: 2px 8px;
                """)
                if hasattr(item, 'text_label'):
                    item.text_label.setStyleSheet("color: #a1a1aa; font-size: 14px;")
                # Restore icon to default color
                item.update_icon("#a1a1aa")
        
        # Emit signal with item id and page
        self.item_clicked.emit(item_id, page)

    def toggle_sidebar(self):
        """Toggle the sidebar between expanded and collapsed states."""
        self.expanded = not self.expanded
        self.settings.set('ui/sidebar/expanded', self.expanded, SettingType.BOOL)
        self.settings.sync()
        
        if self.expanded:
            self._expand_sidebar()
        else:
            self._collapse_sidebar()

    def _expand_sidebar(self):
        """Expand the sidebar."""
        # Create animation group for all animations to run in parallel
        self.animation_group = QParallelAnimationGroup()
        
        # Width animations
        self.width_animation = QPropertyAnimation(self, b"minimumWidth")
        self.width_animation.setDuration(300)
        self.width_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.width_animation_max = QPropertyAnimation(self, b"maximumWidth")
        self.width_animation_max.setDuration(300)
        self.width_animation_max.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # Add width animations to group
        self.animation_group.addAnimation(self.width_animation)
        self.animation_group.addAnimation(self.width_animation_max)
        
        # Expand sidebar
        self.width_animation.setStartValue(self.collapsed_width)
        self.width_animation.setEndValue(self.expanded_width)
        self.width_animation_max.setStartValue(self.collapsed_width)
        self.width_animation_max.setEndValue(self.expanded_width)
        
        # Animate section titles
        for i in range(self.menu_layout.count()):
            item = self.menu_layout.itemAt(i)
            if item and item.widget():
                section = item.widget()
                if isinstance(section, MenuSection):
                    # Find the section title label
                    for j in range(section.layout.count()):
                        child_item = section.layout.itemAt(j)
                        if child_item and child_item.widget() and isinstance(child_item.widget(), QLabel):
                            label = child_item.widget()
                            label.setVisible(True)
                            opacity_effect = QGraphicsOpacityEffect(label)
                            opacity_effect.setOpacity(0.0)
                            label.setGraphicsEffect(opacity_effect)
                            opacity_anim = QPropertyAnimation(opacity_effect, b"opacity")
                            opacity_anim.setDuration(200)
                            opacity_anim.setStartValue(0.0)
                            opacity_anim.setEndValue(1.0)
                            self.animation_group.addAnimation(opacity_anim)
                            break
        
        # Prepare menu items for expansion
        for item_id, item in self.menu_items.items():
            if hasattr(item, 'text_label'):
                # Make text visible but with 0 opacity
                item.text_label.setVisible(True)
                opacity_effect = QGraphicsOpacityEffect(item.text_label)
                opacity_effect.setOpacity(0.0)
                item.text_label.setGraphicsEffect(opacity_effect)
                opacity_anim = QPropertyAnimation(opacity_effect, b"opacity")
                opacity_anim.setDuration(200)
                opacity_anim.setStartValue(0.0)
                opacity_anim.setEndValue(1.0)
                opacity_anim.finished.connect(lambda btn=item: self._finish_expand_item(btn))
                self.animation_group.addAnimation(opacity_anim)
            else:
                # This block is for compatibility with non-custom items
                item.setText(item.title)
                item.setToolTip("")
                item.setStyleSheet("")
        
        # Start all animations together
        self.animation_group.start()

    def _collapse_sidebar(self):
        """Collapse the sidebar."""
        # Create animation group for all animations to run in parallel
        self.animation_group = QParallelAnimationGroup()
        
        # Width animations
        self.width_animation = QPropertyAnimation(self, b"minimumWidth")
        self.width_animation.setDuration(300)
        self.width_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.width_animation_max = QPropertyAnimation(self, b"maximumWidth")
        self.width_animation_max.setDuration(300)
        self.width_animation_max.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # Add width animations to group
        self.animation_group.addAnimation(self.width_animation)
        self.animation_group.addAnimation(self.width_animation_max)
        
        # Collapse sidebar
        self.width_animation.setStartValue(self.expanded_width)
        self.width_animation.setEndValue(self.collapsed_width)
        self.width_animation_max.setStartValue(self.expanded_width)
        self.width_animation_max.setEndValue(self.collapsed_width)
        
        # Animate section titles
        for i in range(self.menu_layout.count()):
            item = self.menu_layout.itemAt(i)
            if item and item.widget():
                section = item.widget()
                if isinstance(section, MenuSection):
                    # Find the section title label
                    for j in range(section.layout.count()):
                        child_item = section.layout.itemAt(j)
                        if child_item and child_item.widget() and isinstance(child_item.widget(), QLabel):
                            label = child_item.widget()
                            # Create opacity effect for fade-out
                            opacity_effect = QGraphicsOpacityEffect(label)
                            label.setGraphicsEffect(opacity_effect)
                            opacity_anim = QPropertyAnimation(opacity_effect, b"opacity")
                            opacity_anim.setDuration(200)
                            opacity_anim.setStartValue(1.0)
                            opacity_anim.setEndValue(0.0)
                            opacity_anim.finished.connect(lambda lbl=label: lbl.setVisible(False))
                            self.animation_group.addAnimation(opacity_anim)
                            break
        
        # Animate menu items text
        for item_id, item in self.menu_items.items():
            if hasattr(item, 'text_label'):
                # Create opacity effect for text fade-out
                opacity_effect = QGraphicsOpacityEffect(item.text_label)
                item.text_label.setGraphicsEffect(opacity_effect)
                opacity_anim = QPropertyAnimation(opacity_effect, b"opacity")
                opacity_anim.setDuration(200)
                opacity_anim.setStartValue(1.0)
                opacity_anim.setEndValue(0.0)
                opacity_anim.finished.connect(lambda btn=item: self._finish_collapse_item(btn))
                self.animation_group.addAnimation(opacity_anim)
            else:
                item.setText("")
                item.setToolTip(item.title)
                item.setStyleSheet("padding-left: 8px;")
        
        # Start all animations together
        self.animation_group.start()

    def _finish_collapse_item(self, item):
        """Finish the collapse animation for a menu item."""
        if hasattr(item, 'text_label'):
            item.text_label.setVisible(False)
            item.button_layout.setContentsMargins(8, 4, 8, 4)
            item.setToolTip(item.title)
    
    def _finish_expand_item(self, item):
        """Finish the expand animation for a menu item."""
        if hasattr(item, 'text_label'):
            item.button_layout.setContentsMargins(16, 4, 16, 4)
            item.setToolTip("")

    def _apply_collapsed_state(self):
        """Apply the collapsed state without animation when initializing from settings"""
        # Set width
        self.setFixedWidth(self.collapsed_width)
        
        # Hide title
        self.title.setVisible(False)
        
        # Hide section titles
        for i in range(self.menu_layout.count()):
            item = self.menu_layout.itemAt(i)
            if item and item.widget():
                section = item.widget()
                if isinstance(section, MenuSection):
                    # Find the section title label
                    for j in range(section.layout.count()):
                        child_item = section.layout.itemAt(j)
                        if child_item and child_item.widget() and isinstance(child_item.widget(), QLabel):
                            label = child_item.widget()
                            label.setVisible(False)
                            break
        
        # Collapse menu items
        for item_id, item in self.menu_items.items():
            self._finish_collapse_item(item) 