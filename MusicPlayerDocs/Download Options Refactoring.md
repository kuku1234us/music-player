# Download Options Refactoring

## Introduction

This document outlines a comprehensive plan for refactoring how our application generates and manages yt-dlp download options. Currently, our system has two separate paths for initiating downloads: manual URL entry via the YouTube page UI, and automated requests from Chrome extensions. These paths use different code to generate the same type of data (download options), which creates unnecessary duplication and potential for inconsistencies.

The goal of this refactoring is to centralize all download option generation logic in one place, specifically in the `YtDlpModel` class, following the principle of separation of concerns. This will make our code more maintainable, easier to understand, and more flexible for future enhancements.

## 2025-12 Update: StreamPicker and the Two-Phase YouTube Download Pipeline

During real-world testing, we discovered that YouTube behaves differently depending on what we ask yt-dlp to do. A **format listing** (`yt-dlp -F` or `--dump-single-json`) can show “nice” HTTPS/DASH formats at the correct resolution, but the **actual media download** can fail (403) unless we provide additional signals (cookies + a JS runtime for challenge solving).

This produced a common bug: **the app “works”, but chooses the wrong stream** (e.g., drifting to 1080p, or falling back to slow m3u8). The fix is not a longer format selector string; the fix is a clearer separation of responsibilities:

1. **Pick formats deterministically (no cookies)**: Probe formats with no cookies (same intent as `-F`), then choose explicit format IDs like `298+140`.
2. **Download reliably (cookies + JS runtime)**: Use those explicit IDs while downloading with:
   - `--cookies-from-browser firefox`
   - `--js-runtimes node:<path>` (or deno if available)

Think of this like “selecting a product from a catalog” versus “actually paying for it”. Browsing might be easy, but checkout requires more authentication steps. We model that explicitly in code.

