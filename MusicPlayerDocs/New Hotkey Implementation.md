# New Hotkey & VLC Architecture Specification

This document outlines the specifications for the new VLC threading architecture and the implementation of context-sensitive hotkeys (`Page Up`, `Page Down`, `Delete`).

## 1. VLC Threading Architecture (New)

To resolve UI blocking issues (5-6s delays) during media switching caused by hardware resource release in `libvlc`, we are moving to a **Multi-Threaded, Double-Buffered** architecture.

### 1.1 The Problem

- **Blocking Call**: `vlc.MediaPlayer.stop()` can block the calling thread for several seconds when using hardware acceleration (`--avcodec-hw=any`, `--vout=directdraw`) with certain codecs (VP9).
- **UI Freeze**: Currently, `stop()` is called on the main UI thread, causing the application to freeze during file transitions.

### 1.2 The Solution: Async Worker Threads

We will decouple the VLC lifecycle from the UI thread.

1.  **Per-Playback Worker**: Every time a new media is loaded, a **new** `VLCWorker` and `QThread` are created.
2.  **Instant Switching**: The UI immediately switches focus to the new worker/thread.
3.  **Background Cleanup**: The _previous_ worker is signaled to stop. It executes `stop()` and `release()` in its own background thread. If this takes 5 seconds, it happens silently in the background without affecting the UI.
4.  **Zombie Management**: The `VLCBackend` maintains a list of "zombie" threads (threads currently stopping) to prevent premature garbage collection until they are truly finished.

### 1.3 Video Output Surfaces (HWND) and Why We Allocate a Fresh Surface Per Switch

When you embed VLC into a Qt widget on Windows, VLC needs a stable native window handle (HWND). If VLC cannot reliably keep rendering into the HWND you provide, it will fall back to creating its **own** top-level window. This is the “mysterious VLC popup window” bug you observed during rapid switching and during repeat.

The tricky part is that `libvlc_media_player_stop()` can block for seconds, and while it blocks it may still be detaching the video output pipeline from the HWND. If, during that teardown window, we reuse the **same** HWND for a new playback session, VLC ends up with two different sessions fighting over one native surface. That race condition is exactly the sort of scenario that triggers:

- the old audio continuing while a new video starts, and/or
- VLC deciding to spawn a new popup window for video rendering.

To avoid this, we deliberately copy the proven behavior from `vlc_test_ab.py`:

- **We allocate a fresh `VideoWidget` (fresh HWND) on every switch**.
- We keep the old `VideoWidget` alive (hidden) until the old worker thread finishes `stop()` + `release()`.
- Only after the old worker finishes do we delete the old surface.

Conceptually, think of each `VideoWidget` as a “disposable monitor.” We never ask two VLC sessions to share the same monitor at the same time.

#### Surface lifecycle diagram

```
Switch A -> B

  Surface_A (HWND_A)  <- Worker_A (playing)
        |
        | user switches
        v
  Surface_B (HWND_B)  <- Worker_B (playing immediately)
  Surface_A (HWND_A)  <- Worker_A (stopping in background; may block)

When Worker_A finishes:
  delete Surface_A safely
```

#### Implementation detail: `surface_released(hwnd)`

To make the “delete surfaces only when safe” rule enforceable, the backend emits a signal when an old worker has truly finished:

- `VLCBackend.surface_released(hwnd: int)` is emitted when the retired worker thread finishes.
- `MainPlayer` forwards that to `PlayerPage.release_video_surface(hwnd)`.
- `PlayerPage` removes that widget from the stack and `deleteLater()`s it.

## 2. Feature Specifications (Hotkeys)

### 2.1. Context Tracking

The `MainPlayer` must track the **source** of the current playback to determine how to handle hotkeys.

- **Source: `playlist`**: Playback initiated from the Playlist Page.
- **Source: `browser`**: Playback initiated from the Browser Page (e.g., double-clicking a file).
- **Source: `single`**: Playback initiated from the Player Page (e.g., Open File dialog) or other generic sources.

### 2.2. Hotkey Definitions

| Hotkey        | Function       | Behavior by Context                                                                                                                                                                                                       |
| :------------ | :------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Page Up**   | Previous Media | **Playlist Mode:** Plays the previous track in the active playlist.<br>**Browser Mode:** Plays the previous media file in the browser's current file list (respecting current sort order).<br>**Single Mode:** No action. |
| **Page Down** | Next Media     | **Playlist Mode:** Plays the next track in the active playlist.<br>**Browser Mode:** Plays the next media file in the browser's current file list (respecting current sort order).<br>**Single Mode:** No action.         |
| **Delete**    | Delete File    | **Browser Mode:** Initiates the deletion workflow for the currently playing file.<br>**Playlist/Single Mode:** No action.                                                                                                 |

