"""
Audio player core functionality.
"""
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaFormat


class Player(QObject):
    """
    Music player implementation using PyQt6 QMediaPlayer.
    
    Signals:
        position_changed: Emitted when the playback position changes
        duration_changed: Emitted when the duration of the media changes
        state_changed: Emitted when the player state changes
    """
    position_changed = pyqtSignal(int)
    duration_changed = pyqtSignal(int)
    state_changed = pyqtSignal(QMediaPlayer.PlaybackState)
    
    def __init__(self):
        super().__init__()
        
        # Create media player and audio output
        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)
        
        # Connect signals
        self._player.positionChanged.connect(self.position_changed)
        self._player.durationChanged.connect(self.duration_changed)
        self._player.playbackStateChanged.connect(self.state_changed)
    
    def play(self):
        """Start or resume playback."""
        self._player.play()
    
    def pause(self):
        """Pause playback."""
        self._player.pause()
    
    def stop(self):
        """Stop playback."""
        self._player.stop()
    
    def set_source(self, url):
        """
        Set the media source to play.
        
        Args:
            url: URL of the media to play
        """
        self._player.setSource(url)
    
    def set_position(self, position):
        """
        Set the current playback position.
        
        Args:
            position: Position in milliseconds
        """
        self._player.setPosition(position)
    
    def set_volume(self, volume):
        """
        Set the audio volume.
        
        Args:
            volume: Volume from 0.0 (mute) to 1.0 (full volume)
        """
        self._audio_output.setVolume(volume)
    
    def get_position(self):
        """Get the current playback position in milliseconds."""
        return self._player.position()
    
    def get_duration(self):
        """Get the total duration of the current media in milliseconds."""
        return self._player.duration()
    
    def get_state(self):
        """Get the current playback state."""
        return self._player.playbackState()
    
    @staticmethod
    def get_supported_mime_types():
        """
        Get a list of supported audio mime types.
        
        Returns:
            List of strings containing supported mime types
        """
        result = []
        audio_mime_types = QMediaFormat.supportedMimeTypes(QMediaFormat.ConversionMode.Decode)
        
        for mime_type in audio_mime_types:
            mime_type_str = mime_type.toString()
            if mime_type_str.startswith("audio/"):
                result.append(mime_type_str)
        
        return result 