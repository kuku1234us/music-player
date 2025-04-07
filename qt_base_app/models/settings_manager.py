"""
Settings manager module for handling application settings.

This module provides a robust and reusable settings management system that can be used
across different applications. It wraps QSettings to provide:
- Type safety and validation
- Default values
- Hierarchical settings organization
- Support for complex data types
- Settings migration capabilities
- Singleton pattern for global access
"""

from typing import Any, Dict, List, Optional, Union, TypeVar, Type
from enum import Enum
import json
from datetime import datetime
from pathlib import Path
from PyQt6.QtCore import QSettings

T = TypeVar('T')

class SettingType(Enum):
    """Enumeration of supported setting types"""
    STRING = str
    INT = int
    FLOAT = float
    BOOL = bool
    LIST = list
    DICT = dict
    DATETIME = datetime
    PATH = Path

class SettingsManager:
    """
    A singleton class to manage application settings with type safety and validation.
    
    Features:
    - Type-safe settings storage and retrieval
    - Hierarchical organization with namespaces
    - Default values
    - Complex data type support (lists, dicts, datetime, paths)
    - Settings validation
    - Automatic type conversion
    - Settings migration from legacy QSettings
    
    Example usage:
        settings = SettingsManager.instance()
        
        # Store settings
        settings.set('player/volume', 75, SettingType.INT)
        settings.set('preferences/playlists_dir', Path('/music/playlists'), SettingType.PATH)
        
        # Retrieve settings
        volume = settings.get('player/volume', 100, SettingType.INT)
        playlists_dir = settings.get('preferences/playlists_dir', Path.home(), SettingType.PATH)
    """
    
    _instance = None
    
    @classmethod
    def instance(cls) -> 'SettingsManager':
        """Get the singleton instance of SettingsManager"""
        if cls._instance is None:
            cls._instance = cls('MusicPlayer', 'App')
            cls._instance._migrate_legacy_settings()
        return cls._instance
    
    def __init__(self, organization: str, application: str):
        """
        Initialize the settings manager.
        
        Args:
            organization: Organization name
            application: Application name
        """
        if SettingsManager._instance is not None:
            raise RuntimeError("Use SettingsManager.instance() to get the settings manager")
            
        self._settings = QSettings(organization, application)
        self._type_converters = {
            SettingType.STRING: str,
            SettingType.INT: int,
            SettingType.FLOAT: float,
            SettingType.BOOL: bool,
            SettingType.LIST: self._convert_list,
            SettingType.DICT: self._convert_dict,
            SettingType.DATETIME: self._convert_datetime,
            SettingType.PATH: Path
        }
        
        # Default settings with their types
        self._defaults = {
            'player/volume': (100, SettingType.INT),
            'preferences/seek_interval': (3, SettingType.INT),
            'preferences/playlists_dir': (str(Path.home()), SettingType.PATH),
            'ui/sidebar/expanded': (True, SettingType.BOOL),
            'recent/files': ([], SettingType.LIST),
            'recent/playlists': ([], SettingType.LIST)
        }
        
        # Initialize with defaults if not set
        for key, (default_value, setting_type) in self._defaults.items():
            if not self.contains(key):
                self.set(key, default_value, setting_type)
    
    def _migrate_legacy_settings(self):
        """Migrate settings from legacy QSettings to new format"""
        # Legacy settings locations
        legacy_player = QSettings('MusicPlayer', 'Player')
        legacy_prefs = QSettings('MusicPlayer', 'Preferences')
        
        # Migration mappings (old_key, old_settings, new_key, setting_type)
        migrations = [
            # Player settings
            ('player/volume', legacy_player, 'player/volume', SettingType.INT),
            
            # Preference settings
            ('seek_interval', legacy_prefs, 'preferences/seek_interval', SettingType.INT),
            ('playlists_dir', legacy_prefs, 'preferences/playlists_dir', SettingType.PATH),
            ('sidebar_expanded', legacy_prefs, 'ui/sidebar/expanded', SettingType.BOOL)
        ]
        
        # Perform migrations
        for old_key, old_settings, new_key, setting_type in migrations:
            if old_settings.contains(old_key):
                value = old_settings.value(old_key)
                if value is not None:
                    try:
                        self.set(new_key, value, setting_type)
                        old_settings.remove(old_key)
                    except (ValueError, TypeError) as e:
                        print(f"Error migrating setting {old_key}: {e}")
        
        # Sync changes
        legacy_player.sync()
        legacy_prefs.sync()
        self.sync()

    def set_defaults(self, defaults: Dict[str, tuple]):
        """
        Set default values for settings.
        
        Args:
            defaults: Dictionary of setting keys and their (default_value, type) tuples
        """
        self._defaults.update(defaults)
        for key, (default_value, setting_type) in defaults.items():
            if not self.contains(key):
                self.set(key, default_value, setting_type)
                
    def reset_to_defaults(self):
        """Reset all settings to their default values"""
        for key, (default_value, setting_type) in self._defaults.items():
            self.set(key, default_value, setting_type)
            
    def get_setting_type(self, key: str) -> Optional[SettingType]:
        """Get the type of a setting by its key"""
        return self._defaults.get(key, (None, None))[1]

    def set(self, key: str, value: Any, setting_type: Optional[Union[SettingType, Type]] = None) -> None:
        """
        Set a setting value with optional type validation.
        
        Args:
            key: The setting key (can be hierarchical, e.g., 'app/window/size')
            value: The value to store
            setting_type: Optional type validation (SettingType enum or Python type)
        
        Raises:
            ValueError: If type validation fails
            TypeError: If the value cannot be serialized
        """
        if setting_type:
            if isinstance(setting_type, SettingType):
                converter = self._type_converters[setting_type]
            else:
                converter = setting_type
                
            try:
                value = converter(value)
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid value type for {key}. Expected {setting_type}, got {type(value)}") from e
        
        # Special handling for complex types
        if isinstance(value, (list, dict, datetime, Path)):
            value = self._serialize_value(value)
            
        # Special handling for boolean values to ensure consistent storage
        if isinstance(value, bool):
            value = 1 if value else 0
            
        self._settings.setValue(key, value)
        
    def get(self, key: str, default: Any = None, setting_type: Optional[Union[SettingType, Type]] = None) -> Any:
        """
        Get a setting value with type conversion.
        
        Args:
            key: The setting key
            default: Default value if setting doesn't exist
            setting_type: Optional type to convert the value to
            
        Returns:
            The setting value converted to the specified type, or the default value
        """
        value = self._settings.value(key, default)
        
        if value is None:
            return default
        
        # Special handling for boolean values from QSettings
        if setting_type == SettingType.BOOL or setting_type == bool:
            # QSettings sometimes stores booleans as strings, handle both cases
            if isinstance(value, str):
                # Case-insensitive comparison for string representations
                return value.lower() in ('true', '1', 'yes', 'y', 'on')
            else:
                # Otherwise, convert to bool directly
                return bool(value)
            
        if setting_type:
            if isinstance(setting_type, SettingType):
                converter = self._type_converters[setting_type]
            else:
                converter = setting_type
                
            try:
                if isinstance(value, str) and setting_type in [SettingType.LIST, SettingType.DICT, 
                                                             SettingType.DATETIME, SettingType.PATH]:
                    value = self._deserialize_value(value, setting_type)
                else:
                    value = converter(value)
            except (ValueError, TypeError) as e:
                return default
                
        return value
    
    def remove(self, key: str) -> None:
        """Remove a setting"""
        self._settings.remove(key)
    
    def clear(self) -> None:
        """Clear all settings"""
        self._settings.clear()
    
    def contains(self, key: str) -> bool:
        """Check if a setting exists"""
        return self._settings.contains(key)
    
    def all_keys(self) -> List[str]:
        """Get all setting keys"""
        return self._settings.allKeys()
    
    def begin_group(self, prefix: str) -> None:
        """Begin a settings group"""
        self._settings.beginGroup(prefix)
    
    def end_group(self) -> None:
        """End the current settings group"""
        self._settings.endGroup()
    
    def sync(self) -> None:
        """Sync settings to storage"""
        self._settings.sync()
        
    def _serialize_value(self, value: Any) -> str:
        """Serialize complex types to string"""
        if isinstance(value, (list, dict)):
            return json.dumps(value)
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, Path):
            return str(value)
        return value
        
    def _deserialize_value(self, value: str, setting_type: SettingType) -> Any:
        """Deserialize string to complex type"""
        if setting_type == SettingType.LIST:
            return json.loads(value)
        elif setting_type == SettingType.DICT:
            return json.loads(value)
        elif setting_type == SettingType.DATETIME:
            return datetime.fromisoformat(value)
        elif setting_type == SettingType.PATH:
            return Path(value)
        return value
    
    def _convert_list(self, value: Union[str, list]) -> list:
        """Convert value to list"""
        if isinstance(value, str):
            return json.loads(value)
        return list(value)
    
    def _convert_dict(self, value: Union[str, dict]) -> dict:
        """Convert value to dict"""
        if isinstance(value, str):
            return json.loads(value)
        return dict(value)
    
    def _convert_datetime(self, value: Union[str, datetime]) -> datetime:
        """Convert value to datetime"""
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value 