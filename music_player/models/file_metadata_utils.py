import os
from typing import Dict, Optional
import win32com.client

# Cache for property indices to avoid repeated lookups
_property_index_cache = {}

def _get_property_indices(shell) -> Dict[str, int]:
    """Dynamically get the indices for all available file properties."""
    global _property_index_cache
    if _property_index_cache:
        return _property_index_cache

    # Create a temporary empty folder to query property names
    # This is a standard trick to get the full list of property headers
    temp_folder = shell.NameSpace(os.environ['TEMP'])
    
    indices = {}
    # Iterate through a reasonable number of indices to find all properties
    for i in range(500): # Check up to index 499
        prop_name = temp_folder.GetDetailsOf(None, i)
        if prop_name:
            indices[prop_name] = i
    
    _property_index_cache = indices
    return indices

def get_windows_file_properties(file_path: str) -> Dict[str, str]:
    """Retrieve extended file properties using Windows Shell API."""
    if os.name != 'nt':
        return {}  # Non-Windows fallback

    properties = {}
    try:
        shell = win32com.client.Dispatch("Shell.Application")
        prop_indices = _get_property_indices(shell)
        
        folder = shell.NameSpace(os.path.dirname(file_path))
        file_item = folder.ParseName(os.path.basename(file_path))
        
        for name, index in prop_indices.items():
            value = folder.GetDetailsOf(file_item, index)
            if value:  # Only add if non-empty
                properties[name] = value
                
    except Exception as e:
        print(f"Error getting properties for {file_path}: {e}")
    
    return properties

def get_video_metadata(file_path: str) -> Dict[str, Optional[str]]:
    props = get_windows_file_properties(file_path)
    # Dimensions can be in a single 'Dimensions' field or separate 'Frame width'/'Frame height' fields
    dimensions = props.get('Dimensions')
    if not dimensions or 'x' not in dimensions:
        width = props.get('Frame width', 'N/A')
        height = props.get('Frame height', 'N/A')
        dimensions = f"{width}x{height}" if width != 'N/A' or height != 'N/A' else 'N/A'

    metadata = {
        'dimensions': dimensions,
        'bitrate': props.get('Data rate', 'N/A'),
        'frame_rate': props.get('Frame rate', 'N/A'),
        'audio_bitrate': props.get('Bit rate', 'N/A'), # 'Bit rate' is usually audio-specific for videos
    }
    return metadata

def get_audio_metadata(file_path: str) -> Dict[str, Optional[str]]:
    props = get_windows_file_properties(file_path)
    metadata = {
        'bitrate': props.get('Bit rate', 'N/A'),
        'audio_bitrate': props.get('Bit rate', 'N/A'),
    }
    return metadata

def get_image_metadata(file_path: str) -> Dict[str, Optional[str]]:
    props = get_windows_file_properties(file_path)
    metadata = {
        'dimensions': props.get('Dimensions', 'N/A'),
    }
    return metadata

def is_video_file(filename: str) -> bool:
    video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.webm'}
    return os.path.splitext(filename)[1].lower() in video_extensions

def is_audio_file(filename: str) -> bool:
    audio_extensions = {'.mp3', '.wav', '.flac', '.ogg'}
    return os.path.splitext(filename)[1].lower() in audio_extensions

def is_image_file(filename: str) -> bool:
    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}
    return os.path.splitext(filename)[1].lower() in image_extensions 