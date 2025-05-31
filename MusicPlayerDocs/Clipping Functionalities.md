# Introduction

The media clipping functionality allows users to easily cut out unwanted portions from the currently playing audio or video file. This feature enables users to create shorter, more focused clips from their media directly within the application.

**Supported Media Types:**

- **Audio files:** MP3, AAC, FLAC, Opus, Vorbis, ALAC, PCM formats
- **Video files:** H.264, H.265/HEVC, VP9, and other FFmpeg-supported codecs

The system automatically detects the media type and applies the optimal processing approach:

- **Audio:** Sample-accurate cutting with audio-optimized encoding
- **Video:** Keyframe-aware adaptive processing for optimal speed and quality balance

# Hotkeys and Usage

The clipping process is controlled by three primary hotkeys:

**Important:** These markers are temporary and stored only in memory for the currently loaded media. They will be reset automatically if you load a new media file or restart the application.

- **`b` - Mark Beginning:**

  - When a media file is playing, pressing the `b` key marks the current playback position as the beginning of a new segment.
  - This creates a pending begin marker that will be used when you press `e` to define the end of the segment.

- **`e` - Mark End:**

  - Pressing the `e` key marks the current playback position as the end of the current segment.
  - This finalizes a segment using the pending begin marker and creates a new segment in the list.
  - The "End" point must be after the "Beginning" point. If an "End" point is marked before the "Beginning" point, a warning will be logged.

- **`Ctrl+s` - Save Clipped Media:**
  - This hotkey becomes active once at least one complete segment has been defined (both begin and end markers).
  - Pressing `Ctrl+s` initiates the clipping process using all defined segments and saves the result to a new file.
  - Multiple segments will be concatenated into a single output file.

# Visual Changes to Timeline

To provide clear visual feedback to the user, the player timeline will be updated as segments are defined:

- **Pending Begin Marker:** When `b` is pressed, a green marker appears on the timeline showing the pending beginning point.
- **Defined Segments:** When `e` is pressed, the pending marker is converted into a segment, visually represented as a highlighted region on the timeline.
- **Multiple Segments:** Users can define multiple non-contiguous segments, each displayed as separate highlighted regions.
- **Marker Interaction:** Users can click on markers or segments on the timeline to remove them.
- **Unwanted Portions:** Areas not covered by segments are visually dimmed to indicate they will be excluded from the clip.

# Clipping Mechanism

The actual clipping of the media file is handled by the `ClippingManager` model (`music_player.models.ClippingManager`). This manager is a singleton responsible for:

- **Multi-Segment State Management:** It keeps track of:

  - `_current_media_path`: The media file being processed
  - `_pending_begin_marker_ms`: Temporary begin marker (when `b` is pressed)
  - `_segments`: List of finalized segments `[(start_ms, end_ms), ...]`

- **Signaling Updates:** It emits a `markers_updated(media_path, pending_begin_ms, segments)` signal whenever the markers or segments change. The UI listens to this signal to redraw the timeline.

- **Filename Generation:**

  - A new media file is created for the clipped content
  - The original file remains untouched
  - New filename format: `originalname_clipped.ext`
  - If that exists: `originalname_clipped_1.ext`, `originalname_clipped_2.ext`, etc.
  - Example: `MySong.mp3` → `MySong_clipped.mp3`

- **Adaptive Processing Pipeline:**

  The system automatically detects media type and applies the appropriate processing:

  **Audio Processing:**

  - **Sample-Accurate Cutting:** Audio doesn't have keyframes, so precise cutting is used
  - **Audio-Optimized Encoding:** Uses codec-specific quality settings (VBR for MP3, CRF for others)
  - **Format Preservation:** Maintains original codec, sample rate, and channel configuration
  - **High-Quality Processing:** Optimized for audio quality over processing speed

  **Video Processing (Keyframe-Aware):**

  - **Option A - Keyframe Snapping:** When start point is within 0.4s of a keyframe
    - Snaps to nearest keyframe for instant stream copy processing
    - Reports time adjustment to user
  - **Option B - Minimal Re-encoding:** When start point is far from keyframes
    - Re-encodes only the beginning portion (start to first keyframe)
    - Stream copies the remainder for efficiency
    - Maintains original codec and quality settings
  - **Option C - Unsupported Codec Fallback:** When codec can't be re-encoded
    - Enhanced keyframe snapping with extended search range
    - Prefers backward snapping to avoid content loss
    - Uses pure stream copy for entire segment

  **Multi-Segment Processing:**

  - Each segment is processed individually using the appropriate method
  - Segments are then concatenated into a single output file
  - Mixed processing methods are supported (some snapped, some re-encoded)
  - Temporary files are automatically cleaned up

