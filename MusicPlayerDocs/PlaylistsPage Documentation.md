# Playlists Page Documentation

## 1. Introduction

This document outlines the design and implementation plan for the `PlaylistsPage` within the Music Player application. The goal of this page is to provide users with a comprehensive interface for creating, managing, viewing, and playing music playlists.

## 2. Core Concepts

*   **Modes:** The page operates in two distinct modes:
    *   **Dashboard Mode:** Provides an overview of all existing playlists, allowing users to add, delete, or select a playlist to view/play.
    *   **Play Mode:** Displays the contents of a single, selected playlist. Allows editing of the playlist and serves as the source for playback initiated from this page.
*   **Current Playing Playlist:** A globally accessible reference (likely managed by the `MusicPlayerDashboard` or a dedicated service) to the `Playlist` object that is currently loaded for playback. This is updated when a playlist is opened in "Play Mode" and potentially cleared or changed when a single file is opened elsewhere (e.g., from `PlayerPage`).
*   **Selection Pool:** A temporary holding area within the "Play Mode" view. It contains a list of tracks (file paths) that can be easily added to the currently viewed playlist. Tracks in the pool are unique.

## 3. UI Structure and Layout

The `PlaylistsPage` widget will contain a `QStackedWidget` to manage switching between the two modes.

### 3.1 Dashboard Mode Layout

*   **View Container:** A `QWidget` subclass (`PlaylistDashboardWidget`).
*   **Layout:** Likely a `QVBoxLayout`.
*   **Components:**
    *   **Playlist List (`PlaylistListView`):** A `QListWidget` (or custom view) displaying the names of all saved playlists.
    *   **Action Buttons:** Buttons for "Add New Playlist" and "Delete Selected Playlist".

### 3.2 Play Mode Layout

*   **View Container:** A `QWidget` subclass (`PlaylistEditWidget`).
*   **Layout:** Likely a `QVBoxLayout` containing:
    *   **Top Section:** A `QHBoxLayout` containing:
        *   A "Back" button (to return to Dashboard Mode).
        *   A `QLabel` displaying the current playlist's name.
        *   Stretch/Spacer.
    *   **Main Content Area:** A `QSplitter` (horizontal) dividing the space between:
        *   **Left Pane (Playlist Tracks):** A `TrackListView` component displaying the tracks currently in the playlist. Allows reordering (optional) and deletion.
        *   **Right Pane (Selection Pool):** A `SelectionPoolWidget` containing:
            *   An "Add Selected to Playlist" button (`+`).
            *   A `TrackListView` displaying tracks in the selection pool. Allows multi-selection. May include inline "+" buttons per track.

## 4. Components Breakdown

*   **`PlaylistsPage` (Main Widget):**
    *   Owns the `QStackedWidget`.
    *   Owns instances of `PlaylistDashboardWidget` and `PlaylistEditWidget`.
    *   Manages switching between modes (`_enter_dashboard_mode`, `_enter_play_mode`).
    *   Communicates with the `PlaylistManager` (or equivalent) to load/save/delete playlists.
    *   Updates the global "Current Playing Playlist" state when entering Play Mode.
    *   Handles Drag and Drop events for the entire page (delegating to the Selection Pool if in Play Mode).

*   **`PlaylistDashboardWidget`:**
    *   Contains the `PlaylistListView` and action buttons.
    *   Emits signals when "Add", "Delete" are clicked, or when a playlist is selected/double-clicked in the list view.

*   **`PlaylistListView` (`QListWidget` or Custom):**
    *   Displays playlist names.
    *   Handles single selection for deletion.
    *   Handles double-click or Enter key press to trigger opening a playlist.

*   **`PlaylistEditWidget`:**
    *   Container for the Play Mode UI.
    *   Displays the playlist title.
    *   Owns the `QSplitter`, `TrackListView` (for playlist), and `SelectionPoolWidget`.
    *   Connects signals/slots between the playlist view, selection pool, and underlying playlist data.
    *   Handles the "Back" button action.

*   **`TrackListView` (`QListWidget` or Custom):**
    *   Displays track information (e.g., title, maybe artist/duration fetched later). Needs to store the full file path associated with each item.
    *   Supports single and multi-selection (`QAbstractItemView.ExtendedSelection`).
    *   Handles deletion of items (for the playlist view).
    *   Optionally supports drag-and-drop reordering within the playlist view.
    *   May display an inline "+" button for each item when used in the Selection Pool.

