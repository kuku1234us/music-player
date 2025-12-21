# MusicPlayerDL Video Chrome Extension

This Chrome extension adds a right-click context menu option to download YouTube and Bilibili videos using the **MusicPlayer** application.

## Features

- **Context menu integration**: Right-click on videos to access download options
- **Toolbar button**: Click the extension icon when viewing a video to download it
- **Video MusicPlayerDL**: Downloads video with default 720p quality
- **URL cleansing**: Automatically removes unnecessary parameters from video URLs
- **Protocol handler integration**: Seamless video downloading

## Installation

### Prerequisites

- Make sure the MusicPlayer application is installed and working
- Ensure `MusicPlayer.exe` is available (e.g. under `dist\MusicPlayer.exe` when building locally)

### Extension Installation

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" using the toggle in the top-right corner
3. Click "Load unpacked" and select the `musicplayerdl-video` folder
4. Verify the extension is enabled and appears in your extensions list

### Protocol Handler Registration

Ensure that the `musicplayerdl://` protocol handler is registered on your system.
You can run `setup.bat` in this folder to register the protocol for the current user.

## Usage

### Via Context Menu
1. Navigate to a YouTube or Bilibili video
2. Right-click on the video
3. Select "Video MusicPlayerDL"
4. MusicPlayer will launch and automatically add the video to the download queue

### Via Toolbar Button
1. Navigate to a YouTube or Bilibili video page
2. Click the MusicPlayerDL Video extension icon in the toolbar
3. MusicPlayer will launch and automatically add the current video to the download queue

## Troubleshooting

- If the context menu doesn't appear, make sure you're right-clicking on a video element
- If MusicPlayer doesn't launch, verify the protocol handler is registered correctly
- Check that the path to `MusicPlayer.exe` in the protocol handler registry matches your installation

## For Developers

### Extension Structure

- `manifest.json`: Extension configuration
- `background.js`: Handles context menu creation, toolbar button clicks, and URL processing
- `content.js`: Helps with video element detection

### Protocol Handler

The extension uses a custom URL protocol (`musicplayerdl://`) to launch the application:
- `musicplayerdl://video/[encoded-url]`: For video downloads

## License

See the main MusicPlayer application repository for license information.

## Related Extensions

Check out the companion extension **MusicPlayerDL Audio Downloader** for audio-only downloads. 