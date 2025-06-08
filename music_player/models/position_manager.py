"""
Position Manager for Music Player Auto-Save Functionality.

This module manages the automatic saving and restoring of playback positions
using SQLite database storage in the user-configurable working directory.
"""
import os
import sqlite3
import threading
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
import time

from qt_base_app.models.settings_manager import SettingsManager, SettingType
from qt_base_app.models.logger import Logger
from music_player.models.settings_defs import PREF_WORKING_DIR_KEY, DEFAULT_WORKING_DIR


class PlaybackPositionManager:
    """
    Singleton manager for saving and restoring playback positions using SQLite.
    Positions are stored in the user-configurable Working Directory.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Prevent multiple initialization
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self.settings = SettingsManager.instance()
        self.logger = Logger.instance()
        self._db_lock = threading.Lock()
        self._retry_count = 3
        self._retry_delay = 0.1  # 100ms delay between retries
        
        self._init_database()
    
    @classmethod
    def instance(cls):
        """Get the singleton instance of PlaybackPositionManager."""
        return cls()
    
    def _get_database_path(self) -> str:
        """Get the path to the SQLite database file."""
        working_dir = self.settings.get(PREF_WORKING_DIR_KEY, 
                                       DEFAULT_WORKING_DIR, 
                                       SettingType.PATH)
        working_dir = Path(working_dir)
        working_dir.mkdir(parents=True, exist_ok=True)
        return str(working_dir / "playback_positions.db")
    
    def _init_database(self):
        """Initialize the SQLite database and create tables if they don't exist."""
        db_path = self._get_database_path()
        self.logger.info(self.__class__.__name__, f"Initializing position database at: {db_path}")
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Create table with proper schema including playback_rate and subtitle state
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS playback_positions (
                        file_path TEXT PRIMARY KEY,
                        position_ms INTEGER NOT NULL,
                        duration_ms INTEGER NOT NULL,
                        playback_rate REAL NOT NULL DEFAULT 1.0,
                        subtitle_enabled INTEGER NOT NULL DEFAULT 0,
                        subtitle_track_id INTEGER NOT NULL DEFAULT -1,
                        subtitle_language TEXT DEFAULT '',
                        last_updated TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                """)
                
                # Check if columns exist, add them if missing (for existing databases)
                cursor.execute("PRAGMA table_info(playback_positions)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'playback_rate' not in columns:
                    self.logger.info(self.__class__.__name__, "Adding playback_rate column to existing database")
                    cursor.execute("ALTER TABLE playback_positions ADD COLUMN playback_rate REAL NOT NULL DEFAULT 1.0")
                
                if 'subtitle_enabled' not in columns:
                    self.logger.info(self.__class__.__name__, "Adding subtitle state columns to existing database")
                    cursor.execute("ALTER TABLE playback_positions ADD COLUMN subtitle_enabled INTEGER NOT NULL DEFAULT 0")
                    cursor.execute("ALTER TABLE playback_positions ADD COLUMN subtitle_track_id INTEGER NOT NULL DEFAULT -1")
                    cursor.execute("ALTER TABLE playback_positions ADD COLUMN subtitle_language TEXT DEFAULT ''")
                
                # Create index for performance
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_last_updated 
                    ON playback_positions(last_updated)
                """)
                
                conn.commit()
                self.logger.info(self.__class__.__name__, "Position database initialized successfully")
                
        except sqlite3.Error as e:
            self.logger.error(self.__class__.__name__, f"Failed to initialize database: {e}")
            raise RuntimeError(f"Database initialization failed: {e}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a connection to the SQLite database with retry logic."""
        db_path = self._get_database_path()
        
        for attempt in range(self._retry_count):
            try:
                # Set timeout to handle database locking
                conn = sqlite3.connect(db_path, timeout=5.0)
                conn.execute("PRAGMA foreign_keys = ON")
                return conn
                
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower() and attempt < self._retry_count - 1:
                    self.logger.warning(self.__class__.__name__, 
                                      f"Database locked, retrying in {self._retry_delay}s (attempt {attempt + 1}/{self._retry_count})")
                    time.sleep(self._retry_delay)
                    self._retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    self.logger.error(self.__class__.__name__, f"Database connection failed: {e}")
                    raise
            except sqlite3.Error as e:
                self.logger.error(self.__class__.__name__, f"Database error: {e}")
                raise
        
        raise sqlite3.OperationalError(f"Failed to connect to database after {self._retry_count} attempts")
    
    def save_position(self, file_path: str, position_ms: int, duration_ms: int, playback_rate: float = 1.0,
                     subtitle_enabled: bool = False, subtitle_track_id: int = -1, subtitle_language: str = '') -> bool:
        """
        Save the playback position, rate, and subtitle state for a media file.
        
        Args:
            file_path (str): Absolute path to the media file
            position_ms (int): Current playback position in milliseconds
            duration_ms (int): Total duration of the media in milliseconds
            playback_rate (float): Current playback rate (1.0 = normal speed)
            subtitle_enabled (bool): Whether subtitles are currently enabled
            subtitle_track_id (int): ID of the currently selected subtitle track (-1 if disabled)
            subtitle_language (str): Language code of the current subtitle track
            
        Returns:
            bool: True if save was successful, False otherwise
        """
        if not file_path or position_ms < 0 or duration_ms <= 0:
            self.logger.warning(self.__class__.__name__, 
                              f"Invalid parameters for save_position: path={file_path}, pos={position_ms}, dur={duration_ms}")
            return False
        
        # Validate position is within bounds
        if position_ms > duration_ms:
            self.logger.warning(self.__class__.__name__, 
                              f"Position {position_ms}ms exceeds duration {duration_ms}ms for {file_path}")
            return False
        
        # Validate playback rate is reasonable
        if playback_rate <= 0 or playback_rate > 10.0:  # Allow up to 10x speed
            self.logger.warning(self.__class__.__name__, 
                              f"Invalid playback rate {playback_rate} for {file_path}, using 1.0")
            playback_rate = 1.0
        
        # Normalize file path
        try:
            normalized_path = os.path.abspath(file_path)
            
            # Handle network drive mappings for consistency with MediaManager
            if os.name == 'nt':
                normalized_path = self._resolve_network_path(normalized_path)
                
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Failed to normalize path {file_path}: {e}")
            return False
        
        # Check if file exists
        if not os.path.exists(normalized_path):
            self.logger.warning(self.__class__.__name__, f"File does not exist: {normalized_path}")
            return False
        
        timestamp = datetime.now().isoformat()
        
        try:
            with self._db_lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Use INSERT OR REPLACE for upsert functionality
                    cursor.execute("""
                        INSERT OR REPLACE INTO playback_positions 
                        (file_path, position_ms, duration_ms, playback_rate, subtitle_enabled, subtitle_track_id, subtitle_language, last_updated, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 
                               COALESCE((SELECT created_at FROM playback_positions WHERE file_path = ?), ?))
                    """, (normalized_path, position_ms, duration_ms, playback_rate, int(subtitle_enabled), subtitle_track_id, subtitle_language, timestamp, normalized_path, timestamp))
                    
                    conn.commit()
                    return True
                    
        except sqlite3.Error as e:
            self.logger.error(self.__class__.__name__, f"Failed to save position for {file_path}: {e}")
            return False
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Unexpected error saving position: {e}")
            return False
    
    def get_saved_position(self, file_path: str) -> tuple[Optional[int], float, bool, int, str]:
        """
        Get the saved playback position, rate, and subtitle state for a media file.
        
        Args:
            file_path (str): Absolute path to the media file
            
        Returns:
            tuple[Optional[int], float, bool, int, str]: (position in milliseconds or None, playback rate, subtitle enabled, subtitle track id, subtitle language)
        """
        if not file_path:
            return None, 1.0, False, -1, ''
        
        # Normalize file path
        try:
            normalized_path = os.path.abspath(file_path)
            
            # Handle network drive mappings for consistency with MediaManager
            if os.name == 'nt':
                normalized_path = self._resolve_network_path(normalized_path)
                
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Failed to normalize path {file_path}: {e}")
            return None, 1.0, False, -1, ''
        
        try:
            with self._db_lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT position_ms, duration_ms, playback_rate, subtitle_enabled, subtitle_track_id, subtitle_language FROM playback_positions WHERE file_path = ?",
                        (normalized_path,)
                    )
                    result = cursor.fetchone()
                    
                    if result:
                        position_ms, duration_ms, playback_rate, subtitle_enabled, subtitle_track_id, subtitle_language = result
                        
                        # Handle case where fields might be None from old database entries
                        if playback_rate is None:
                            playback_rate = 1.0
                        if subtitle_enabled is None:
                            subtitle_enabled = False
                        if subtitle_track_id is None:
                            subtitle_track_id = -1
                        if subtitle_language is None:
                            subtitle_language = ''
                        
                        # Convert subtitle_enabled from integer back to boolean
                        subtitle_enabled = bool(subtitle_enabled)
                        
                        # Validate that the saved position is reasonable
                        if 0 <= position_ms <= duration_ms:
                            return position_ms, playback_rate, subtitle_enabled, subtitle_track_id, subtitle_language
                        else:
                            self.logger.warning(self.__class__.__name__, 
                                              f"Invalid saved position {position_ms}ms (duration: {duration_ms}ms) for {file_path}")
                            # Clean up the invalid entry
                            self.clear_position(normalized_path)
                            return None, 1.0, False, -1, ''
                    
                    return None, 1.0, False, -1, ''
                    
        except sqlite3.Error as e:
            self.logger.error(self.__class__.__name__, f"Failed to get position for {file_path}: {e}")
            return None, 1.0, False, -1, ''
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Unexpected error getting position: {e}")
            return None, 1.0, False, -1, ''
    
    def _resolve_network_path(self, path: str) -> str:
        """
        Resolve mapped network drives to their UNC paths for consistent database storage.
        
        Args:
            path (str): File path that might use a mapped drive
            
        Returns:
            str: UNC path if it's a mapped network drive, otherwise the original path
        """
        if not path or len(path) < 3:
            return path
            
        # Check if it's a drive letter path (e.g., Z:\...)
        if path[1:3] == ':\\':
            drive_letter = path[0].upper()
            
            try:
                import subprocess
                # Use Windows NET USE command to get UNC path for the drive
                result = subprocess.run(
                    ['net', 'use', f'{drive_letter}:'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    # Parse the output to find the remote path
                    output_lines = result.stdout.strip().split('\n')
                    for line in output_lines:
                        if 'Remote name' in line or 'remote name' in line:
                            # Extract UNC path from "Remote name \\server\share"
                            parts = line.split()
                            if len(parts) >= 3 and parts[-1].startswith('\\\\'):
                                unc_root = parts[-1]
                                # Replace drive portion with UNC root
                                relative_path = path[3:]  # Remove "Z:\"
                                unc_path = os.path.join(unc_root, relative_path).replace('\\', '/')
                                unc_path = unc_path.replace('/', '\\')  # Ensure Windows separators
                                return unc_path
                        
                        # Alternative parsing for different NET USE output formats
                        if '\\\\' in line and drive_letter in line:
                            # Find UNC path in the line
                            unc_start = line.find('\\\\')
                            if unc_start >= 0:
                                # Extract everything from \\ onwards, but stop at whitespace
                                unc_part = line[unc_start:].split()[0]
                                if unc_part.count('\\') >= 3:  # Valid UNC path \\server\share
                                    relative_path = path[3:]  # Remove "Z:\"
                                    unc_path = os.path.join(unc_part, relative_path).replace('\\', '/')
                                    unc_path = unc_path.replace('/', '\\')  # Ensure Windows separators
                                    return unc_path
                                    
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError) as e:
                self.logger.warning(self.__class__.__name__, f"Could not resolve network drive {drive_letter}: {e}")
            except Exception as e:
                self.logger.warning(self.__class__.__name__, f"Unexpected error resolving network drive {drive_letter}: {e}")
        
        # Return original path if not a mapped drive or resolution failed
        return path
    
    def clear_position(self, file_path: str) -> bool:
        """
        Clear the saved position for a media file.
        
        Args:
            file_path (str): Absolute path to the media file
            
        Returns:
            bool: True if cleared successfully, False otherwise
        """
        if not file_path:
            return False
        
        # Normalize file path
        try:
            normalized_path = os.path.abspath(file_path)
            
            # Handle network drive mappings for consistency with MediaManager
            if os.name == 'nt':
                normalized_path = self._resolve_network_path(normalized_path)
                
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Failed to normalize path {file_path}: {e}")
            return False
        
        try:
            with self._db_lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM playback_positions WHERE file_path = ?", (normalized_path,))
                    conn.commit()
                    
                    return cursor.rowcount > 0
                        
        except sqlite3.Error as e:
            self.logger.error(self.__class__.__name__, f"Failed to clear position for {file_path}: {e}")
            return False
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Unexpected error clearing position: {e}")
            return False
    
    def cleanup_deleted_files(self) -> int:
        """
        Remove position entries for files that no longer exist on disk.
        
        Returns:
            int: Number of entries removed
        """
        removed_count = 0
        
        try:
            with self._db_lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Get all file paths from database
                    cursor.execute("SELECT file_path FROM playback_positions")
                    all_paths = cursor.fetchall()
                    
                    paths_to_remove = []
                    for (file_path,) in all_paths:
                        try:
                            if not os.path.exists(file_path):
                                paths_to_remove.append(file_path)
                        except (OSError, ValueError) as e:
                            # Handle invalid paths or permission errors
                            self.logger.warning(self.__class__.__name__, 
                                              f"Cannot check existence of {file_path}: {e}")
                            paths_to_remove.append(file_path)
                    
                    # Remove non-existent files in batch
                    if paths_to_remove:
                        cursor.executemany("DELETE FROM playback_positions WHERE file_path = ?", 
                                         [(path,) for path in paths_to_remove])
                        removed_count = cursor.rowcount
                        conn.commit()
                        
                        self.logger.info(self.__class__.__name__, 
                                       f"Cleanup removed {removed_count} entries for deleted/invalid files")
                    else:
                        self.logger.info(self.__class__.__name__, "Cleanup found no deleted files to remove")
                    
        except sqlite3.Error as e:
            self.logger.error(self.__class__.__name__, f"Database error during cleanup: {e}")
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Unexpected error during cleanup: {e}")
        
        return removed_count
    
    def get_database_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics about the position database.
        
        Returns:
            dict: Statistics including total files, total hours, database size, etc.
        """
        stats = {
            'total_files': 0,
            'total_hours': 0.0,
            'total_duration_hours': 0.0,
            'database_size_bytes': 0,
            'database_size_mb': 0.0,
            'oldest_entry': None,
            'newest_entry': None
        }
        
        try:
            with self._db_lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Count total files
                    cursor.execute("SELECT COUNT(*) FROM playback_positions")
                    stats['total_files'] = cursor.fetchone()[0]
                    
                    if stats['total_files'] > 0:
                        # Calculate total saved time (positions)
                        cursor.execute("SELECT SUM(position_ms) FROM playback_positions")
                        total_position_ms = cursor.fetchone()[0] or 0
                        stats['total_hours'] = total_position_ms / (1000 * 60 * 60)
                        
                        # Calculate total duration time
                        cursor.execute("SELECT SUM(duration_ms) FROM playback_positions")
                        total_duration_ms = cursor.fetchone()[0] or 0
                        stats['total_duration_hours'] = total_duration_ms / (1000 * 60 * 60)
                        
                        # Get oldest and newest entries
                        cursor.execute("SELECT MIN(created_at) FROM playback_positions")
                        stats['oldest_entry'] = cursor.fetchone()[0]
                        
                        cursor.execute("SELECT MAX(last_updated) FROM playback_positions")
                        stats['newest_entry'] = cursor.fetchone()[0]
            
            # Get database file size
            db_path = self._get_database_path()
            if os.path.exists(db_path):
                stats['database_size_bytes'] = os.path.getsize(db_path)
                stats['database_size_mb'] = stats['database_size_bytes'] / (1024 * 1024)
                
        except sqlite3.Error as e:
            self.logger.error(self.__class__.__name__, f"Database error getting stats: {e}")
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Unexpected error getting stats: {e}")
        
        return stats
    
    def is_position_significant(self, current_position_ms: int, last_saved_position_ms: int) -> bool:
        """
        Check if the position change is significant enough to warrant saving.
        
        Args:
            current_position_ms (int): Current playback position
            last_saved_position_ms (int): Last saved position
            
        Returns:
            bool: True if the change is significant (>1 second)
        """
        return abs(current_position_ms - last_saved_position_ms) > 1000

    def should_save_position(self, position_ms: int, duration_ms: int, last_saved_position_ms: int = 0) -> bool:
        """
        Comprehensive check for whether a position should be saved based on all criteria.
        
        Args:
            position_ms (int): Current playback position in milliseconds
            duration_ms (int): Total duration of the media in milliseconds
            last_saved_position_ms (int): Last saved position for change detection
            
        Returns:
            bool: True if position should be saved, False otherwise
        """
        # Basic validation
        if position_ms < 0 or duration_ms <= 0:
            return False
        
        # Don't save very beginning (first 5 seconds)
        if position_ms <= 5000:
            return False
        
        # Don't save very end (last 10 seconds)
        if position_ms >= (duration_ms - 10000):
            return False
        
        # Check if position changed significantly (if last position provided)
        if last_saved_position_ms > 0:
            return self.is_position_significant(position_ms, last_saved_position_ms)
        
        return True

    def handle_periodic_save(self, file_path: str, current_pos: int, current_duration: int, 
                           current_rate: float, last_saved_position: int, subtitle_enabled: bool = False,
                           subtitle_track_id: int = -1, subtitle_language: str = '') -> tuple[bool, int]:
        """
        Handle periodic position saving with all business logic encapsulated.
        
        Args:
            file_path (str): Path to the media file
            current_pos (int): Current playback position in milliseconds
            current_duration (int): Total duration in milliseconds
            current_rate (float): Current playback rate
            last_saved_position (int): Last saved position for change detection
            subtitle_enabled (bool): Whether subtitles are currently enabled
            subtitle_track_id (int): ID of the currently selected subtitle track
            subtitle_language (str): Language code of the current subtitle track
            
        Returns:
            tuple[bool, int]: (success, new_last_saved_position)
        """
        # Validate inputs
        if not file_path or not current_pos or not current_duration:
            return False, last_saved_position
        
        # Check if position should be saved
        if not self.should_save_position(current_pos, current_duration, last_saved_position):
            return False, last_saved_position
        
        # Save the position, rate, and subtitle state
        success = self.save_position(file_path, current_pos, current_duration, current_rate, 
                                   subtitle_enabled, subtitle_track_id, subtitle_language)
        
        if success:
            return True, current_pos
        else:
            return False, last_saved_position

    def handle_position_on_media_change(self, old_file_path: str, new_file_path: str, 
                                      current_pos: int, current_duration: int, current_rate: float,
                                      subtitle_enabled: bool = False, subtitle_track_id: int = -1, 
                                      subtitle_language: str = '') -> tuple[bool, int]:
        """
        Handle position saving when media changes, with validation and business logic.
        
        Args:
            old_file_path (str): Path to the previous media file
            new_file_path (str): Path to the new media file (for comparison)
            current_pos (int): Current playback position in milliseconds
            current_duration (int): Total duration in milliseconds
            current_rate (float): Current playback rate
            subtitle_enabled (bool): Whether subtitles are currently enabled
            subtitle_track_id (int): ID of the currently selected subtitle track
            subtitle_language (str): Language code of the current subtitle track
            
        Returns:
            tuple[bool, int]: (success, saved_position)
        """
        # Only save if we're switching to a different file
        if not old_file_path or old_file_path == new_file_path:
            return False, 0
        
        # Check if position meets save criteria
        if not self.should_save_position(current_pos, current_duration):
            return False, 0
        
        success = self.save_position(old_file_path, current_pos, current_duration, current_rate,
                                   subtitle_enabled, subtitle_track_id, subtitle_language)
        
        if success:
            return True, current_pos
        else:
            return False, 0

    def handle_manual_action_save(self, file_path: str, current_pos: int, current_duration: int, 
                                current_rate: float, action_type: str = "manual", subtitle_enabled: bool = False,
                                subtitle_track_id: int = -1, subtitle_language: str = '') -> tuple[bool, int]:
        """
        Handle position saving for manual actions (pause, stop) with business logic.
        
        Args:
            file_path (str): Path to the media file
            current_pos (int): Current playback position in milliseconds
            current_duration (int): Total duration in milliseconds
            current_rate (float): Current playback rate
            action_type (str): Type of action for logging ("pause", "stop", "manual")
            subtitle_enabled (bool): Whether subtitles are currently enabled
            subtitle_track_id (int): ID of the currently selected subtitle track
            subtitle_language (str): Language code of the current subtitle track
            
        Returns:
            tuple[bool, int]: (success, saved_position)
        """
        if not file_path or not current_pos or not current_duration:
            return False, 0
        
        # Check if position meets save criteria
        if not self.should_save_position(current_pos, current_duration):
            return False, 0
        
        success = self.save_position(file_path, current_pos, current_duration, current_rate,
                                   subtitle_enabled, subtitle_track_id, subtitle_language)
        
        if success:
            return True, current_pos
        else:
            return False, 0 