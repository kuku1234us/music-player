"""
AI module for music player application.
Includes tools for music classification and analysis.
"""

# Remove the old import
# from .MusicPicks import MusicClassifier

# Add the new import
from .groq_music_model import GroqMusicModel

# Update __all__
__all__ = ['GroqMusicModel'] 