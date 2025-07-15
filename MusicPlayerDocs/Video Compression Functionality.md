# Video Compression Functionality

## Overview

The video compression functionality allows users to compress selected video files to 720p resolution using FFmpeg. This feature supports both individual file selection and recursive directory processing, with a non-blocking UI that displays real-time progress.

## Requirements

### Functional Requirements

1. **Video Compression**

   - Compress selected video files to 720p resolution
   - Use FFmpeg with optimized parameters: `ffmpeg -i input.mp4 -vf "scale=-2:720" -c:v libx264 -crf 23 -preset medium -c:a copy -c:s copy -map 0 -movflags +faststart output.mp4`
   - Support common video formats: `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.m4v`, `.flv`
   - Maintain aspect ratio using `-2:720` scaling
   - Copy all audio tracks without re-encoding (`-c:a copy`)
   - Copy all subtitle tracks without re-encoding (`-c:s copy`)
   - Include all streams from input file (`-map 0`)
   - Enable fast start for web optimization (`-movflags +faststart`)

2. **File Management**

   - After successful compression, delete the original file
   - Rename compressed file to have the same stem as the original file
   - Handle file conflicts and errors gracefully

3. **Recursive Directory Processing**

   - When a directory is selected, recursively find all video files within it
   - Process all found video files using the same compression logic
   - Maintain directory structure in processing order

4. **User Interface**

   - Add a new RoundButton with video compression icon
   - Display progress overlay similar to MP3 conversion
   - Show current file being processed and overall progress
   - Allow cancellation of ongoing operations

5. **Error Handling**
   - Handle FFmpeg errors gracefully
   - Skip corrupted or unsupported files
   - Display error messages for failed compressions
   - Continue processing remaining files after errors

### Command Optimization Benefits

The optimized FFmpeg command provides several advantages:

1. **Performance Improvements**

   - **Faster Processing**: Only video stream is re-encoded, audio and subtitles are copied directly
   - **Reduced CPU Usage**: No audio processing overhead
   - **Lower Memory Usage**: Streaming copy operations are more memory efficient

2. **Quality Preservation**

   - **Original Audio Quality**: Audio tracks maintain their original quality and format
   - **Subtitle Integrity**: All subtitle tracks (SRT, ASS, VTT, etc.) are preserved exactly
   - **Metadata Preservation**: Chapter markers, track titles, and other metadata are retained

3. **Stream Compatibility**

   - **Multiple Audio Tracks**: Preserves all audio tracks (different languages, commentary, etc.)
   - **Multiple Subtitle Tracks**: Keeps all subtitle tracks and their formatting
   - **Stream Mapping**: `-map 0` ensures all streams from input are considered

4. **Robustness**

   - **Format Flexibility**: Works with various input containers (MKV, AVI, MOV, etc.)
   - **Codec Independence**: Handles different audio codecs without conversion issues
   - **Error Reduction**: Fewer encoding steps mean fewer potential failure points

5. **Web Optimization**
   - **Fast Start**: `-movflags +faststart` moves metadata to the beginning of the file
   - **Streaming Ready**: Enables immediate playback start over HTTP/internet connections
   - **Progressive Download**: Video can start playing before fully downloaded
   - **Better User Experience**: Reduces buffering time for web-based playback

### Non-Functional Requirements

1. **Performance**

   - Use background worker threads to avoid blocking UI
   - Process files sequentially to avoid overwhelming system resources
   - Provide real-time progress feedback

2. **User Experience**
   - Consistent UI design with existing conversion functionality
   - Clear progress indication and status messages
   - Responsive cancellation mechanism

## Architecture

### Component Structure

```
VideoCompressionManager
├── VideoCompressionWorker (QRunnable)
├── VideoCompressionProgress (UI Overlay)
├── VideoCompressionTask (Data Structure)
└── Integration with BrowserPage
```

### Class Responsibilities

1. **VideoCompressionManager**

   - Manages compression queue and worker threads
   - Handles file discovery and task creation
   - Emits progress signals to UI
   - Manages cancellation and cleanup

2. **VideoCompressionWorker**

   - Executes FFmpeg compression in background thread
   - Tracks progress using FFmpeg output parsing
   - Handles file operations (delete original, rename compressed)
   - Reports progress and completion status

3. **VideoCompressionProgress**

   - Displays compression progress overlay
   - Shows current file and overall progress
   - Handles error display and completion messages
   - Provides cancellation interface

4. **VideoCompressionTask**
   - Data structure representing a single compression task
   - Contains input path, output path, and metadata
   - Tracks task status and progress

