# Introduction

# Play Video Implementation Plan

## 1. Goal

Modify the `PlayerPage` and underlying `MainPlayer` to support video playback for video media files, displaying the video instead of the album artwork when a video file is loaded.

## 2. Current Structure Analysis

*   **`PlayerPage` (`music_player/ui/pages/player_page.py`):**
    *   Currently displays track info (title, artist, album), album artwork (`AlbumArtWidget`), playback controls, progress bar, and volume control.
    *   Uses a `QVBoxLayout` as the main layout.
    *   Contains an `AlbumArtWidget` which is essentially a QLabel used to display images.
    *   Instantiates and interacts with `MainPlayer`.
    *   Loads media using `load_media(track_data)`, which calls `self.player.load_media(path)`.
*   **`MainPlayer` (`music_player/ui/vlc_player/main_player.py`):**
    *   Wraps the `vlc.MediaPlayer` instance.
    *   Manages playback state (play, pause, stop, seek, volume).
    *   Handles media loading (`load_media`), state changes, and errors.
    *   Extracts metadata (including album art) using `vlc.Meta`.
    *   **Crucially, it currently lacks the mechanism to render video output to a widget.** VLC requires a window handle (like a `QWidget`'s `winId()`) to draw video onto.
*   **Album Artwork:** Fetched via `vlc.Meta.ArtworkURL` and displayed in the `AlbumArtWidget`.

### 2.1 Current Playback Initiation Flows

Before implementing video playback, it's essential to understand how media playback is currently initiated or changed within the application. There are three primary user interactions that trigger playback:

1.  **Via the Player Page "Open File" Button:**
    *   The user clicks the round "Open File" button (`self.open_file_button`) located on the main `PlayerPage` (`player_page.py`).
    *   This action triggers the `_on_open_file_clicked` slot within `PlayerPage`, which directly calls the `load_media` method on the persistent `MainPlayer` instance.
    *   The `MainPlayer.load_media` method (`main_player.py`) presents a file dialog. Upon selecting a file, it explicitly sets the playback mode to `'single'`, clears any active playlist reference, adds the file to recently played items, and then calls the internal `_load_and_play_path` method.
    *   `_load_and_play_path` is the core method that validates the path, updates the player's state to `STATE_PLAYING`, and instructs the `VLCBackend` to load and play the selected file.

2.  **Via the Playlist View (`PlaylistPlaymodeWidget`):**
    *   **Playing the Entire Playlist:** Clicking the "Play Playlist" button (`self.play_playlist_button` in `playlist_playmode.py`) triggers the `_on_play_playlist_requested` slot. This emits the `playlist_play_requested` signal with the current `Playlist` object. This signal is connected externally (likely in the dashboard) to the `MainPlayer.load_playlist` slot. The `load_playlist` slot sets the playback mode to `'playlist'`, updates internal and global playlist references, adds the playlist to recently played, retrieves the first track, and calls `_load_and_play_path` to start playback.
    *   **Playing a Specific Track:** Double-clicking a track in the playlist table triggers the `_on_track_double_clicked` slot. This updates the global `player_state` with the current playlist context and emits the `track_selected_for_playback` signal with the specific track's file path. This signal is connected externally to the `MainPlayer.play_track_from_playlist` slot. This slot verifies the player is in playlist mode, updates the *playlist object's* internal pointer to the selected track, adds the specific track to recently played, and then directly loads and plays that track using the `VLCBackend`.

3.  **Via the Browser Page File List (`BrowserTableView`):**
    *   Double-clicking a *file* (not a directory) in the `BrowserTableView` (`browser_table.py`) triggers its `mouseDoubleClickEvent` method.
    *   This method verifies the item is a file and emits the `fileDoubleClicked` signal.
    *   Within `BrowserPage` (`browser_page.py`), this signal is connected to the `_on_file_double_clicked` slot, which in turn emits the `play_single_file_requested` signal.
    *   This final signal is connected externally to the `MainPlayer.play_single_file` slot. This slot explicitly sets the playback mode to `'single'`, clears any playlist reference, adds the file to recently played, and calls `_load_and_play_path` to initiate playback.

Understanding these flows highlights that methods like `_load_and_play_path`, `load_playlist`, `play_track_from_playlist`, and `play_single_file` within `MainPlayer` are the central points where media loading occurs. Therefore, the logic for detecting media type (audio vs. video) and signaling the `PlayerPage` will need to be integrated primarily within these `MainPlayer` methods.

### 2.2 Automatic Next-Track Playback (Playlist Mode)

In addition to manual initiation, the application automatically transitions to the next track when playing in playlist mode. This mechanism is crucial for continuous playback and relies on cooperation between the `VLCBackend`, `MainPlayer`, and the `Playlist` object.

1.  **Track Completion:** When the `VLCBackend` detects that the currently playing media has finished, it emits an `end_reached` signal.
2.  **Signal Handling in `MainPlayer`:** The `MainPlayer` connects this `end_reached` signal to its own `_on_end_reached` slot.
3.  **Delegation to `Playlist`:** Inside `_on_end_reached`, if the player is confirmed to be in `'playlist'` mode with a valid `_current_playlist`, it calls the `get_next_file()` method on the `_current_playlist` object. This delegates the core logic of deciding which track comes next to the `Playlist` instance itself.
4.  **Next Track Logic in `Playlist`:** The `Playlist.get_next_file()` method (`playlist.py`) implements the rules for track advancement based on the playlist's current repeat mode (`_current_repeat_mode`):
    *   **`REPEAT_ONE`:** Returns the path of the current track again.
    *   **`REPEAT_RANDOM`:** Uses a pre-shuffled list of indices (`_shuffled_indices`). It advances a pointer (`_shuffle_index`) within this list, regenerating the shuffle order if the end is reached (while avoiding immediate repeats). It returns the path corresponding to the track at the new shuffled index.
    *   **`REPEAT_ALL`:**
        *   If a custom sort order (`_sorted_indices`) is active (usually set by the UI table), it advances a pointer (`_sorted_playback_index`) through this sorted list, wrapping around to the beginning if needed, and returns the corresponding track path.
        *   If no custom sort order is active, it performs simple linear advancement, incrementing the current track index (`_current_index`) and wrapping around to 0 if the end of the playlist is reached.
5.  **Action in `MainPlayer`:** The `_on_end_reached` slot receives the path of the next track (or `None` if playback should stop) from `Playlist.get_next_file()`. If a valid path is received, it calls the internal `_load_and_play_path` method to load and play this next track. If `None` is received, it stops the player.

This design effectively encapsulates the playlist's state and playback rules (including repeat and shuffle logic) within the `Playlist` class, while `MainPlayer` orchestrates the playback based on the information provided by the `Playlist` object.

## 3. Proposed Changes

### 3.1. `MainPlayer` Modifications

1.  **Add Video Output Capability:**
    *   Modify `MainPlayer` to accept a widget handle (e.g., `winId`) during initialization or via a dedicated method (e.g., `set_video_widget(widget)`).
    *   When a video widget is set, use the appropriate VLC function (e.g., `set_hwnd` on Windows, `set_xwindow` on Linux, `set_nsobject` on macOS) on the `vlc.MediaPlayer` instance to direct video output to that widget.
    *   Keep track of whether the current media is video or audio. This might require checking metadata or file type upon loading.
    *   Potentially add a signal `media_type_changed(is_video: bool)` emitted when media is loaded, indicating if it's video or audio.

### 3.2. `PlayerPage` Modifications

1.  **Add Video Widget:**
    *   Import `QVideoWidget` from `PyQt6.QtMultimediaWidgets` (or use a basic `QWidget` if `QVideoWidget` isn't suitable/available with VLC integration). A simple `QWidget` is often sufficient as VLC just needs a drawable surface handle. Let's plan to use a standard `QWidget` initially.
    *   Add a `QWidget` instance (`self.video_widget`) to the `PlayerPage` layout.
2.  **Layout Adjustments:**
    *   Modify the layout (`setup_ui`) to accommodate the video display.
    *   Place the `self.video_widget` where the `AlbumArtWidget` currently is.
    *   Use a `QStackedWidget` to easily switch between showing the `AlbumArtWidget` (for audio) and the `self.video_widget` (for video). The `AlbumArtWidget` will be page 0, `self.video_widget` will be page 1.
3.  **Conditional Visibility:**
    *   Connect to the (new) `media_type_changed` signal from `MainPlayer` (or determine media type locally if easier).
    *   When audio is loaded, show the `AlbumArtWidget` (set `QStackedWidget` index to 0).
    *   When video is loaded, show the `self.video_widget` (set `QStackedWidget` index to 1).
4.  **Pass Window Handle:**
    *   After the `PlayerPage` UI is fully realized (e.g., in `showEvent` or after initialization if the window is already visible), get the window handle of `self.video_widget` (`self.video_widget.winId()`).
    *   Call the new method in `MainPlayer` (e.g., `self.player.set_video_widget(self.video_widget)`) to pass the handle. This needs to happen *before* video playback starts but *after* the widget is created and shown. It might need to be called again if the widget is recreated.
5.  **Update `load_media`:**
    *   Ensure `load_media` triggers the process to determine if the new media is audio or video, leading to the correct widget being displayed in the `QStackedWidget`.

### 3.3. `AlbumArtWidget` Modifications (Minor)

*   Ensure it handles cases where no artwork is available gracefully (which it likely already does).

### 3.4 Interaction Flow for Display Switching

To achieve the goal of seamlessly switching between displaying album art for audio files and video playback for video files, the implementation will rely on a coordinated effort between the `MainPlayer` and the `PlayerPage`. This interaction ensures that the correct UI element is presented based on the type of media currently loaded.

The process begins when new media is loaded into the `MainPlayer`. As part of the loading process (detailed in step 6.2), the `MainPlayer`, utilizing the underlying VLC backend, will determine whether the media contains a video track. This detection capability is crucial and resides within the `MainPlayer` as it directly interacts with the media source.

Once the media type is identified, `MainPlayer` communicates this information to the `PlayerPage` using a dedicated PyQt signal, tentatively named `media_type_determined`. This signal will carry a boolean value: `True` if the media includes video, `False` otherwise. Using a signal promotes loose coupling, allowing `MainPlayer` to broadcast the media type without needing direct knowledge of the `PlayerPage`'s internal structure.

The `PlayerPage`, in turn, will be structured (as per step 6.3) to use a `QStackedWidget`. This widget acts as a container holding both the `AlbumArtWidget` (at index 0) and the new `VideoWidget` (at index 1). The `PlayerPage` will connect its `_on_media_type_determined` slot (detailed in step 6.5) to the `MainPlayer`'s `media_type_determined` signal.

When the signal is received, the `_on_media_type_determined` slot in `PlayerPage` executes the switching logic. If the received boolean is `True` (indicating video), the slot activates the `VideoWidget` by setting the `QStackedWidget`'s current index to 1. Conversely, if the boolean is `False` (indicating audio), it activates the `AlbumArtWidget` by setting the index to 0 and proceeds with displaying the fetched album artwork.

Finally, if the `VideoWidget` is activated, an additional step is required (detailed in step 6.6): the `PlayerPage` must provide the `VideoWidget`'s window handle (`winId()`) to the `MainPlayer`. The `MainPlayer` then instructs the VLC backend to render the video output directly onto this specific widget surface.

This combination of media type detection in the backend, signal-based communication, and a `QStackedWidget` for view management in the UI allows the application to intelligently adapt its display based on the content being played.

## 4. Implementation Steps

1.  **Modify `MainPlayer`:**
    *   Add `_video_widget: Optional[QWidget] = None` instance variable.
    *   Add `set_video_widget(self, widget: QWidget)` method. This method stores the widget and calls the appropriate VLC `set_xwindow`/`set_hwnd`/`set_nsobject` function using `self.media_player`.
    *   Add logic inside `load_media` (or triggered by a signal after media parsing) to determine if the loaded media has a video track. A simple way might be `self.media_player.get_media().parse_with_options(vlc.MediaParseFlag.local, 0)` followed by checking `track_info()` or similar VLC methods.
    *   Emit a new signal `media_type_determined = pyqtSignal(bool)` (True if video, False if audio) after loading and parsing media.
2.  **Modify `PlayerPage.setup_ui`:**
    *   Create `self.video_widget = QWidget()`.
    *   Create `self.media_display_stack = QStackedWidget()`.
    *   Add `self.album_art_widget` to the stack (index 0).
    *   Add `self.video_widget` to the stack (index 1).
    *   Replace the direct layout insertion of `self.album_art_widget` with the insertion of `self.media_display_stack`.
    *   Set the initial index of the stack to 0 (`self.media_display_stack.setCurrentIndex(0)`).
3.  **Modify `PlayerPage.__init__`:**
    *   Connect the `MainPlayer.media_type_determined` signal to a new slot in `PlayerPage` (e.g., `_on_media_type_determined`).
4.  **Implement `PlayerPage._on_media_type_determined` Slot:**
    *   This slot receives the `is_video: bool` argument.
    *   If `is_video` is True, set `self.media_display_stack.setCurrentIndex(1)`.
    *   If `is_video` is False, set `self.media_display_stack.setCurrentIndex(0)` and proceed with loading album art as usual.
5.  **Implement Window Handle Passing in `PlayerPage`:**
    *   Override `showEvent(self, event)` in `PlayerPage`.
    *   Inside `showEvent`, after calling `super().showEvent(event)`, call `self.player.set_video_widget(self.video_widget)`. Ensure this is done only once or is safe to call multiple times. Alternatively, call it after UI setup if the page is guaranteed to be visible.
6.  **Testing:**
    *   Test with various audio files (MP3, FLAC) - should show album art.
    *   Test with various video files (MP4, MKV) - should show video in the `video_widget` area.
    *   Test switching between audio and video files.
    *   Test window resizing during video playback.
    *   Test seeking, pausing, playing video.

## 5. Considerations

*   **Aspect Ratio:** VLC might handle this automatically, but ensure the `video_widget` resizes correctly within the layout and the video maintains its aspect ratio. The `video_widget` might need size policies adjusted.
*   **Performance:** Video rendering can be more resource-intensive. Monitor performance.
*   **Error Handling:** Ensure errors during video playback or handle passing are caught.
*   **Platform Differences:** `winId()` and the corresponding VLC functions (`set_hwnd`, `set_xwindow`, `set_nsobject`) are platform-specific. Ensure the correct VLC call is made based on the operating system (`sys.platform`).
*   **`winId()` Changes on Re-parenting:** It's critical to remember that the `winId()` of the `VideoWidget` will change if it's re-parented between different top-level window contexts (e.g., from the main application window to a separate `FullScreenVideoHostWindow` for full-screen mode). The `winId()` is tied to the native top-level window. Therefore, VLC must be updated with the new `winId()` via `VLCBackend.set_video_output()` whenever such a re-parenting and context switch occurs to ensure continuous and correct video rendering.
*   **VLC Instance:** Ensure the VLC instance is created appropriately for video playback (it usually is by default).

## 6. Implementation Checklist

- [x] **6.1 Create `VideoWidget`:**
    - [x] Create `music_player/ui/components/player_components/video_widget.py` containing a basic `VideoWidget` class inheriting from `QWidget`.
    - [x] Set a default background color (e.g., black) for the widget.
- [x] **6.2 Modify `MainPlayer` (Core Video Logic):**
    - [x] Add `_video_widget` attribute.
    - [x] Add `set_video_widget(widget)` method (including platform-specific VLC calls).
    - [x] Add `media_type_determined = pyqtSignal(bool)` signal.
    - [x] Implement media type detection (audio vs video) during media loading.
    - [x] Emit `media_type_determined` signal after detection.
- [x] **6.3 Modify `PlayerPage.setup_ui` (Layout):**
    - [x] Import the new `VideoWidget` from its file.
    - [x] Instantiate `self.video_widget = VideoWidget()`.
    - [x] Instantiate `self.media_display_stack = QStackedWidget()`.
    - [x] Add `self.album_art_widget` to the stack (index 0).
    - [x] Add `self.video_widget` to the stack (index 1).
    - [x] Replace the direct layout insertion of `self.album_art_widget` with `self.media_display_stack`.
    - [x] Ensure the initial stack index is set to 0 (show album art by default).
- [x] **6.4 Modify `PlayerPage.__init__` (Signal Connection):**
    - [x] Connect the `MainPlayer.media_type_determined` signal to a new slot `_on_media_type_determined` in `PlayerPage`.
- [x] **6.5 Implement `PlayerPage._on_media_type_determined` Slot (Display Switching):**
    - [x] Implement the `_on_media_type_determined(self, is_video: bool)` slot.
    - [x] Inside the slot, set `self.media_display_stack.setCurrentIndex(1)` if `is_video` is True.
    - [x] Set `self.media_display_stack.setCurrentIndex(0)` if `is_video` is False.
    - [x] Ensure album art loading logic is still triggered appropriately when `is_video` is False.
- [x] **6.6 Implement `PlayerPage` Window Handle Passing:**
    - [x] Override `showEvent(self, event)` in `PlayerPage` (or find another suitable method called after the UI is fully realized).
    - [x] Inside `showEvent` (after `super().showEvent(event)`), call `self.player.set_video_widget(self.video_widget)`, passing the instance of the created `VideoWidget`.
- [ ] **6.7 Testing:**
    - [ ] Test with various audio files (MP3, FLAC) - should show album art correctly.
    - [ ] Test with various video files (MP4, MKV, AVI) - should show video playback.
    - [ ] Test switching between audio and video files during playback.
    - [ ] Test loading video files directly via "Open File" and from playlists/browser.
    - [ ] Test window resizing during video playback (check aspect ratio handling).
    - [ ] Test standard playback controls (seek, pause, play, volume) with video.
    - [ ] Verify behavior across different repeat/shuffle modes with mixed audio/video playlists (video should still play when its turn comes).
