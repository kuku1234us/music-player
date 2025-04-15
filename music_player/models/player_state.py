"""
Shared state module for the Music Player application.
Stores global references and state that needs to be accessed by multiple components.
"""
from typing import Optional, List, Callable
from music_player.models.playlist import Playlist

# Global variable to store the current playlist being played
current_playing_playlist: Optional[Playlist] = None

# Callbacks for track selection (Not used for playback request anymore)
_track_selected_callbacks: List[Callable[[str], None]] = []

# Callbacks for track play requests - REMOVED
# _track_play_requested_callbacks: List[Callable[[int], None]] = []

def set_current_playlist(playlist: Optional[Playlist]) -> None:
    """Set the current global playlist reference"""
    global current_playing_playlist
    current_playing_playlist = playlist

def get_current_playlist() -> Optional[Playlist]:
    """Get the current global playlist reference"""
    global current_playing_playlist
    return current_playing_playlist

def select_track(filepath: str) -> None:
    """
    // ... existing code ...
        except Exception as e:
            print(f"[PlayerState] Error in track selection callback: {e}")

# --- Track Play Request Mechanism - REMOVED --- 
# def register_track_play_requested_callback(callback: Callable[[int], None]) -> None:
#     """
#     Register a callback to be called when a track play is requested.
#     
#     Args:
#         callback: Function that takes a track_index parameter
#     """
#     if callback not in _track_play_requested_callbacks:
#         _track_play_requested_callbacks.append(callback)
# 
# def unregister_track_play_requested_callback(callback: Callable[[int], None]) -> None:
#     """Remove a callback from the track play request notification list."""
#     if callback in _track_play_requested_callbacks:
#         _track_play_requested_callbacks.remove(callback)

# --- Track Play Request Function - REMOVED ---
# def request_play_track(track_index: int) -> None:
#     """
#     Request to play a track from the current playlist at the specified index.
#     
#     Args:
#         track_index (int): The index of the track to play in the current playlist
#     """
#     global current_playing_playlist
#     
#     # First, validate that we have a playlist and the index is valid
#     if current_playing_playlist is None:
#         print("[PlayerState] Error: No playlist is currently set")
#         return
#         
#     if track_index < 0 or track_index >= len(current_playing_playlist.tracks):
#         print(f"[PlayerState] Error: Track index {track_index} is out of range")
#         return
#     
#     # Get the filepath for logging purposes
#     filepath = current_playing_playlist.tracks[track_index]
#     print(f"[PlayerState] Requesting to play track at index {track_index}: {filepath}")
#     
#     # Notify all registered callbacks
#     for callback in _track_play_requested_callbacks:
#         try:
#             callback(track_index)
#         except Exception as e:
#             print(f"[PlayerState] Error in track play requested callback: {e}") 