```
┌──────────────────────────┐
│ YtDlpModel (UI / Preset) │  (resolution/https/m4a/subtitles)
└─────────────┬────────────┘
              v
┌──────────────────────────┐
│ StreamPicker (no cookies)│  yt-dlp --dump-single-json (no cookies)
│ chooses explicit IDs     │  e.g. "298+140-drc"
└─────────────┬────────────┘
              v
┌──────────────────────────┐
│ CLIDownloadWorker         │  yt-dlp download with:
│ cookies + JS runtime      │  --cookies-from-browser firefox
│                            │  --js-runtimes node:<path>
└──────────────────────────┘

## Current Implementation Analysis

### Two Separate Paths

Our application currently handles download option generation in two different ways:

1. **Manual URL Entry (via UI)**
   - When a user enters a URL in the YouTube downloader page, the application:
     - Collects format preferences from UI controls (resolution, audio format, HTTPS, etc.)
     - Uses `VideoInput.get_format_options()` to gather these preferences
     - Calls `YtDlpModel.generate_format_string()` to create format options
     - Passes these options to the download manager

2. **Chrome Extensions (via Protocol Handler)**
   - When a Chrome extension triggers a download:
     - The application receives a URL and format type ("audio" or "video")
     - `YoutubePage.auto_add_download()` contains hardcoded format strings for each type
     - These hardcoded options are passed directly to the download manager
   - Currently, we have two Chrome extensions:
     - One for downloading audio only
     - One for downloading 720p video

### Issues with Current Approach

1. **Duplication of Logic**: Format string generation exists in two places
2. **Inconsistent Updates**: Changes to format options need to be made in multiple places
3. **Violation of Separation of Concerns**: The controller (YoutubePage) contains model logic (format strings)
4. **Reduced Flexibility**: Hardcoded options are difficult to modify or extend
5. **Limited Extension Support**: Adding a new extension option requires hardcoding new format strings
6. **Resolution Handling Issues**: Current implementation only checks video height, not accounting for portrait videos
7. **Codec Compatibility Issues**: Current implementation excludes AV1 but doesn't specifically select AVC for optimal mobile compatibility

## Implementation Milestones

Below is a checklist of all the milestones we need to complete for this refactoring:

- [x] **Update YtDlpModel Class**
  - [x] Add `prefer_best_video` parameter to `generate_format_string()`
  - [x] Add `prefer_avc` parameter to `generate_format_string()`
  - [x] Implement improved resolution handling for portrait/landscape videos
  - [x] Implement AVC codec preference for better mobile compatibility
  - [x] Add `get_preset_options()` method for predefined format sets
  - [x] Create presets for audio_default, video_720p_default, best_video_default

- [x] **Update VideoInput Component**
  - [x] Add "Best" toggle button to resolution options
  - [x] Update `get_format_options()` method to handle the new option
  - [x] Add compatibility layer for different versions of `generate_format_string()`
  - [x] Add helper method `set_format_best_video()`

- [x] **Refactor YoutubePage**
  - [x] Update `auto_add_download()` to use YtDlpModel presets
  - [x] Add support for "best-video" format type
  - [x] Remove hardcoded format strings

- [x] **Create Tests**
  - [x] Write tests for YtDlpModel presets
  - [x] Write tests for resolution handling (portrait & landscape)
  - [x] Write tests for codec selection
  - [x] Write tests for the refactored auto_add_download method

- [x] **Test Full Download Flow**
  - [x] Test manual URL entry with all resolution options
  - [x] Test with portrait videos *(Fixed by implementing yt-dlp's `?` operator for resolution selection)*
  - [x] Test with landscape videos
  - [x] Test audio downloads
  - [x] Test protocol handler with existing extensions
  - [x] Verify AVC codec selection for 720p/1080p

- [ ] **Create New Chrome Extension**
  - [ ] Create extension for best quality downloads
  - [ ] Configure to use "best-video" format type
  - [ ] Design appropriate icon
  - [ ] Test with various YouTube videos
  - [ ] Package for distribution

- [ ] **Documentation and Review**
  - [ ] Update comments in code
  - [ ] Update docstrings
  - [ ] Update user documentation
  - [ ] Conduct code review
  - [ ] Address review feedback

- [ ] **Deploy**
  - [ ] Update main branch with changes
  - [ ] Release new Chrome extension

## Refactoring Plan

### Step 1: Add Format Presets to YtDlpModel

First, we'll enhance the `YtDlpModel` class to include predefined format presets that can be easily reused. These presets are primarily designed to support our Chrome extensions, each of which provides a different download option in the browser's context menu.

```python
@staticmethod
def get_preset_options(preset_name):
    """
    Return predefined option sets for common download scenarios.
    
    Args:
        preset_name (str): Name of the preset to retrieve 
                          ('audio_default', 'video_720p_default', 'best_video_default')
    
    Returns:
        dict: Dictionary containing format options for the specified preset
    """
    if preset_name == "audio_default":
        return YtDlpModel.generate_format_string(
            resolution=None,  # Audio only
            use_https=True,
            use_m4a=True,
            subtitle_lang=None,
            use_cookies=False  # Deprecated/ignored; download pipeline enforces cookies+JS runtime for YouTube
        )
    elif preset_name == "video_720p_default":
        return YtDlpModel.generate_format_string(
            resolution=720,
            use_https=True,
            use_m4a=True,
            subtitle_lang=None,
            use_cookies=False,  # Deprecated/ignored
            prefer_avc=True  # Specifically prefer AVC codec for better device compatibility
        )
    elif preset_name == "best_video_default":
        # This preset doesn't limit resolution, getting the best quality available
        return YtDlpModel.generate_format_string(
            resolution=None,  # No resolution limit
            use_https=True,
            use_m4a=True,
            subtitle_lang=None,
            use_cookies=False,  # Deprecated/ignored
            prefer_best_video=True,  # Indicates we want best video
            prefer_avc=False   # Don't restrict codecs for best quality
        )
    else:
        print(f"Warning: Unknown preset '{preset_name}'. Returning empty options.")
        return {}
