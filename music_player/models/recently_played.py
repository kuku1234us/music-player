# music_player/models/recently_played.py

import json
from collections import deque
from typing import List, Dict, Optional, Union
from pathlib import Path

from qt_base_app.models.settings_manager import SettingsManager, SettingType
# Remove unused imports causing circular dependency
# from music_player.models.playlist import Playlist, PlaylistManager # Import Playlist

MAX_RECENT_ITEMS = 15 # Maximum number of items to keep
SETTINGS_KEY = 'app/recently_played' # Use a specific key in settings

class RecentlyPlayedModel:
    """
    Manages the list of recently played items (files or playlists).
    Uses SettingsManager for persistence.
    Acts as a singleton.
    """
    _instance = None

    @classmethod
    def instance(cls) -> 'RecentlyPlayedModel':
        """Get the singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if RecentlyPlayedModel._instance is not None:
            raise RuntimeError("Use RecentlyPlayedModel.instance() to get the instance")

        self.settings = SettingsManager.instance()
        # Use a deque for efficient adding/removing from ends and size limiting
        self._recently_played = deque(maxlen=MAX_RECENT_ITEMS)
        self._load()

    def _load(self):
        """Load the recently played list from settings."""
        # Retrieve as LIST, which should handle JSON deserialization if stored correctly
        data = self.settings.get(SETTINGS_KEY, [], SettingType.LIST)
        if isinstance(data, list):
            # Validate items before adding
            validated_items = [item for item in data if self._validate_item(item)]
            self._recently_played.clear()
            self._recently_played.extend(validated_items) # Add validated items
        else:
            # Handle potential data corruption or unexpected type
            print(f"[RecentlyPlayedModel] Warning: Corrupted or invalid recently played data in settings. Resetting.")
            self._recently_played.clear()
            self._save() # Save the empty list

    def _validate_item(self, item: Dict) -> bool:
        """Check if an item dictionary has the required keys and valid types."""
        if not isinstance(item, dict):
            return False
        required_keys = {'type': str, 'name': str, 'path': str}
        for key, expected_type in required_keys.items():
            if key not in item or not isinstance(item[key], expected_type):
                print(f"[RecentlyPlayedModel] Validation failed for item: {item}. Missing or invalid key: {key}")
                return False
        if item.get('type') not in ['file', 'playlist']:
            print(f"[RecentlyPlayedModel] Validation failed for item: {item}. Invalid type: {item.get('type')}")
            return False
        # Optionally, check if path exists? Might be too slow/unreliable here.
        return True

    def _save(self):
        """Save the recently played list to settings."""
        # Convert deque to a standard list for saving
        data_to_save = list(self._recently_played)
        self.settings.set(SETTINGS_KEY, data_to_save, SettingType.LIST)
        self.settings.sync() # Ensure data is written immediately

    def add_item(self, item_type: str, name: str, path: Union[str, Path]):
        """
        Add a new item to the recently played list.
        Avoids duplicates based on path and brings existing items to the front.

        Args:
            item_type: 'file' or 'playlist'.
            name: Display name (filename or playlist name).
            path: Full path to the file or playlist file (string or Path object).
        """
        if item_type not in ['file', 'playlist']:
            print(f"[RecentlyPlayedModel] Warning: Invalid item type '{item_type}' provided.")
            return

        if not name or not path:
            print(f"[RecentlyPlayedModel] Warning: Missing name or path for recently played item.")
            return

        # Ensure path is a resolved absolute path string
        resolved_path_str = str(Path(path).resolve())

        new_item = {
            'type': item_type,
            'name': name,
            'path': resolved_path_str
        }

        # Check for duplicates based on resolved path and remove if found
        found_index = -1
        for i, existing_item in enumerate(self._recently_played):
            # Compare resolved paths
            if existing_item.get('path') == resolved_path_str:
                found_index = i
                break

        if found_index != -1:
            # Item exists, remove it from its current position
            del self._recently_played[found_index]

        # Add the new/updated item to the front (left side of deque)
        self._recently_played.appendleft(new_item)

        # Save changes
        self._save()
        print(f"[RecentlyPlayedModel] Added/Updated '{name}' ({item_type}) to recently played.")

    def get_items(self) -> List[Dict]:
        """Return the list of recently played items."""
        # Return a standard list copy
        return list(self._recently_played)

    def clear(self):
        """Clear the recently played list."""
        self._recently_played.clear()
        self._save()
