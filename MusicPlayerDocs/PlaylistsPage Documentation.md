# Playlists Page Documentation

## 1. Introduction

This document outlines the design and implementation of the `PlaylistsPage` within the Music Player application. The goal of this page is to provide users with an interface for creating, managing, viewing, and potentially playing music playlists.

Currently, the page primarily features a **Dashboard Mode** for managing the list of playlists. A **Play Mode** for viewing and editing individual playlist contents, including a **Selection Pool** feature, is planned as described below.

## 2. Core Concepts

*   **Modes:** The page is designed to operate in two distinct modes:
    *   **Dashboard Mode (Implemented):** Provides an overview of all existing playlists located in the configured working directory. Allows users to create, import, rename, delete, or select a playlist. Selecting a playlist transitions the view to Play Mode.
    *   **Play Mode (Partially Implemented - Layout and Basic Functionality):** Displays the contents (tracks) of a single, selected playlist. It allows users to manage the tracks within that playlist and interact with a temporary "Selection Pool" to stage tracks before adding them.
*   **Current Playing Playlist (Global Reference - Implemented):** When a playlist is selected in Dashboard Mode and the application enters Play Mode, a global variable (`current_playing_playlist` in `playlists_page.py`) is updated to hold a reference to the selected `Playlist` object. This allows other components, like the main player, to access the currently active playlist for playback. The `playlist_selected_for_playback` signal is also emitted. Playback itself starts immediately upon entering Play Mode.
*   **Selection Pool (Planned Functionality within Play Mode):** A key feature of the Play Mode. The Selection Pool acts as a temporary staging area or clipboard for track file paths. Users can populate this pool by dragging files/folders from their operating system, using a "Browse" button to select a folder, or by removing tracks from the currently viewed playlist. Tracks from the pool can then be added back into the current playlist. This facilitates easier playlist editing and track management.

## 3. UI Structure and Layout

The `PlaylistsPage` widget contains a `QStackedWidget` to manage switching between the different views (Dashboard and Play Mode).

### 3.1 Dashboard Mode Layout (Implemented)

*   **View Container:** A `QWidget` subclass (`PlaylistDashboardWidget`).
*   **Layout:** A `QVBoxLayout` containing:
    *   **Playlist List (`PlaylistListView`):** A `QListWidget` displaying the names of all saved playlists found in the configured directory (`<Working Directory>/playlists/`).
    *   **Empty Message (`QLabel`):** Shown when no playlists are found.
    *   **Floating Add Button (`RoundButton`):** A '+' button positioned at the bottom center to trigger new playlist creation.

### 3.2 Play Mode Layout (Implemented for Breadcrumb and List; Selection Pool Planned)

*   **View Container:** A `QWidget` subclass (`PlaylistPlaymodeWidget`).
*   **Layout:** Currently uses absolute positioning for the breadcrumb and content area.
    *   **Breadcrumb Container (`QWidget`):** Positioned at the top (0, 0).
        *   **Layout:** `QHBoxLayout`.
        *   **Back Button (`QPushButton`):** '<' button to return to Dashboard Mode.
        *   **Playlist Name (`QLabel`):** Displays the name of the current playlist.
    *   **Content Container (`QWidget`):** Positioned below the breadcrumb.
        *   **Layout:** `QVBoxLayout` containing:
            *   **Playlist Tracks (`QListWidget`):** Displays the filenames of tracks currently in the loaded playlist. *(Scrollable by default)*.
            *   **Empty Message (`QLabel`):** Shown when the playlist has no tracks.
            *   **(Planned): Selection Pool Area:**
                *   **Header/Title (`QLabel`, `QHBoxLayout`):** Likely a label "Selection Pool" and potentially action buttons (like the planned "Browse" button).
                *   **Selection Pool List (`SelectionPoolWidget`):** A distinct area (likely another `QListWidget` or similar) below the header, displaying the filenames staged in the pool.

## 4. Components Breakdown

*   **`PlaylistsPage` (Main Widget - Implemented):**
    *   Owns the `QStackedWidget`.
    *   Owns instances of `PlaylistDashboardWidget` and `PlaylistPlaymodeWidget`.
    *   Manages switching between Dashboard and Play Modes (`_enter_dashboard_mode`, `_enter_play_mode`).
    *   Communicates with `PlaylistManager` for playlist operations.
    *   Updates the global `current_playing_playlist` variable.
    *   Emits `playlist_selected_for_playback` signal.
    *   **(Planned):** Will need to handle Drag and Drop events (specifically `dragEnterEvent`, `dragMoveEvent`, `dropEvent`) when in Play Mode to accept files/folders dropped onto the page, adding relevant tracks to the `SelectionPoolWidget`.

*   **`PlaylistDashboardWidget` (Implemented):**
    *   Contains the `PlaylistListView`, empty message label, and the floating Add button.
    *   Emits signals for user actions (create, import, select).
    *   **(Planned):** Needs UI (e.g., context menu) to trigger edit/rename/delete signals.