```

We'll need to update the `generate_format_string` method to handle the improved resolution handling and codec selection:

```python
@staticmethod
def generate_format_string(resolution=None, use_https=True, use_m4a=True, 
                          subtitle_lang=None, use_cookies=False, 
                          prefer_best_video=False, prefer_avc=False):
    """
    Generate the yt-dlp format string based on the provided parameters.
    
    Args:
        resolution (int, optional): Target video resolution (720, 1080, None for audio only or best)
        use_https (bool): Whether to prefer HTTPS protocol
        use_m4a (bool): Whether to prefer M4A/MP4 formats
        subtitle_lang (str, optional): Language code for subtitles (e.g., 'en', 'es', etc.) or None to disable
        use_cookies (bool): Deprecated/ignored. Cookies are enforced in the download pipeline.
        prefer_best_video (bool): If True, prefer best video quality regardless of resolution
        prefer_avc (bool): If True, prefer AVC codec (H.264) for better device compatibility
        
    Returns:
        dict: Dictionary with format options for yt-dlp
    """
    format_options = {}
    
    # ... existing code ...

    # Important note for new developers:
    #
    # The `format` field we build here is a selector string. It describes our intent
    # (resolution / protocol / container), but yt-dlp may still “choose differently”
    # depending on which URLs are actually downloadable in this session.
    #
    # For YouTube, we therefore attach a small "stream_picker" hint object. The
    # download worker can probe formats WITHOUT cookies and replace the selector
    # with explicit format IDs (e.g. "298+140") before starting the actual download.
    format_options["stream_picker"] = {
        "target_height": resolution,
        "target_width": resolution,  # used for portrait matching
        "prefer_best_video": prefer_best_video,
        "prefer_protocol": "https" if use_https else "any",
        "prefer_m4a": use_m4a,
        "prefer_avc": prefer_avc,
    }
    
    # Determine codec filtering based on parameters
    codec_filter = ""
    if prefer_avc:
        # Prefer AVC codec (H.264) for better device compatibility
        codec_filter = "[vcodec^=avc]"
        print(f"DEBUG: Using AVC codec filter for better compatibility")
    
    if resolution and not prefer_best_video:
        # Resolution-specific format with smarter handling for portrait/landscape videos
        print(f"DEBUG: Generating video format with target resolution: {resolution}p")
        
        # For 720p/1080p with aspect ratio awareness
        # Instead of using height<=?, we'll use quality selection algorithm
        # This better handles both portrait and landscape videos
        format_str = f"bestvideo[height<={resolution}]"
        
        # Add codec preference if specified
        if codec_filter:
            format_str += codec_filter
            
        if use_https:
            format_str += "[protocol=https]"
        if use_m4a:
            format_str += "[ext=mp4]"
        
        # Audio format
        audio_str = "bestaudio"
        if use_https:
            audio_str += "[protocol=https]"
        if use_m4a:
            audio_str += "[ext=m4a]"
        
        # Fall back options - incorporate codec preference
        fallback = f"best[height<={resolution}]"
        if codec_filter:
            fallback += codec_filter
        if use_https:
            fallback += "[protocol=https]"
        if use_m4a:
            fallback += "[ext=mp4]"
        
        # Complete format string
        format_str = f"{format_str}+{audio_str}/{fallback}/best"
        format_options["format"] = format_str
        
        # Force MP4 output if m4a is selected
        if use_m4a:
            format_options["merge_output_format"] = "mp4"
            
        print(f"DEBUG: Resolution-specific format string: {format_str}")
            
    elif prefer_best_video:
        # Best video format - no resolution limiting or codec restriction
        print(f"DEBUG: Generating best video format without codec restrictions")
        format_str = "bestvideo"  # No codec filtering for best quality
        if use_https:
            format_str += "[protocol=https]"
        if use_m4a:
            format_str += "[ext=mp4]"
        
        # Audio format
        audio_str = "bestaudio"
        if use_https:
            audio_str += "[protocol=https]"
        if use_m4a:
            audio_str += "[ext=m4a]"
        
        # Fall back options - no codec filtering
        fallback = "best"  # Just use best available
        if use_https:
            fallback += "[protocol=https]"
        if use_m4a:
            fallback += "[ext=mp4]"
        
        # Complete format string
        format_str = f"{format_str}+{audio_str}/{fallback}/best"
        format_options["format"] = format_str
        
        # Force MP4 output if m4a is selected
        if use_m4a:
            format_options["merge_output_format"] = "mp4"
            
        print(f"DEBUG: Best video format string: {format_str}")
    else:
        # Audio only format
        print(f"DEBUG: Generating audio-only format")
        format_str = "bestaudio"
        if use_https:
            format_str += "[protocol=https]"
        if use_m4a:
            format_str += "[ext=m4a]"
            format_options["merge_output_format"] = "m4a"
        else:
            format_str += "/best"
        
        format_options["format"] = format_str
            
        print(f"DEBUG: Audio-only format string: {format_str}")
    
    # ... rest of existing code ...
    
    return format_options
