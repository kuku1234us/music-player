# MusicPlayer Chrome Extension Integration

## Introduction

This document explains how the MusicPlayer Chrome extensions (one for audio downloads, one for video downloads) integrate with the main MusicPlayer desktop application. This system allows users to initiate downloads directly from YouTube within their browser, sending the request seamlessly to the MusicPlayer application running on their computer.

## Core Components and Workflow

The integration relies on several key components working together: the Chrome extensions themselves, a custom URL protocol (`musicplayerdl://`), operating system registration of this protocol, and the MusicPlayer application's handling of incoming requests.

### 1. Chrome Extensions (`musicplayer-audio-extension` & `musicplayer-video-extension`)

We provide two distinct Chrome extensions, functionally identical except for the type of download they initiate:

*   **`musicplayer-audio-extension`**: Designed to trigger audio-only downloads.
*   **`musicplayer-video-extension`**: Designed to trigger video downloads (currently configured for 720p MP4, though this is handled by the application logic).

Each extension consists of the following standard Chrome extension components:

*   **Manifest (`manifest.json`)**:
    *   **Purpose**: This is the blueprint of the extension. It defines essential metadata like the extension's name, version, description, and icons.
    *   **Permissions**: It declares the necessary permissions the extension needs to function. Key permissions include `contextMenus` (to add right-click options within the browser) and potentially `scripting` or `tabs` (to interact with web page content, specifically YouTube, and to trigger the opening of the custom protocol URL).
    *   **Scripts**: It specifies the background script (`background.js`) that handles core logic and potentially content scripts (`content.js`) that interact directly with the YouTube webpage.

*   **Content Script (`content.js`)**:
    *   **Execution Context**: This script runs directly within the environment of the YouTube web pages the user visits.
    *   **Functionality**: Its primary role could be to identify YouTube video URLs on the page or even to add custom "Download with MusicPlayer" buttons directly onto the YouTube interface (though the current implementation focuses on context menus).
    *   **Communication**: When the user interacts with an element related to the extension (like clicking a context menu item, which is handled via the background script), the content script (if used for direct interaction) would send a message containing the video URL to the background script using `chrome.runtime.sendMessage`.