*   **`PlaylistListView` (`QListWidget` subclass - Implemented):**
    *   Displays playlist names in Dashboard Mode.
    *   Stores the `Playlist` object with each item.
    *   Handles double-click to trigger entering Play Mode.
    *   **(Planned):** Needs context menus for edit/rename/delete actions.

*   **`PlaylistPlaymodeWidget` (Implemented for Breadcrumb and Track List):**
    *   Container for the Play Mode UI.
    *   Displays the breadcrumb (Back button, Playlist name).
    *   Contains the `QListWidget` (`tracks_list`) to display tracks of the loaded playlist.
    *   Loads playlist data via `load_playlist` method.
    *   Emits `back_requested` signal.
    *   **(Planned):** Will contain the `SelectionPoolWidget` and its associated header/buttons (including "Browse"). Will need methods to interact with the pool (add tracks, get selected tracks from pool) and to handle actions like removing tracks from its `tracks_list` (which should add them to the pool). Will likely trigger the folder browsing action when the "Browse" button is clicked.

*   **`SelectionPoolWidget` (Planned / Not Implemented - File `selection_pool.py` created):**
    *   Planned component for managing and displaying the track selection pool in Play Mode.
    *   Likely a `QListWidget` or custom view, placed below a header containing its title and action buttons (like "Browse").
    *   Needs methods to add tracks (individually or list), remove tracks, get selected tracks, and clear the pool.
    *   Will need to handle user interaction for selecting items to be added back to the main playlist.

*   **`TrackListView` (`QListWidget` or Custom - Name used conceptually, current implementation uses plain `QListWidget` in `PlaylistPlaymodeWidget`):**
    *   Component for displaying tracks within the playlist in Play Mode.
    *   **(Planned):** Needs context menus or buttons to allow track removal (which adds to Selection Pool) and potentially reordering via DND within the list itself.

## 5. State Management

*   **Mode Switching (Implemented):** `PlaylistsPage` uses `self.stacked_widget.setCurrentWidget()`.
*   **Current Playlist (in Play Mode - Implemented):** `PlaylistsPage` stores `_current_playlist_in_edit`, and `PlaylistPlaymodeWidget` stores `current_playlist`.
*   **Current Playing Playlist (Global - Implemented):** The global variable `current_playing_playlist` in `playlists_page.py` holds the reference for playback. Updated when entering Play Mode. Accessible via `PlaylistsPage.get_current_playing_playlist()`.
*   **Selection Pool State (Planned / Not Implemented):** This state (list of track file paths) will likely be managed within the `SelectionPoolWidget` itself, or potentially held in the parent `PlaylistPlaymodeWidget` or even `PlaylistsPage` if complex interactions are needed.

## 6. Workflow and Interaction

*   **Viewing Playlists (Implemented):** Navigate to `PlaylistsPage` -> Dashboard Mode -> `PlaylistManager` loads -> List populated.
*   **Adding Playlist (Implemented):** Click '+' -> Prompt -> Save via `PlaylistManager` -> Refresh list.
*   **Importing Playlist (Implemented for JSON copy/other copy):** Trigger import -> File Dialog -> Overwrite check -> `Playlist.load_from_file` for JSON / Simple copy for others -> Save via `PlaylistManager` -> Refresh list.
*   **Renaming Playlist (Implemented Logic, No UI Trigger):** Needs context menu. Logic: Prompt -> Check conflict -> Rename file -> Update `Playlist` object -> Save -> Refresh list.
*   **Deleting Playlist (Implemented Logic, No UI Trigger):** Needs context menu. Logic: Confirm -> `PlaylistManager.delete_playlist` -> Refresh list.
*   **Opening Playlist (Implemented):** Double-click item -> `_enter_play_mode` called -> Global playlist ref updated -> `PlaylistPlaymodeWidget` loaded -> `playlist_selected_for_playback` emitted -> `MainPlayer` (or other listener) should start playback. View switches to `PlaylistPlaymodeWidget`.
*   **Returning to Dashboard (Implemented):** Click '<' in Play Mode breadcrumb -> `_enter_dashboard_mode` called -> View switches to `PlaylistDashboardWidget`. *Playback continues.*
*   **Adding to Selection Pool via DND (Planned):**
    1.  User drags file(s) or folder(s) from Explorer onto the `PlaylistsPage` while in Play Mode.
    2.  `PlaylistsPage.dropEvent` (or similar DND handlers) receives the event.
    3.  If folders are dropped, recursively find all media files within them.
    4.  Extract file paths.
    5.  Call a method on `SelectionPoolWidget` (e.g., `add_tracks(list_of_paths)`) to add the valid media file paths to the pool.
*   **Adding to Selection Pool via Browse Button (Planned):**
    1.  User clicks the "Browse" button located near the Selection Pool in Play Mode.
    2.  A folder selection dialog (`QFileDialog.getExistingDirectory`) opens.
    3.  User selects a folder and confirms.
    4.  The application recursively scans the selected folder for media files (e.g., based on extensions like `.mp3`, `.flac`, `.wav`, `.ogg`, `.m4a`).
    5.  The list of found media file paths is passed to the `SelectionPoolWidget` (`add_tracks(list_of_paths)`).