```

### Step 2: Refactor the auto_add_download Method

Next, we'll modify the `auto_add_download` method in the `YoutubePage` class to use our new preset functionality. We'll expand it to handle our three Chrome extension types:

```python
def auto_add_download(self, url: str, format_type: str):
    """
    Adds a download initiated via the protocol handler.
    
    Args:
        url (str): URL to download from
        format_type (str): Type of media to download ('audio', 'video', or 'best-video')
    """
    # Use logger
    self.logger.info(self.__class__.__name__, f"Auto adding download: URL={url}, Type={format_type}")
    
    # 1. Update the VideoInput field visually
    if hasattr(self.video_input, 'set_url'):
        self.video_input.set_url(url)
    else:
        self.logger.warning(self.__class__.__name__, 
                           "Cannot update VideoInput URL field.")
    
    # 2. Determine download options using YtDlpModel presets
    if format_type == "audio":
        self.logger.info(self.__class__.__name__, 
                        "Using audio_default preset for protocol download.")
        options = YtDlpModel.get_preset_options("audio_default")
    elif format_type == "video":
        self.logger.info(self.__class__.__name__, 
                        "Using video_720p_default preset for protocol download.")
        options = YtDlpModel.get_preset_options("video_720p_default")
    elif format_type == "best-video":
        self.logger.info(self.__class__.__name__, 
                        "Using best_video_default preset for protocol download.")
        options = YtDlpModel.get_preset_options("best_video_default")
    else:
        self.logger.error(self.__class__.__name__, 
                         f"Unknown format_type '{format_type}'. Cannot determine options.")
        return  # Don't proceed if type is unknown

    # 3. Get output directory from settings (unchanged)
    output_dir = self.settings.get(YT_DOWNLOAD_DIR_KEY, DEFAULT_YT_DOWNLOAD_DIR, SettingType.PATH)
    output_dir_str = str(output_dir)
    
    # Validate the directory (unchanged)
    if not output_dir_str or not os.path.isdir(output_dir_str):
        self.logger.error(self.__class__.__name__, 
                         f"Download directory '{output_dir_str}' is invalid or missing.")
        return
    
    # 4. Call DownloadManager
    self.logger.info(self.__class__.__name__, 
                    f"Adding download: URL={url}, Dir={output_dir_str}")
    self.download_manager.add_download(url, options, output_dir_str)
