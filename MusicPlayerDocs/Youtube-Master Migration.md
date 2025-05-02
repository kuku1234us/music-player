# Introduction

This document details the migration of all functionalities of the Youtube-Master app into the music_player app and all its steps.

## Migration Plan

This plan outlines the steps to integrate the functionality of the standalone `youtube-master` application into the `music_player` application, leveraging the `qt_base_app` framework used by `music_player`.

### Phase 1: File Preparation and Model Integration

- [x] 1.  **Create UI Component Directory:**
    *   Create a new directory using the relative path `music_player/ui/youtube_components/` (Absolute path: `D:/projects/musicplayer/music_player/ui/youtube_components/`).
    *   This directory will house the specific UI widgets adapted from `youtube-master` (e.g., `VideoInput`, `DownloadQueue`, `YoutubeProgress`, `ToggleButton`).

- [x] 2.  **Copy Models:**
    *   Copy the following model files from the source directory `youtube-master/src/youtubemaster/models/` to the target directory `music_player/models/` (located at `D:/projects/musicplayer/music_player/models/`):
        *   `SiteModel.py`
        *   `YoutubeModel.py`
        *   `BilibiliModel.py`
        *   `Yt_DlpModel.py`
        *   `DownloadManager.py`
        *   `CLIDownloadWorker.py`
        *   **Important Design Note:** This migration will *only* utilize the `CLIDownloadWorker.py`, which interacts with the `yt-dlp` command-line executable. The alternative `PythonDownloadWorker.py` (if present in the source) or direct usage of the `yt-dlp` Python package will *not* be implemented. This decision is based on the perceived stability and more frequent updates of the CLI compared to potential issues or slower update cycles in the Python package integration, ensuring better compatibility with YouTube's changing platform.
        *   *Note:* `ThemeManager.py` from `youtube-master` is likely redundant as `music_player` uses the `ThemeManager` from `qt_base_app`. Assess if any specific theme logic needs merging.
    *   **Action:** Perform file copy operation.

- [x] 3.  **Update `music_player/models/__init__.py`:**
    *   Add imports for the newly copied models to make them accessible within the `music_player` package (`music_player.models`).
    *   **Action:** Edit `music_player/models/__init__.py`.

### Phase 2: Sidebar and Page Setup

- [x] 1.  **Update Configuration (`music_player_config.yaml`):**
    *   Add a new item to the `sidebar.sections` list (e.g., under the "Main" section) for the YouTube downloader.
    *   Define `id`, `title`, `icon`, and `page` (e.g., `YoutubePage`).
    *   **Example Addition:**
        ```yaml
        - id: "youtube_downloader"
          title: "Youtube"
          icon: "fa5s.download"  # Or brands.youtube
          page: "YoutubePage"
        ```
    *   **Action:** Edit `music_player/resources/music_player_config.yaml`.

- [x] 2.  **Create New Page File:**
    *   Create the file `music_player/ui/pages/youtube_page.py`.
    *   Implement the `YoutubePage` class inheriting from `QWidget` (following the pattern of `BrowserPage`).
    *   In its `__init__` method:
        *   Set `objectName` and `page_id` property.
        *   Get instances of `ThemeManager` and `SettingsManager`.
        *   Call `super().__init__()`.
        *   Initialize page-specific attributes (like the future `DownloadManager` instance).
        *   Use internal `_setup_ui()` and `_connect_signals()` methods for structure.
    *   **Action:** Create and implement the basic structure of `music_player/ui/pages/youtube_page.py`.

- [x] 3.  **Integrate Page into Dashboard (`dashboard.py`):**
    *   Import `YoutubePage` at the top of `music_player/ui/dashboard.py`.
    *   In the `initialize_pages` method:
        *   Instantiate `YoutubePage`.
        *   Store the instance in `self.pages` dictionary.
        *   Add the page to the `content_stack` using `self.add_page('youtube_downloader', youtube_page_instance)`, ensuring the ID matches the `music_player_config.yaml` entry. (Note: The page itself does *not* manage its addition to the stack).
    *   Ensure the `on_sidebar_item_clicked` method (or the base class implementation) correctly handles navigation to this new page based on the ID.
    *   **Action:** Edit `music_player/ui/dashboard.py`.

### Phase 3: UI Replication