## Implementation Details

### 1. Video File Detection

```python
SUPPORTED_VIDEO_EXTENSIONS = {
    '.mp4', '.mkv', '.avi', '.mov', '.webm',
    '.m4v', '.flv', '.wmv', '.mpg', '.mpeg'
}

def is_video_file(file_path: str) -> bool:
    """Check if file is a supported video format."""
    return Path(file_path).suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS
```

### 2. Recursive Directory Processing

```python
def discover_video_files(paths: List[str]) -> List[str]:
    """Recursively discover all video files in given paths."""
    video_files = []
    for path in paths:
        if os.path.isfile(path) and is_video_file(path):
            video_files.append(path)
        elif os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if is_video_file(file_path):
                        video_files.append(file_path)
    return video_files
```

### 3. FFmpeg Command Building

```python
def build_compression_command(input_path: str, output_path: str) -> List[str]:
    """Build FFmpeg command for video compression with stream copying."""
    return [
        'ffmpeg',
        '-i', input_path,
        '-vf', 'scale=-2:720',        # Scale video to 720p, maintain aspect ratio
        '-c:v', 'libx264',            # Video codec: H.264
        '-crf', '23',                 # Constant Rate Factor for quality
        '-preset', 'medium',          # Encoding speed/quality balance
        '-c:a', 'copy',               # Copy all audio streams without re-encoding
        '-c:s', 'copy',               # Copy all subtitle streams without re-encoding
        '-map', '0',                  # Include all streams from input
        '-movflags', '+faststart',    # Enable fast start for web optimization
        '-y',                         # Overwrite output file if exists
        output_path
    ]
```

### 4. FFmpeg Progress Parsing

```python
def parse_ffmpeg_progress(line: str) -> Optional[float]:
    """Parse FFmpeg output to extract progress percentage."""
    # Parse time=00:01:23.45 format
    time_match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
    if time_match:
        hours, minutes, seconds = time_match.groups()
        current_time = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        # Calculate percentage based on total duration
        return (current_time / total_duration) * 100
    return None
```

### 5. File Operations

```python
def handle_compression_completion(original_path: str, compressed_path: str):
    """Handle file operations after successful compression."""
    try:
        # Verify compressed file exists and is valid
        if not os.path.exists(compressed_path) or os.path.getsize(compressed_path) == 0:
            raise Exception("Compressed file is invalid or empty")

        # Note: The -movflags +faststart option ensures the output MP4 has its
        # metadata (moov atom) at the beginning, enabling fast streaming playback
        # over the internet without requiring the entire file to be downloaded first

        # Create final path with original filename
        original_name = Path(original_path).stem
        final_path = Path(compressed_path).parent / f"{original_name}.mp4"

        # Handle filename conflicts
        if final_path.exists() and final_path != Path(compressed_path):
            counter = 1
            while final_path.exists():
                final_path = Path(compressed_path).parent / f"{original_name}_{counter}.mp4"
                counter += 1

        # Rename compressed file
        os.rename(compressed_path, final_path)

        # Delete original file
        os.remove(original_path)

        return str(final_path)
    except Exception as e:
        # Clean up compressed file on error
        if os.path.exists(compressed_path):
            os.remove(compressed_path)
        raise e
```

## UI Integration

### 1. RoundButton Addition

```python
# In BrowserPage._setup_ui()
self.video_compress_button = RoundButton(
    parent=self,
    icon_name="fa5s.video",  # Video icon
    diameter=48,
    icon_size=20,
    bg_opacity=0.5
)
self.video_compress_button.setToolTip("Compress Selected Videos to 720p")
```

### 2. Progress Overlay

The progress overlay will follow the same pattern as the MP3 conversion overlay:

```python
class VideoCompressionProgress(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._apply_theme_styles()

    def show_compression_started(self, total_files: int):
        """Display compression start message."""

    def show_file_progress(self, filename: str, file_index: int, total_files: int, percentage: float):
        """Update progress for current file."""

    def show_file_completed(self, original_filename: str, compressed_filename: str):
        """Show completion message."""

    def show_file_failed(self, filename: str, error_message: str):
        """Show error message."""

    def show_batch_finished(self):
        """Show completion of all compressions."""
```

### 3. Button Positioning

```python
# In BrowserPage.resizeEvent()
video_compress_button_x = cancel_conversion_button_x - self.video_compress_button.width() - 10
self.video_compress_button.move(video_compress_button_x, button_y)
self.video_compress_button.raise_()
```

