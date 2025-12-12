# models/playlist.py
import json
import os
import re
import random # Import random for shuffle
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from qt_base_app.models.settings_manager import SettingsManager, SettingType
from qt_base_app.models.logger import Logger
# Assuming enums are accessible or defined here/imported globally
# If not, define them or adjust path
from music_player.ui.vlc_player.enums import REPEAT_ONE, REPEAT_ALL, REPEAT_RANDOM
from datetime import datetime
from music_player.models.settings_defs import PREF_WORKING_DIR_KEY, DEFAULT_WORKING_DIR

# Module-level cache for working directory
_cached_working_dir: Optional[Path] = None

# --- Define a default location for the working directory ---
def get_default_working_dir() -> Path:
    global _cached_working_dir
    if _cached_working_dir is not None:
        return _cached_working_dir

    settings = SettingsManager.instance()
    logger = Logger.instance()
    
    # Get working directory from settings
    working_dir = settings.get(PREF_WORKING_DIR_KEY, None, SettingType.PATH)
    
    # Check if the working directory is valid and accessible
    if working_dir is not None:
        try:
            # Verify if the directory exists or can be created
            if not working_dir.exists():
                logger.debug("PlaylistModel", f"get_default_working_dir: Directory doesn't exist, creating: {working_dir}")
                working_dir.mkdir(parents=True, exist_ok=True)
                
            # Test if we can write to it
            test_file = working_dir / ".write_test"
            test_file.touch()
            test_file.unlink()  # Remove the test file
                
            # If we got this far, the directory is valid
            _cached_working_dir = working_dir
            return working_dir
        except Exception as e:
            logger.debug("PlaylistModel", f"get_default_working_dir: Exception when validating working dir: {e}")
            logger.warning("PlaylistModel", f"Invalid working directory from settings '{working_dir}': {e}")
            # Fall through to default
    else:
        logger.debug("PlaylistModel", f"get_default_working_dir: No working_dir in settings or value is None")
    
    # Use a reliable default location in the user's home directory
    home_music_dir = Path.home() / ".musicplayer"
    try:
        home_music_dir.mkdir(parents=True, exist_ok=True)
        # Save this as the new default
        settings.set(PREF_WORKING_DIR_KEY, home_music_dir, SettingType.PATH)
        _cached_working_dir = home_music_dir
        return home_music_dir
    except Exception as e:
        logger.debug("PlaylistModel", f"get_default_working_dir: Error creating home dir: {e}")
        logger.error("PlaylistModel", f"Error creating directory in home folder: {e}")
        # Last resort fallback - use current working directory
        cwd = Path.cwd()
        logger.debug("PlaylistModel", f"get_default_working_dir: Last resort fallback to cwd: {cwd}")
        _cached_working_dir = cwd
        return cwd

def is_valid_working_dir(path: Path) -> bool:
    """Check if a path is valid and accessible for use as a working directory."""
    if path is None:
        return False
        
    try:
        # Check if the path exists
        if not path.exists():
            try:
                # Try to create it
                path.mkdir(parents=True, exist_ok=True)
            except Exception:
                return False
                
        # Check if we have write permissions
        test_file = path / ".write_test"
        try:
            test_file.touch()
            test_file.unlink()  # Remove the test file
            return True
        except Exception:
            return False
    except Exception:
        # Any other errors (like invalid drive)
        return False