- **Error Handling:** Comprehensive error handling with fallback options:

  - ffmpeg/ffprobe not found detection
  - Codec compatibility verification
  - Graceful fallback to basic encoding when needed
  - Detailed logging for troubleshooting

- **Signal Emission:**
  - `clip_successful(original_path, clipped_path)` on success
  - `clip_failed(original_path, error_message)` on failure

## Post-Clipping Behavior **(COMPLETED)**

Once the clipping process completes successfully:

- **Automatic Mode Switch:** Player switches from playlist mode to single file mode
- **Automatic Media Loading:** The newly created clipped file is automatically loaded
- **Immediate Playback:** Playback starts immediately from the beginning of the clipped content
- **Timeline Reset:** All clipping markers are cleared for the new clipped media
- **Focus Management:** Player regains focus to ensure continued hotkey functionality
- **State Consistency:** Player's internal state is updated to reference the new clipped file

This ensures a seamless user experience where the result of the clipping operation is immediately available for playback and further editing.

## Data Structure for Markers

**Current Multi-Segment Implementation:**

```python
self._current_media_path: Optional[str] = None
self._pending_begin_marker_ms: Optional[int] = None
self._segments: List[Tuple[int, int]] = []
```

- `_current_media_path`: Path of the media file being processed
- `_pending_begin_marker_ms`: Temporary begin marker (set by `b` key)
- `_segments`: List of finalized segments `(start_ms, end_ms)`

**Signal Structure:**

```python
markers_updated = pyqtSignal(str, object, list)  # (media_path, pending_begin_ms, segments)
clip_successful = pyqtSignal(str, str)  # (original_path, clipped_path)
clip_failed = pyqtSignal(str, str)  # (original_path, error_message)
```

This structure allows users to define multiple non-contiguous segments from a single media file, which are processed and merged into a single output file.

## Implementation Status

### Core Functionality ✅ COMPLETED

- [x] Singleton ClippingManager implementation
- [x] Multi-segment state management with `_pending_begin_marker_ms` and `_segments` list
- [x] Media type detection (audio/video/unknown)
- [x] Filename generation with `_clipped` suffix and conflict resolution
- [x] Signal emission for UI updates and completion status

### Audio Support ✅ COMPLETED

- [x] Audio codec detection and analysis
- [x] Sample-accurate audio clipping
- [x] Audio-optimized encoding with format-specific quality settings
- [x] Support for MP3, AAC, FLAC, Opus, Vorbis, ALAC, PCM formats

### Video Support ✅ COMPLETED

- [x] Adaptive keyframe-aware processing (Options A, B, C)
- [x] Video codec detection and compatibility checking
- [x] Multi-phase minimal re-encoding for precision
- [x] Enhanced keyframe snapping for unsupported codecs
- [x] Codec matching for seamless concatenation

### UI Integration ✅ COMPLETED

- [x] Timeline visualization of markers and segments
- [x] Hotkey implementation (`b`, `e`, `Ctrl+s`)
- [x] Visual feedback for pending markers and defined segments
- [x] Post-clipping automatic loading and playback

### Multi-Segment Processing ✅ COMPLETED

- [x] Segment overlap detection and merging
- [x] Individual segment processing with per-segment strategy selection
- [x] Multi-segment concatenation
- [x] Temporary file management and cleanup

### Error Handling ✅ COMPLETED

- [x] Comprehensive error detection and reporting
- [x] Graceful fallback options
- [x] Detailed logging throughout the process
- [x] User-friendly error messages

## Testing Recommendations

### Audio Testing

- [ ] Test various audio formats (MP3, AAC, FLAC, etc.)
- [ ] Verify sample-accurate cutting
- [ ] Test long audio files (60+ minutes)
- [ ] Verify audio quality preservation

### Video Testing

- [ ] Test keyframe snapping scenarios (within 0.4s threshold)
- [ ] Test minimal re-encoding scenarios (beyond 0.4s threshold)
- [ ] Test unsupported codec fallback
- [ ] Test various video formats (H.264, H.265, VP9, etc.)

### Multi-Segment Testing

- [ ] Test single segment processing
- [ ] Test multiple non-overlapping segments
- [ ] Test overlapping segments (should merge automatically)
- [ ] Test mixed processing methods across segments

### UI and Integration Testing

- [ ] Test hotkey functionality across different scenarios
- [ ] Test timeline visualization updates
- [ ] Test post-clipping behavior (mode switch, auto-loading)
- [ ] Test error handling and user feedback

### Performance Testing

- [ ] Measure processing time differences between audio and video
- [ ] Test memory usage with multiple large segments
- [ ] Verify temporary file cleanup
- [ ] Test processing efficiency reporting
