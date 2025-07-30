"""
Utilities for video file detection and discovery.
"""
import os
from pathlib import Path
from typing import List, Set

# Supported video file extensions
SUPPORTED_VIDEO_EXTENSIONS: Set[str] = {
    '.mp4', '.mkv', '.avi', '.mov', '.webm',
    '.m4v', '.flv', '.wmv', '.mpg', '.mpeg',
    '.3gp', '.f4v', '.ts', '.mts', '.m2ts'
}

def is_video_file(file_path: str) -> bool:
    """
    Check if a file is a supported video format.
    
    Args:
        file_path: Path to the file to check
        
    Returns:
        bool: True if file has a supported video extension
    """
    if not file_path:
        return False
    
    try:
        extension = Path(file_path).suffix.lower()
        return extension in SUPPORTED_VIDEO_EXTENSIONS
    except Exception:
        return False

def get_video_files_in_directory(directory_path: str, recursive: bool = False) -> List[str]:
    """
    Get all video files in a directory.
    
    Args:
        directory_path: Path to the directory to search
        recursive: If True, search subdirectories recursively
        
    Returns:
        List[str]: List of video file paths
    """
    video_files = []
    
    if not os.path.isdir(directory_path):
        return video_files
    
    try:
        if recursive:
            # Use os.walk for recursive search
            for root, dirs, files in os.walk(directory_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if is_video_file(file_path):
                        video_files.append(file_path)
        else:
            # Search only immediate directory
            for item in os.listdir(directory_path):
                item_path = os.path.join(directory_path, item)
                if os.path.isfile(item_path) and is_video_file(item_path):
                    video_files.append(item_path)
    except (OSError, IOError) as e:
        print(f"[VideoFileUtils] Error scanning directory {directory_path}: {e}")
    
    return sorted(video_files)

def discover_video_files(paths: List[str]) -> List[str]:
    """
    Recursively discover all video files in the given paths.
    
    This function handles both individual files and directories,
    recursively searching directories for video files.
    
    Args:
        paths: List of file or directory paths to search
        
    Returns:
        List[str]: List of discovered video file paths
    """
    video_files = []
    
    for path in paths:
        if not path or not os.path.exists(path):
            print(f"[VideoFileUtils] Path does not exist: {path}")
            continue
        
        try:
            if os.path.isfile(path):
                # Single file - check if it's a video
                if is_video_file(path):
                    video_files.append(path)
                else:
                    print(f"[VideoFileUtils] Skipping non-video file: {path}")
            elif os.path.isdir(path):
                # Directory - recursively find video files
                found_videos = get_video_files_in_directory(path, recursive=True)
                video_files.extend(found_videos)
                print(f"[VideoFileUtils] Found {len(found_videos)} video files in directory: {path}")
            else:
                print(f"[VideoFileUtils] Skipping unknown path type: {path}")
        except Exception as e:
            print(f"[VideoFileUtils] Error processing path {path}: {e}")
    
    # Remove duplicates while preserving order
    unique_video_files = []
    seen = set()
    for video_file in video_files:
        if video_file not in seen:
            unique_video_files.append(video_file)
            seen.add(video_file)
    
    print(f"[VideoFileUtils] Total unique video files discovered: {len(unique_video_files)}")
    return unique_video_files

def get_video_file_info(file_path: str) -> dict:
    """
    Get basic information about a video file.
    
    Args:
        file_path: Path to the video file
        
    Returns:
        dict: Dictionary containing file information
    """
    info = {
        'path': file_path,
        'filename': os.path.basename(file_path),
        'extension': Path(file_path).suffix.lower(),
        'size_bytes': 0,
        'exists': False,
        'is_video': False
    }
    
    try:
        if os.path.exists(file_path):
            info['exists'] = True
            info['is_video'] = is_video_file(file_path)
            
            if os.path.isfile(file_path):
                info['size_bytes'] = os.path.getsize(file_path)
    except Exception as e:
        print(f"[VideoFileUtils] Error getting file info for {file_path}: {e}")
    
    return info

def validate_video_files(file_paths: List[str]) -> List[str]:
    """
    Validate a list of video file paths, removing invalid ones.
    
    Args:
        file_paths: List of file paths to validate
        
    Returns:
        List[str]: List of valid video file paths
    """
    valid_files = []
    
    for file_path in file_paths:
        if not file_path:
            continue
            
        try:
            if os.path.exists(file_path) and os.path.isfile(file_path) and is_video_file(file_path):
                valid_files.append(file_path)
            else:
                print(f"[VideoFileUtils] Invalid video file: {file_path}")
        except Exception as e:
            print(f"[VideoFileUtils] Error validating file {file_path}: {e}")
    
    return valid_files

def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        str: Formatted size string
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

def get_supported_extensions() -> Set[str]:
    """
    Get the set of supported video file extensions.
    
    Returns:
        Set[str]: Set of supported extensions (with dots)
    """
    return SUPPORTED_VIDEO_EXTENSIONS.copy()

def get_extensions_filter_string() -> str:
    """
    Get a filter string for file dialogs.
    
    Returns:
        str: Filter string for video files
    """
    extensions = [ext[1:] for ext in SUPPORTED_VIDEO_EXTENSIONS]  # Remove dots
    return f"Video files ({' '.join(['*.' + ext for ext in extensions])})"

def get_all_video_files(directory_path: str) -> List[str]:
    """
    Alias for get_video_files_in_directory with recursive=True.
    Finds all video files in a directory and its subdirectories.
    
    Args:
        directory_path: The root directory to start searching from.
        
    Returns:
        A list of full paths to all found video files.
    """
    return get_video_files_in_directory(directory_path, recursive=True)