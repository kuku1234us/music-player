"""
Database manager for yt-dlp update tracking.

This module extends the same SQLite database used by PlaybackPositionManager
to track yt-dlp update history, check times, and version information.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List

from music_player.models.database import BaseDatabaseManager, DatabaseUtils


class YtDlpUpdateManager(BaseDatabaseManager):
    """Database manager for yt-dlp update tracking."""

    # ------------------------------------------------------------------
    # Database initialization
    # ------------------------------------------------------------------
    def _init_database(self) -> None:
        """Initialize the tables and default entries used for yt-dlp updates."""
        db_path = self._get_database_path()

        # Primary update history table
        updates_table = """
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

        result = self._execute_with_retry(updates_table)
        if result is None:
            raise RuntimeError("yt-dlp update table creation failed")

        self._create_index("idx_yt_dlp_last_check", "yt_dlp_updates", "last_check_time")
        self._create_index("idx_yt_dlp_url", "yt_dlp_updates", "current_download_url")

        # Settings table
        settings_table = """
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

        result = self._execute_with_retry(settings_table)
        if result is None:
            raise RuntimeError("yt-dlp settings table creation failed")

        self._initialize_default_settings()

    # ------------------------------------------------------------------
    # Update history helpers
    # ------------------------------------------------------------------
    def get_last_check_time(self) -> Optional[datetime]:
        """Return the timestamp of the most recent update check."""
        result = self._execute_with_retry(
            """
                SELECT last_check_time FROM yt_dlp_updates
                ORDER BY last_check_time DESC
                LIMIT 1
            """,
            fetch_one=True,
        )

        if result:
            return DatabaseUtils.parse_timestamp(result[0])
        return None

    def get_current_version_info(self) -> Optional[Dict[str, str]]:
        """Return the currently installed yt-dlp download URL and version string."""
        result = self._execute_with_retry(
            """
                SELECT current_download_url, current_version_string FROM yt_dlp_updates
                ORDER BY updated_at DESC
                LIMIT 1
            """,
            fetch_one=True,
        )

        if not result:
            return None

        return {
            "download_url": result[0],
            "version_string": result[1],
        }

    def record_check_attempt(
        self,
        latest_url: str,
        latest_version_string: str,
        current_url: str,
        current_version_string: str,
        install_path: str,
    ) -> bool:
        """Persist a new update check in the database."""
        if not latest_url or not current_url or not install_path:
            self.logger.warning(self.__class__.__name__, "Invalid parameters for record_check_attempt")
            return False

        timestamp = DatabaseUtils.normalize_timestamp()

        existing = self._execute_with_retry(
            "SELECT id, check_count FROM yt_dlp_updates ORDER BY updated_at DESC LIMIT 1",
            fetch_one=True,
        )

        if existing:
            result = self._execute_with_retry(
                """
                    UPDATE yt_dlp_updates
                    SET latest_checked_url = ?,
                        latest_version_string = ?,
                        last_check_time = ?,
                        check_count = ?,
                        updated_at = ?
                    WHERE id = ?
                """,
                (latest_url, latest_version_string, timestamp, existing[1] + 1, timestamp, existing[0]),
            )
        else:
            result = self._execute_with_retry(
                """
                    INSERT INTO yt_dlp_updates (
                        current_download_url,
                        current_version_string,
                        latest_checked_url,
                        latest_version_string,
                        last_check_time,
                        install_path,
                        check_count,
                        update_count,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
                """,
                (
                    current_url,
                    current_version_string,
                    latest_url,
                    latest_version_string,
                    timestamp,
                    install_path,
                    timestamp,
                    timestamp,
                ),
            )

        if result is not None:
            self.logger.debug(self.__class__.__name__, f"Recorded check attempt: {latest_url}")
            return True
        return False

    def record_update_success(
        self,
        new_download_url: str,
        new_version_string: str,
        install_path: str,
        backup_path: str | None = None,
    ) -> bool:
        """Record a successful update event."""
        if not new_download_url or not install_path:
            self.logger.warning(self.__class__.__name__, "Invalid parameters for record_update_success")
            return False

        timestamp = DatabaseUtils.normalize_timestamp()

        existing = self._execute_with_retry(
            "SELECT id, update_count FROM yt_dlp_updates ORDER BY updated_at DESC LIMIT 1",
            fetch_one=True,
        )

        if existing:
            result = self._execute_with_retry(
                """
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
                """,
                (
                    new_download_url,
                    new_version_string,
                    timestamp,
                    install_path,
                    backup_path,
                    existing[1] + 1,
                    timestamp,
                    existing[0],
                ),
            )
        else:
            result = self._execute_with_retry(
                """
                    INSERT INTO yt_dlp_updates (
                        current_download_url,
                        current_version_string,
                        latest_checked_url,
                        latest_version_string,
                        last_check_time,
                        last_update_time,
                        install_path,
                        backup_path,
                        check_count,
                        update_count,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
                """,
                (
                    new_download_url,
                    new_version_string,
                    new_download_url,
                    new_version_string,
                    timestamp,
                    timestamp,
                    install_path,
                    backup_path,
                    timestamp,
                    timestamp,
                ),
            )

        if result is not None:
            self.logger.info(self.__class__.__name__, f"Recorded successful update to: {new_download_url}")
            return True
        return False

    def record_update_error(self, error_message: str) -> bool:
        """Persist an update error."""
        if not error_message:
            self.logger.warning(self.__class__.__name__, "Empty error message for record_update_error")
            return False

        timestamp = DatabaseUtils.normalize_timestamp()

        result = self._execute_with_retry(
            """
                UPDATE yt_dlp_updates
                SET last_error_message = ?, updated_at = ?
                WHERE id = (SELECT id FROM yt_dlp_updates ORDER BY updated_at DESC LIMIT 1)
            """,
            (error_message, timestamp),
        )

        if result == 0:
            result = self._execute_with_retry(
                """
                    INSERT INTO yt_dlp_updates (
                        current_download_url,
                        latest_checked_url,
                        last_check_time,
                        install_path,
                        check_count,
                        update_count,
                        last_error_message,
                        created_at,
                        updated_at
                    ) VALUES ('unknown', 'unknown', ?, 'unknown', 1, 0, ?, ?, ?)
                """,
                (timestamp, error_message, timestamp, timestamp),
            )

        if result is not None and result > 0:
            self.logger.debug(self.__class__.__name__, f"Recorded update error: {error_message}")
            return True
        return False

    # ------------------------------------------------------------------
    # Download / installation logging (mostly pass-through currently)
    # ------------------------------------------------------------------
    def record_download_start(self, download_url: str, target_path: str) -> bool:
        self.logger.debug(self.__class__.__name__, f"Download started: {download_url} -> {target_path}")
        return True

    def record_download_complete(
        self,
        download_url: str,
        file_size: int,
        download_time: float,
        checksum: str | None = None,
    ) -> bool:
        speed_mbps = (file_size / 1024 / 1024) / download_time if download_time > 0 else 0
        self.logger.info(
            self.__class__.__name__,
            f"Download completed: {file_size} bytes in {download_time:.1f}s ({speed_mbps:.1f} MB/s)",
        )
        if checksum:
            self.logger.debug(self.__class__.__name__, f"File checksum: {checksum}")
        return True

    def record_installation_start(self, source_file: str, target_path: str) -> bool:
        self.logger.debug(self.__class__.__name__, f"Installation started: {source_file} -> {target_path}")
        return True

    def record_installation_complete(
        self,
        installed_path: str,
        backup_path: str | None = None,
        previous_version: str | None = None,
        new_version: str | None = None,
    ) -> bool:
        self.logger.info(self.__class__.__name__, f"Installation completed: {installed_path}")
        if backup_path:
            self.logger.debug(self.__class__.__name__, f"Backup created: {backup_path}")
        if previous_version and new_version:
            self.logger.info(
                self.__class__.__name__,
                f"Version updated: {previous_version} -> {new_version}",
            )
        return True

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def get_update_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return a list of recent update entries."""
        results = self._execute_with_retry(
            """
                SELECT current_download_url, current_version_string, latest_checked_url, latest_version_string,
                       last_check_time, last_update_time, check_count, update_count, last_error_message,
                       created_at, updated_at
                FROM yt_dlp_updates
                ORDER BY updated_at DESC
                LIMIT ?
            """,
            (limit,),
            fetch_all=True,
        )

        if not results:
            return []

        history: List[Dict[str, Any]] = []
        for row in results:
            history.append(
                {
                    "current_download_url": row[0],
                    "current_version_string": row[1],
                    "latest_checked_url": row[2],
                    "latest_version_string": row[3],
                    "last_check_time": row[4],
                    "last_update_time": row[5],
                    "check_count": row[6],
                    "update_count": row[7],
                    "last_error_message": row[8],
                    "created_at": row[9],
                    "updated_at": row[10],
                }
            )

        return history

    def get_database_stats(self) -> Dict[str, Any]:
        """Return summarized statistics about the update database."""
        total_records_result = self._execute_with_retry(
            "SELECT COUNT(*) FROM yt_dlp_updates",
            fetch_one=True,
        )
        total_records = total_records_result[0] if total_records_result else 0

        latest = self._execute_with_retry(
            """
                SELECT current_download_url, current_version_string, last_check_time, last_update_time,
                       check_count, update_count, last_error_message
                FROM yt_dlp_updates
                ORDER BY updated_at DESC
                LIMIT 1
            """,
            fetch_one=True,
        )

        return {
            "total_records": total_records,
            "database_path": self._get_database_path(),
            "current_download_url": latest[0] if latest else None,
            "current_version_string": latest[1] if latest else None,
            "last_check_time": latest[2] if latest else None,
            "last_update_time": latest[3] if latest else None,
            "total_checks": latest[4] if latest else 0,
            "total_updates": latest[5] if latest else 0,
            "last_error": latest[6] if latest else None,
        }

    def cleanup_old_records(self, keep_count: int = 50) -> int:
        """Remove all but the most recent `keep_count` records."""
        try:
            result = self._execute_with_retry(
                """
                    DELETE FROM yt_dlp_updates
                    WHERE id NOT IN (
                        SELECT id FROM yt_dlp_updates
                        ORDER BY updated_at DESC
                        LIMIT ?
                    )
                """,
                (keep_count,),
            )

            deleted_count = result if result is not None else 0
            if deleted_count > 0:
                self.logger.info(
                    self.__class__.__name__,
                    f"Cleaned up {deleted_count} old update records",
                )
            return deleted_count
        except Exception as exc:
            self.logger.error(self.__class__.__name__, f"Error cleaning up old records: {exc}")
            return 0

    # ------------------------------------------------------------------
    # Settings management
    # ------------------------------------------------------------------
    def _initialize_default_settings(self) -> None:
        """Insert default settings row if none exist."""
        try:
            result = self._execute_with_retry("SELECT COUNT(*) FROM yt_dlp_settings", fetch_one=True)
            if not result or result[0] != 0:
                return

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
        except Exception as exc:
            self.logger.error(self.__class__.__name__, f"Error initializing default settings: {exc}")

    def get_settings(self) -> Dict[str, Any]:
        """Return the persisted settings (or defaults if missing)."""
        try:
            result = self._execute_with_retry(
                """
                    SELECT enabled, auto_update, check_interval_hours, install_path,
                           timeout_seconds, max_retries,
                           verify_checksums, keep_backups, notification_level, updated_at
                    FROM yt_dlp_settings
                    WHERE id = 1
                """,
                fetch_one=True,
            )

            if result:
                return {
                    "enabled": bool(result[0]),
                    "auto_update": bool(result[1]),
                    "check_interval_hours": result[2],
                    "install_path": result[3],
                    "timeout_seconds": result[4],
                    "max_retries": result[5],
                    "verify_checksums": bool(result[6]),
                    "keep_backups": result[7],
                    "notification_level": result[8],
                    "updated_at": result[9],
                }

            self.logger.warning(self.__class__.__name__, "No settings found, returning defaults")
            return self._get_default_settings()
        except Exception as exc:
            self.logger.error(self.__class__.__name__, f"Error getting settings: {exc}")
            return self._get_default_settings()

    def update_setting(self, key: str, value: Any) -> bool:
        """Update a single setting value."""
        valid_keys = {
            "enabled",
            "auto_update",
            "check_interval_hours",
            "install_path",
            "timeout_seconds",
            "max_retries",
            "verify_checksums",
            "keep_backups",
            "notification_level",
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

            self.logger.error(self.__class__.__name__, f"Failed to update setting {key}")
            return False
        except Exception as exc:
            self.logger.error(self.__class__.__name__, f"Error updating setting {key}: {exc}")
            return False

    def update_multiple_settings(self, settings: Dict[str, Any]) -> bool:
        """Update multiple settings at once."""
        valid_keys = {
            "enabled",
            "auto_update",
            "check_interval_hours",
            "install_path",
            "timeout_seconds",
            "max_retries",
            "verify_checksums",
            "keep_backups",
            "notification_level",
        }

        invalid_keys = set(settings.keys()) - valid_keys
        if invalid_keys:
            self.logger.error(self.__class__.__name__, f"Invalid setting keys: {invalid_keys}")
            return False

        try:
            now = datetime.now().isoformat()
            set_clause = ", ".join(f"{key} = ?" for key in settings.keys())
            query = f"UPDATE yt_dlp_settings SET {set_clause}, updated_at = ? WHERE id = 1"
            params = list(settings.values()) + [now]

            result = self._execute_with_retry(query, tuple(params))
            if result is not None:
                self.logger.info(self.__class__.__name__, f"Updated {len(settings)} settings")
                return True

            self.logger.error(self.__class__.__name__, "Failed to update multiple settings")
            return False
        except Exception as exc:
            self.logger.error(self.__class__.__name__, f"Error updating multiple settings: {exc}")
            return False

    def reset_settings_to_defaults(self) -> bool:
        """Reset all settings to their default values."""
        try:
            defaults = self._get_default_settings()
            return self.update_multiple_settings(defaults)
        except Exception as exc:
            self.logger.error(self.__class__.__name__, f"Error resetting settings: {exc}")
            return False

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------
    def _get_default_settings(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "auto_update": True,
            "check_interval_hours": 24,
            "install_path": r"C:\yt-dlp\yt-dlp.exe",
            "timeout_seconds": 30,
            "max_retries": 3,
            "verify_checksums": True,
            "keep_backups": 3,
            "notification_level": "normal",
        } 