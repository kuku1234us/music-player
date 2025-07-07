"""
Audio Manager for handling audio-related business logic.
"""
import re
from typing import Optional, List, Dict, Any


class AudioManager:
    """
    Manager for handling audio track selection operations and state.
    Encapsulates audio track business logic to keep GUI code clean.
    """
    
    def __init__(self):
        self.reset_state()
    
    def reset_state(self):
        """Reset internal audio state tracking."""
        self.has_multiple_audio_tracks = False
        self.current_audio_track = -1
        self.audio_tracks = []
        self.current_audio_language = ""

    def extract_language_code(self, track_name) -> str:
        """
        Extract a 2-3 letter language code from a track name.
        
        Args:
            track_name (str or bytes): Full name of the track
            
        Returns:
            str: Extracted language code or "AUD" if not found
        """
        if isinstance(track_name, bytes):
            try:
                track_name = track_name.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    track_name = track_name.decode('latin-1')
                except Exception:
                    return "AUD"

        if not track_name:
            return "AUD"
            
        # Try to extract any 2-3 letter code in square brackets or parentheses
        match = re.search(r'[\[\(]([a-z]{2,3})[\]\)]', track_name.lower())
        if match:
            return match.group(1).upper()
            
        # Try to find common language identifiers
        track_lower = track_name.lower()
        
        language_patterns = [
            (r'\b(en|fr|es|de|it|ru|ja|zh|ko|ar|nl|pt|sv|pl|tr|he|vi|th)\b', 0),
            (r'\b(eng|fre|spa|ger|ita|rus|jpn|chi|kor)\b', 0),
            (r'\b(english|french|spanish|german|italian|russian|japanese|chinese|korean|arabic|dutch|portuguese|swedish|polish|turkish|hebrew|vietnamese|thai)\b', 2)
        ]
        
        for pattern, length in language_patterns:
            match = re.search(pattern, track_lower)
            if match:
                code = match.group(1)
                if length > 0:
                    code = code[:length]
                return code.upper()
                
        return "AUD"

    def process_audio_tracks(self, audio_tracks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Process audio tracks and determine the best track to auto-select.
        Prefers English tracks. Always selects at least one track if available.
        Filters out disabled tracks (usually ID -1).
        
        Args:
            audio_tracks (List[Dict]): List of audio track information
            
        Returns:
            Optional[Dict]: Best track to select, or None if no tracks available
        """
        if not audio_tracks:
            self.reset_state()
            return None
        
        self.audio_tracks = audio_tracks
        
        # Filter out disabled tracks (usually ID -1)
        valid_tracks = [track for track in audio_tracks if track.get('id', -1) >= 0]
        
        if not valid_tracks:
            self.reset_state()
            return None
        
        # Only mark as having multiple tracks if there are actually multiple valid tracks
        self.has_multiple_audio_tracks = len(valid_tracks) > 1
        
        # Find the first English track among valid tracks
        english_track = None
        for track in valid_tracks:
            track_name = track.get('name', '')
            lang_code = self.extract_language_code(track_name)
            if lang_code in ('EN', 'ENG'):
                english_track = track
                break
        
        if english_track:
            return english_track
        
        # If no English track, return the first valid track
        return valid_tracks[0] if valid_tracks else None

    def update_audio_state(self, track_id: int):
        """
        Update the internal audio state when a track is selected.
        
        Args:
            track_id (int): ID of the selected audio track
        """
        self.current_audio_track = track_id
        
        # Update language if we have track information
        for track in self.audio_tracks:
            if track['id'] == track_id:
                track_name = track.get('name', '')
                self.current_audio_language = self.extract_language_code(track_name)
                break

    def get_audio_state_info(self) -> Dict[str, Any]:
        """
        Get current audio state information for UI updates.
        
        Returns:
            Dict: Audio state information
        """
        return {
            'has_multiple_audio_tracks': self.has_multiple_audio_tracks,
            'current_audio_language': self.current_audio_language,
            'audio_tracks': self.audio_tracks,
            'current_audio_track': self.current_audio_track
        } 