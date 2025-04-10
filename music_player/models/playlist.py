# models/playlist.py
import json
import os
import re
from pathlib import Path
from typing import List, Optional, Dict, Any

# --- Define a location for playlists ---
# Ideally, this would use a platform-specific user data directory.
# For simplicity now, let's put it in the project structure.
# This should be configured properly later.
DEFAULT_PLAYLIST_DIR = Path(__file__).parent.parent / "resources" / "playlists"
DEFAULT_PLAYLIST_DIR.mkdir(parents=True, exist_ok=True) # Ensure directory exists

class Playlist:
    """
    Represents a single playlist, containing a name and a list of track file paths.
    """
    def __init__(self, name: str, filepath: Optional[Path] = None, tracks: Optional[List[str]] = None):
        """
        Initializes a Playlist object.

        Args:
            name (str): The name of the playlist.
            filepath (Optional[Path]): The absolute path to the playlist file on disk.
                                       If None, it's considered an unsaved playlist.
            tracks (Optional[List[str]]): An initial list of absolute track file paths.
        """
        if not name:
            raise ValueError("Playlist name cannot be empty.")
        self.name: str = name
        self.filepath: Optional[Path] = filepath
        # Use a set for quick uniqueness checks, but store as list to maintain order
        self._track_set: set[str] = set(tracks) if tracks else set()
        self.tracks: List[str] = list(tracks) if tracks else []

        # If filepath is provided but no tracks, attempt to load
        if self.filepath and self.filepath.exists() and not tracks:
            self._load()

    def add_track(self, track_path: str) -> bool:
        """
        Adds a track's absolute file path to the playlist if not already present.

        Args:
            track_path (str): The absolute path to the track file.

        Returns:
            bool: True if the track was added, False if it was already present.
        """
        if track_path not in self._track_set:
            self.tracks.append(track_path)
            self._track_set.add(track_path)
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
        try:
            self.tracks.remove(track_path)
            self._track_set.remove(track_path)
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
                    self.tracks = [str(track) for track in loaded_tracks] # Ensure strings
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

    def save(self, playlist_dir: Path = DEFAULT_PLAYLIST_DIR) -> bool:
        """
        Saves the playlist tracks to its filepath (JSON format).
        If filepath is None, generates one based on the name in the specified directory.

        Args:
            playlist_dir (Path): The directory where playlists should be saved.
                                 Defaults to DEFAULT_PLAYLIST_DIR.

        Returns:
            bool: True if saving was successful, False otherwise.
        """
        if not self.filepath:
            self.filepath = PlaylistManager.get_playlist_path(self.name, playlist_dir)

        data: Dict[str, Any] = {
            "name": self.name,
            "tracks": self.tracks
        }
        try:
            # Ensure the directory exists
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
                tracks = data.get("tracks", [])
                if not name or not isinstance(tracks, list):
                    print(f"Error: Invalid playlist format in {filepath}")
                    return None
                # Create playlist instance but pass tracks directly to avoid reload
                playlist = Playlist(name=name, filepath=filepath, tracks=[str(t) for t in tracks])
                return playlist
        except (json.JSONDecodeError, IOError, TypeError) as e:
            print(f"Error loading playlist from {filepath}: {e}")
            return None
        except Exception as e: # Catch other potential errors
             print(f"Unexpected error loading playlist from file {filepath}: {e}")
             return None

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
    def __init__(self, playlist_dir: Path = DEFAULT_PLAYLIST_DIR):
        """
        Initializes the PlaylistManager.

        Args:
            playlist_dir (Path): The directory to store and load playlist files from.
                                 Defaults to DEFAULT_PLAYLIST_DIR.
        """
        self.playlist_dir = Path(playlist_dir)
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
    def get_playlist_path(playlist_name: str, playlist_dir: Path = DEFAULT_PLAYLIST_DIR) -> Path:
        """
        Generates the expected file path for a given playlist name in the directory.

        Args:
            playlist_name (str): The name of the playlist.
            playlist_dir (Path): The directory where playlists are stored.

        Returns:
            Path: The absolute path for the playlist file (e.g., .../playlists/My Favs.json).
        """
        filename = f"{PlaylistManager._sanitize_filename(playlist_name)}.json"
        return playlist_dir / filename

    def load_playlists(self) -> List[Playlist]:
        """
        Loads all playlists (*.json) from the managed directory.

        Returns:
            List[Playlist]: A list of loaded Playlist objects.
        """
        playlists: List[Playlist] = []
        for filepath in self.playlist_dir.glob("*.json"):
            playlist = Playlist.load_from_file(filepath)
            if playlist:
                playlists.append(playlist)
        return playlists

    def save_playlist(self, playlist: Playlist) -> bool:
        """
        Saves a Playlist object to the managed directory.
        Assigns a filepath based on the name if the playlist doesn't have one.

        Args:
            playlist (Playlist): The playlist object to save.

        Returns:
            bool: True if saving was successful, False otherwise.
        """
        # Ensure the playlist gets saved within the manager's directory
        if not playlist.filepath or playlist.filepath.parent != self.playlist_dir:
             playlist.filepath = self.get_playlist_path(playlist.name, self.playlist_dir)
        return playlist.save(self.playlist_dir) # Use the instance save method

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