*   **`SelectionPoolWidget`:**
    *   Contains the "Add Selected" button and the `TrackListView` for the pool.
    *   Manages the internal list of unique track file paths in the pool.
    *   Provides methods to add tracks/folders (`add_paths_to_pool`), ensuring uniqueness.
    *   Handles Drag and Drop events specifically for adding items to the pool.
    *   Emits a signal when "Add Selected" is clicked, passing the list of selected file paths.
    *   Connects to the playlist's track deletion signal to add deleted tracks back to the pool.

## 5. State Management

*   **Mode Switching:** `PlaylistsPage` will have an internal state variable (e.g., `self._mode`) and use `self.stacked_widget.setCurrentWidget()` to change the visible view.
*   **Current Playlist (in Play Mode):** `PlaylistEditWidget` will hold a reference to the currently loaded `Playlist` object for display and modification.
*   **Current Playing Playlist (Global):**
    *   When `_enter_play_mode` is called, `PlaylistsPage` needs to update a central state manager or emit a signal indicating the new playlist to be used for playback. The `MainPlayer` should listen for this change.
    *   When the user initiates playback elsewhere (e.g., "Open File" in `PlayerPage`), the central state manager should clear the "Current Playing Playlist" or update it accordingly.
*   **Selection Pool State:** `SelectionPoolWidget` maintains its own list of file paths. This state is transient and might be cleared when switching playlists or modes, or persisted across sessions (TBD). For simplicity, let's assume it's cleared when leaving Play Mode initially.

## 6. Workflow and Interaction

*   **Viewing Playlists:** User navigates to `PlaylistsPage`, sees Dashboard Mode by default. `PlaylistListView` is populated.
*   **Adding Playlist:** User clicks "Add", a dialog prompts for a name, a new empty `Playlist` object is created and saved (via `PlaylistManager`), list view updates.
*   **Deleting Playlist:** User selects a playlist, clicks "Delete", confirmation dialog, playlist is deleted (via `PlaylistManager`), list view updates.
*   **Opening Playlist:** User double-clicks a playlist item.
    1.  `PlaylistsPage` calls `_enter_play_mode(playlist_object)`.
    2.  Switches `QStackedWidget` to `PlaylistEditWidget`.
    3.  Loads playlist tracks into the playlist's `TrackListView`.
    4.  Updates the playlist title label.
    5.  Updates the global "Current Playing Playlist" reference.
    6.  Signals `MainPlayer` to start playing the first track of this playlist.
    7.  Clears the `SelectionPoolWidget`.
*   **Adding to Selection Pool (DND Files):** User drags media files onto `SelectionPoolWidget`.
    1.  `SelectionPoolWidget` accepts the drop event.
    2.  Extracts file paths from the event's MIME data.
    3.  Calls `add_paths_to_pool` for each valid media file path.
*   **Adding to Selection Pool (DND Folders):** User drags folders onto `SelectionPoolWidget`.
    1.  `SelectionPoolWidget` accepts the drop event.
    2.  Extracts folder paths.
    3.  Recursively scans each folder for valid media files.
    4.  Calls `add_paths_to_pool` for each found media file path.
*   **Adding to Selection Pool (From Other Playlist):** (Requires UI element, e.g., a button "Import from Playlist...") User selects another playlist, its tracks are added via `add_paths_to_pool`.
*   **Adding to Selection Pool (From Deletion):** User selects track(s) in the playlist's `TrackListView` and triggers deletion.
    1.  `PlaylistEditWidget` handles the deletion action.
    2.  Calls `playlist_object.remove_track(track_path)`.
    3.  Calls `selection_pool_widget.add_paths_to_pool([track_path])`.
    4.  Updates the playlist's `TrackListView`.
*   **Adding Track from Pool to Playlist:**
    *   **Single:** User clicks inline "+" on a track in the pool's `TrackListView`. `SelectionPoolWidget` emits signal with the single track path.
    *   **Multiple:** User selects multiple tracks in the pool's `TrackListView`, clicks the main "Add Selected" button. `SelectionPoolWidget` emits signal with the list of selected track paths.
    *   `PlaylistEditWidget` receives the signal, calls `playlist_object.add_track(path)` for each path, updates the playlist's `TrackListView`.

## 7. Data Model (`playlist.py`)

A new file `./music_player/models/playlist.py` defines the core data structures for managing playlists. It contains the `Playlist` class to represent individual playlists and a `PlaylistManager` class to handle interactions with the filesystem.

### 7.1 `Playlist` Class

**Purpose:** Represents a single, ordered collection of music tracks.

**Key Attributes:**

