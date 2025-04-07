"""
Theme manager for Qt applications.
"""
from pathlib import Path
import yaml
from typing import Dict, Any


class ThemeManager:
    """
    Singleton class for managing application theme.
    Loads theme configuration from YAML file and provides access to theme properties.
    """
    _instance = None
    _theme_data: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ThemeManager, cls).__new__(cls)
            cls._instance._load_theme()
        return cls._instance

    @classmethod
    def instance(cls):
        """Get the singleton instance of ThemeManager."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_theme(self):
        """Load theme configuration from YAML file."""
        theme_path = Path(__file__).parent / 'theme.yaml'
        try:
            with open(theme_path, 'r', encoding='utf-8') as f:
                self._theme_data = yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading theme configuration: {e}")
            self._theme_data = {}

    def get_color(self, *path: str) -> str:
        """
        Get a color value from the theme.
        
        Args:
            *path: The path to the color in the theme configuration
                  e.g., 'background', 'primary' for colors.background.primary
        
        Returns:
            str: The color value or a default if not found
        """
        current = self._theme_data.get('colors', {})
        for key in path:
            current = current.get(key, {})
        return current if isinstance(current, str) else "#000000"

    def get_dimension(self, *path: str) -> int:
        """
        Get a dimension value from the theme.
        
        Args:
            *path: The path to the dimension in the theme configuration
                  e.g., 'sidebar', 'expanded_width' for dimensions.sidebar.expanded_width
        
        Returns:
            int: The dimension value or 0 if not found
        """
        current = self._theme_data.get('dimensions', {})
        for key in path:
            current = current.get(key, {})
        return current if isinstance(current, int) else 0

    def get_typography(self, *path: str) -> Dict[str, int]:
        """
        Get typography settings from the theme.
        
        Args:
            *path: The path to the typography settings
                  e.g., 'title' for typography.title
        
        Returns:
            Dict[str, int]: Dictionary with 'size' and 'weight' or defaults
        """
        current = self._theme_data.get('typography', {})
        for key in path:
            current = current.get(key, {})
        
        if isinstance(current, dict) and 'size' in current and 'weight' in current:
            return current
        return {'size': 14, 'weight': 400}

    def get_stylesheet(self, component: str) -> str:
        """
        Get stylesheet for a specific component.
        
        Args:
            component: The component name ('window', 'sidebar', 'card', etc.)
        
        Returns:
            str: The stylesheet for the component
        """
        if component == 'window':
            return f"""
                QMainWindow {{
                    background-color: {self.get_color('background', 'primary')};
                }}
                QScrollBar:vertical {{
                    background: {self.get_color('background', 'secondary')};
                    width: 6px;
                    margin: 0px;
                }}
                QScrollBar::handle:vertical {{
                    background: {self.get_color('background', 'tertiary')};
                    min-height: 20px;
                    border-radius: 3px;
                }}
                QScrollBar::add-line:vertical,
                QScrollBar::sub-line:vertical {{
                    height: 0px;
                }}
            """
        elif component == 'card':
            return f"""
                background-color: {self.get_color('background', 'card')};
                border: 1px solid {self.get_color('border', 'primary')};
                border-radius: {self.get_dimension('card', 'border_radius')}px;
                padding: {self.get_dimension('card', 'padding')}px;
            """
        elif component == 'sidebar':
            return f"""
                background-color: {self.get_color('background', 'sidebar')};
            """
        
        return ""  # Return empty stylesheet for unknown components 