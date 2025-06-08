#!/usr/bin/env python3
"""
Test script to verify subtitle controls are properly displayed when videos with subtitles are loaded.
"""
import sys
import os

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt6.QtWidgets import QApplication
from music_player.ui.vlc_player.main_player import MainPlayer

def test_subtitle_display():
    """Test that subtitle controls are displayed when video with subtitles is loaded."""
    app = QApplication(sys.argv)
    
    # Create MainPlayer instance
    player = MainPlayer(persistent_mode=True)
    player.show()
    
    print("[Test] MainPlayer created with subtitle controls")
    print(f"[Test] SubtitleManager instance: {player.subtitle_manager}")
    print(f"[Test] PlayerWidget subtitle_controls: {player.player_widget.subtitle_controls}")
    
    # Check that subtitle controls exist and are properly connected
    subtitle_controls = player.player_widget.subtitle_controls
    print(f"[Test] Subtitle controls state: visible={subtitle_controls.isVisible()}")
    
    # Test SubtitleManager state
    state_info = player.subtitle_manager.get_subtitle_state_info()
    print(f"[Test] Initial SubtitleManager state: {state_info}")
    
    print("\n[Test] Load a video file with subtitles to test automatic subtitle detection.")
    print("[Test] Expected behavior:")
    print("  1. Subtitle controls should become visible")
    print("  2. First suitable subtitle track should be auto-enabled")
    print("  3. Language code should be displayed in the controls")
    
    # Keep the app running so user can test
    app.exec()

if __name__ == "__main__":
    test_subtitle_display() 