*   **Background Script (`background.js`)**:
    *   **Persistent Logic**: This script runs in the background, listening for events.
    *   **Context Menu Setup**: It utilizes the `chrome.contextMenus.create` API to dynamically add entries like "Download Audio (MusicPlayer)" or "Download Video (MusicPlayer)" to the browser's right-click context menu. These menu items are configured to appear specifically when the user right-clicks on links or relevant elements within YouTube pages.
    *   **Event Listening**: It actively listens for click events on the context menu items it created, using `chrome.contextMenus.onClicked.addListener`.
    *   **Custom Protocol URL Construction**: This is a critical step. When a context menu item is clicked, the background script receives information about the context (e.g., the link URL). It extracts the relevant YouTube video URL and constructs a specialized URL using our custom protocol:
        *   `musicplayer-audio-extension` constructs: `musicplayerdl://audio/<encoded_youtube_url>`
        *   `musicplayer-video-extension` constructs: `musicplayerdl://video/<encoded_youtube_url>`
        *   The `<encoded_youtube_url>` part is the standard YouTube video URL, but encoded (using JavaScript's `encodeURIComponent` function) to ensure special characters are handled correctly within the URL structure.
    *   **Invoking the Protocol Handler**: The background script then instructs the browser to navigate to this newly constructed `musicplayerdl://` URL (e.g., using `chrome.tabs.create({ url: protocolUrl })`). The browser itself doesn't understand this protocol; it passes the request to the operating system.

### 2. Custom URL Protocol (`musicplayerdl://`) and OS Registration

*   **The Bridge**: The `musicplayerdl://` protocol acts as the bridge between the browser/web context and the local desktop application.
*   **Operating System Integration**: For this bridge to work, the operating system must know which application should handle URLs starting with `musicplayerdl://`. This is achieved through protocol handler registration.

*   **Windows Registration using PowerShell (`register_protocol.ps1`)**: 
    *   **Purpose**: To associate the `musicplayerdl://` protocol with the MusicPlayer executable on Windows systems, we provide a PowerShell script named `register_protocol.ps1`, typically located in the application's root directory.
    *   **Mechanism**: This script modifies the Windows Registry to create the necessary associations. Specifically, it operates under the `HKEY_CURRENT_USER\Software\Classes\musicplayerdl` key.
    *   **User-Specific**: By targeting `HKEY_CURRENT_USER` (HKCU), the script registers the protocol handler *only for the user running the script*. This approach avoids the need for elevated administrator privileges, making setup simpler and safer.
    *   **Configuration**: The script contains variables (`$ExecutablePath`, `$ProtocolName`) that must be correctly set to point to the final location of `MusicPlayer.exe` (e.g., within the `dist` folder after building) and the desired protocol name.
    *   **Execution**: The script needs to be run via PowerShell. Users might need to adjust their PowerShell execution policy temporarily (e.g., using `Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process`) to allow the script to run.
    *   **Key Registry Entry**: The most crucial registry value set by the script is under the `shell\open\command` subkey. It defines the command line that Windows executes when a `musicplayerdl://` link is activated. The value is formatted like `"C:\path\to\your\dist\MusicPlayer.exe" "%1"`, ensuring the full executable path is quoted and the incoming URL (`%1`) is also quoted and passed as the first argument to the application.
    *   **Result**: Once successfully executed, Windows knows to launch `MusicPlayer.exe` (and pass the URL) whenever a `musicplayerdl://` link is encountered by the browser or other applications.

*   **Registration Mechanism (Other OS)**: Similar registration mechanisms involving configuration files or system settings exist for macOS and Linux, though they are not detailed here.
*   **Launching the Application**: When the browser attempts to open a `musicplayerdl://` URL, the OS consults its protocol handler registrations, finds the association with `MusicPlayer.exe`, and launches the application. Crucially, the *entire* `musicplayerdl://...` URL is passed as a command-line argument to the launched `MusicPlayer.exe` process.

### 3. MusicPlayer Application Handling (`run.py` and Single Instance Logic)

The MusicPlayer application needs to be able to receive these incoming requests and handle them appropriately, ensuring only one instance of the application's UI is active. This logic is implemented within the application's main entry point, `musicplayer/run.py`, wrapping the standardized setup provided by the `qt_base_app` framework.

*   **Entry Point Logic (`run.py`)**: The sequence of operations in `run.py` is crucial:
    1.  **Define Application ID**: A unique string identifier is defined (e.g., `APPLICATION_ID = "MusicPlayer-SingleInstance"`).
    2.  **Early Argument Parsing**: *Before* any Qt objects are created or `qt_base_app.app.create_application` is called, the script checks `sys.argv` for command-line arguments.
        *   It looks specifically for an argument starting with `musicplayerdl://`.
        *   If found, it parses this argument to extract the `format_type` (e.g., "audio", "video") and the decoded `url`. This data is stored temporarily.
    3.  **Attempt Socket Connection**: A `QLocalSocket` is created, and an attempt is made to connect to the server name defined by `APPLICATION_ID`. A short timeout is used.
    4.  **Handle Existing Instance (Connection Succeeds)**: If the socket connects successfully, it means another MusicPlayer instance is already running and is listening on that ID.
        *   The currently executing script (the "subsequent" instance) formats the parsed `format_type` and `url` into a delimited string (e.g., `"audio|https://..."`).
        *   This string is sent through the connected `QLocalSocket` to the already running (first) instance.
        *   The subsequent instance script then immediately terminates using `sys.exit(0)`, preventing a duplicate window from opening.
    5.  **Handle First Instance (Connection Fails)**: If the socket connection fails (times out), it signifies that no other instance is running. This script is the "first" instance.
        *   **Framework Initialization**: The script proceeds to call `qt_base_app.app.create_application(...)`, passing necessary parameters like the main window class (`Dashboard`), application name, organization name, configuration paths, etc. This function initializes the `QApplication`, `SettingsManager`, `Logger`, creates the main window instance, and applies themes/styles. It returns the `app` (QApplication) and `window` (Dashboard) instances.
        *   **Setup Local Server**: *After* `create_application` returns, a `QLocalServer` is created. `server.listen(APPLICATION_ID)` is called, making this first instance listen for connections from potential subsequent instances.
        *   **Setup Listener**: A simple `QObject` subclass (e.g., `SingleInstanceListener`) is instantiated. This object defines a Qt signal, for example, `url_received = pyqtSignal(str, str)` (url, format_type).
        *   **Implement Connection Handling**: A function or method is defined to handle incoming connections detected by the `QLocalServer`. When the server's `newConnection` signal is emitted, this handler:
            *   Accepts the pending connection (`server.nextPendingConnection()`).
            *   Reads the data (the `"type|url"` string) sent by the subsequent instance from the socket.
            *   Parses the received string to extract the `url` and `format_type`.
            *   Emits the `listener.url_received` signal with the extracted `url` and `format_type`.
        *   **Connect Server Signal**: The `QLocalServer`'s `newConnection` signal is connected to the connection handling function described above.
        *   **Connect Listener Signal to Window**: The `listener.url_received` signal is connected to a specific slot method within the main `window` object (the `Dashboard` instance). This slot (e.g., `window.handle_protocol_url(url, format_type)`) is responsible for taking the URL and type and passing it to the appropriate page (YoutubePage) for processing.
        *   **Process Initial URL (If Any)**: If the script initially parsed a `musicplayerdl://` URL from its *own* command-line arguments (in step 2), the `window.handle_protocol_url(url, format_type)` method is called directly *now*, passing the initially parsed URL and type. This handles the case where the very first instance is launched via the protocol.
        *   **Run Application**: Finally, `qt_base_app.app.run_application(app, window)` is called, which shows the main window and starts the Qt event loop.

*   **Window Handling Slot (`Dashboard.handle_protocol_url`)**:
    *   **Purpose**: This method, implemented within the main `MusicPlayerDashboard` class (`dashboard.py`), acts as the central receiver for download requests initiated via the protocol handler.
    *   **Trigger**: It is designed to be connected directly to the `url_received` signal emitted by the `SingleInstanceListener` in `run.py`. It is also called directly by `run.py` if the *first* instance of the application is launched with a protocol URL argument.
    *   **Arguments**: It accepts two string arguments: `url` (the decoded YouTube/Bilibili URL) and `format_type` ("audio" or "video").
    *   **Responsibilities**:
        1.  **Logging**: Logs the reception of the URL and its type for debugging purposes.
        2.  **Page Lookup**: Retrieves the instance of `YoutubePage` from the dashboard's internal page registry (e.g., `self.pages['youtube_downloader']`).
        3.  **Method Invocation**: Checks if the `YoutubePage` instance exists and has the necessary method (e.g., `auto_add_download`). If both are present, it calls `youtube_page.auto_add_download(url, format_type)`, delegating the task of adding the download to the appropriate page.
        4.  **UI Navigation**: Switches the main content area to display the `YoutubePage` (`self.show_page('youtube_downloader')`) and updates the sidebar selection (`self.sidebar.set_selected_item('youtube_downloader')`) so the user immediately sees the download being added to the queue.
        5.  **Error Handling**: Includes checks and logs messages if the `YoutubePage` or its handler method cannot be found, preventing crashes.

*   **Youtube Page Handling (`YoutubePage.auto_add_download`)**:
    *   **Purpose**: This method within `YoutubePage` is responsible for the final steps of initiating a download requested via the protocol.
    *   It receives the `url` and `format_type` from the `Dashboard.handle_protocol_url` method.
    *   It interacts with the `VideoInput` component to populate the URL field visually, providing immediate feedback to the user.
    *   **Download Options Determination**: Based on the `format_type`:
        *   If `format_type` is "audio", it constructs the download options equivalent to selecting the "Audio", "HTTPS", "MP4" (container), and "Cookies" (using Firefox) toggles in the UI. This ensures a consistent audio download configuration.
        *   If `format_type` is "video", it likely constructs options equivalent to selecting the default video toggles (e.g., "Video", "720p", "MP4", "HTTPS", "Cookies"). (The exact default video options need confirmation).
    *   It triggers the `DownloadManager.add_download(url, options)` method, passing the URL and the determined download options dictionary. This initiates the metadata fetching and subsequent download process via `CLIDownloadWorker`.

## Summary Flow

1.  **User Action**: User right-clicks a YouTube link/page in Chrome.
2.  **Extension**: User selects "Download Audio (MusicPlayer)" or "Download Video (MusicPlayer)" from the context menu.
3.  **Extension**: The background script constructs `musicplayerdl://<type>/<encoded_url>`.
4.  **Browser**: Attempts to open the `musicplayerdl://` URL.
5.  **Operating System**: Sees the `musicplayerdl` protocol, looks up the registered handler (`MusicPlayer.exe`), and launches `MusicPlayer.exe`, passing the full URL as a command-line argument.
6.  **MusicPlayer `run.py` (New Instance)**: Starts. Parses command-line argument to get type and URL (if present).
7.  **MusicPlayer `run.py` (New Instance)**: Attempts `QLocalSocket` connection to `MusicPlayer-SingleInstance`.
8.  **Scenario A: First Instance (Connection Fails)**:
    *   Calls `create_application` -> gets `app`, `window`.
    *   Starts `QLocalServer` listening on `MusicPlayer-SingleInstance`.
    *   Sets up listener object and signal connections (`newConnection` -> handler -> `listener.url_received` -> `window.handle_protocol_url`).
    *   If URL was parsed initially, calls `window.handle_protocol_url` directly.
    *   Calls `run_application`.
9.  **Scenario B: Subsequent Instance (Connection Succeeds)**:
    *   Sends `"type|url"` message via the connected `QLocalSocket` to the first instance.
    *   Exits via `sys.exit(0)`.
10. **MusicPlayer (First Instance - Handler)**: If Scenario B occurred, the `QLocalServer`'s handler receives the connection/message, parses it, and emits `listener.url_received(url, type)`.
11. **MusicPlayer (First Instance - Window Slot)**: The `window.handle_protocol_url` slot receives the signal (or was called directly in Scenario A) and passes the `url`/`type` to the `YoutubePage`.
12. **MusicPlayer (`YoutubePage`)**: Receives the `url`/`type` and tells the `DownloadManager` to add the download.
13. **Result**: The download appears in the MusicPlayer queue. Only one UI instance is ever shown.