- [x] 1.  **Copy and Adapt UI Components:**
    *   **Copy Source Files:** Copy the original UI component source files from `youtube-master/src/youtubemaster/ui/` to `music_player/ui/youtube_components/`. This includes:
        *   `VideoInput.py`
        *   `DownloadQueue.py`
        *   `YoutubeProgress.py`
        *   Identify and copy any other necessary base UI components (like `ToggleButton` if it's in a separate file). -> (ToggleButton found within VideoInput.py, FlowLayout.py copied)
    *   **Fix Imports:** Review each copied file within `music_player/ui/youtube_components/`.
        *   Update imports referencing `youtubemaster.models` to use `music_player.models`.
        *   Update imports referencing `youtubemaster.utils` (e.g., for Logger, config) to use equivalents from `qt_base_app` or `music_player` (SettingsManager).
        *   Adjust relative imports between the copied components if necessary.
    *   **Initial Styling:** Minimal styling changes at this stage. Focus on making the components functional. Deeper theme integration can happen later if needed.
    *   **Action:** Copy UI component files, edit copied files in `music_player/ui/youtube_components/` to fix imports. -> (Imports fixed for VideoInput, DownloadQueue, YoutubeProgress, FlowLayout needs no fix)

- [x] 2.  **Build `YoutubePage` Layout (`_setup_ui`):**
    *   In `music_player/ui/pages/youtube_page.py`, within the `_setup_ui` method:
        *   Import the newly adapted components from `music_player.ui.youtube_components`.
        *   Instantiate these components.
        *   Assemble the page's layout using standard Qt layouts (`QVBoxLayout`, `QHBoxLayout`, etc.) to mirror the structure of `youtube-master`'s `MainWindow` (input section on top, queue below).
    *   **Action:** Edit `music_player/ui/pages/youtube_page.py`.

### Phase 4: Backend Logic Integration and Adaptation

- [x] 0.  **Fix Internal Imports in Migrated Models:**
    *   Review each copied model file (`SiteModel.py`, `YoutubeModel.py`, `BilibiliModel.py`, `Yt_DlpModel.py`, `DownloadManager.py`, `CLIDownloadWorker.py`) within `music_player/models/`.
    *   Change any imports referencing the old `youtubemaster` package (e.g., `from youtubemaster.models...`, `from youtubemaster.utils...`) to use relative imports (`from .`), imports from `qt_base_app`, or standard library imports as appropriate.
    *   Replace `youtubemaster.utils.logger` usage with the singleton `Logger.instance()` from `qt_base_app.models.logger`.
    *   Replace API key handling (`youtubemaster.utils.env_loader`) with `SettingsManager.instance().get(...)` (pending key definition in Step 4).
    *   **Action:** Edit copied model files in `music_player/models/`.

- [x] 1.  **Instantiate `DownloadManager`:**
    *   In `YoutubePage.__init__`, instantiate the `DownloadManager` and store it as an instance variable (e.g., `self.download_manager = DownloadManager(parent=self)`).
    *   Ensure `DownloadManager` is initialized correctly, potentially passing necessary configuration loaded via `SettingsManager`.

- [x] 2.  **Connect Signals and Slots (`_connect_signals`):**
    *   In `YoutubePage._connect_signals`:
        *   Connect signals from the UI components (e.g., `VideoInput.add_clicked`) to appropriate slots *within* `YoutubePage` (`_on_add_download_clicked`).
        *   Connect signals from `self.download_manager` (`download_started`, `download_progress`, `download_complete`, `download_error`, `queue_updated`) to slots *within* `YoutubePage`.
    *   Implement the necessary slots within `YoutubePage` (`_on_download_started`, `_on_download_progress`, etc.).
    *   **Action:** Edit `music_player/ui/pages/youtube_page.py`.

- [x] 2.1. **Implement `DownloadQueue` Update Methods:**
    *   Implement the UI update methods (`add_or_update_item`, `update_item_progress`, `update_item_status`) within the migrated `music_player.ui.components.youtube_components.DownloadQueue` class. (Note: These methods correspond to `update_queue`, `on_download_started`, `on_download_progress`, `on_download_complete`, `on_download_error` which were found to be already implemented.)
    *   These methods will be called by the slots created in `YoutubePage` (Step 2) to visually update the download items based on `DownloadManager` signals.
    *   Adapt the logic from the original `youtube-master.ui.DownloadQueue` and `youtube-master.ui.YoutubeProgress` components.
    *   **Action:** Edit `music_player/ui/components/youtube_components/DownloadQueue.py` and potentially `music_player/ui/components/youtube_components/YoutubeProgress.py`. -> (Verified as already complete)

- [x] 3.  **Adapt Threading:**
    *   Verify that the threading model (`CLIDownloadWorker` launched by `DownloadManager`) functions correctly within the `music_player`'s event loop and environment.
    *   Ensure thread safety (`QMutex` usage in `DownloadManager`) remains effective.
    *   Check `QObject` parentage for threads and workers to ensure proper cleanup (`deleteLater`).
    *   Refactored to use QObject worker + moveToThread pattern per Qt best practices.
    *   **Action:** Review and potentially adapt `DownloadManager.py` and `CLIDownloadWorker.py`.

- [x] 4.  **Identify and Migrate Persistent Settings:**
    *   Systematically review `youtube-master` codebase (esp. `DownloadManager`, `VideoInput`, config loading logic if any) to identify user-configurable settings that need to persist between sessions (e.g., default download directory, **max concurrent downloads**, last used format options, API keys, **individual toggle button states**):
        *   Define a constant key in `music_player/models/settings_defs.py` (e.g., `YT_DOWNLOAD_DIR_KEY`, `YT_MAX_CONCURRENT_KEY`, `YT_ACTIVE_RESOLUTION_KEY`, `YT_HTTPS_ENABLED_KEY`).
        *   Add an entry to the `MUSIC_PLAYER_DEFAULTS` dictionary in `settings_defs.py`.
    *   Update the relevant `music_player` code (`DownloadManager`, `YoutubePage`, `VideoInput`) to use `SettingsManager.instance().get(KEY)` and `SettingsManager.instance().set(KEY, value)`. (Ensure `set_defaults` is called in `run.py`).
    *   **Add controls for relevant settings (like Max Concurrent Downloads, Download Directory) to `PreferencesPage`**. Remove any duplicated controls (like the concurrency SpinBox) from the migrated `DownloadQueue` header.
    *   **Action:** Review `youtube-master` code, edit `settings_defs.py`, edit adapted components (`DownloadManager`, `YoutubePage`, `VideoInput`, `PreferencesPage`, `DownloadQueue`).

- [x] 5.  **Handle Configuration (using `SettingsManager`):**
    *   Identify necessary **static** configuration settings from `youtube-master` (e.g., default max concurrent downloads *if not user-changeable*).
    *   Add static configuration to `music_player_config.yaml` under a new section (e.g., `youtube_downloader`).
    *   Adapt `DownloadManager` and potentially `YoutubePage` to read these **static** settings using `SettingsManager.instance().get_yaml_config()`.
    *   **Action:** Edit `music_player_config.yaml`, `DownloadManager.py`, `YoutubePage.py`.

- [x] 6.  **Implement UI Helper Functionality:**
    *   Implement the 'Clear Completed' button functionality in the migrated `DownloadQueue` header. Connect its `clicked` signal to a slot that iterates through completed items and calls `self.download_manager.cancel_download()` for each.
    *   Verify or implement the click-to-open file location functionality in the migrated `YoutubeProgress` component (check `mouseReleaseEvent` and `open_file_location` logic).
    *   **Action:** Edit `music_player/ui/components/youtube_components/DownloadQueue.py` and `music_player/ui/components/youtube_components/YoutubeProgress.py`.

### Phase 5: Testing and Refinement

# ... existing description ...

### Phase 6: Chrome Extension Migration

- [ ] 1.  **Copy Extension Files:**
    # ... existing description ...

- [ ] 2.  **Update Extension Manifests and Scripts:**
    *   Modify `manifest.json` in both extensions:
        # ... existing description ...
    *   Modify `background.js` (or equivalent script) in both extensions:
        *   Change the protocol from `youtubemaster://` to a new protocol specific to `music_player` (e.g., `musicplayerdl://`).
        *   Update the path/command used to invoke the `music_player` executable if necessary (though protocol handler should manage this).
    *   **Implement command-line argument parsing:**
        *   In `music_player`'s entry point (`run.py` or within `qt_base_app.app.create_application`), add logic to parse `sys.argv`.
        *   Detect if the application was launched with arguments matching the new protocol (e.g., `musicplayerdl://<type>/<url>`).
        *   If protocol arguments are detected, extract the type (video/audio) and URL, and automatically add the URL to the `DownloadManager` after the main window is initialized.
    *   **Action:** Edit copied extension files (`manifest.json`, `background.js`). Edit `run.py` or `qt_base_app/app.py`.

- [ ] 3.  **Implement Protocol Handler Registration:**
    # ... existing description ...

- [ ] 4.  **Test Extension Integration:**
    # ... existing description ...