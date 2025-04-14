# models/playlist.py
import json
import os
import re
import random # Import random for shuffle
from pathlib import Path
from typing import List, Optional, Dict, Any
from qt_base_app.models.settings_manager import SettingsManager, SettingType
# Assuming enums are accessible or defined here/imported globally
# If not, define them or adjust path
from music_player.ui.vlc_player.enums import REPEAT_ONE, REPEAT_ALL, REPEAT_RANDOM

# --- Define a default location for the working directory ---
def get_default_working_dir() -> Path:
    settings = SettingsManager.instance()
    
    # Get working directory from settings
    working_dir = settings.get('preferences/working_dir', None, SettingType.PATH)
    
    # Check if the working directory is valid and accessible
    if working_dir is not None:
        try:
            # Verify if the directory exists or can be created
            if not working_dir.exists():
                working_dir.mkdir(parents=True, exist_ok=True)
                
            # Test if we can write to it
            test_file = working_dir / ".write_test"
            test_file.touch()
            test_file.unlink()  # Remove the test file
                
            # If we got this far, the directory is valid
            return working_dir
        except Exception as e:
            print(f"Warning: Invalid working directory from settings '{working_dir}': {e}")
            # Fall through to default
    
    # Use a reliable default location in the user's home directory
    home_music_dir = Path.home() / ".musicplayer"
    try:
        home_music_dir.mkdir(parents=True, exist_ok=True)
        # Save this as the new default
        settings.set('preferences/working_dir', home_music_dir, SettingType.PATH)
        print(f"Created default working directory: {home_music_dir}")
        return home_music_dir
    except Exception as e:
        print(f"Error creating directory in home folder: {e}")
        # Last resort fallback - use current working directory
        return Path.cwd()

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
    def __init__(self, name: str, filepath: Optional[Path] = None, tracks: Optional[List[str]] = None):
        """
        Initializes a Playlist object.

        Args:
            name (str): The name of the playlist.
            filepath (Optional[Path]): The absolute path to the playlist file on disk.
                                       If None, it's considered an unsaved playlist.
                                       Should be within the working directory.
            tracks (Optional[List[str]]): An initial list of absolute track file paths.
        """
        if not name:
            raise ValueError("Playlist name cannot be empty.")
        self.name: str = name
        self.filepath: Optional[Path] = filepath
        # Use a set for quick uniqueness checks, but store as list to maintain order
        self._track_set: set[str] = set(tracks) if tracks else set()
        self.tracks: List[str] = list(tracks) if tracks else []
        self._current_index: int = -1 # Initialize current index
        
        # Add tracking for repeat mode
        self._current_repeat_mode: str = REPEAT_ALL  # Default to REPEAT_ALL
        self._shuffled_indices: List[int] = []       # For REPEAT_RANDOM mode
        self._shuffle_index: int = -1                # Current position in shuffle list

        # If filepath is provided but no tracks, attempt to load
        if self.filepath and self.filepath.exists() and not tracks:
            self._load()
            # After loading, set index to 0 if tracks exist
            if self.tracks:
                self._current_index = 0

    def add_track(self, track_path: str) -> bool:
        """
        Adds a track's absolute file path to the playlist if not already present.

        Args:
            track_path (str): The absolute path to the track file.

        Returns:
            bool: True if the track was added, False if it was already present.
        """
        # Ensure path normalization for consistency
        norm_path = os.path.normpath(track_path)
        if norm_path not in self._track_set:
            self.tracks.append(norm_path)
            self._track_set.add(norm_path)
            
            # If we're in REPEAT_RANDOM mode, update the shuffle indices
            if self._current_repeat_mode == REPEAT_RANDOM:
                self._regenerate_shuffle_indices()
                
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
            self.tracks.remove(norm_path)
            self._track_set.remove(norm_path)
            
            # If we're in REPEAT_RANDOM mode, update the shuffle indices
            if self._current_repeat_mode == REPEAT_RANDOM:
                self._regenerate_shuffle_indices()
                
            return True
        except ValueError:
            return False # Track not found in list
        except KeyError:
            return False # Track not found in set (shouldn't happen if list succeeded)

    def _load(self) -> None:
        """Loads the playlist tracks from its filepath (JSON format)."""
        if not self.filepath or not self.filepath.exists():
            print(f"Warning: Playlist file not found for loading: {self.filepath}")
            return
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data: Dict[str, Any] = json.load(f)
                # Basic validation
                loaded_name = data.get("name")
                loaded_tracks = data.get("tracks", [])
                if loaded_name != self.name:
                    print(f"Warning: Playlist name mismatch in file '{self.filepath}'. Expected '{self.name}', found '{loaded_name}'. Using loaded name.")
                    self.name = loaded_name # Update name from file if different
                if isinstance(loaded_tracks, list):
                    # Normalize paths on load
                    self.tracks = [os.path.normpath(str(track)) for track in loaded_tracks]
                    self._track_set = set(self.tracks)
                else:
                     print(f"Warning: Invalid track format in {self.filepath}. Expected a list.")
                     self.tracks = []
                     self._track_set = set()

        except (json.JSONDecodeError, IOError, TypeError) as e:
            print(f"Error loading playlist from {self.filepath}: {e}")
            # Reset to empty state if loading fails
            self.tracks = []
            self._track_set = set()
        except Exception as e: # Catch other potential errors
             print(f"Unexpected error loading playlist {self.filepath}: {e}")
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
        elif self.filepath.parent != playlist_subdir:
            # If the filepath is outside the designated playlist subdir, force it inside
            print(f"Warning: Playlist filepath '{self.filepath}' is outside the expected directory '{playlist_subdir}'. Correcting path.")
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
            print(f"Error saving playlist to {self.filepath}: {e}")
            return False
        except Exception as e: # Catch other potential errors
             print(f"Unexpected error saving playlist {self.filepath}: {e}")
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
            print(f"Error: Playlist file not found: {filepath}")
            return None
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data: Dict[str, Any] = json.load(f)
                name = data.get("name")
                tracks_raw = data.get("tracks", [])
                if not name or not isinstance(tracks_raw, list):
                    print(f"Error: Invalid playlist format in {filepath}")
                    return None
                # Normalize paths on load
                tracks = [os.path.normpath(str(t)) for t in tracks_raw]
                # Create playlist instance but pass tracks directly to avoid reload
                playlist = Playlist(name=name, filepath=filepath, tracks=tracks)
                # Initialize index after loading
                if playlist.tracks:
                    playlist._current_index = 0
                return playlist
        except json.JSONDecodeError as je:
            print(f"Error loading playlist from {filepath}: {type(je).__name__} - {je}")
            
            # Try with different encoding as fallback
            try:
                with open(filepath, 'r', encoding='latin-1') as f:
                    data = json.load(f)
                    name = data.get("name")
                    tracks_raw = data.get("tracks", [])
                    if not name or not isinstance(tracks_raw, list):
                        print(f"Error: Invalid playlist format in {filepath} (latin-1 encoding)")
                        return None
                    # Normalize paths on load
                    tracks = [os.path.normpath(str(t)) for t in tracks_raw]
                    # Create playlist instance with fallback encoding
                    playlist = Playlist(name=name, filepath=filepath, tracks=tracks)
                    # Initialize index after fallback loading
                    if playlist.tracks:
                        playlist._current_index = 0
                    print(f"Successfully loaded playlist with latin-1 encoding: {name}")
                    return playlist
            except Exception as alt_e:
                print(f"Failed alternative encoding attempt: {type(alt_e).__name__} - {alt_e}")
            return None
        except (IOError, TypeError) as e:
            print(f"Error loading playlist from {filepath}: {type(e).__name__} - {e}")
            return None
        except Exception as e: # Catch other potential errors
            print(f"Unexpected error loading playlist from file {filepath}: {type(e).__name__} - {e}")
            return None
            
    # --- Track Access and Navigation Logic ---

    def set_repeat_mode(self, mode: str) -> None:
        """
        Sets the repeat mode and updates internal state accordingly.
        
        Args:
            mode (str): One of REPEAT_ONE, REPEAT_ALL, or REPEAT_RANDOM
        """
        if mode not in [REPEAT_ONE, REPEAT_ALL, REPEAT_RANDOM]:
            print(f"Warning: Invalid repeat mode '{mode}'. Using REPEAT_ALL.")
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
                    print(f"[Playlist] Prevented repeat by swapping first track in new shuffle")
            
            self._shuffled_indices = indices
            
        # Reset shuffle index to beginning
        self._shuffle_index = 0
        print(f"[Playlist] Generated new shuffle order: {self._shuffled_indices}")

    def get_track_at(self, index: int) -> Optional[str]:
        """Returns the track path at the given index, or None if index is invalid."""
        if 0 <= index < len(self.tracks):
            return self.tracks[index]
        return None

    def get_first_file(self) -> Optional[str]:
        """Returns the first track in the playlist and sets the internal index."""
        if not self.tracks:
            self._current_index = -1
            return None
            
        # For REPEAT_RANDOM, use the first track in shuffle order
        if self._current_repeat_mode == REPEAT_RANDOM:
            if not self._shuffled_indices:
                self._regenerate_shuffle_indices()
            self._shuffle_index = 0
            self._current_index = self._shuffled_indices[0]
        else:
            self._current_index = 0
            
        return self.tracks[self._current_index]

    def get_next_file(self) -> Optional[str]:
        """
        Calculates the path of the next track based on the current repeat mode and updates internal index.

        Returns:
            Optional[str]: The path of the next track, or None if playback should stop.
        """
        num_tracks = len(self.tracks)
        if num_tracks == 0:
            self._current_index = -1
            return None
            
        # If only one track, always return it
        if num_tracks == 1:
            self._current_index = 0
            return self.tracks[0]

        if self._current_repeat_mode == REPEAT_ONE:
            # Stay on the current track, just ensure index is valid
            if 0 <= self._current_index < num_tracks:
                # No change needed to self._current_index
                return self.tracks[self._current_index]
            else: # Invalid index somehow, reset to first
                self._current_index = 0
                return self.tracks[0]

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
            return self.tracks[self._current_index]

        # --- Linear Navigation (REPEAT_ALL or stop) ---
        next_idx = self._current_index + 1

        if next_idx >= num_tracks: # Reached or passed the end
            if self._current_repeat_mode == REPEAT_ALL:
                self._current_index = 0 # Wrap around
                return self.tracks[0]
            else: # Not REPEAT_ALL (implies stop)
                # Keep index at the end? Or reset? Resetting seems safer.
                self._current_index = -1
                return None
        else: # Normal advance
            self._current_index = next_idx
            return self.tracks[next_idx]

    def get_previous_file(self) -> Optional[str]:
        """
        Calculates the path of the previous track based on the current repeat mode and updates internal index.
        REPEAT_ONE behaves linearly when going backward.

        Returns:
            Optional[str]: The path of the previous track, or None if invalid.
        """
        num_tracks = len(self.tracks)
        if num_tracks == 0:
            self._current_index = -1
            return None
            
        # If only one track, always return it
        if num_tracks == 1:
            self._current_index = 0
            return self.tracks[0]

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
            return self.tracks[self._current_index]

        # --- Linear Navigation (REPEAT_ALL, REPEAT_ONE behave same way backward) ---
        prev_idx = self._current_index - 1

        if prev_idx < 0:
             # Wrap around to the end only if REPEAT_ALL
             if self._current_repeat_mode == REPEAT_ALL: # Wrap only on REPEAT_ALL
                 self._current_index = num_tracks - 1
                 return self.tracks[self._current_index]
             else: # REPEAT_ONE or default stop: Don't wrap, effectively stay at 0 or first item?
                  # Let's stay at the first item (index 0) if going back from it.
                  if self._current_index == 0: # If already at first, stay there
                      # No change to self._current_index
                      return self.tracks[0]
                  else: # Landed here unexpectedly? Reset to first.
                      self._current_index = 0
                      return self.tracks[0]
        else: # Normal move backward
            self._current_index = prev_idx
            return self.tracks[prev_idx]

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
    Manages the loading, saving, and deletion of Playlist objects from disk.
    """
    def __init__(self, working_dir: Optional[Path] = None):
        """
        Initializes the PlaylistManager.

        Args:
            working_dir (Optional[Path]): The application's working directory.
                                          If None, uses the default from settings.
        """
        if working_dir is None:
            working_dir = get_default_working_dir()
        self.working_dir = working_dir
        # Playlists are stored in a subdirectory
        self.playlist_dir = self.working_dir / "playlists"
        self.playlist_dir.mkdir(parents=True, exist_ok=True) # Ensure it exists

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
        found_files = list(self.playlist_dir.glob("*.json"))
        
        for filepath in found_files:
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
            print(f"Cannot delete playlist '{playlist.name}' - no associated file path.")
            return False # Cannot delete if we don't know the file

        try:
            if playlist.filepath.exists():
                os.remove(playlist.filepath)
                print(f"Deleted playlist file: {playlist.filepath}")
            else:
                 print(f"Playlist file not found for deletion: {playlist.filepath}")
            return True
        except OSError as e:
            print(f"Error deleting playlist file {playlist.filepath}: {e}")
            return False
        except Exception as e: # Catch other potential errors
             print(f"Unexpected error deleting playlist file {playlist.filepath}: {e}")
             return False

