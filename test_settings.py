#!/usr/bin/env python
"""
Test script to check sidebar settings.
"""
import sys
import os

# Add the project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qt_base_app.models.settings_manager import SettingsManager, SettingType

def main():
    """Test settings manager."""
    settings = SettingsManager.instance()
    
    # Print settings file location
    print(f"Settings file location: {settings._settings.fileName()}")
    
    # Check if the sidebar setting exists
    raw_value = settings._settings.value('ui/sidebar/expanded')
    print(f"Raw value from QSettings: {raw_value} (type: {type(raw_value)})")
    
    sidebar_expanded = settings.get('ui/sidebar/expanded', None, SettingType.BOOL)
    print(f"Processed value from settings manager: {sidebar_expanded}")
    
    # Toggle the sidebar setting
    new_value = not bool(sidebar_expanded) if sidebar_expanded is not None else True
    print(f"Setting sidebar expanded to: {new_value}")
    settings.set('ui/sidebar/expanded', new_value, SettingType.BOOL)
    settings.sync()
    
    # Verify the change
    raw_value = settings._settings.value('ui/sidebar/expanded')
    print(f"Raw value after change: {raw_value} (type: {type(raw_value)})")
    
    sidebar_expanded = settings.get('ui/sidebar/expanded', None, SettingType.BOOL)
    print(f"Processed value after change: {sidebar_expanded}")

if __name__ == "__main__":
    main() 