class Playlist:
    """
    Represents a single playlist, containing a name and a list of track file paths.
    Includes logic for determining next/previous track index based on repeat/shuffle modes.
    """
    def __init__(self, name: str, filepath: Optional[Path] = None, tracks: Optional[List[Union[str, Dict[str, str]]]] = None):
        """
        Initializes a Playlist object.

        Args:
            name (str): The name of the playlist.
            filepath (Optional[Path]): The absolute path to the playlist file on disk.
                                       If None, it's considered an unsaved playlist.
                                       Should be within the working directory.
            tracks (Optional[List[Union[str, Dict[str, str]]]]): An initial list of absolute track file paths or track dictionaries.
        """
        if not name:
            raise ValueError("Playlist name cannot be empty.")
        self.name: str = name
        self.filepath: Optional[Path] = filepath
        # Use a set for quick uniqueness checks on paths
        self._track_set: set[str] = set()
        # Store tracks as list of dicts: {'path': str, 'added_time': str}
        self.tracks: List[Dict[str, str]] = []
        # Initialize current index to -1 (no track selected)
        self._current_index: int = -1
        
        # Add tracking for repeat mode
        self._current_repeat_mode: str = REPEAT_ALL  # Default to REPEAT_ALL
        self._shuffled_indices: List[int] = []       # For REPEAT_RANDOM mode
        self._shuffle_index: int = -1                # Current position in shuffle list
        self._sorted_indices: List[int] = []         # For sorted REPEAT_ALL mode
        self._sorted_playback_index: int = -1        # Current position in sorted list

        # If filepath is provided but no tracks list was given, attempt to load
        if self.filepath and self.filepath.exists() and tracks is None:
            self._load()
        # If an initial tracks list was provided (potentially old format)
        elif tracks:
            self._initialize_tracks(tracks)

    def _initialize_tracks(self, initial_tracks: List[Union[str, Dict[str, str]]]):
        """Initializes the tracks list, handling potential old format."""
        self.tracks = []
        self._track_set = set()
        current_time_iso = datetime.now().isoformat()

        for item in initial_tracks:
            track_data = None
            if isinstance(item, str):
                # Old format: Convert string path to new dict format
                norm_path = os.path.normpath(item)
                if norm_path not in self._track_set:
                    track_data = {
                        'path': norm_path,
                        'added_time': current_time_iso # Use current time for migration
                    }
            elif isinstance(item, dict) and 'path' in item and 'added_time' in item:
                # New format: Validate and use
                norm_path = os.path.normpath(item['path'])
                if norm_path not in self._track_set:
                    # Basic validation of timestamp format
                    try:
                        datetime.fromisoformat(item['added_time'])
                        track_data = {'path': norm_path, 'added_time': item['added_time']}
                    except (TypeError, ValueError):
                        Logger.instance().warning("Playlist", f"Invalid timestamp format for {norm_path} in playlist {self.name}. Using current time.")
                        track_data = {'path': norm_path, 'added_time': current_time_iso}
            
            if track_data:
                 self.tracks.append(track_data)
                 self._track_set.add(track_data['path'])

    def add_track(self, track_path: str) -> bool:
        """
        Adds a track's absolute file path to the playlist if not already present.

        Args:
            track_path (str): The absolute path to the track file.

        Returns:
            bool: True if the track was added, False if it was already present.
        """
        norm_path = os.path.normpath(track_path)
        if norm_path not in self._track_set:
            # Create track data dictionary with current timestamp
            added_time_iso = datetime.now().isoformat()
            track_data = {'path': norm_path, 'added_time': added_time_iso}
            
            self.tracks.append(track_data)
            self._track_set.add(norm_path)
            
            # If we're in REPEAT_RANDOM mode, update the shuffle indices
            if self._current_repeat_mode == REPEAT_RANDOM:
                self._regenerate_shuffle_indices()
            # Invalidate sorted indices as the order might change
            self._sorted_indices = []
            self._sorted_playback_index = -1
                
            return True
        return False

    def remove_track(self, track_path: str) -> bool:
        """
        Removes a track from the playlist by its path.

        Args:
            track_path (str): The absolute path of the track to remove.

        Returns:
            bool: True if the track was found and removed, False otherwise.
        """
        norm_path = os.path.normpath(track_path)
        try:
            # Find the index of the track dictionary to remove
            index_to_remove = -1
            for i, track_data in enumerate(self.tracks):
                if track_data.get('path') == norm_path:
                    index_to_remove = i
                    break
            
            if index_to_remove != -1:
                del self.tracks[index_to_remove]
                self._track_set.remove(norm_path)
                
                # If we're in REPEAT_RANDOM mode, update the shuffle indices
                if self._current_repeat_mode == REPEAT_RANDOM:
                    self._regenerate_shuffle_indices()
                # Invalidate sorted indices as the order will change
                self._sorted_indices = []
                self._sorted_playback_index = -1
                
            return True
        except ValueError:
            return False # Track not found in list
        except KeyError:
            return False # Track not found in set (shouldn't happen if list succeeded)

    def _load(self) -> None:
        """Loads the playlist tracks from its filepath (JSON format)."""
        if not self.filepath or not self.filepath.exists():
            Logger.instance().warning("Playlist", f"Playlist file not found for loading: {self.filepath}")
            return
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data: Dict[str, Any] = json.load(f)
                loaded_name = data.get("name")
                loaded_tracks_raw = data.get("tracks", []) # Raw data
                if loaded_name != self.name:
                    Logger.instance().warning("Playlist", f"Playlist name mismatch in file '{self.filepath}'. Expected '{self.name}', found '{loaded_name}'. Using loaded name.")
                    self.name = loaded_name
                
                # Process loaded tracks, handling old/new format
                self._initialize_tracks(loaded_tracks_raw)

        except (json.JSONDecodeError, IOError, TypeError) as e:
            Logger.instance().error("Playlist", f"Error loading playlist from {self.filepath}: {e}")
            # Reset to empty state if loading fails
            self.tracks = []
            self._track_set = set()
        except Exception as e: # Catch other potential errors
             Logger.instance().error("Playlist", f"Unexpected error loading playlist {self.filepath}: {e}")
             self.tracks = []
             self._track_set = set()

    def save(self, working_dir: Optional[Path] = None) -> bool:
        """
        Saves the playlist tracks to its filepath (JSON format).
        If filepath is None, generates one based on the name in the specified working directory.

        Args:
            working_dir (Optional[Path]): The directory where playlists should be saved.
                                          If None, uses the default working directory from settings.

        Returns:
            bool: True if saving was successful, False otherwise.
        """
        if working_dir is None:
            working_dir = get_default_working_dir()

        # Determine the playlists subdirectory within the working directory
        playlist_subdir = working_dir / "playlists"
        playlist_subdir.mkdir(parents=True, exist_ok=True)

        if not self.filepath:
            self.filepath = PlaylistManager.get_playlist_path(self.name, playlist_subdir)
        # Use os.path.samefile for robust comparison, ensuring paths exist first
        elif self.filepath.parent.exists() and not os.path.samefile(str(self.filepath.parent), str(playlist_subdir)):
            # If the filepath is outside the designated playlist subdir, force it inside
            Logger.instance().warning("Playlist", f"Playlist filepath '{self.filepath}' is outside the expected directory '{playlist_subdir}'. Correcting path.")
            self.filepath = PlaylistManager.get_playlist_path(self.name, playlist_subdir)

        data: Dict[str, Any] = {
            "name": self.name,
            "tracks": self.tracks # Already normalized
        }
        try:
            # Ensure the specific directory exists (already done for playlist_subdir, but safe)
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4) # Use indent for readability
            return True
        except (IOError, TypeError) as e:
            Logger.instance().error("Playlist", f"Error saving playlist to {self.filepath}: {e}")
            return False
        except Exception as e: # Catch other potential errors
             Logger.instance().error("Playlist", f"Unexpected error saving playlist {self.filepath}: {e}")
             return False

    @staticmethod
    def load_from_file(filepath: Path) -> Optional['Playlist']:
        """
        Loads a playlist from a specific file path.

        Args:
            filepath (Path): The absolute path to the playlist file.

        Returns:
            Optional[Playlist]: The loaded Playlist object, or None if loading failed.
        """
        if not filepath.exists():
            Logger.instance().error("Playlist", f"Error: Playlist file not found: {filepath}")
            return None
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data: Dict[str, Any] = json.load(f)
                name = data.get("name")
                tracks_raw = data.get("tracks", [])
                if not name or not isinstance(tracks_raw, list):
                    Logger.instance().error("Playlist", f"Error: Invalid playlist format in {filepath}")
                    return None
                # Pass tracks_raw directly to the constructor
                playlist = Playlist(name=name, filepath=filepath, tracks=tracks_raw)
                # Initialize index after loading, but leave as -1 for potential random first track
                # This allows get_first_file() to work correctly for REPEAT_RANDOM mode
                return playlist
        except json.JSONDecodeError as je:
            Logger.instance().error("Playlist", f"Error loading playlist from {filepath}: {type(je).__name__} - {je}")
            
            # Try with different encoding as fallback
            try:
                with open(filepath, 'r', encoding='latin-1') as f:
                    data = json.load(f)
                    name = data.get("name")
                    tracks_raw = data.get("tracks", [])
                    if not name or not isinstance(tracks_raw, list):
                        Logger.instance().error("Playlist", f"Error: Invalid playlist format in {filepath} (latin-1 encoding)")
                        return None
                    # Pass tracks_raw directly to the constructor for fallback encoding
                    playlist = Playlist(name=name, filepath=filepath, tracks=tracks_raw)
                    Logger.instance().info("Playlist", f"Successfully loaded playlist with latin-1 encoding: {name}")
                    return playlist
            except Exception as alt_e:
                Logger.instance().error("Playlist", f"Failed alternative encoding attempt: {type(alt_e).__name__} - {alt_e}")
            return None
        except (IOError, TypeError) as e:
            Logger.instance().error("Playlist", f"Error loading playlist from {filepath}: {type(e).__name__} - {e}")
            return None
        except Exception as e: # Catch other potential errors
            Logger.instance().error("Playlist", f"Unexpected error loading playlist from file {filepath}: {type(e).__name__} - {e}")
            return None
            
    # --- Track Access and Navigation Logic ---

    def set_repeat_mode(self, mode: str) -> None:
        """
        Sets the repeat mode and updates internal state accordingly.
        
        Args:
            mode (str): One of REPEAT_ONE, REPEAT_ALL, or REPEAT_RANDOM
        """
        if mode not in [REPEAT_ONE, REPEAT_ALL, REPEAT_RANDOM]:
            Logger.instance().warning("Playlist", f"Invalid repeat mode '{mode}'. Using REPEAT_ALL.")
            mode = REPEAT_ALL
        
        # If changing to REPEAT_RANDOM, regenerate shuffle indices
        if mode == REPEAT_RANDOM and (self._current_repeat_mode != REPEAT_RANDOM or not self._shuffled_indices):
            self._regenerate_shuffle_indices()
        
        self._current_repeat_mode = mode
        
    def get_repeat_mode(self) -> str:
        """
        Gets the current repeat mode.
        
        Returns:
            str: The current repeat mode
        """
        return self._current_repeat_mode

    def update_sort_order(self, sorted_indices: List[int]):
        """
        Updates the internal sorted order based on the UI.

        Args:
            sorted_indices (List[int]): A list of original track indices
                                        in the order they are displayed in the UI.
        """
        if not isinstance(sorted_indices, list):
            Logger.instance().warning("Playlist", "update_sort_order received non-list.")
            return

        self._sorted_indices = sorted_indices
        Logger.instance().debug("Playlist", f"Updated sorted indices: {self._sorted_indices}")

        # Reset sorted playback index, will be updated when track selected/played
        # Or try to find current track in new order?
        if 0 <= self._current_index < len(self.tracks):
            try:
                # Find the position of the currently playing track's original index
                # within the new sorted list.
                self._sorted_playback_index = self._sorted_indices.index(self._current_index)
                Logger.instance().debug("Playlist", f"Updated sorted playback index to: {self._sorted_playback_index}")
            except ValueError:
                # Current track index not found in new sort order (shouldn't happen if list is complete)
                Logger.instance().warning("Playlist", f"Current index {self._current_index} not found in new sorted indices {self._sorted_indices}. Resetting playback index.")
                self._sorted_playback_index = 0 # Start from beginning of new sort
        else:
            self._sorted_playback_index = 0 # Default to start if no track was playing

    def _regenerate_shuffle_indices(self, after_completion=False) -> None:
        """
        Regenerates the shuffled indices to ensure all tracks are played once 
        before any track is repeated.
        
        Args:
            after_completion (bool): If True, indicates this regeneration is happening
                                    after completing a full shuffle cycle, so we should
                                    avoid repeating the current track at the beginning.
        """
        num_tracks = len(self.tracks)
        if num_tracks == 0:
            self._shuffled_indices = []
            self._shuffle_index = -1
            return
            
        # Generate a list of all indices
        indices = list(range(num_tracks))
        
        # If we already have a current index, handle special cases
        if 0 <= self._current_index < num_tracks and not after_completion:
            # Only put current track first when not regenerating after completion
            # Remove current index from list to prevent duplicates
            if self._current_index in indices:
                indices.remove(self._current_index)
            # Shuffle the remaining indices
            random.shuffle(indices)
            # Put current index first
            self._shuffled_indices = [self._current_index] + indices
        else:
            # Just shuffle all indices for a completely fresh order
            random.shuffle(indices)
            
            # If regenerating after completion and we have more than 1 track,
            # make sure the first track in the new shuffle isn't the same as the last track played
            if after_completion and num_tracks > 1 and 0 <= self._current_index < num_tracks:
                # If by chance the current/last track ended up first, swap it with another position
                if indices[0] == self._current_index:
                    # Find a position to swap with (not the first position)
                    swap_pos = random.randint(1, num_tracks - 1)
                    # Swap the first element with the randomly chosen position
                    indices[0], indices[swap_pos] = indices[swap_pos], indices[0]
                    Logger.instance().debug("Playlist", f"Prevented repeat by swapping first track in new shuffle")
            
            self._shuffled_indices = indices
            
        # Reset shuffle index to beginning
        self._shuffle_index = 0
        Logger.instance().debug("Playlist", f"Generated new shuffle order: {self._shuffled_indices}")

    def get_track_at(self, index: int) -> Optional[str]:
        """Returns the track path at the given index, or None if index is invalid."""
        if 0 <= index < len(self.tracks):
            # Ensure we return the path string from the track dictionary
            track_data = self.tracks[index]
            return track_data.get('path') if isinstance(track_data, dict) else None
        return None

    def get_first_file(self) -> Optional[str]:
        """Returns the path string of the first track and sets the internal index."""
        if not self.tracks:
            self._current_index = -1
            return None

        # --- Handle REPEAT_ALL with sorted indices first --- 
        if self._current_repeat_mode == REPEAT_ALL and self._sorted_indices:
            if len(self._sorted_indices) > 0:
                first_sorted_original_index = self._sorted_indices[0]
                # Validate the index before using it
                if 0 <= first_sorted_original_index < len(self.tracks):
                    self._current_index = first_sorted_original_index
                    self._sorted_playback_index = 0 # Start at beginning of sorted list
                    Logger.instance().debug("Playlist", f"First sorted track index: {self._current_index}")
                    track_data = self.tracks[self._current_index]
                    return track_data.get('path') if isinstance(track_data, dict) else None
                else:
                     Logger.instance().warning("Playlist", f"First sorted index {first_sorted_original_index} is invalid. Falling back.")
            # If _sorted_indices is somehow empty, fall through to default logic
        # -----------------------------------------------------

        # For REPEAT_RANDOM, use the first track in shuffle order
        if self._current_repeat_mode == REPEAT_RANDOM:
            # Force a true random shuffle by temporarily setting _current_index to -1
            # This prevents the current index from influencing the shuffle
            original_index = self._current_index
            self._current_index = -1
            
            # Regenerate shuffle indices to get a fresh random order
            if not self._shuffled_indices:
                self._regenerate_shuffle_indices()
            else:
                # Force regeneration even if we already have shuffled indices
                self._regenerate_shuffle_indices()
                
            self._shuffle_index = 0
            # Get the first random track from the shuffled indices
            self._current_index = self._shuffled_indices[0]
            Logger.instance().debug("Playlist", f"First random track index: {self._current_index}")
        else:
            self._current_index = 0
            
        # Ensure the path string is returned
        if 0 <= self._current_index < len(self.tracks):
            track_data = self.tracks[self._current_index]
            # --- DEBUG --- 
            # ------------- 
            path_to_return = track_data.get('path') if isinstance(track_data, dict) else None
            # --- MORE DEBUG ---
            # ------------------
            return path_to_return
        # --- DEBUG --- 
        Logger.instance().debug("Playlist", f"get_first_file: Index {self._current_index} out of bounds (len={len(self.tracks)}). Returning None.")
        # ------------- 
        return None # Return None if index is invalid

    def get_next_file(self) -> Optional[str]:
        """
        Calculates the path string of the next track based on the current repeat mode and updates internal index.

        Returns:
            Optional[str]: The path string of the next track, or None if playback should stop.
        """
        num_tracks = len(self.tracks)
        if num_tracks == 0:
            self._current_index = -1
            return None
            
        # If only one track, always return it
        if num_tracks == 1:
            self._current_index = 0
            return self.tracks[0].get('path')

        if self._current_repeat_mode == REPEAT_ONE:
            # Stay on the current track, just ensure index is valid
            if 0 <= self._current_index < num_tracks:
                # No change needed to self._current_index
                return self.tracks[self._current_index].get('path')
            else: # Invalid index somehow, reset to first
                self._current_index = 0
                return self.tracks[0].get('path')

        if self._current_repeat_mode == REPEAT_RANDOM:
            # Use our shuffled indices for proper random playback
            if not self._shuffled_indices:
                self._regenerate_shuffle_indices()
                
            # Increment shuffle index
            self._shuffle_index += 1
            
            # If we've reached the end of our shuffle sequence, regenerate
            if self._shuffle_index >= len(self._shuffled_indices):
                self._regenerate_shuffle_indices(after_completion=True)
                self._shuffle_index = 0
                
            # Set current index to the track at current shuffle position
            self._current_index = self._shuffled_indices[self._shuffle_index]
            # Ensure the path string is returned
            if 0 <= self._current_index < len(self.tracks):
                track_data = self.tracks[self._current_index]
                return track_data.get('path') if isinstance(track_data, dict) else None
            # Return None if index became invalid (e.g., end of list without repeat)
            elif self._current_index == -1: 
                return None
            # Fallback: Should ideally not be reached if logic above is correct
            return None 

        # --- REPEAT_ALL Mode (potentially sorted) --- 
        if self._current_repeat_mode == REPEAT_ALL and self._sorted_indices:
            # Play according to the UI-defined sort order
            self._sorted_playback_index += 1
            if self._sorted_playback_index >= len(self._sorted_indices):
                self._sorted_playback_index = 0 # Wrap around
            
            # Get the original index from the sorted list
            original_index = self._sorted_indices[self._sorted_playback_index]
            # Update the main current_index to match
            self._current_index = original_index
            
            # Return the path using the original index
            if 0 <= original_index < len(self.tracks):
                 track_data = self.tracks[original_index]
                 return track_data.get('path') if isinstance(track_data, dict) else None
            else: # Index somehow invalid
                 Logger.instance().warning("Playlist", f"Invalid original index {original_index} from sorted list.")
                 self._current_index = -1 # Reset main index
                 self._sorted_playback_index = -1 # Reset sorted index
                 return None
        
        # --- Fallback / Original REPEAT_ALL linear logic --- 
        # (Used if mode is REPEAT_ALL but _sorted_indices is empty)
        next_idx = self._current_index + 1
        if next_idx >= num_tracks: # Reached or passed the end
            # Wrap around only needed for REPEAT_ALL here (REPEAT_ONE handled above)
            self._current_index = 0 
            return self.tracks[0].get('path') if num_tracks > 0 else None
        else: # Normal advance
            self._current_index = next_idx
            return self.tracks[next_idx].get('path')

    def get_previous_file(self) -> Optional[str]:
        """
        Calculates the path string of the previous track based on the current repeat mode and updates internal index.

        Returns:
            Optional[str]: The path string of the previous track, or None if invalid.
        """
        num_tracks = len(self.tracks)
        if num_tracks == 0:
            self._current_index = -1
            return None
            
        # If only one track, always return it
        if num_tracks == 1:
            self._current_index = 0
            return self.tracks[0].get('path')

        if self._current_repeat_mode == REPEAT_RANDOM:
            # Use our shuffled indices for proper random playback
            if not self._shuffled_indices:
                self._regenerate_shuffle_indices()
                
            # Decrement shuffle index
            self._shuffle_index -= 1
            
            # If we've reached the beginning of our shuffle sequence, wrap around
            if self._shuffle_index < 0:
                self._shuffle_index = len(self._shuffled_indices) - 1
                
            # Set current index to the track at current shuffle position
            self._current_index = self._shuffled_indices[self._shuffle_index]
            # Ensure the path string is returned
            if 0 <= self._current_index < len(self.tracks):
                track_data = self.tracks[self._current_index]
                return track_data.get('path') if isinstance(track_data, dict) else None
            # Return None if index became invalid (e.g., beginning of list without wrap)
            elif self._current_index == -1: # Check if index reset
                return None
            # Fallback: Check if index remained at 0 after trying to go back
            elif self._current_index == 0 and len(self.tracks) > 0: 
                track_data = self.tracks[0]
                return track_data.get('path') if isinstance(track_data, dict) else None
            return None

        # --- REPEAT_ALL Mode (potentially sorted) --- 
        if self._current_repeat_mode == REPEAT_ALL and self._sorted_indices:
            # Play according to the UI-defined sort order (backwards)
            self._sorted_playback_index -= 1
            if self._sorted_playback_index < 0:
                self._sorted_playback_index = len(self._sorted_indices) - 1 # Wrap around to end
            
            # Get the original index from the sorted list
            original_index = self._sorted_indices[self._sorted_playback_index]
            # Update the main current_index to match
            self._current_index = original_index
            
            # Return the path using the original index
            if 0 <= original_index < len(self.tracks):
                 track_data = self.tracks[original_index]
                 return track_data.get('path') if isinstance(track_data, dict) else None
            else: # Index somehow invalid
                 Logger.instance().warning("Playlist", f"Invalid original index {original_index} from sorted list (prev).")
                 self._current_index = -1 # Reset main index
                 self._sorted_playback_index = -1 # Reset sorted index
                 return None

        # --- Fallback / Original REPEAT_ALL/REPEAT_ONE linear logic (backwards) --- 
        # (Used if mode is REPEAT_ALL but _sorted_indices is empty, or if mode is REPEAT_ONE)
        prev_idx = self._current_index - 1
        if prev_idx < 0:
             # Wrap around to the end only if REPEAT_ALL
             if self._current_repeat_mode == REPEAT_ALL: # Wrap only on REPEAT_ALL
                 self._current_index = num_tracks - 1
                 return self.tracks[self._current_index].get('path') if num_tracks > 0 else None
             else: # REPEAT_ONE: Don't wrap, stay at the first item.
                 if self._current_index == 0: 
                     return self.tracks[0].get('path') if num_tracks > 0 else None
                 else: # Landed here unexpectedly? Reset to first.
                     self._current_index = 0
                     return self.tracks[0].get('path') if num_tracks > 0 else None
        else: # Normal move backward
            self._current_index = prev_idx
            return self.tracks[prev_idx].get('path')

    def select_track_by_filepath(self, filepath: str) -> bool:
        """
        Finds the given filepath in the playlist and sets the internal index accordingly.
        Also handles updating the shuffle index if in REPEAT_RANDOM mode.

        Args:
            filepath (str): The absolute (and normalized) path of the track to select.

        Returns:
            bool: True if the track was found and index was set, False otherwise.
        """
        norm_path = os.path.normpath(filepath)
        try:
            # Find the index in the main track list by iterating through dicts
            track_index = -1
            for i, track_data in enumerate(self.tracks):
                if track_data.get('path') == norm_path:
                    track_index = i
                    break
            
            if track_index == -1:
                 raise ValueError # Path not found
                 
            self._current_index = track_index
            Logger.instance().debug("Playlist", f"Selected track index {self._current_index} for path: {norm_path}")

            # If in random mode, update the shuffle index
            if self._current_repeat_mode == REPEAT_RANDOM:
                if not self._shuffled_indices:
                    # Regenerate if shuffle isn't active, ensure current track is first
                    Logger.instance().debug("Playlist", "Regenerating shuffle indices for track selection.")
                    self._regenerate_shuffle_indices() # This now handles putting _current_index first
                    self._shuffle_index = 0 # We are at the start of the (new) shuffle sequence
                else:
                    # Find the position of the selected track_index in the shuffle list
                    try:
                        self._shuffle_index = self._shuffled_indices.index(track_index)
                        Logger.instance().debug("Playlist", f"Set shuffle index to {self._shuffle_index}")
                    except ValueError:
                        # Should not happen if _regenerate_shuffle_indices is called correctly
                        # when tracks are added/removed, but handle defensively.
                        Logger.instance().warning("Playlist", f"Track index {track_index} not found in shuffle indices {self._shuffled_indices}. Regenerating.")
                        self._regenerate_shuffle_indices()
                        try:
                           self._shuffle_index = self._shuffled_indices.index(track_index)
                        except ValueError:
                             Logger.instance().error("Playlist", f"Could not find track index {track_index} even after regenerating shuffle.")
                             self._shuffle_index = 0 # Fallback
            # If in sorted REPEAT_ALL mode, update the sorted playback index
            elif self._current_repeat_mode == REPEAT_ALL and self._sorted_indices:
                try:
                    self._sorted_playback_index = self._sorted_indices.index(track_index)
                    Logger.instance().debug("Playlist", f"Set sorted playback index to {self._sorted_playback_index}")
                except ValueError:
                    # Should not happen if update_sort_order called correctly
                    Logger.instance().warning("Playlist", f"Track index {track_index} not found in sorted indices {self._sorted_indices}. Resetting.")
                    self._sorted_playback_index = 0 # Fallback

            return True
        except ValueError:
            Logger.instance().error("Playlist", f"Track path not found in playlist: {norm_path}")
            self._current_index = -1 # Indicate no valid track selected
            return False

    # --- Standard Dunder Methods ---

    def __len__(self) -> int:
        """Returns the number of tracks in the playlist."""
        return len(self.tracks)

    def __repr__(self) -> str:
        """Returns a string representation of the playlist."""
        return f"Playlist(name='{self.name}', tracks={len(self.tracks)}, filepath='{self.filepath}')"

    def __eq__(self, other: object) -> bool:
        """Checks equality based on filepath if available, otherwise name."""
        if not isinstance(other, Playlist):
            return NotImplemented
        if self.filepath and other.filepath:
            return self.filepath == other.filepath
        # If filepaths aren't set for comparison, fall back to name (less reliable)
        return self.name == other.name and self.tracks == other.tracks

    def __hash__(self) -> int:
        """Computes hash based on filepath if available, otherwise name."""
        if self.filepath:
            return hash(self.filepath)
        # Fallback hash (less reliable)
        return hash((self.name, tuple(self.tracks)))

