# File Comparison and Deletion Tool

A PyQt6 application for comparing two directories and removing duplicate files from the target directory.

## Features

- **Side-by-side directory comparison**: View contents of two directories simultaneously
- **Automatic duplicate detection**: Find files in the target directory that exist in the old directory
- **Visual highlighting**: Duplicate files are highlighted in red
- **Safe deletion**: Confirmation dialog before deleting files
- **Progress tracking**: Real-time progress bars for comparison and deletion operations
- **Non-blocking UI**: All operations run in background threads to keep the UI responsive

## Requirements

- Python 3.9 or higher
- PyQt6
- qtawesome

## Installation

The application uses the same dependencies as your music player project. If you have the music player environment set up, you can run this directly.

## Usage

### Running the Application

```bash
python file_compare_app.py
```

Or use the launcher script:

```bash
python run_file_compare.py
```

### How to Use

1. **Select Directories**:

   - Click "Select Directory" in the "Old" pane to choose the reference directory
   - Click "Select Directory" in the "Target" pane to choose the directory to clean up

2. **Compare Directories**:

   - Click "Compare Directories" to find duplicate files
   - Files in the target directory that exist in the old directory will be highlighted in red
   - The status will show how many duplicate files were found

3. **Delete Duplicates**:
   - Click "Delete Selected Files" to remove the duplicate files
   - Confirm the deletion in the dialog box
   - The target directory will be automatically refreshed after deletion

### Interface Layout

```
┌─────────────────┬─────────────────┐
│      Old        │     Target      │
│                 │                 │
│ [Select Dir]    │ [Select Dir]    │
│                 │                 │
│ File List       │ File List       │
│ (Reference)     │ (To Clean)      │
│                 │                 │
│ X files         │ Y files         │
└─────────────────┴─────────────────┘
│ [Compare] [Delete] [Progress Bar] │
│ Status: Ready                      │
└─────────────────────────────────────┘
```

### Safety Features

- **Confirmation Dialog**: You must confirm before any files are deleted
- **Progress Tracking**: See real-time progress during comparison and deletion
- **Error Handling**: Errors are displayed without crashing the application
- **Non-destructive**: Only files in the target directory are affected

### File Matching

The application matches files by **filename only** (not by content or path). This means:

- `video1.mp4` in the old directory will match `video1.mp4` in the target directory
- Files with the same name but different content will be considered duplicates
- Files in different subdirectories with the same name will be matched

### Windows 10 Compatibility

The application is specifically designed for Windows 10 and includes:

- Windows-style file dialogs
- Proper handling of Windows file paths
- Windows-compatible file operations

## Troubleshooting

### Common Issues

1. **"No module named 'PyQt6'"**

   - Install PyQt6: `pip install PyQt6`

2. **"No module named 'qtawesome'"**

   - Install qtawesome: `pip install qtawesome`

3. **Permission errors when deleting files**

   - Ensure you have write permissions to the target directory
   - Close any applications that might have the files open

4. **Slow performance with large directories**
   - The application processes files in background threads
   - Large directories may take time to scan and compare

### Error Messages

- **"Error loading directory"**: Check if the directory path is valid and accessible
- **"Error deleting file"**: File might be in use or you lack permissions
- **"No duplicate files found"**: No files in the target directory match files in the old directory

## Technical Details

### Architecture

- **Main Window**: `FileCompareApp` - Main application window
- **Directory Pane**: `DirectoryPane` - Individual directory display component
- **Worker Threads**:
  - `FileComparisonWorker` - Handles directory comparison
  - `FileDeletionWorker` - Handles file deletion
- **UI Components**: PyQt6 widgets for modern, responsive interface

### Threading

All heavy operations (comparison and deletion) run in background threads to prevent UI blocking:

- Comparison worker scans directories and finds duplicates
- Deletion worker removes files from the target directory
- Progress signals update the UI in real-time

### File Operations

- **Recursive scanning**: Searches all subdirectories
- **Safe deletion**: Uses `os.remove()` with error handling
- **Path handling**: Uses `os.path` for cross-platform compatibility
- **Error recovery**: Continues processing even if individual files fail

## License

This application is part of the music player project and follows the same licensing terms.