### 2.3. Browser Mode Deletion Workflow

When the `Delete` key is pressed while in **Browser Mode**:

1.  **Confirmation:** A custom dialog appears asking for confirmation to delete the _currently playing_ file.
    - **No Sound:** The dialog must not emit a system beep or sound (standard `QMessageBox` often beeps on Windows).
    - **Focus:** The dialog takes focus.
2.  **Action - Enter (Yes):**
    - **Release Lock:** Playback stops immediately to release the file lock (Windows filesystem requirement).
    - **Delete:** The file is permanently deleted from the filesystem (`os.remove`).
    - **Auto-Advance:** The player automatically loads and starts playing the _next_ file in the browser list (respecting sort order). If no next file exists, it stops or plays the previous one.
3.  **Action - Esc (Cancel):**
    - The dialog closes.
    - Playback continues uninterrupted (if possible, or resumes).

---

## 3. Technical Implementation Plan

### Step 1: Update `MainPlayer` State Management

We need to enhance `MainPlayer` to explicitly track the playback source.

- **File:** `music_player/ui/vlc_player/main_player.py`
- **Changes:**
  - Add `self.playback_source` attribute (default: `'single'`) in `__init__`.
  - Update `load_media_unified(self, filepath, source_context)`:
    - Map `source_context` strings to internal source types:
      - `"browser_files"` -> `'browser'`
      - `"playlist_track_selection"` or `"internal_playlist_navigation"` -> `'playlist'`
      - Others (`"file_dialog"`, `"youtube_downloader"`, etc.) -> `'single'`
    - Store this in `self.playback_source`.
  - Define new signals to communicate with the BrowserPage (to avoid circular imports/tight coupling):
    - `browser_nav_request = pyqtSignal(str)`: Emits `'next'` or `'prev'`.
    - `browser_delete_request = pyqtSignal(str)`: Emits the filepath to delete.

### Step 2: Update `HotkeyHandler`

Map the new keys to handler methods in `MainPlayer`.

- **File:** `music_player/ui/vlc_player/hotkey_handler.py`
- **Changes:**
  - Import `Qt.Key.Key_PageUp`, `Qt.Key.Key_PageDown`, `Qt.Key.Key_Delete`.
  - Add mappings in `self.hotkeys`:
    - `Qt.Key.Key_PageUp` -> `self.main_player.on_prev_media_request`
    - `Qt.Key.Key_PageDown` -> `self.main_player.on_next_media_request`
    - `Qt.Key.Key_Delete` -> `self.main_player.on_delete_media_request`

### Step 3: Implement Request Handlers in `MainPlayer`

Implement the logic to route hotkey requests based on `playback_source`.

- **File:** `music_player/ui/vlc_player/main_player.py`
- **Changes:**
  - Implement `on_next_media_request()`:
    - If `playback_mode == 'playlist'` (or source is 'playlist'): Call `play_next_track()`.
    - If `playback_source == 'browser'`: Emit `browser_nav_request.emit('next')`.
  - Implement `on_prev_media_request()`:
    - If `playback_mode == 'playlist'` (or source is 'playlist'): Call `play_previous_track()`.
    - If `playback_source == 'browser'`: Emit `browser_nav_request.emit('prev')`.
  - Implement `on_delete_media_request()`:
    - If `playback_source == 'browser'` and `self.current_media_path`: Emit `browser_delete_request.emit(self.current_media_path)`.

### Step 4: Implement Navigation & Deletion Logic in `BrowserPage`

The `BrowserPage` holds the sorted model (`QSortFilterProxyModel` via `self.file_table.model()`), so it knows what "next" is.

- **File:** `music_player/ui/pages/browser_page.py`
- **Changes:**
  - Add helper method `_get_adjacent_file(current_path, direction='next') -> str | None`:
    - Get the proxy model: `model = self.file_table.model()`.
    - Iterate rows `range(model.rowCount())` to find the row where data matches `current_path`.
    - Target row is `current_row + 1` (next) or `current_row - 1` (prev).
    - Return the path at the target row if valid, else `None`.
  - Add slot `handle_browser_nav_request(direction)`:
    - Calls `_get_adjacent_file` with the current media path.
    - If a file is found, emit `play_single_file_requested(path)`.
  - Add slot `handle_browser_delete_request(file_path)`:
    - **Identify Next:** Call `_get_adjacent_file` to find the next file _before_ deletion.
    - **Confirm:** Create a custom `QDialog` (not `QMessageBox`) to ensure no system sound is played.
      - Set layout with Label ("Delete file?\n...") and Buttons (Yes/Cancel).
      - Call `exec()`.
    - **Execute (if Yes):**
      - Call `self.player.stop()` (passed via a new setter or signal, see Step 5). Alternatively, assume `MainPlayer` handles stop if we request it, but `BrowserPage` doesn't directly control `MainPlayer` stop.
      - _Correction:_ `BrowserPage` cannot directly stop `MainPlayer`. The `MainPlayer` should probably handle the stop if deletion is confirmed, or we use `self.oplayer_service`? No, `oplayer_service` is for upload.
      - _Refined Logic:_ `BrowserPage` needs a way to stop playback. We can add a signal `request_stop_playback` to `BrowserPage`, connected to `MainPlayer.stop`.
      - Once stopped (file lock released):
        - `os.remove(file_path)`
        - Manually remove the row from `self.model` (source model) to update UI immediately without full refresh.
        - If a "next file" was identified, emit `play_single_file_requested(next_file)`.