# --- Playlist Manager ---

class PlaylistManager:
    """
    Manages loading, saving, and discovering playlists within a specified working directory.
    """
    def __init__(self, working_dir: Optional[Path] = None):
        """
        Initialize the playlist manager.

        Args:
            working_dir (Optional[Path]): The base directory for playlist operations.
                                          If None, the default working directory will be
                                          determined lazily when needed.
        """
        # Store the provided working_dir, but don't resolve the default yet.
        self._working_dir = working_dir

    @property
    def working_dir(self) -> Path:
        """Lazily gets the working directory, resolving default if needed."""
        if self._working_dir is None:
            # Resolve the default directory only when first accessed
            self._working_dir = get_default_working_dir()
        return self._working_dir

    @property
    def playlist_dir(self) -> Path:
        """Gets the specific 'playlists' subdirectory, ensuring it exists."""
        # Use the working_dir property to ensure it's resolved
        p_dir = self.working_dir / "playlists"
        try:
             p_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
             Logger.instance().error("PlaylistManager", f"Error ensuring playlist directory exists: {p_dir} - {e}")
             # Fallback or re-raise depending on desired strictness
             # For now, return the path anyway, operations might fail later
        return p_dir

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Removes invalid characters for filenames."""
        # Remove characters not allowed in common filesystems
        sanitized = re.sub(r'[\\/*?:"<>|]', "", name)
        # Replace potential leading/trailing dots or spaces
        sanitized = sanitized.strip(". ")
        if not sanitized: # Handle case where name becomes empty
            sanitized = "untitled"
        return sanitized

    @staticmethod
    def get_playlist_path(playlist_name: str, playlist_dir: Optional[Path] = None) -> Path:
        """
        Generates the expected file path for a given playlist name in the playlist subdirectory.

        Args:
            playlist_name (str): The name of the playlist.
            playlist_dir (Optional[Path]): The specific directory for playlists.
                                           If None, uses the default determined from settings.

        Returns:
            Path: The absolute path for the playlist file (e.g., .../working_dir/playlists/My Favs.json).
        """
        if playlist_dir is None:
            # Determine default playlist dir based on working dir setting
            default_working = get_default_working_dir()
            playlist_dir = default_working / "playlists"
            playlist_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{PlaylistManager._sanitize_filename(playlist_name)}.json"
        return playlist_dir / filename

    def load_playlists(self) -> List[Playlist]:
        """
        Loads all playlists (*.json) from the managed directory.

        Returns:
            List[Playlist]: A list of loaded Playlist objects.
        """
        playlists: List[Playlist] = []
        for filename in os.listdir(self.playlist_dir):
            # === Add check to skip aiprompts.json ===
            if filename.lower() == 'aiprompts.json':
                continue # Skip this specific file
            # ==========================================
            
            # Construct the full path
            filepath = self.playlist_dir / filename
            playlist = Playlist.load_from_file(filepath)
            # Check explicitly for None instead of using boolean evaluation
            # This ensures empty playlists (0 tracks) are still considered valid
            if playlist is not None:
                playlists.append(playlist)
        
        return playlists

    def save_playlist(self, playlist: Playlist) -> bool:
        """
        Saves a Playlist object to the managed playlist directory.
        Assigns a filepath within the correct subdirectory if needed.

        Args:
            playlist (Playlist): The playlist object to save.

        Returns:
            bool: True if saving was successful, False otherwise.
        """
        # Ensure the playlist gets saved within the manager's playlist directory
        expected_path = self.get_playlist_path(playlist.name, self.playlist_dir)
        if playlist.filepath != expected_path:
             playlist.filepath = expected_path
        # Use the playlist's save method, providing the working directory (it calculates subdir)
        return playlist.save(self.working_dir)

    def delete_playlist(self, playlist: Playlist) -> bool:
        """
        Deletes the playlist file from disk.

        Args:
            playlist (Playlist): The playlist object to delete.

        Returns:
            bool: True if deletion was successful or file didn't exist, False otherwise.
        """
        if not playlist.filepath:
            Logger.instance().error("PlaylistManager", f"Cannot delete playlist '{playlist.name}' - no associated file path.")
            return False # Cannot delete if we don't know the file

        try:
            if playlist.filepath.exists():
                os.remove(playlist.filepath)
                Logger.instance().info("PlaylistManager", f"Deleted playlist file: {playlist.filepath}")
            else:
                 Logger.instance().warning("PlaylistManager", f"Playlist file not found for deletion: {playlist.filepath}")
            return True
        except OSError as e:
            Logger.instance().error("PlaylistManager", f"Error deleting playlist file {playlist.filepath}: {e}")
            return False
        except Exception as e: # Catch other potential errors
             Logger.instance().error("PlaylistManager", f"Unexpected error deleting playlist file {playlist.filepath}: {e}")
             return False