*   `name (str)`: The user-defined name of the playlist.
*   `filepath (Optional[Path])`: The absolute path to the `.json` file where this playlist is stored on disk. If `None`, the playlist is considered new or unsaved.
*   `tracks (List[str])`: An ordered list containing the absolute file paths of the tracks included in the playlist.
*   `_track_set (set[str])`: An internal set containing the same track paths as `tracks`. This is used purely for performance optimization, allowing for quick O(1) checks for track existence (uniqueness) when adding new tracks, rather than iterating through the `tracks` list (O(n)).

**Key Methods:**

*   `__init__(self, name, filepath=None, tracks=None)`: Constructor. Initializes the name and track list. If a valid `filepath` is provided and no initial `tracks` are given, it attempts to automatically load the playlist content from the file by calling `_load()`.
*   `add_track(self, track_path)`: Adds a given track file path to the end of the `tracks` list and `_track_set`. It first checks for existence in the `_track_set` to ensure track uniqueness within the playlist. Returns `True` if the track was added, `False` otherwise.
*   `remove_track(self, track_path)`: Removes a track path from both the `tracks` list and the `_track_set`. Returns `True` if successful, `False` if the track wasn't found.
*   `_load(self)`: Private helper method to load playlist data (name and track list) from the JSON file specified by `self.filepath`. Includes error handling for file not found, JSON decoding errors, and basic format validation. It updates the instance's `name` if the file contains a different name.
*   `save(self, playlist_dir=DEFAULT_PLAYLIST_DIR)`: Saves the playlist's current state (name and track list) to a JSON file. If `self.filepath` is not set (i.e., it's a new playlist), it determines the correct path using `PlaylistManager.get_playlist_path()` within the specified `playlist_dir`. It ensures the target directory exists and handles potential I/O errors.
*   `load_from_file(filepath)` (staticmethod): A factory method that takes a file path, reads the JSON data, validates it, and returns a new `Playlist` instance. Returns `None` if loading fails.
*   `__len__(self)`: Returns the number of tracks.
*   `__repr__(self)`: Provides a developer-friendly string representation.
*   `__eq__(self, other)`, `__hash__(self)`: Define equality and hashing based primarily on the `filepath` for reliable use in collections when playlists are associated with files. Falls back to name and track content if filepaths are not available.

**Design Choices:**

*   Uses JSON for storing playlist data due to its human-readability and ease of parsing in Python.
*   Maintains both a `list` (for order) and a `set` (for uniqueness check performance) of tracks.
*   Separates the logic for loading a playlist from a file (`load_from_file`) from the instance initialization (`__init__`).

### 7.2 `PlaylistManager` Class

**Purpose:** Acts as a service to discover, load, save, and delete `Playlist` objects from a designated directory on the filesystem.

**Key Attributes:**

*   `playlist_dir (Path)`: The directory managed by this instance, where playlist `.json` files are stored.

**Key Methods:**

*   `__init__(self, playlist_dir=DEFAULT_PLAYLIST_DIR)`: Constructor. Sets the target directory and ensures it exists.
*   `_sanitize_filename(name)` (staticmethod): A private helper to remove characters from a playlist name that are invalid in filenames across different operating systems.
*   `get_playlist_path(playlist_name, playlist_dir=DEFAULT_PLAYLIST_DIR)` (staticmethod): Generates the full, absolute path for a playlist file given its name and the target directory, incorporating filename sanitization.
*   `load_playlists(self)`: Scans the `playlist_dir` for `.json` files, attempts to load each one using `Playlist.load_from_file`, and returns a list of successfully loaded `Playlist` objects.
*   `save_playlist(self, playlist)`: Saves a given `Playlist` object. It ensures the playlist's `filepath` attribute points within the manager's `playlist_dir`, generating the path if necessary, before calling the `playlist.save()` method.
*   `delete_playlist(self, playlist)`: Deletes the associated `.json` file for the given `Playlist` object from the filesystem. Checks if the `filepath` attribute exists and handles potential file system errors.

**Design Choices:**

*   Centralizes filesystem interactions related to playlists.
*   Provides utility methods for generating consistent file paths and sanitizing names.
*   Decouples the `Playlist` object itself from the knowledge of *where* all playlists are stored system-wide; the `Playlist` only knows its *own* path once saved.

## 8. Future Enhancements (Optional)

*   Track reordering via Drag and Drop within the playlist view.
*   Inline editing of playlist names in Dashboard Mode.
*   Search/filtering within playlist view and selection pool.
*   Fetching and displaying more track metadata (duration, artist) in the lists.
*   Saving/Loading Selection Pool state.
*   Importing/Exporting different playlist formats.