### Step 5: Wire Components in `Dashboard`

Connect the new signals between `MainPlayer` and `BrowserPage`.

- **File:** `music_player/ui/dashboard.py` (in `initialize_pages`)
- **Changes:**
  - Connect `self.player.browser_nav_request` -> `browser_page.handle_browser_nav_request`.
  - Connect `self.player.browser_delete_request` -> `browser_page.handle_browser_delete_request`.
  - _New Connection:_ Connect `browser_page.request_stop_playback` -> `self.player.stop`.
  - _Important:_ Set `browser_page.persistent_player = self.player` so BrowserPage can access the currently playing file path when computing next/prev.

---

## 5. Repeat Behavior at End of Media (Single Mode)

In this project, the player never truly “stops”; it always follows one of our repeat modes. In single mode, when a media reaches the end, we should restart it from the beginning without creating a new VLC session.

In practice, `libVLC` has a sharp edge: once the player reaches the `Ended` state, some calls like `set_time(0)` may be ignored. Our old backend handled this by doing a small “reset” cycle before seeking, and we keep the same idea in the threaded worker:

1. When `end_reached` fires, `MainPlayer` performs `seek(0)` then `play()`.
2. The worker’s `seek()` detects `Ended/Stopped/Error` and performs:
   - `stop()` (in worker thread; UI stays responsive),
   - re-assert the video output HWND (`set_hwnd`),
   - `play()` then `pause()` (to kick VLC into a seekable state),
   - then `set_time(0)`.
3. Finally, `play()` resumes from the beginning.

This approach restarts playback without creating a new worker or thread and avoids VLC popup windows by always re-asserting the HWND after a stop.

---

## Milestone Checklist

- [x] Implement `VLCBackend` worker-per-session threading model.
- [x] Ensure `stop()`/`release()` happens off the UI thread.
- [x] Implement context-aware hotkeys (`PageUp`, `PageDown`, `Delete`) in `HotkeyHandler`.
- [x] Wire navigation/delete signals in `dashboard.py`.
- [x] Ensure video output uses native HWND surfaces to avoid VLC popup windows.
- [x] Allocate a fresh `VideoWidget` surface (HWND) per switch; delete old surfaces only after worker finishes.
- [ ] Verify no overlapping audio after rapid switching in production app (matches `vlc_test_ab.py`).
- [ ] Verify repeat-at-end reliably restarts from 0 in single mode for all tested videos.

### Step 6: Refine `load_media_unified` Calls

Ensure `BrowserPage` sends the correct source flag when it asks to play a file.

- **File:** `music_player/ui/pages/browser_page.py` (no change needed)
  - _Verification:_ `BrowserPage` currently uses a lambda in `dashboard.py`:
    `browser_page.play_single_file_requested.connect(lambda filepath: self.player.load_media_unified(filepath, "browser_files"))`
  - This is already correct. "browser_files" will be mapped to `'browser'` source in Step 1.

---

## 4. Implementation Details

### Silent Deletion Dialog

To ensure no sound is played, we instantiate a `QDialog` instead of `QMessageBox`.

```python
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox

class SilentConfirmDialog(QDialog):
    def __init__(self, parent, filename):
        super().__init__(parent)
        self.setWindowTitle("Confirm Deletion")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Are you sure you want to delete:\n{filename}?"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
```

### Sorting Awareness

`BrowserPage` uses `QSortFilterProxyModel`. Accessing data via the proxy model's index ensures we respect the current visual sort order (Filename, Date, Size, etc.).

```python
# In BrowserPage
proxy_model = self.file_table.model()
for row in range(proxy_model.rowCount()):
    # Get data from column 0 (Filename) or use UserRole to get full item dict
    idx = proxy_model.index(row, 0)
    # Check if this row matches current file path
```
