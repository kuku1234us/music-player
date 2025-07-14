"""
Database manager for yt-dlp update tracking.

This module extends the same SQLite database used by PlaybackPositionManager
to track yt-dlp update history, check times, and version information.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List

from music_player.models.database import BaseDatabaseManager, DatabaseUtils


class YtDlpUpdateManager(BaseDatabaseManager):
    """
    Database manager for yt-dlp update tracking.
    Reuses the same database as PlaybackPositionManager for consistency.
    """
    
    def _init_database(self):
        """Initialize the yt-dlp update tracking table if it doesn't exist."""
        db_path = self._get_database_path()
        self.logger.info(self.__class__.__name__, f"Initializing yt-dlp update table in database: {db_path}")
                
        # Create yt-dlp update tracking table
        table_creation_query = """
            CREATE TABLE IF NOT EXISTS yt_dlp_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                current_download_url TEXT NOT NULL,
                current_version_string TEXT,
                latest_checked_url TEXT NOT NULL,
                latest_version_string TEXT,
                last_check_time TEXT NOT NULL,
                last_update_time TEXT,
                install_path TEXT NOT NULL,
                backup_path TEXT,
                check_count INTEGER NOT NULL DEFAULT 1,
                update_count INTEGER NOT NULL DEFAULT 0,
                last_error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """
        
        result = self._execute_with_retry(table_creation_query)
        if result is None:
            raise RuntimeError("yt-dlp update table creation failed")
        
        # Create indexes for performance
        self._create_index("idx_yt_dlp_last_check", "yt_dlp_updates", "last_check_time")
        self._create_index("idx_yt_dlp_url", "yt_dlp_updates", "current_download_url")
        
        # Create yt-dlp settings table
        settings_table_query = """
            CREATE TABLE IF NOT EXISTS yt_dlp_settings (
                id INTEGER PRIMARY KEY,
                enabled BOOLEAN NOT NULL DEFAULT 1,
                auto_update BOOLEAN NOT NULL DEFAULT 1,
                check_interval_hours INTEGER NOT NULL DEFAULT 24,
                install_path TEXT NOT NULL DEFAULT 'C:\\yt-dlp\\yt-dlp.exe',
                timeout_seconds INTEGER NOT NULL DEFAULT 30,
                max_retries INTEGER NOT NULL DEFAULT 3,
                verify_checksums BOOLEAN NOT NULL DEFAULT 1,
                keep_backups INTEGER NOT NULL DEFAULT 3,
                notification_level TEXT NOT NULL DEFAULT 'normal',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """
        
        result = self._execute_with_retry(settings_table_query)
        if result is None:
            raise RuntimeError("yt-dlp settings table creation failed")
        
        # Initialize default settings if table is empty
        self._initialize_default_settings()
        
        self.logger.info(self.__class__.__name__, "yt-dlp update table initialized successfully")
    
    def get_last_check_time(self) -> Optional[datetime]:
        """
        Get the last update check timestamp from database.
        
        Returns:
            datetime: Last check time, or None if no checks recorded
        """
        result = self._execute_with_retry("""
            SELECT last_check_time FROM yt_dlp_updates 
            ORDER BY last_check_time DESC 
            LIMIT 1
        """, fetch_one=True)
        
        if result:
            # Parse ISO format datetime string
            return DatabaseUtils.parse_timestamp(result[0])
        return None
    
    def get_current_version_info(self) -> Optional[Dict[str, str]]:
        """
        Get the current installed yt-dlp version information from database.
        
        Returns:
            Dict: Version information with 'download_url' and 'version_string', or None if not recorded
        """
        result = self._execute_with_retry("""
            SELECT current_download_url, current_version_string FROM yt_dlp_updates 
            ORDER BY updated_at DESC 
            LIMIT 1
        """, fetch_one=True)
        
        if result:
            return {
                'download_url': result[0],
                'version_string': result[1]
            }
        return None
    
    def record_check_attempt(self, latest_url: str, latest_version_string: str, 
                            current_url: str, current_version_string: str, install_path: str) -> bool:
        """
        Record an update check attempt in database.
        
        Args:
            latest_url (str): Latest download URL found from GitHub
            latest_version_string (str): Latest version string (optional)
            current_url (str): Current download URL
            current_version_string (str): Current version string (optional)
            install_path (str): Path to yt-dlp.exe installation
            
        Returns:
            bool: True if record was successful
        """
        if not latest_url or not current_url or not install_path:
            self.logger.warning(self.__class__.__name__, "Invalid parameters for record_check_attempt")
            return False
        
        timestamp = DatabaseUtils.normalize_timestamp()
        
        # Check if we have any existing records
        existing = self._execute_with_retry(
            "SELECT id, check_count FROM yt_dlp_updates ORDER BY updated_at DESC LIMIT 1", 
            fetch_one=True
        )
        
        if existing:
            # Update existing record
            result = self._execute_with_retry("""
                UPDATE yt_dlp_updates 
                SET latest_checked_url = ?, 
                    latest_version_string = ?,
                    last_check_time = ?, 
                    check_count = ?,
                    updated_at = ?
                WHERE id = ?
            """, (latest_url, latest_version_string, timestamp, existing[1] + 1, timestamp, existing[0]))
        else:
            # Create new record
            result = self._execute_with_retry("""
                INSERT INTO yt_dlp_updates 
                (current_download_url, current_version_string, latest_checked_url, latest_version_string,
                 last_check_time, install_path, check_count, update_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
            """, (current_url, current_version_string, latest_url, latest_version_string, 
                 timestamp, install_path, timestamp, timestamp))
        
        success = result is not None
        if success:
            self.logger.debug(self.__class__.__name__, f"Recorded check attempt: {latest_url}")
        return success
    
    def record_update_success(self, new_download_url: str, new_version_string: str, 
                             install_path: str, backup_path: str = None) -> bool:
        """
        Record a successful update in database.
        
        Args:
            new_download_url (str): Download URL that was successfully installed
            new_version_string (str): Version string of installed version (optional)
            install_path (str): Path to yt-dlp.exe installation
            backup_path (str): Path to backup file (optional)
            
        Returns:
            bool: True if record was successful
        """
        if not new_download_url or not install_path:
            self.logger.warning(self.__class__.__name__, "Invalid parameters for record_update_success")
            return False
        
        timestamp = DatabaseUtils.normalize_timestamp()
        
        # Check if we have any existing records
        existing = self._execute_with_retry(
            "SELECT id, update_count FROM yt_dlp_updates ORDER BY updated_at DESC LIMIT 1", 
            fetch_one=True
        )
        
        if existing:
            # Update existing record
            result = self._execute_with_retry("""
                UPDATE yt_dlp_updates 
                SET current_download_url = ?, 
                    current_version_string = ?,
                    last_update_time = ?,
                    install_path = ?,
                    backup_path = ?,
                    update_count = ?,
                    last_error_message = NULL,
                    updated_at = ?
                WHERE id = ?
            """, (new_download_url, new_version_string, timestamp, install_path, backup_path, 
                 existing[1] + 1, timestamp, existing[0]))
        else:
            # Create new record (shouldn't happen in normal flow, but handle it)
            result = self._execute_with_retry("""
                INSERT INTO yt_dlp_updates 
                (current_download_url, current_version_string, latest_checked_url, latest_version_string,
                 last_check_time, last_update_time, install_path, backup_path, 
                 check_count, update_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
            """, (new_download_url, new_version_string, new_download_url, new_version_string,
                 timestamp, timestamp, install_path, backup_path, timestamp, timestamp))
        
        success = result is not None
        if success:
            self.logger.info(self.__class__.__name__, f"Recorded successful update to: {new_download_url}")
        return success
    
    def record_update_error(self, error_message: str) -> bool:
        """
        Record an update error in database.
        
        Args:
            error_message (str): Error message to record
            
        Returns:
            bool: True if record was successful
        """
        if not error_message:
            self.logger.warning(self.__class__.__name__, "Empty error message for record_update_error")
            return False
        
        timestamp = DatabaseUtils.normalize_timestamp()
        
        # Update most recent record with error
        result = self._execute_with_retry("""
            UPDATE yt_dlp_updates 
            SET last_error_message = ?, updated_at = ?
            WHERE id = (SELECT id FROM yt_dlp_updates ORDER BY updated_at DESC LIMIT 1)
        """, (error_message, timestamp))
        
        if result == 0:  # No rows updated, no existing record
            # Create a minimal record with error
            result = self._execute_with_retry("""
                INSERT INTO yt_dlp_updates 
                (current_download_url, latest_checked_url, last_check_time, 
                 install_path, check_count, update_count, last_error_message, created_at, updated_at)
                VALUES ('unknown', 'unknown', ?, 'unknown', 1, 0, ?, ?, ?)
            """, (timestamp, error_message, timestamp, timestamp))
        
        success = result is not None and result > 0
        if success:
            self.logger.debug(self.__class__.__name__, f"Recorded update error: {error_message}")
        return success
    
    def record_download_start(self, download_url: str, target_path: str) -> bool:
        """
        Record the start of a download operation.
        
        Args:
            download_url (str): URL being downloaded
            target_path (str): Local path for download
            
        Returns:
            bool: True if record was successful
        """
        self.logger.debug(self.__class__.__name__, 
            f"Download started: {download_url} -> {target_path}")
        return True  # For now, just log it
    
    def record_download_complete(self, download_url: str, file_size: int, 
                                download_time: float, checksum: str = None) -> bool:
        """
        Record successful completion of a download.
        
        Args:
            download_url (str): URL that was downloaded
            file_size (int): Size of downloaded file in bytes
            download_time (float): Time taken to download in seconds
            checksum (str): SHA256 checksum of downloaded file
            
        Returns:
            bool: True if record was successful
        """
        speed_mbps = (file_size / 1024 / 1024) / download_time if download_time > 0 else 0
        self.logger.info(self.__class__.__name__, 
            f"Download completed: {file_size} bytes in {download_time:.1f}s ({speed_mbps:.1f} MB/s)")
        
        if checksum:
            self.logger.debug(self.__class__.__name__, f"File checksum: {checksum}")
        
        return True  # For now, just log the metrics
    
    def record_installation_start(self, source_file: str, target_path: str) -> bool:
        """
        Record the start of an installation operation.
        
        Args:
            source_file (str): Source file being installed
            target_path (str): Target installation path
            
        Returns:
            bool: True if record was successful
        """
        self.logger.debug(self.__class__.__name__, 
            f"Installation started: {source_file} -> {target_path}")
        return True  # For now, just log it
    
    def record_installation_complete(self, installed_path: str, backup_path: str = None, 
                                   previous_version: str = None, new_version: str = None) -> bool:
        """
        Record successful completion of an installation.
        
        Args:
            installed_path (str): Path where file was installed
            backup_path (str): Path to backup file (if created)
            previous_version (str): Previous version that was replaced
            new_version (str): New version that was installed
            
        Returns:
            bool: True if record was successful
        """
        self.logger.info(self.__class__.__name__, 
            f"Installation completed: {installed_path}")
        
        if backup_path:
            self.logger.debug(self.__class__.__name__, f"Backup created: {backup_path}")
        
        if previous_version and new_version:
            self.logger.info(self.__class__.__name__, 
                f"Version updated: {previous_version} -> {new_version}")
        
        return True  # For now, just log the details
    
    def get_update_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent update history from database.
        
        Args:
            limit (int): Maximum number of records to return
            
        Returns:
            List[Dict]: List of update records
        """
        results = self._execute_with_retry("""
            SELECT current_download_url, current_version_string, latest_checked_url, latest_version_string,
                   last_check_time, last_update_time, check_count, update_count, last_error_message,
                   created_at, updated_at
            FROM yt_dlp_updates 
            ORDER BY updated_at DESC 
            LIMIT ?
        """, (limit,), fetch_all=True)
        
        if not results:
            return []
        
        history = []
        for row in results:
            history.append({
                'current_download_url': row[0],
                'current_version_string': row[1],
                'latest_checked_url': row[2],
                'latest_version_string': row[3],
                'last_check_time': row[4],
                'last_update_time': row[5],
                'check_count': row[6],
                'update_count': row[7],
                'last_error_message': row[8],
                'created_at': row[9],
                'updated_at': row[10]
            })
        
        return history
    
    def get_database_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the yt-dlp update database.
        
        Returns:
            Dict: Database statistics
        """
        # Get total records
        total_records_result = self._execute_with_retry(
            "SELECT COUNT(*) FROM yt_dlp_updates", 
            fetch_one=True
        )
        total_records = total_records_result[0] if total_records_result else 0
        
        # Get most recent record
        latest = self._execute_with_retry("""
            SELECT current_download_url, current_version_string, last_check_time, last_update_time, 
                   check_count, update_count, last_error_message
            FROM yt_dlp_updates 
            ORDER BY updated_at DESC 
            LIMIT 1
        """, fetch_one=True)
        
        stats = {
            'total_records': total_records,
            'database_path': self._get_database_path(),
            'current_download_url': latest[0] if latest else None,
            'current_version_string': latest[1] if latest else None,
            'last_check_time': latest[2] if latest else None,
            'last_update_time': latest[3] if latest else None,
            'total_checks': latest[4] if latest else 0,
            'total_updates': latest[5] if latest else 0,
            'last_error': latest[6] if latest else None
        }
        
        return stats
    
    def cleanup_old_records(self, keep_count: int = 50) -> int:
        """
        Clean up old update records, keeping only the most recent ones.
        
        Args:
            keep_count (int): Number of recent records to keep
            
        Returns:
            int: Number of records deleted
        """
        try:
            result = self._execute_with_retry("""
                DELETE FROM yt_dlp_updates 
                WHERE id NOT IN (
                    SELECT id FROM yt_dlp_updates 
                    ORDER BY updated_at DESC 
                    LIMIT ?
                )
            """, (keep_count,))
            
            deleted_count = result if result is not None else 0
            
            if deleted_count > 0:
                self.logger.info(self.__class__.__name__, f"Cleaned up {deleted_count} old update records")
            
            return deleted_count
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Error cleaning up old records: {e}")
            return 0

    # --- Settings Management Methods ---
    
    def _initialize_default_settings(self):
        """Initialize default settings if the settings table is empty."""
        try:
            # Check if settings already exist
            query = "SELECT COUNT(*) FROM yt_dlp_settings"
            result = self._execute_with_retry(query, fetch_one=True)
            
            if result and result[0] == 0:
                # No settings exist, create default entry
                now = datetime.now().isoformat()
                insert_query = """
                    INSERT INTO yt_dlp_settings (
                        id, enabled, auto_update, check_interval_hours, install_path,
                        timeout_seconds, max_retries, verify_checksums, keep_backups,
                        notification_level, created_at, updated_at
                    ) VALUES (1, 1, 1, 24, 'C:\\yt-dlp\\yt-dlp.exe', 30, 3, 1, 3, 'normal', ?, ?)
                """
                
                result = self._execute_with_retry(insert_query, (now, now))
                if result is not None:
                    self.logger.info(self.__class__.__name__, "Default yt-dlp settings initialized")
                else:
                    self.logger.error(self.__class__.__name__, "Failed to initialize default settings")
                    
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Error initializing default settings: {e}")
    
    def get_settings(self) -> Dict[str, Any]:
        """
        Get all yt-dlp updater settings from database.
        
        Returns:
            Dict: All settings with their current values
        """
        try:
            query = """
                SELECT enabled, auto_update, check_interval_hours, install_path,
                       timeout_seconds, max_retries, verify_checksums, keep_backups,
                       notification_level, updated_at
                FROM yt_dlp_settings WHERE id = 1
            """
            
            result = self._execute_with_retry(query, fetch_one=True)
            if result:
                row = result
                return {
                    'enabled': bool(row[0]),
                    'auto_update': bool(row[1]),
                    'check_interval_hours': row[2],
                    'install_path': row[3],
                    'timeout_seconds': row[4],
                    'max_retries': row[5],
                    'verify_checksums': bool(row[6]),
                    'keep_backups': row[7],
                    'notification_level': row[8],
                    'updated_at': row[9]
                }
            else:
                # Return defaults if no settings found
                self.logger.warning(self.__class__.__name__, "No settings found, returning defaults")
                return self._get_default_settings()
                
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Error getting settings: {e}")
            return self._get_default_settings()
    
    def update_setting(self, key: str, value: Any) -> bool:
        """
        Update a specific setting in the database.
        
        Args:
            key (str): Setting key to update
            value (Any): New value for the setting
            
        Returns:
            bool: True if update was successful
        """
        valid_keys = {
            'enabled', 'auto_update', 'check_interval_hours', 'install_path',
            'timeout_seconds', 'max_retries', 'verify_checksums', 'keep_backups',
            'notification_level'
        }
        
        if key not in valid_keys:
            self.logger.error(self.__class__.__name__, f"Invalid setting key: {key}")
            return False
        
        try:
            now = datetime.now().isoformat()
            query = f"UPDATE yt_dlp_settings SET {key} = ?, updated_at = ? WHERE id = 1"
            
            result = self._execute_with_retry(query, (value, now))
            if result is not None:
                self.logger.debug(self.__class__.__name__, f"Updated setting {key} = {value}")
                return True
            else:
                self.logger.error(self.__class__.__name__, f"Failed to update setting {key}")
                return False
                
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Error updating setting {key}: {e}")
            return False
    
    def update_multiple_settings(self, settings: Dict[str, Any]) -> bool:
        """
        Update multiple settings in a single transaction.
        
        Args:
            settings (Dict): Dictionary of setting key-value pairs
            
        Returns:
            bool: True if all updates were successful
        """
        valid_keys = {
            'enabled', 'auto_update', 'check_interval_hours', 'install_path',
            'timeout_seconds', 'max_retries', 'verify_checksums', 'keep_backups',
            'notification_level'
        }
        
        # Validate all keys first
        invalid_keys = set(settings.keys()) - valid_keys
        if invalid_keys:
            self.logger.error(self.__class__.__name__, f"Invalid setting keys: {invalid_keys}")
            return False
        
        try:
            now = datetime.now().isoformat()
            
            # Build dynamic query
            set_clauses = [f"{key} = ?" for key in settings.keys()]
            set_clause = ", ".join(set_clauses)
            query = f"UPDATE yt_dlp_settings SET {set_clause}, updated_at = ? WHERE id = 1"
            
            # Build parameter tuple
            params = list(settings.values()) + [now]
            
            result = self._execute_with_retry(query, tuple(params))
            if result is not None:
                self.logger.info(self.__class__.__name__, f"Updated {len(settings)} settings")
                return True
            else:
                self.logger.error(self.__class__.__name__, "Failed to update multiple settings")
                return False
                
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Error updating multiple settings: {e}")
            return False
    
    def reset_settings_to_defaults(self) -> bool:
        """
        Reset all settings to their default values.
        
        Returns:
            bool: True if reset was successful
        """
        try:
            defaults = self._get_default_settings()
            return self.update_multiple_settings(defaults)
            
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Error resetting settings: {e}")
            return False
    
    def _get_default_settings(self) -> Dict[str, Any]:
        """Get default settings values."""
        return {
            'enabled': True,
            'auto_update': True,
            'check_interval_hours': 24,
            'install_path': r'C:\yt-dlp\yt-dlp.exe',
            'timeout_seconds': 30,
            'max_retries': 3,
            'verify_checksums': True,
            'keep_backups': 3,
            'notification_level': 'normal'
        } 