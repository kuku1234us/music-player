# Media Conversion Implementation

## 1. Introduction

This document outlines the design and implementation plan for adding a media conversion functionality to the Music Player application. The primary goal is to allow users to convert selected audio/video files from the `BrowserPage` into MP3 format using FFmpeg.

## 2. Functionality Specification

*   **Trigger:** A new round button labeled "MP" will be added to the `BrowserPage`.
*   **Input:** Users can select one or more files from the `BrowserTableView` in the `BrowserPage`.
*   **Action:** Upon clicking the "MP" button:
    *   The selected files will be queued for conversion.
    *   Each file will be converted to MP3 format.
*   **Conversion Parameters:**
    *   **Output Format:** MP3
    *   **Audio Bitrate:** 256kbps
    *   **Output Filename:** The stem of the original filename will be used, with the ".mp3" extension. (e.g., `song.wav` -> `song.mp3`).
    *   **Output Folder:** The same directory currently being viewed in the `BrowserPage`.
    *   **Overwrite:** If an output file with the same name already exists, it should be overwritten (or prompt user - TBD, initially overwrite).
*   **User Feedback:**
    *   A new UI component, `ConversionProgress`, will display the status of the conversion process. This includes:
        *   Overall progress (e.g., "Converting file X of Y: current_filename.ext").
        *   Progress of the currently converting file (if FFmpeg provides parseable progress).
        *   Status messages (e.g., starting, completed, failed).
    *   The `BrowserPage` should refresh its view after conversions are complete to show the new MP3 files.
*   **Error Handling:**
    *   Errors during the conversion of individual files (e.g., invalid input file, FFmpeg error) should be reported via the `ConversionProgress` UI.
    *   The system should attempt to convert subsequent files in the queue even if one fails.

## 3. Implementation Design

The implementation will involve modifications to existing UI components and the creation of new model and UI components.

### 3.1. New/Modified Code Modules

*   **`music_player/ui/pages/browser_page.py` (`BrowserPage`):**
    *   **Responsibilities:**
        *   Instantiate and display the new "MP" `RoundButton`.
        *   Instantiate and manage the `ConversionProgress` UI component (likely an overlay).
        *   Handle the "MP" button click event:
            *   Retrieve selected file paths from `BrowserTableView`.
            *   Filter out non-convertible files (e.g., directories, non-media files - initial filter can be lenient).
            *   Identify the current output directory.
            *   Instantiate `ConversionManager` (or get a shared instance).
            *   Pass the list of files to convert and the output directory to `ConversionManager`.
            *   Connect to signals from `ConversionManager` to update the `ConversionProgress` UI.
            *   Refresh the browser view upon completion of all conversions.
*   **`music_player/models/conversion_manager.py` (`ConversionManager` - New):**
    *   **Responsibilities:**
        *   Manage a queue of conversion tasks.
        *   Process one conversion at a time to avoid system overload.
        *   Construct and execute FFmpeg commands using `subprocess` module in a separate thread (QRunnable/QThread) to avoid blocking the UI.
        *   Parse FFmpeg's stderr output for progress information (if feasible and reliable). Duration and current time processed are key.
        *   Handle potential errors during FFmpeg execution.
    *   **Signals:**
        *   `conversion_batch_started(total_files: int)`
        *   `conversion_file_started(filename: str, file_index: int, total_files: int)`
        *   `conversion_progress(filename: str, percentage: float)` (Percentage of the current file)
        *   `conversion_file_completed(original_filename: str, output_filepath: str)`
        *   `conversion_file_failed(filename: str, error_message: str)`
        *   `conversion_batch_finished()`
*   **`music_player/ui/components/browser_components/conversion_progress.py` (`ConversionProgress` - New):**
    *   **Responsibilities:**
        *   A `QWidget` designed to display conversion status. Could be an overlay similar to `UploadStatusOverlay`.
        *   Display overall progress (e.g., "File 2/5: Converting my_song.wav...").
        *   Display a progress bar for the current file's conversion.
        *   Show status messages for individual files (success, failure).
        *   Provide a way to be shown/hidden by `BrowserPage`.
*   **`music_player/ui/components/round_button.py` (`RoundButton`):**
    *   No functional changes required. A new instance will be created with the text "MP".
*   **`music_player/ui/components/browser_components/browser_table.py` (`BrowserTableView`):**
    *   No direct changes. `BrowserPage` will continue to use `get_selected_items_data()` to get file information.

### 3.2. FFmpeg Integration

*   **Command Structure:** A typical command will be:
    `ffmpeg -i "<input_filepath>" -b:a 256k -vn "<output_filepath.mp3>"`
    *   `-i <input_filepath>`: Specifies the input file.
    *   `-b:a 256k`: Sets the audio bitrate to 256 kbps.
    *   `-vn`: Disables video recording (ensures output is audio-only MP3).
    *   `<output_filepath.mp3>`: Specifies the output MP3 file.
    *   Need to add `-y` for overwriting without prompt, or handle existing files.
