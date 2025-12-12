"""
Position Manager for Music Player Auto-Save Functionality.

This module manages the automatic saving and restoring of playback positions
using SQLite database storage in the user-configurable working directory.
"""
import os
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from music_player.models.database import BaseDatabaseManager, DatabaseUtils


class PlaybackPositionManager(BaseDatabaseManager):
    """
    Singleton manager for saving and restoring playback positions using SQLite.
    Positions are stored in the user-configurable Working Directory.
    """
    
    def _init_database(self):
        """Initialize the SQLite database and create tables if they don't exist."""
        db_path = self._get_database_path()
        
        # Create table with proper schema including playback_rate and subtitle state
        table_creation_query = """
            CREATE TABLE IF NOT EXISTS playback_positions (
                file_path TEXT PRIMARY KEY,
                position_ms INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                playback_rate REAL NOT NULL DEFAULT 1.0,
                subtitle_enabled INTEGER NOT NULL DEFAULT 0,
                subtitle_track_id INTEGER NOT NULL DEFAULT -1,
                subtitle_language TEXT DEFAULT '',
                audio_track_id INTEGER NOT NULL DEFAULT -1,
                last_updated TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """
        
        result = self._execute_with_retry(table_creation_query)
        if result is None:
            raise RuntimeError("Database initialization failed")
        
        # Add columns if missing (for existing databases)
        self._add_column_if_missing("playback_positions", "playback_rate", "REAL NOT NULL DEFAULT 1.0")
        self._add_column_if_missing("playback_positions", "subtitle_enabled", "INTEGER NOT NULL DEFAULT 0")
        self._add_column_if_missing("playback_positions", "subtitle_track_id", "INTEGER NOT NULL DEFAULT -1")
        self._add_column_if_missing("playback_positions", "subtitle_language", "TEXT DEFAULT ''")
        self._add_column_if_missing("playback_positions", "audio_track_id", "INTEGER NOT NULL DEFAULT -1")
        
        # Create index for performance
        self._create_index("idx_last_updated", "playback_positions", "last_updated")
        
    
    def save_position(self, file_path: str, position_ms: int, duration_ms: int, playback_rate: float = 1.0,
                     subtitle_enabled: bool = False, subtitle_track_id: int = -1, subtitle_language: str = '',
                     audio_track_id: int = -1) -> bool:
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
            audio_track_id (int): ID of the currently selected audio track (-1 if default)
            
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
        normalized_path = DatabaseUtils.validate_path(file_path)
        if not normalized_path:
            self.logger.error(self.__class__.__name__, f"Failed to normalize path {file_path}")
            return False
        
        # Handle network drive mappings for consistency with MediaManager
        if os.name == 'nt':
            normalized_path = self._resolve_network_path(normalized_path)
        
        # Check if file exists
        if not os.path.exists(normalized_path):
            self.logger.warning(self.__class__.__name__, f"File does not exist: {normalized_path}")
            return False
        
        timestamp = DatabaseUtils.normalize_timestamp()
        
        # Use INSERT OR REPLACE for upsert functionality
        result = self._execute_with_retry("""
            INSERT OR REPLACE INTO playback_positions 
            (file_path, position_ms, duration_ms, playback_rate, subtitle_enabled, subtitle_track_id, subtitle_language, audio_track_id, last_updated, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 
                   COALESCE((SELECT created_at FROM playback_positions WHERE file_path = ?), ?))
        """, (normalized_path, position_ms, duration_ms, playback_rate, int(subtitle_enabled), 
              subtitle_track_id, subtitle_language, audio_track_id, timestamp, normalized_path, timestamp))
        
        return result is not None
    
    def get_saved_position(self, file_path: str) -> tuple[Optional[int], float, bool, int, str, int]:
        """
        Get the saved playback position, rate, and subtitle state for a media file.
        
        Args:
            file_path (str): Absolute path to the media file
            
        Returns:
            tuple[Optional[int], float, bool, int, str, int]: (position in milliseconds or None, playback rate, subtitle enabled, subtitle track id, subtitle language, audio_track_id)
        """
        if not file_path:
            return None, 1.0, False, -1, '', -1
        
        # Normalize file path
        normalized_path = DatabaseUtils.validate_path(file_path)
        if not normalized_path:
            self.logger.error(self.__class__.__name__, f"Failed to normalize path {file_path}")
            return None, 1.0, False, -1, '', -1
        
        # Handle network drive mappings for consistency with MediaManager
        if os.name == 'nt':
            normalized_path = self._resolve_network_path(normalized_path)
        
        result = self._execute_with_retry(
            "SELECT position_ms, duration_ms, playback_rate, subtitle_enabled, subtitle_track_id, subtitle_language, audio_track_id FROM playback_positions WHERE file_path = ?",
            (normalized_path,), fetch_one=True
        )
        
        if result:
            position_ms, duration_ms, playback_rate, subtitle_enabled, subtitle_track_id, subtitle_language, audio_track_id = result
            
            # Handle case where fields might be None from old database entries
            if playback_rate is None:
                playback_rate = 1.0
            if subtitle_enabled is None:
                subtitle_enabled = False
            if subtitle_track_id is None:
                subtitle_track_id = -1
            if subtitle_language is None:
                subtitle_language = ''
            if audio_track_id is None:
                audio_track_id = -1
            
            # Convert subtitle_enabled from integer back to boolean
            subtitle_enabled = bool(subtitle_enabled)
            
            # Validate that the saved position is reasonable
            if 0 <= position_ms <= duration_ms:
                return position_ms, playback_rate, subtitle_enabled, subtitle_track_id, subtitle_language, audio_track_id
            else:
                self.logger.warning(self.__class__.__name__, 
                                  f"Invalid saved position {position_ms}ms (duration: {duration_ms}ms) for {file_path}")
                # Clean up the invalid entry
                self.clear_position(normalized_path)
                return None, 1.0, False, -1, '', -1
        
        return None, 1.0, False, -1, '', -1

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
        normalized_path = DatabaseUtils.validate_path(file_path)
        if not normalized_path:
            self.logger.error(self.__class__.__name__, f"Failed to normalize path {file_path}")
            return False
        
        # Handle network drive mappings for consistency with MediaManager
        if os.name == 'nt':
            normalized_path = self._resolve_network_path(normalized_path)
        
        result = self._execute_with_retry("DELETE FROM playback_positions WHERE file_path = ?", (normalized_path,))
        return result is not None and result > 0
    
    def cleanup_deleted_files(self) -> int:
        """
        Remove position entries for files that no longer exist on disk.
        
        Returns:
            int: Number of entries removed
        """
        # Get all file paths from database
        all_paths_result = self._execute_with_retry("SELECT file_path FROM playback_positions", fetch_all=True)
        if not all_paths_result:
            self.logger.info(self.__class__.__name__, "No entries found to cleanup")
            return 0
        
        paths_to_remove = []
        for (file_path,) in all_paths_result:
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
            operations = [("DELETE FROM playback_positions WHERE file_path = ?", (path,)) for path in paths_to_remove]
            success = self._execute_transaction(operations)
            
            if success:
                removed_count = len(paths_to_remove)
                self.logger.info(self.__class__.__name__, 
                               f"Cleanup removed {removed_count} entries for deleted/invalid files")
                return removed_count
            else:
                self.logger.error(self.__class__.__name__, "Failed to cleanup deleted files")
                return 0
        else:
            self.logger.info(self.__class__.__name__, "Cleanup found no deleted files to remove")
            return 0
    
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
        
        # Count total files
        total_files_result = self._execute_with_retry("SELECT COUNT(*) FROM playback_positions", fetch_one=True)
        if total_files_result:
            stats['total_files'] = total_files_result[0]
        
        if stats['total_files'] > 0:
            # Calculate total saved time (positions)
            total_position_result = self._execute_with_retry("SELECT SUM(position_ms) FROM playback_positions", fetch_one=True)
            if total_position_result:
                total_position_ms = total_position_result[0] or 0
                stats['total_hours'] = total_position_ms / (1000 * 60 * 60)
            
            # Calculate total duration time
            total_duration_result = self._execute_with_retry("SELECT SUM(duration_ms) FROM playback_positions", fetch_one=True)
            if total_duration_result:
                total_duration_ms = total_duration_result[0] or 0
                stats['total_duration_hours'] = total_duration_ms / (1000 * 60 * 60)
            
            # Get oldest and newest entries
            oldest_result = self._execute_with_retry("SELECT MIN(created_at) FROM playback_positions", fetch_one=True)
            if oldest_result:
                stats['oldest_entry'] = oldest_result[0]
            
            newest_result = self._execute_with_retry("SELECT MAX(last_updated) FROM playback_positions", fetch_one=True)
            if newest_result:
                stats['newest_entry'] = newest_result[0]
        
        # Get database file size
        db_path = self._get_database_path()
        if os.path.exists(db_path):
            stats['database_size_bytes'] = os.path.getsize(db_path)
            stats['database_size_mb'] = stats['database_size_bytes'] / (1024 * 1024)
        
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
                           subtitle_track_id: int = -1, subtitle_language: str = '',
                           audio_track_id: int = -1) -> tuple[bool, int]:
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
            audio_track_id (int): ID of the currently selected audio track
            
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
                                   subtitle_enabled, subtitle_track_id, subtitle_language,
                                   audio_track_id)
        
        if success:
            return True, current_pos
        else:
            return False, last_saved_position

    def handle_position_on_media_change(self, old_file_path: str, new_file_path: str, 
                                      current_pos: int, current_duration: int, current_rate: float,
                                      subtitle_enabled: bool = False, subtitle_track_id: int = -1, 
                                      subtitle_language: str = '',
                                      audio_track_id: int = -1) -> tuple[bool, int]:
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
            audio_track_id (int): ID of the currently selected audio track
            
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
                                   subtitle_enabled, subtitle_track_id, subtitle_language,
                                   audio_track_id)
        
        if success:
            return True, current_pos
        else:
            return False, 0

    def handle_manual_action_save(self, file_path: str, current_pos: int, current_duration: int, 
                                current_rate: float, action_type: str = "manual", subtitle_enabled: bool = False,
                                subtitle_track_id: int = -1, subtitle_language: str = '',
                                audio_track_id: int = -1) -> tuple[bool, int]:
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
            audio_track_id (int): ID of the currently selected audio track
            
        Returns:
            tuple[bool, int]: (success, saved_position)
        """
        if not file_path or not current_pos or not current_duration:
            return False, 0
        
        # Check if position meets save criteria
        if not self.should_save_position(current_pos, current_duration):
            return False, 0
        
        success = self.save_position(file_path, current_pos, current_duration, current_rate,
                                   subtitle_enabled, subtitle_track_id, subtitle_language,
                                   audio_track_id)
        
        if success:
            return True, current_pos
        else:
            return False, 0 