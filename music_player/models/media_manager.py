"""
Media Manager for handling media loading and validation business logic.
"""
import os
from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path
from qt_base_app.models.logger import Logger
from .windows_path_utils import resolve_mapped_drive_to_unc


class MediaManager:
    """
    Manager for handling media-related operations and validation.
    Encapsulates media business logic to keep GUI code clean.
    """
    
    @staticmethod
    def validate_media_path(file_path: str) -> Tuple[bool, str, str]:
        """
        Validate a media file path and extract the actual path.
        
        Args:
            file_path (str or dict): Path to validate (can be string or dict with 'path' key)
            
        Returns:
            Tuple[bool, str, str]: (is_valid, actual_path, error_message)
        """
        # Handle dict input (extract path if it's a dict)
        actual_path = file_path
        if isinstance(file_path, dict):
            actual_path = file_path.get('path', '')
            Logger.instance().warning(caller="MediaManager", msg=f"[MediaManager] Warning: Received dict, extracted path: {actual_path}")
        
        # Validate path exists
        if not actual_path:
            return False, actual_path, "Empty file path provided"
        
        if not os.path.exists(actual_path):
            return False, actual_path, f"Media file not found: {actual_path}"
        
        return True, actual_path, ""
    
    @staticmethod
    def get_file_info(file_path: str) -> Dict[str, Any]:
        """
        Get basic information about a media file.
        
        Args:
            file_path (str): Path to the media file
            
        Returns:
            Dict: File information including basename, size, etc.
        """
        if not os.path.exists(file_path):
            return {}
        
        try:
            file_stat = os.stat(file_path)
            return {
                'basename': os.path.basename(file_path),
                'size': file_stat.st_size,
                'modified_time': file_stat.st_mtime,
                'is_valid': True
            }
        except Exception as e:
            Logger.instance().error(caller="MediaManager", msg=f"[MediaManager] Error getting file info for {file_path}: {e}")
            return {'is_valid': False, 'error': str(e)}
    
    @staticmethod
    def is_media_file(file_path: str) -> bool:
        """
        Check if a file is a supported media file based on extension.
        
        Args:
            file_path (str): Path to check
            
        Returns:
            bool: True if it's a supported media file
        """
        if not file_path:
            return False
        
        # Get file extension
        _, ext = os.path.splitext(file_path.lower())
        
        # Supported media extensions
        audio_extensions = {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a'}
        video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.webm', '.wmv', '.flv'}
        playlist_extensions = {'.m3u', '.m3u8', '.pls'}
        
        return ext in (audio_extensions | video_extensions | playlist_extensions)
    
    @staticmethod
    def prepare_media_for_loading(file_path: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Prepare a media file for loading with validation and information gathering.
        
        Args:
            file_path (str): Path to the media file
            
        Returns:
            Tuple[bool, str, Dict]: (success, normalized_absolute_path, file_info)
        """
        # Validate the path
        is_valid, actual_path, error_msg = MediaManager.validate_media_path(file_path)
        if not is_valid:
            return False, actual_path, {'error': error_msg}
        
        # Normalize the path to ensure consistency across all components
        try:
            normalized_path = os.path.abspath(actual_path)
            
            # Handle network drive mappings (Windows specific)
            if os.name == 'nt':
                normalized_path = MediaManager._resolve_network_path(normalized_path)
            
        except Exception as e:
            Logger.instance().error(caller="MediaManager", msg=f"[MediaManager] Warning: Failed to normalize path {actual_path}: {e}")
            normalized_path = actual_path  # Fall back to original if normalization fails
        
        # Get file information using the normalized path
        file_info = MediaManager.get_file_info(normalized_path)
        if not file_info.get('is_valid', False):
            return False, normalized_path, file_info
        
        # Check if it's a supported media type
        if not MediaManager.is_media_file(normalized_path):
            file_info['warning'] = f"File type may not be supported: {normalized_path}"
        
        return True, normalized_path, file_info
    
    @staticmethod
    def _resolve_network_path(path: str) -> str:
        """
        Resolve mapped network drives to their UNC paths for consistent database storage.
        
        Args:
            path (str): File path that might use a mapped drive
            
        Returns:
            str: UNC path if it's a mapped network drive, otherwise the original path
        """
        if not path or len(path) < 3:
            return path
            
        # Resolve mapped drives WITHOUT spawning a subprocess (prevents console flashes in GUI exe)
        resolved = resolve_mapped_drive_to_unc(path)
        if resolved != path:
            Logger.instance().debug(caller="MediaManager", msg=f"[MediaManager] Resolved mapped drive: {path} -> {resolved}")
        return resolved
        
        # Return original path if not a mapped drive or resolution failed
        return path
    
    @staticmethod
    def compare_media_paths(path1: str, path2: str) -> bool:
        """
        Compare two media paths to determine if they refer to the same file.
        
        Args:
            path1 (str): First path to compare
            path2 (str): Second path to compare
            
        Returns:
            bool: True if paths refer to the same file
        """
        if not path1 or not path2:
            return False
        
        try:
            # Normalize paths for comparison
            norm_path1 = os.path.normpath(os.path.abspath(path1))
            norm_path2 = os.path.normpath(os.path.abspath(path2))
            return norm_path1 == norm_path2
        except Exception:
            # Fall back to string comparison if path normalization fails
            return path1 == path2
    
    @staticmethod
    def get_media_directory(file_path: str) -> Optional[str]:
        """
        Get the directory containing a media file.
        
        Args:
            file_path (str): Path to the media file
            
        Returns:
            Optional[str]: Directory path, or None if invalid
        """
        if not file_path or not os.path.exists(file_path):
            return None
        
        return os.path.dirname(os.path.abspath(file_path))
    
    @staticmethod
    def suggest_backup_files(file_path: str, max_suggestions: int = 3) -> List[str]:
        """
        Suggest backup files in the same directory if the original file is not found.
        
        Args:
            file_path (str): Original file path that wasn't found
            max_suggestions (int): Maximum number of suggestions to return
            
        Returns:
            List[str]: List of suggested alternative files
        """
        if not file_path:
            return []
        
        directory = os.path.dirname(file_path)
        if not os.path.exists(directory):
            return []
        
        original_basename = os.path.basename(file_path)
        original_name, original_ext = os.path.splitext(original_basename)
        
        suggestions = []
        try:
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                if os.path.isfile(item_path) and MediaManager.is_media_file(item_path):
                    # Prioritize files with similar names
                    item_name, item_ext = os.path.splitext(item)
                    if (original_name.lower() in item_name.lower() or 
                        item_name.lower() in original_name.lower()):
                        suggestions.append(item_path)
                        
                if len(suggestions) >= max_suggestions:
                    break
                    
        except Exception as e:
            Logger.instance().error(caller="MediaManager", msg=f"[MediaManager] Error suggesting backup files: {e}")
        
        return suggestions 