## Worker Thread Design

### 1. VideoCompressionManager

```python
class VideoCompressionManager(QObject):
    # Signals
    compression_batch_started = pyqtSignal(int)  # total_files
    compression_file_started = pyqtSignal(str, str, int, int)  # task_id, filename, index, total
    compression_file_progress = pyqtSignal(str, float)  # task_id, percentage
    compression_file_completed = pyqtSignal(str, str, str)  # task_id, original_filename, compressed_filename
    compression_file_failed = pyqtSignal(str, str, str)  # task_id, filename, error_message
    compression_batch_finished = pyqtSignal()

    def start_compressions(self, selected_objects: List[Dict], output_directory: str):
        """Start compression process for selected items."""

    def cancel_all_compressions(self):
        """Cancel all ongoing compressions."""
```

### 2. VideoCompressionWorker

```python
class VideoCompressionWorker(QRunnable):
    def __init__(self, task: VideoCompressionTask, ffmpeg_path: str):
        super().__init__()
        self.task = task
        self.ffmpeg_path = ffmpeg_path
        self.cancelled = False
        self.signals = VideoCompressionWorkerSignals()

    def run(self):
        """Execute compression in background thread."""
        try:
            self._compress_video()
        except Exception as e:
            self.signals.worker_failed.emit(self.task.task_id, str(e))
        finally:
            self.signals.worker_finished.emit(self.task.task_id)

    def _compress_video(self):
        """Perform actual video compression."""

    def cancel(self):
        """Cancel the compression operation."""
        self.cancelled = True
```

### 3. Task Data Structure

```python
class VideoCompressionTask:
    def __init__(self, task_id: str, input_path: str, output_path: str,
                 file_index: int, total_files: int):
        self.task_id = task_id
        self.input_path = input_path
        self.output_path = output_path
        self.file_index = file_index
        self.total_files = total_files
        self.status = "pending"  # pending, processing, completed, failed, cancelled
        self.progress = 0.0
        self.error_message = ""
        self.original_filename = os.path.basename(input_path)
```

## Implementation Steps

### Phase 1: Core Infrastructure

1. Create `VideoCompressionManager` class
2. Create `VideoCompressionWorker` class
3. Create `VideoCompressionTask` data structure
4. Implement video file detection logic
5. Implement recursive directory processing

### Phase 2: FFmpeg Integration

1. Add FFmpeg path detection and validation
2. Implement compression command building
3. Add progress parsing from FFmpeg output
4. Implement file operations (delete, rename)
5. Add error handling and recovery

### Phase 3: UI Components

1. Create `VideoCompressionProgress` overlay
2. Add video compression RoundButton to BrowserPage
3. Implement progress display and updates
4. Add cancellation functionality
5. Position UI elements correctly

### Phase 4: Integration & Testing

1. Connect signals between manager and UI
2. Integrate with BrowserPage selection system
3. Add comprehensive error handling
4. Test with various video formats and scenarios
5. Optimize performance and memory usage

## Error Handling Strategy

### Common Error Scenarios

1. **FFmpeg Not Found**

   - Display error message with installation instructions
   - Disable compression functionality

2. **Insufficient Disk Space**

   - Check available space before compression
   - Display appropriate error message

3. **File Access Errors**

   - Handle permission issues
   - Skip locked or inaccessible files

4. **Compression Failures**

   - Parse FFmpeg error output
   - Display meaningful error messages
   - Continue with remaining files

5. **Cancellation Handling**
   - Clean up temporary files
   - Restore original files if needed
   - Update UI appropriately

## Performance Considerations

1. **Memory Management**

   - Process files sequentially to avoid memory issues
   - Clean up temporary files promptly
   - Monitor memory usage during compression

2. **CPU Usage**

   - Use single worker thread to avoid overwhelming system
   - Allow user to cancel long-running operations
   - Provide progress feedback for better UX

3. **Disk I/O**
   - Minimize file operations
   - Use temporary files for intermediate results
   - Verify file integrity before final operations

## Testing Strategy

1. **Unit Tests**

   - Video file detection
   - Directory traversal
   - FFmpeg command building
   - Progress parsing

2. **Integration Tests**

   - End-to-end compression workflow
   - Error handling scenarios
   - Cancellation behavior
   - UI interaction

3. **Performance Tests**
   - Large file handling
   - Multiple file processing
   - Memory usage monitoring
   - Cancellation responsiveness

This comprehensive specification provides the foundation for implementing the video compression functionality while maintaining consistency with the existing MP3 conversion system.
