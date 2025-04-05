# Music Player

A simple music player application built with Python and PyQt6.

## Features

- Play, pause, and stop music playback
- Dark theme UI
- Support for common audio formats (MP3, WAV, OGG, FLAC)
- Basic playlist functionality

## Requirements

- Python 3.9 or higher
- Poetry for dependency management

## Installation

1. Clone this repository:
```
git clone https://github.com/yourusername/music-player.git
cd music-player
```

2. Install dependencies using Poetry:
```
poetry install
```

## Running the application

```
poetry run python -m music_player.main
```

## Development

This project uses Poetry for dependency management. To add new dependencies:

```
poetry add package-name
```

## Project Structure

- `music_player/` - Main package
  - `core/` - Core functionality and backend logic
  - `ui/` - User interface components
  - `resources/` - Application resources (icons, etc.)

## License

MIT 