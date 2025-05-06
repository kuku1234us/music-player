# MusicPlayerDL Best Quality Downloader

This Chrome extension allows you to download YouTube and Bilibili videos in the best available quality directly to your MusicPlayer application.

## Features

- Download videos from YouTube and Bilibili in the highest available quality
- Works with YouTube Shorts
- Adds a download button to the YouTube player interface
- Right-click context menu integration
- No quality or codec restrictions - gets the best possible version

## Installation

### Loading the Extension in Chrome

1. Download or clone this repository
2. Open Chrome and navigate to `chrome://extensions/`
3. Enable "Developer mode" by toggling the switch in the top right corner
4. Click "Load unpacked" and select the `musicplayerdl-best` folder
5. The extension should now be installed and active

### Requirements

- Google Chrome or Chromium-based browser
- MusicPlayer application installed on your system
- URL protocol handler registered (see below)

## Usage

### From YouTube/Bilibili Web Pages

1. Navigate to any YouTube or Bilibili video
2. Click the extension icon in your browser toolbar
3. The MusicPlayer application will launch and begin downloading the video

### From the Context Menu

1. Right-click on a YouTube or Bilibili video
2. Select "Best Quality MusicPlayerDL" from the context menu
3. The MusicPlayer application will launch and begin downloading

### From the YouTube Player

1. Play any YouTube video
2. Click the download button (↓★) in the YouTube player controls
3. The MusicPlayer application will launch and begin downloading

## URL Protocol Registration

For this extension to work, you need to have the MusicPlayer application registered to handle the `musicplayerdl://` protocol on your system. This should be set up when you install the MusicPlayer application.

## Troubleshooting

If the extension doesn't work:

1. Make sure the MusicPlayer application is installed
2. Verify the URL protocol handler is registered
3. Check if there are any errors in the Chrome DevTools console

## License

This extension is provided as-is under the same license as the MusicPlayer application.

## Privacy

This extension does not collect or transmit any personal data. It only processes video URLs locally to format them for the MusicPlayer application. 