# MusicPlayer Chrome Extension Integration

## Introduction

This document explains how the MusicPlayer Chrome extensions integrate with the main MusicPlayer desktop application. This system allows users to initiate downloads directly from YouTube within their browser, sending the request seamlessly to the MusicPlayer application running on their computer.

## Core Components and Workflow

The integration relies on several key components working together: the Chrome extensions themselves, a custom URL protocol (`musicplayerdl://`), operating system registration of this protocol, and the MusicPlayer application's handling of incoming requests.

### 1. Chrome Extensions

We provide three distinct Chrome extensions, each designed to trigger a specific type of download:

*   **`musicplayerdl-audio`**: Designed to trigger audio-only downloads.
*   **`musicplayerdl-video`**: Designed to trigger video downloads (configured for 720p MP4).
*   **`musicplayerdl-best`**: Designed to trigger best quality video downloads (no resolution limitation, highest available quality).

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
    *   **Context Menu Setup**: It utilizes the `chrome.contextMenus.create` API to dynamically add entries like "Audio MusicPlayerDL", "Video MusicPlayerDL", or "Best Quality MusicPlayerDL" to the browser's right-click context menu. These menu items are configured to appear specifically when the user right-clicks on links or relevant elements within YouTube pages.
    *   **Event Listening**: It actively listens for click events on the context menu items it created, using `chrome.contextMenus.onClicked.addListener`.
    *   **Custom Protocol URL Construction**: This is a critical step. When a context menu item is clicked, the background script receives information about the context (e.g., the link URL). It extracts the relevant YouTube video URL and constructs a specialized URL using our custom protocol:
        *   `musicplayerdl-audio` constructs: `musicplayerdl://audio/<encoded_youtube_url>`
        *   `musicplayerdl-video` constructs: `musicplayerdl://video/<encoded_youtube_url>`
        *   `musicplayerdl-best` constructs: `musicplayerdl://best/<encoded_youtube_url>`
        *   The `<encoded_youtube_url>` part is the standard YouTube video URL, but encoded (using JavaScript's `encodeURIComponent` function) to ensure special characters are handled correctly within the URL structure.
    *   **Invoking the Protocol Handler**: The background script then instructs the browser to navigate to this newly constructed `musicplayerdl://` URL (e.g., using `chrome.tabs.update({ url: protocolUrl })`). The browser itself doesn't understand this protocol; it passes the request to the operating system.

### 2. Custom URL Protocol (`musicplayerdl://`) and OS Registration

*   **The Bridge**: The `musicplayerdl://` protocol acts as the bridge between the browser/web context and the local desktop application.
*   **Operating System Integration**: For this bridge to work, the operating system must know which application should handle URLs starting with `musicplayerdl://`. This is achieved through protocol handler registration.

*   **Windows Registration**: 
    *   **Purpose**: To associate the `musicplayerdl://` protocol with the MusicPlayer executable on Windows systems.
    *   **Mechanism**: This is accomplished through registry files (`.reg`) and setup batch scripts that modify the Windows Registry to create the necessary associations.
    *   **Key Registry Entry**: The most crucial registry value is under the `HKEY_CLASSES_ROOT\musicplayerdl\shell\open\command` key. It defines the command line that Windows executes when a `musicplayerdl://` link is activated. The value is formatted like `"D:\projects\musicplayer\run.py" "%1"`, ensuring the full path is quoted and the incoming URL (`%1`) is also quoted and passed as the first argument to the application.
    *   **Result**: Once successfully registered, Windows knows to launch the MusicPlayer application (and pass the URL) whenever a `musicplayerdl://` link is encountered by the browser or other applications.

*   **Protocol URL Structure**: 
    *   The protocol URLs follow a consistent format: `musicplayerdl://format/encoded_url`
    *   The forward slash ("/") acts as a separator between the format type and the encoded URL
    *   This structure is preserved when the operating system passes the URL to our application
    *   The application's URL parser is designed to extract the components based on this format

### 3. MusicPlayer Application Handling (`run.py` and Single Instance Logic)

The MusicPlayer application needs to be able to receive these incoming requests and handle them appropriately, ensuring only one instance of the application's UI is active. This logic is implemented within the application's main entry point, `run.py`.

*   **Entry Point Logic (`run.py`)**: The sequence of operations in `run.py` is crucial:
    1.  **Define Application ID**: A unique string identifier is defined (e.g., `APPLICATION_ID = "MusicPlayer-SingleInstance"`).
    2.  **Command-Line Argument Check**: The script checks `sys.argv` for command-line arguments that could contain protocol URLs.
    3.  **Attempt Socket Connection**: A `QLocalSocket` is created, and an attempt is made to connect to the server name defined by `APPLICATION_ID`.
    4.  **Handle Existing Instance (Connection Succeeds)**: If the socket connects successfully, it means another MusicPlayer instance is already running.
        *   The current instance sends the raw command line argument (the protocol URL) to the running instance through the socket.
        *   The current instance then exits immediately, preventing duplicate windows.
    5.  **Handle First Instance (Connection Fails)**: If no other instance is running, the current instance becomes the "main" instance.
        *   It parses the protocol URL (if present) to extract the format type and target URL.
        *   It initializes the application, creates the main window, and sets up a `QLocalServer` to listen for future instances.
        *   It establishes a listener mechanism to handle incoming connections from future instances.
        *   It processes any initial protocol URL it might have received on launch.

*   **Protocol URL Parser (`parse_protocol_url`)**: A dedicated function parses `musicplayerdl://` URLs:
    *   It handles various format types: `audio/`, `video/`, and `best/` prefixes.
    *   It correctly decodes the URL component using `urllib.parse.unquote`.
    *   It returns the format type and target URL for processing.

*   **Connection Handler**: The running instance's server has a handler function that:
    *   Accepts incoming connections from new instances.
    *   Reads the raw protocol URL data sent through the socket.
    *   Parses the URL to extract the format type and target URL.
    *   Emits a signal with the extracted URL and format type for the application to handle.

*   **Window Handling Slot (`Dashboard.handle_protocol_url`)**:
    *   This method receives the protocol URL data (format type and target URL).
    *   It locates the YouTube download page and tells it to add a download with the specified parameters.
    *   It navigates the UI to show the YouTube download page so users can see their download being processed.

*   **Youtube Page Handling (`YoutubePage.auto_add_download`)**:
    *   This method processes the download request with the appropriate format type.
    *   It determines download options based on the format type:
        *   `audio`: Uses the audio preset (audio-only, M4A format)
        *   `video`: Uses the 720p video preset (720p resolution, MP4 format)
        *   `best`: Uses the best video preset (highest quality available, no resolution limit)
    *   It initiates the download through the download manager.

## Download Options

Each format type corresponds to specific download presets defined in `Yt_DlpModel.py`:

1. **Audio Preset (`audio_default`)**:
   * Audio-only format
   * Uses HTTPS protocol
   * M4A container format
   * Uses browser cookies for authentication when needed

2. **Video Preset (`video_720p_default`)**:
   * 720p resolution
   * Uses HTTPS protocol
   * MP4 container format
   * Prefers AVC codec for better device compatibility
   * Uses browser cookies when needed

3. **Best Quality Preset (`best_video_default`)**:
   * No resolution limitation - gets the highest quality available
   * Uses HTTPS protocol
   * No codec restrictions to ensure best possible quality
   * Uses browser cookies when needed

## Summary Flow

1.  **User Action**: User right-clicks a YouTube link/page in Chrome.
2.  **Extension**: User selects one of the MusicPlayerDL download options from the context menu (Audio, Video, or Best Quality).
3.  **Extension**: The background script constructs a protocol URL like `musicplayerdl://format/encoded_url`.
4.  **Browser**: Attempts to open the protocol URL.
5.  **Operating System**: Sees the protocol, looks up the registered handler, and launches the MusicPlayer application, passing the URL as a command-line argument.
6.  **MusicPlayer (New Instance)**: Starts and checks if another instance is already running.
7.  **Scenario A: First Instance**:
    *   Parses the protocol URL to extract format type and target URL.
    *   Initializes the application and sets up server to listen for future instances.
    *   Passes the extracted data to the appropriate handler to start the download.
8.  **Scenario B: Subsequent Instance**:
    *   Sends the raw protocol URL to the first instance.
    *   Exits immediately.
9.  **First Instance (Server)**: Receives data from subsequent instances, parses it, and processes downloads.
10. **Result**: The download appears in the MusicPlayer queue, with the UI showing the YouTube downloader page. Only one application instance is ever shown.

## Browser Compatibility Notes

1. **Chrome/Edge**: These browsers work seamlessly with the protocol handlers, passing the URL to the registered application.

2. **Firefox Considerations**: Firefox has additional security prompts when using custom protocols. Users need to confirm they want to open the external application.

3. **Protocol Registration**: For the extensions to work, the protocol handler must be properly registered on the user's system. This is typically done during application installation or through provided setup scripts.
