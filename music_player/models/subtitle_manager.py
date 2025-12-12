"""
Subtitle Manager for handling subtitle-related business logic.
"""
import re
from typing import Optional, List, Dict, Any
from qt_base_app.models.logger import Logger


class SubtitleManager:
    """
    Manager for handling subtitle-related operations and state.
    Encapsulates subtitle business logic to keep GUI code clean.
    """
    
    def __init__(self):
        self.reset_state()
    
    def reset_state(self):
        """Reset internal subtitle state tracking."""
        self.has_subtitle_tracks = False
        self.subtitle_enabled = False
        self.current_subtitle_track = -1
        self.subtitle_tracks = []
        self.current_subtitle_language = ""
    
    def extract_language_code(self, track_name) -> str:
        """
        Extract a 2-3 letter language code from a subtitle track name.
        
        Args:
            track_name (str or bytes): Full name of the subtitle track
            
        Returns:
            str: Extracted language code or "SUB" if not found
        """
        # If track_name is bytes, decode it to a string
        if isinstance(track_name, bytes):
            try:
                track_name = track_name.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    # Try another common encoding if utf-8 fails
                    track_name = track_name.decode('latin-1')
                except Exception:
                    # If all decoding fails, return default
                    Logger.instance().warning(caller="SubtitleManager", msg=f"[SubtitleManager] Warning: Could not decode subtitle track name: {track_name}")
                    return "SUB"
        
        # If the track name is empty, return default value
        if not track_name:
            return "SUB"
            
        # Try to extract any 2-3 letter code in square brackets or parentheses
        match = re.search(r'[\[\(]([a-z]{2,3})[\]\)]', track_name.lower())
        if match:
            return match.group(1).upper()
            
        # Try to find common language identifiers in the track name
        track_lower = track_name.lower()
        
        # Look for language name patterns like "English" or "en"
        language_patterns = [
            # Match standalone 2-letter codes
            (r'\b(en|fr|es|de|it|ru|ja|zh|ko|ar|nl|pt|sv|pl|tr|he|vi|th)\b', 0),
            # Match standalone 3-letter codes
            (r'\b(eng|fre|spa|ger|ita|rus|jpn|chi|kor)\b', 0),
            # Extract from language names (capture first 2 chars)
            (r'\b(english|french|spanish|german|italian|russian|japanese|chinese|korean|arabic|dutch|portuguese|swedish|polish|turkish|hebrew|vietnamese|thai)\b', 2)
        ]
        
        for pattern, length in language_patterns:
            match = re.search(pattern, track_lower)
            if match:
                code = match.group(1)
                # If it's a full language name, take first 2 characters
                if length > 0:
                    code = code[:length]
                return code.upper()
                
        # If track name includes "subtitles" or similar terms, extract nearby text
        subtitle_match = re.search(r'(subtitle|caption)s?\s*[:\-]?\s*([a-z]{2,3}|[A-Za-z]+)', track_lower)
        if subtitle_match:
            code = subtitle_match.group(2)
            # If it's a language name rather than code, take first 2 chars
            if len(code) > 3:
                code = code[:2]
            return code.upper()
                
        # Default to "SUB" if no language code found
        return "SUB"
    
    def process_subtitle_tracks(self, subtitle_tracks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Process subtitle tracks and determine the best track to auto-enable.
        
        Args:
            subtitle_tracks (List[Dict]): List of subtitle track information
            
        Returns:
            Optional[Dict]: Best track to enable, or None if no suitable track found
        """
        if not subtitle_tracks:
            return None
        
        self.subtitle_tracks = subtitle_tracks
        self.has_subtitle_tracks = True
        
        # Find the first non-disabled track (usually ID 1, as 0 is often "Disabled")
        suitable_track = None
        for track in subtitle_tracks:
            # Skip track 0 which is usually "Disabled"
            if track['id'] > 0:
                suitable_track = track
                # Prefer to use display_name if available
                track_name = track.get('display_name', track['name'])
                # Check if language is available directly or extract from name
                self.current_subtitle_language = track.get('language') or self.extract_language_code(track_name)
                break
        
        # If we found a suitable track, prepare it for enabling
        if suitable_track is not None:
            return suitable_track
        
        # If only track 0 exists, try it anyway
        if subtitle_tracks and len(subtitle_tracks) > 0:
            track_0 = subtitle_tracks[0]
            if track_0:
                track_name = track_0.get('display_name', track_0['name'])
                self.current_subtitle_language = (track_0.get('language') or 
                                                 self.extract_language_code(track_name))
                return track_0
        
        return None
    
    def update_subtitle_state(self, track_id: int, enabled: bool) -> bool:
        """
        Update the internal subtitle state when a track is enabled/disabled.
        
        Args:
            track_id (int): ID of the subtitle track
            enabled (bool): Whether the track was successfully enabled
            
        Returns:
            bool: True if state was updated successfully
        """
        if enabled:
            self.subtitle_enabled = True
            self.current_subtitle_track = track_id
            
            # Update language if we have track information
            for track in self.subtitle_tracks:
                if track['id'] == track_id:
                    track_name = track.get('display_name', track['name'])
                    self.current_subtitle_language = (track.get('language') or 
                                                     self.extract_language_code(track_name))
                    break
        else:
            self.subtitle_enabled = False
            # Keep track_id for potential re-enabling, but mark as disabled
        
        return True
    
    def get_next_subtitle_track(self) -> Optional[Dict[str, Any]]:
        """
        Get the next subtitle track for cycling through available tracks.
        
        Returns:
            Optional[Dict]: Next track to enable, or None if no tracks available
        """
        if not self.has_subtitle_tracks or not self.subtitle_tracks:
            return None
            
        # Find the next track after the current one
        current_track = self.current_subtitle_track
        next_track = None
        found_current = False
        
        # First pass: find a track after the current one
        for track in self.subtitle_tracks:
            if found_current and track['id'] > 0:  # Skip disabled tracks (usually id=0)
                next_track = track
                break
            if track['id'] == current_track:
                found_current = True
                
        # If we didn't find a next track, loop back to the first one
        if next_track is None:
            for track in self.subtitle_tracks:
                if track['id'] > 0:  # Skip disabled tracks
                    next_track = track
                    break
                    
        # If we still don't have a track, try to enable track 0 as a fallback
        if next_track is None and self.subtitle_tracks:
            next_track = self.subtitle_tracks[0]
        
        return next_track
    
    def get_subtitle_state_info(self) -> Dict[str, Any]:
        """
        Get current subtitle state information for UI updates.
        
        Returns:
            Dict: Subtitle state information
        """
        return {
            'has_subtitle_tracks': self.has_subtitle_tracks,
            'subtitle_enabled': self.subtitle_enabled,
            'current_subtitle_language': self.current_subtitle_language,
            'subtitle_tracks': self.subtitle_tracks
        }
    
    def select_track_by_id(self, track_id: int) -> Optional[Dict[str, Any]]:
        """
        Select a specific subtitle track by ID.
        
        Args:
            track_id (int): ID of the subtitle track to select, or -1 to disable
            
        Returns:
            Optional[Dict]: Track information if found, None otherwise
        """
        if track_id < 0:
            # Disable subtitles
            self.subtitle_enabled = False
            return {'id': -1, 'action': 'disable'}
            
        # Find the track with the given ID
        for track in self.subtitle_tracks:
            if track['id'] == track_id:
                return track
                
        return None 