*   **Adding to Selection Pool via Deletion (Planned):**
    1.  User selects a track in the `PlaylistPlaymodeWidget.tracks_list`.
    2.  User triggers deletion (e.g., via context menu or 'Delete' key - needs implementation).
    3.  The track is removed from the `Playlist` object (`current_playlist.remove_track`).
    4.  The `Playlist` object is saved (`current_playlist.save()`).
    5.  The removed track's path is added to the `SelectionPoolWidget` (`add_tracks([removed_path])`).
    6.  The `PlaylistPlaymodeWidget.tracks_list` is refreshed.
*   **Adding from Selection Pool to Playlist (Planned):**
    1.  User selects one or more tracks in the `SelectionPoolWidget`.
    2.  User triggers an "Add to Playlist" action (e.g., button, context menu, DND onto track list - needs implementation).
    3.  Get selected track paths from `SelectionPoolWidget`.
    4.  Add these paths to the `Playlist` object (`current_playlist.add_track`).
    5.  Save the `Playlist` object (`current_playlist.save()`).
    6.  Optionally, remove added tracks from the `SelectionPoolWidget`.
    7.  Refresh `PlaylistPlaymodeWidget.tracks_list`.

## 7. Data Model (`playlist.py` - Implemented)

A file `./music_player/models/playlist.py` defines the core data structures.

### 7.1 `Playlist` Class

**Purpose:** Represents a single, ordered collection of music tracks.

**Key Attributes:**

*   `name (str)`: User-defined name.
*   `filepath (Optional[Path])`: Absolute path to the `.json` file (e.g., `.../WorkingDir/playlists/My Favs.json`). `None` if unsaved.
*   `tracks (List[str])`: Ordered list of absolute track file paths.
*   `_track_set (set[str])`: Internal set for quick uniqueness checks.

**Key Methods:**

*   `__init__`: Initializes name, tracks. Loads from `filepath` if provided and `tracks` is `None`.
*   `add_track`: Adds unique track path.
*   `remove_track`: Removes track path.
*   `_load`: Loads data from `self.filepath`.
*   `save(self, working_dir=None)`: Saves state to JSON. Determines path within `<working_dir>/playlists/` if `self.filepath` is `None` or points outside. Uses working directory from settings if `working_dir` arg is `None`.
*   `load_from_file(filepath)` (staticmethod): Factory method to load from a specific path.
*   `__len__`, `__repr__`, `__eq__`, `__hash__`.

**Design Choices:**

*   Uses JSON for internal storage.
*   Maintains `list` and `set` for tracks.

### 7.2 `PlaylistManager` Class

**Purpose:** Service to discover, load, save, delete `Playlist` objects from the designated playlist directory within the application's working directory.

**Key Attributes:**

*   `working_dir (Path)`: The root working directory read from settings (`preferences/working_dir`), defaulting to `Path.home()`.
*   `playlist_dir (Path)`: The specific subdirectory (`<working_dir>/playlists/`) where `.json` files are stored.

**Key Methods:**

*   `__init__(self, working_dir=None)`: Initializes paths. Reads working directory setting via `get_default_working_dir()` if `working_dir` arg is `None`. Ensures `<working_dir>/playlists/` exists.
*   `_sanitize_filename(name)` (staticmethod): Helper to clean names for filenames.
*   `get_playlist_path(playlist_name, playlist_dir=None)` (staticmethod): Generates the full path within the appropriate `playlist_dir` (calculating default from settings if `playlist_dir` arg is `None`).
*   `load_playlists(self)`: Scans `self.playlist_dir` for `.json` files and loads them.
*   `save_playlist(self, playlist)`: Ensures playlist's filepath points within `self.playlist_dir`, then calls `playlist.save(self.working_dir)`.
*   `delete_playlist(self, playlist)`: Deletes the `.json` file associated with the playlist.

**Design Choices:**

*   Centralizes filesystem interactions for playlists.
*   Uses the application's configured working directory setting.
*   Stores playlists in a dedicated `playlists` subdirectory.

## 8. Future Enhancements (Optional / Planned)

*   **Implement Selection Pool UI/Logic:** Build `SelectionPoolWidget`, integrate into `PlaylistPlaymodeWidget`, implement add/remove/get methods. Add the "Browse" button and connect its logic.
*   **Implement DND for Selection Pool:** Add DND handlers to `PlaylistsPage` for adding files/folders.
*   **Implement Playlist Track Removal/Addition:** Add UI triggers (context menus, buttons) in `PlaylistPlaymodeWidget` and `SelectionPoolWidget` for moving tracks between the playlist and the pool.
*   **Implement Playlist Playback Logic:** Ensure `MainPlayer` listens to `playlist_selected_for_playback` and correctly loads/plays the `current_playing_playlist`.
*   **Implement Dashboard Context Menu:** Add right-click menu to `PlaylistListView` to trigger edit/rename/delete actions.
*   Implement track reordering via Drag and Drop within the playlist track list.
*   Implement search/filtering within the playlist track list or selection pool.
*   Fetch and display more track metadata in lists.
*   Implement import/export for standard formats (M3U, PLS).
