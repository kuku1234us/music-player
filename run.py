#!/usr/bin/env python
"""
Entry point script to run the Music Player application.
"""
import sys
import os

# Add the project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from music_player.main import main

if __name__ == "__main__":
    main() 