```

### Step 3: Add Tests for the New Functionality

It's important to ensure our refactoring doesn't break existing functionality. We'll create tests for both the new preset mechanism and the refactored auto_add_download method:

```python
def test_yt_dlp_model_presets():
    """Test that YtDlpModel presets return the expected options."""
    # Test audio preset
    audio_options = YtDlpModel.get_preset_options("audio_default")
    assert audio_options is not None
    assert 'format' in audio_options
    assert audio_options['format'].startswith('bestaudio')
    
    # Test 720p video preset
    video_options = YtDlpModel.get_preset_options("video_720p_default")
    assert video_options is not None
    assert 'format' in video_options
    assert '720' in video_options['format']
    assert 'vcodec^=avc' in video_options['format']  # Should specify AVC codec
    
    # Test best video preset
    best_video_options = YtDlpModel.get_preset_options("best_video_default")
    assert best_video_options is not None
    assert 'format' in best_video_options
    assert 'bestvideo' in best_video_options['format']
    assert 'vcodec' not in best_video_options['format']  # Should NOT limit codec
    
    # Test unknown preset
    unknown_options = YtDlpModel.get_preset_options("nonexistent_preset")
    assert unknown_options == {}
```

### Step 4: Chrome Extension Updates

While this document focuses on the application code refactoring, we'll also need to create a third Chrome extension that uses the "best-video" format type. Here's a brief overview of how this would work:

1. **Create a new Chrome extension** similar to our existing ones
2. Configure it to send the `best-video` format type to our application
3. Update the manifest to include appropriate context menu entries
4. Design an icon that indicates "best quality" to differentiate it from our 720p extension

This approach ensures all three options (audio, 720p video, best video) appear at the top level of Chrome's context menu without requiring nested menus.

### Step 5: Update Documentation

Finally, we'll update the relevant documentation to reflect our changes:

1. Add comments to the `YtDlpModel` class explaining:
   - The improved resolution handling for both portrait and landscape videos
   - The codec selection strategy (AVC for compatibility vs. unrestricted for best quality)
2. Update docstrings for the modified methods
3. Update any user-facing documentation that references the download options
4. Document the new Chrome extension and its setup process

## Benefits of This Refactoring

This refactoring provides several important benefits:

1. **Improved Separation of Concerns**: All format generation logic now resides in the model layer where it belongs, not in the UI controller.

2. **Reduced Code Duplication**: We eliminate duplicate format generation logic, making the codebase more maintainable.

3. **Enhanced Flexibility**: Adding new download presets becomes a simple task of adding them to the `get_preset_options` method, without modifying controller code.

4. **Better Testability**: Centralized format logic is easier to test comprehensively.

5. **Easier Maintenance**: When yt-dlp changes or we need to update our format strings, changes only need to be made in one place.

6. **Improved User Experience**: By adding a third "best quality" option, we give users more choices without complicating the context menu structure.

7. **Better Video Format Handling**: The improved resolution handling accommodates both portrait and landscape videos.

8. **Improved Device Compatibility**: Using AVC codec for 720p videos ensures better compatibility with mobile devices like iPhones.

## Potential Future Enhancements

Once this refactoring is complete, several enhancements become easier:

1. **User-Configurable Presets**: Allow users to create and save their own download presets.

2. **Preset Sharing**: Implement functionality to export and import download presets.

3. **Dynamic Resolution Selection**: Allow Chrome extensions to specify exact resolution rather than just preset types.

4. **Format Auto-Detection**: Analyze the URL to suggest the most appropriate preset automatically.

5. **More Extension Types**: We could easily add more extensions for specific needs (e.g., audio with subtitles, specific audio formats, etc.)

6. **Advanced Codec Selection**: Add more granular codec preferences based on playback device.

7. **Context-Aware Downloads**: Automatically detect whether a video is portrait or landscape and optimize format accordingly.

## Conclusion

By centralizing our download options generation in the `YtDlpModel` class, we significantly improve the architecture of our application while enabling a new "best quality" download option via a third Chrome extension. The refactoring addresses both architectural issues and practical concerns like aspect ratio handling and codec compatibility.

This refactoring exemplifies good software design principles: separation of concerns, DRY (Don't Repeat Yourself), and encapsulation, while also improving the practical user experience through enhanced media compatibility.

Remember to thoroughly test each step of the implementation, especially with both portrait and landscape videos, to ensure we don't introduce regressions in this critical feature of our application.
