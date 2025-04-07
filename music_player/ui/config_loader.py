"""
Configuration loader for dashboard components.
"""
import os
import yaml
from typing import Dict, Any, List, Optional


class ConfigLoader:
    """
    Load and parse configuration files for dashboard components.
    """
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the config loader.
        
        Args:
            config_path: Path to configuration file. If None, uses default.
        """
        self.config_path = config_path
        self.config_data = {}
        
    def load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Load configuration from YAML file.
        
        Args:
            config_path: Path to configuration file. If None, uses instance path.
            
        Returns:
            Dictionary with configuration data
        """
        path_to_use = config_path or self.config_path
        
        if not path_to_use:
            # Default to the package resources directory
            module_dir = os.path.dirname(os.path.abspath(__file__))
            resources_dir = os.path.join(os.path.dirname(module_dir), "resources")
            path_to_use = os.path.join(resources_dir, "dashboard_config.yaml")
        
        try:
            with open(path_to_use, 'r', encoding='utf-8') as file:
                self.config_data = yaml.safe_load(file)
                return self.config_data
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return {}
    
    def get_sidebar_config(self) -> Dict[str, Any]:
        """
        Get sidebar configuration.
        
        Returns:
            Dictionary with sidebar configuration
        """
        if not self.config_data:
            self.load_config()
        
        return self.config_data.get('sidebar', {})
    
    def get_sidebar_title(self) -> str:
        """Get sidebar title from config."""
        sidebar_config = self.get_sidebar_config()
        return sidebar_config.get('title', 'Dashboard')
    
    def get_sidebar_icon(self) -> str:
        """Get sidebar icon from config."""
        sidebar_config = self.get_sidebar_config()
        return sidebar_config.get('icon', 'fa5s.bars')
    
    def get_sidebar_sections(self) -> List[Dict[str, Any]]:
        """Get sidebar sections from config."""
        sidebar_config = self.get_sidebar_config()
        return sidebar_config.get('sections', [])


# Create a singleton instance for easy access
config = ConfigLoader() 