*   **Progress Parsing:** FFmpeg provides several ways to get progress feedback. The `ConversionManager` will need to parse this output to calculate progress for the UI.
    *   **Method 1: Parsing `stderr`:** FFmpeg typically outputs verbose progress information to `stderr`. This includes lines that update periodically, showing the current encoding time, frame number, bitrate, speed, etc.
        *   Example FFmpeg output line for progress: `frame= 1234 fps= 50 q=28.0 size=   12345kB time=00:00:50.12 bitrate=2048.0kbits/s speed=2.0x`
        *   The `time=` field can be compared against the total duration of the input file (which may need to be obtained beforehand using `ffprobe` or by parsing FFmpeg's initial output for the input file) to calculate a percentage.
    *   **Method 2: `-progress url` Option:** FFmpeg offers a global option `-progress url` (e.g., `-progress -` to send to `stdout`, or `-progress pipe:1` to use a pipe). This instructs FFmpeg to periodically write parsable progress information to the specified URL. The output format is a series of `key=value` pairs, including fields like:
        *   `out_time_ms`: Output time in microseconds.
        *   `total_size`: Total size of the output file so far.
        *   `speed`: Current conversion speed (e.g., `2.0x`).
        This method is often more robust for programmatic parsing than scraping the general `stderr` log.
    *   **Method 3: `-vstats` / `-vstats_file`:** As noted in the FFmpeg documentation (section 5.13), these options generate a file with statistics, including a `time=TIMESTAMP` field, which can be used for progress.
    *   **Chosen Approach:** Initially, we will attempt to use the `-progress pipe:1` method for its structured output. If this proves difficult to implement reliably across platforms or FFmpeg versions, we will fall back to parsing `stderr`. Obtaining the total duration of the input file will be a necessary first step for accurate percentage calculation.
*   **FFmpeg Availability:** The application should ideally check if FFmpeg is installed and in the system's PATH. If not, it should inform the user. (This can be a V2 feature; initially, assume FFmpeg is available).

## 4. Data Structures

*   **`ConversionManager`:**
    *   `_conversion_queue: List[ConversionTask]`
        *   `ConversionTask` (could be a `dataclass` or `dict`):
            *   `input_filepath: Path`
            *   `output_filepath: Path`
            *   `original_filename: str`
            *   `status: str` (e.g., "pending", "converting", "completed", "failed")
            *   `error_message: Optional[str]`
*   **Signals:** Will primarily pass basic types like `str`, `int`, `float`.

## 5. Workflow

1.  User selects files in `BrowserPage`'s `BrowserTableView`.
2.  User clicks the "MP" `RoundButton`.
3.  `BrowserPage` gathers selected file paths and the current directory.
4.  `BrowserPage` calls a method on `ConversionManager` (e.g., `start_conversions(files_to_convert, output_dir)`).
5.  `ConversionManager` populates its `_conversion_queue`.
6.  `ConversionManager` starts processing the queue (one file at a time) in a background thread.
    *   For each file, `ConversionManager` emits `conversion_file_started`.
    *   It launches FFmpeg via `subprocess`.
    *   It reads `stderr` from FFmpeg, parses progress, and emits `conversion_progress`.
    *   On FFmpeg completion:
        *   If successful, emits `conversion_file_completed`.
        *   If failed, emits `conversion_file_failed`.
7.  `BrowserPage` listens to these signals and updates the `ConversionProgress` UI.
8.  After all files in the queue are processed, `ConversionManager` emits `conversion_batch_finished`.
9.  `BrowserPage` hides/resets the `ConversionProgress` UI and calls `_refresh_view()` to update the file listing.

## 6. UI Considerations for `ConversionProgress`

*   Should be non-modal, allowing the user to continue interacting with the application (though perhaps browsing actions are limited or queued if they affect the output dir).
*   Positioned centrally or in a noticeable area of the `BrowserPage`.
*   Clear indication of which file is currently being processed and overall queue status.
*   A visual progress bar for the current file.
*   List or summary of failed conversions if any.

## 7. Future Enhancements (Post-MVP)

*   Allow user to select output directory.
*   Allow user to configure output format and quality settings (bitrate, other codecs).
*   Provide an option to cancel ongoing conversions.
*   Check for FFmpeg availability on startup and guide user if not found.
*   Option to preserve original file's metadata.
*   Handle existing output files more gracefully (prompt to overwrite, rename, skip).

## 8. Implementation Milestones

- [x] **Phase 1: Documentation and Initial Setup**
    - [x] Create `MusicPlayerDocs/Media Conversion Implementation.md` with initial design.
    - [x] Define functionality specifications, UI/model components, and FFmpeg integration strategy.
    - [x] Identify new code modules: `ConversionManager`, `ConversionProgress`.
    - [x] Update documentation with FFmpeg progress feedback details.
- [x] **Phase 2: Basic UI and Model Placeholders**
    - [x] Create `music_player/models/conversion_manager.py` with `ConversionManager` class structure and signals.
    - [x] Create `music_player/ui/components/browser_components/conversion_progress.py` with `ConversionProgress` widget structure.
    - [x] Add "MP3" `RoundButton` to `BrowserPage` (`music_player/ui/pages/browser_page.py`).
    - [x] Instantiate `ConversionManager` and `ConversionProgress` in `BrowserPage`.
    - [x] Connect `mp3_convert_button` click to a handler in `BrowserPage`.
    - [x] Connect `ConversionManager` signals to `ConversionProgress` update methods (placeholder connections in `BrowserPage`).
    - [x] Implement basic file filtering in `BrowserPage` for the conversion button.
    - [x] Add positioning for the new button and `ConversionProgress` overlay in `BrowserPage.resizeEvent()`.
- [ ] **Phase 3: Core Conversion Logic (`ConversionManager`)**
    - [x] Implement `ConversionTask` data structure (dataclass or dict).
    - [x] Implement queuing mechanism in `start_conversions`.
    - [x] Create a `QRunnable` or `QThread` worker (`ConversionWorker`) within `ConversionManager` to handle FFmpeg processes off the main thread.
    - [x] Implement logic to get total duration of input files (e.g., using `ffprobe` or initial FFmpeg output) before starting conversion (`ConversionWorker._get_media_duration()`).
    - [x] Construct FFmpeg command, including input/output paths, bitrate, `-vn`, and `-y` (for overwrite) (`ConversionWorker.run()`).
    - [x] Implement `subprocess.Popen` to run the FFmpeg command (`ConversionWorker.run()`).
    - [x] Add the `-progress pipe:1` argument to the FFmpeg command and capture `stdout` (`ConversionWorker.run()`).
    - [x] Parse the progress data from the pipe (or `stderr` as a fallback) (`ConversionWorker._parse_ffmpeg_progress()`).
        - [x] Extract `out_time_ms` or equivalent `time=` from FFmpeg output.
        - [x] Calculate percentage based on total duration and emit `conversion_progress` signal (`ConversionWorker._parse_ffmpeg_progress()` via `worker_progress`).
    - [x] Handle FFmpeg process completion (`ConversionWorker.run()`):
        - [x] Check return code for success/failure.
        - [x] Emit `conversion_file_completed` with original and new file path on success (via `worker_completed`).
        - [x] Emit `conversion_file_failed` with filename and error on failure (via `worker_failed`).
    - [x] Ensure sequential processing of files in the queue (`ConversionManager._process_next_task()`).
    - [x] Emit `conversion_batch_started` and `conversion_batch_finished` appropriately (`ConversionManager`).
    - [x] Implement basic cancellation logic (`ConversionWorker.cancel()`, `ConversionManager.cancel_all_conversions()`).
    - [x] Add utility to check for FFmpeg/ffprobe (`ConversionManager.check_ffmpeg_tools()`).
- [ ] **Phase 4: `ConversionProgress` UI Refinement**
    - [x] Ensure `show_conversion_started` correctly displays total files (and resets state).
    - [x] Ensure `show_file_progress` updates with current task ID, filename, index, total, and percentage bar, and resets style.
    - [x] Implement `update_current_file_progress` to only update progress if task ID matches.
    - [x] Implement clear display for `show_file_completed` (resets style).
    - [x] Implement clear display for `show_file_failed` (changes progress bar style to error state).
    - [x] Ensure `show_batch_finished` provides a clear summary, resets style, and auto-hides gracefully.
    - [x] Handle error display via `show_error` if general errors occur in the manager.
- [ ] **Phase 5: Integration and Testing**
    - [ ] Thoroughly test with various file types (audio, video, different containers).
    - [ ] Test with files containing spaces or special characters in names/paths.
    - [ ] Test error handling for invalid files or FFmpeg errors.
    - [ ] Test UI responsiveness during conversion.
    - [ ] Verify `BrowserPage` refreshes correctly after conversions.
    - [ ] Test with empty selection and selection of only directories.
- [ ] **Phase 6: Code Cleanup and Refinements (Future Enhancements from Section 7 can be moved here if time permits)**
    - [ ] Review all new code for clarity, efficiency, and comments.
    - [ ] Remove any placeholder/debug print statements (replace with logging where appropriate).
    - [ ] Consider adding `cancel_all_conversions` functionality to `ConversionManager` and a cancel button to `ConversionProgress`.
    - [ ] Check for FFmpeg/ffprobe availability on the system (basic check).
