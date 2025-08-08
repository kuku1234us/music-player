# Douyin Video Processing Feature

## Introduction

This document outlines the specifications and implementation milestones for adding a "抖" RoundButton to the BrowserPage. This button will process selected Douyin video files by trimming the last 3.03 seconds (removing the ending), replacing the original files, and then merging all processed videos into a single output file named `output{XX}.mp4`, where `XX` is the next available two-digit number.

The process will be asynchronous to avoid blocking the UI, with a progress overlay similar to the video compression feature.

## Specifications

### Functional Requirements

1. **UI Addition**:

   - Add a new `RoundButton` with text "抖" (Douyin) to the BrowserPage, positioned appropriately among existing buttons (e.g., after the compression button).
   - Use an appropriate icon for the button (e.g., a scissors icon for trimming or a film strip).

2. **Selection Handling**:

   - Upon clicking the button, retrieve selected items from the `browser_table`.
   - Process only video files (extensions: .mp4, .mkv, etc.).
   - If directories are selected, recursively find and process all video files within them.

3. **Trimming Process**:

   - For each video file:
     - Use FFmpeg to create a new video that excludes the last 3.03 seconds.
     - Command example: `ffmpeg -i input.mp4 -to $(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 input.mp4 | awk '{print $1-3.03}') -c copy output.mp4`
     - Delete the original file.
     - Rename the trimmed file to the original filename.
   - Handle errors gracefully (e.g., skip if duration < 3.03 seconds).

4. **Merging Process**:

   - After trimming all files, collect the list of trimmed video paths.
   - Generate output filename: `output{XX}.mp4` in the current browser directory, where XX starts from 00 and increments until a non-existing file is found.
   - Use FFmpeg to merge videos with re-encoding for compatibility:
     - **Video Codec**: `libx264` with CRF 23 and medium preset for quality/speed balance
     - **Audio Codec**: `aac` with 128k bitrate for consistent audio
     - **Pixel Format**: `yuv420p` for maximum compatibility
     - **Web Optimization**: `faststart` flag for better streaming
     - **Audio Sync Fix**: `-avoid_negative_ts make_zero` to prevent audio desync issues
     - **Command**: `ffmpeg -f concat -safe 0 -i filelist.txt -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k -pix_fmt yuv420p -movflags +faststart -avoid_negative_ts make_zero output.mp4`
   - Re-encoding ensures all videos have consistent properties regardless of original format/resolution
   - Maintains aspect ratios and prevents distortion from videos with different properties
   - The `-avoid_negative_ts make_zero` flag fixes audio sync issues that can occur when concatenating videos with different timestamps or when the output is processed further (e.g., face swapping)
   - Clean up the temporary filelist.txt after successful merge.

5. **Asynchronous Execution**:

   - Use worker threads (similar to `VideoCompressionManager`) for trimming and merging.
   - Display progress overlay with status (e.g., "Trimming X/Y files", then "Merging videos").
   - Emit signals for progress updates and completion.

6. **Error Handling**:
   - Log errors for individual files.
   - Show message box on completion with summary (success count, errors).
   - Skip invalid files without stopping the process.

### Technical Considerations

- **FFmpeg Integration**: Extend or reuse utilities from `ffmpeg_utils.py` for trimming and merging commands.
- **File Management**: Ensure safe file operations (temp files, deletions) to avoid data loss.
- **Performance**: Process files sequentially in a single worker to avoid FFmpeg concurrency issues.
- **UI Responsiveness**: All heavy operations in background thread.

## Implementation Milestones

### Phase 1: UI and Basic Setup

- Add "抖" RoundButton to `browser_page.py`.
- Connect button click to a new method `_on_douyin_process_clicked`.
- Implement basic selection retrieval and validation (get list of video files, recursing directories).

### Phase 2: Trimming Functionality

- Create a new manager class `DouyinProcessor` (similar to `VideoCompressionManager`).
- Implement trimming logic using FFmpeg.
- Handle file replacement (trim to temp, delete original, rename).
- Integrate progress signals.

### Phase 3: Merging Functionality

- Add merging step after trimming completes.
- Implement output filename generation.
- Create FFmpeg concat command.
- Update progress for merging phase.

### Phase 4: Integration and Testing

- Connect manager to BrowserPage.
- Add progress overlay.
- Test with sample videos: single file, multiple files, directories.
- Handle edge cases: short videos, non-video files, errors.

## Potential Challenges

- Accurate duration calculation for trimming.
- Handling videos with variable frame rates during concat.
- Ensuring output directory has write permissions.
- Unicode filename support in FFmpeg commands.

## Success Criteria

- Button appears and functions correctly.
- Videos are trimmed and replaced without data loss.
- Merged video plays correctly with all segments.
- UI remains responsive during processing.
- Errors are handled and reported properly.
