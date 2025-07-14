"""
Base database functionality for Music Player application.

This module provides common SQLite database operations and utilities that can be
shared across different database managers in the application.
"""
import os
import sqlite3
import threading
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
import time
from abc import ABC, abstractmethod

from qt_base_app.models.settings_manager import SettingsManager, SettingType
from qt_base_app.models.logger import Logger


class BaseDatabaseManager(ABC):
    """
    Abstract base class for database managers in the Music Player application.
    
    Provides common functionality for:
    - Singleton pattern implementation
    - Database connection management with retry logic
    - Thread-safe operations
    - Common database path resolution
    - Error handling and logging
    """
    
    _instances = {}  # Class-level dictionary to store instances per subclass
    _class_locks = {}  # Class-level dictionary to store locks per subclass
    
    def __new__(cls):
        # Create class-specific lock if it doesn't exist
        if cls not in cls._class_locks:
            cls._class_locks[cls] = threading.Lock()
        
        # Use class-specific singleton pattern
        if cls not in cls._instances:
            with cls._class_locks[cls]:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__new__(cls)
        return cls._instances[cls]
    
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
        
        # Initialize the specific database tables
        self._init_database()
    
    @classmethod
    def instance(cls):
        """Get the singleton instance of the specific database manager."""
        return cls()
    
    def _get_database_path(self) -> str:
        """Get the path to the SQLite database file."""
        # Get the working directory key and default from settings manager
        # This avoids circular import with settings_defs
        working_dir = self.settings.get('preferences/working_dir', 
                                       str(Path.home()), 
                                       SettingType.PATH)
        working_dir = Path(working_dir)
        working_dir.mkdir(parents=True, exist_ok=True)
        return str(working_dir / "playback_positions.db")  # Shared database file
    
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
    
    def _execute_with_retry(self, query: str, params: tuple = (), 
                           fetch_one: bool = False, fetch_all: bool = False) -> Optional[Any]:
        """
        Execute a database query with retry logic and proper error handling.
        
        Args:
            query (str): SQL query to execute
            params (tuple): Parameters for the query
            fetch_one (bool): Whether to fetch one result
            fetch_all (bool): Whether to fetch all results
            
        Returns:
            Query result or None if failed
        """
        with self._db_lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, params)
                    
                    if fetch_one:
                        return cursor.fetchone()
                    elif fetch_all:
                        return cursor.fetchall()
                    else:
                        conn.commit()
                        return cursor.rowcount
                        
            except sqlite3.Error as e:
                self.logger.error(self.__class__.__name__, f"Database query failed: {e}")
                self.logger.error(self.__class__.__name__, f"Query: {query}")
                self.logger.error(self.__class__.__name__, f"Params: {params}")
                return None
    
    def _execute_transaction(self, operations: list) -> bool:
        """
        Execute multiple database operations in a single transaction.
        
        Args:
            operations (list): List of (query, params) tuples to execute
            
        Returns:
            bool: True if all operations succeeded, False otherwise
        """
        with self._db_lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    
                    for query, params in operations:
                        cursor.execute(query, params)
                    
                    conn.commit()
                    return True
                    
            except sqlite3.Error as e:
                self.logger.error(self.__class__.__name__, f"Transaction failed: {e}")
                return False
    
    def _create_index(self, index_name: str, table_name: str, columns: str) -> bool:
        """
        Create an index on the specified table if it doesn't exist.
        
        Args:
            index_name (str): Name of the index
            table_name (str): Name of the table
            columns (str): Column specification for the index
            
        Returns:
            bool: True if index was created or already exists
        """
        query = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({columns})"
        result = self._execute_with_retry(query)
        return result is not None
    
    def _add_column_if_missing(self, table_name: str, column_name: str, column_definition: str) -> bool:
        """
        Add a column to a table if it doesn't already exist.
        
        Args:
            table_name (str): Name of the table
            column_name (str): Name of the column to add
            column_definition (str): Full column definition (e.g., "REAL NOT NULL DEFAULT 1.0")
            
        Returns:
            bool: True if column was added or already exists
        """
        # Check if column exists
        result = self._execute_with_retry(f"PRAGMA table_info({table_name})", fetch_all=True)
        if result is None:
            return False
        
        columns = [column[1] for column in result]
        
        if column_name not in columns:
            self.logger.info(self.__class__.__name__, f"Adding {column_name} column to {table_name} table")
            query = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
            result = self._execute_with_retry(query)
            return result is not None
        
        return True
    
    def get_database_info(self) -> Dict[str, Any]:
        """
        Get general information about the database.
        
        Returns:
            Dict: Database information including path, size, and table count
        """
        db_path = self._get_database_path()
        info = {
            'database_path': db_path,
            'database_size_bytes': 0,
            'database_size_mb': 0.0,
            'table_count': 0,
            'tables': []
        }
        
        try:
            # Get database file size
            if os.path.exists(db_path):
                info['database_size_bytes'] = os.path.getsize(db_path)
                info['database_size_mb'] = info['database_size_bytes'] / (1024 * 1024)
            
            # Get table information
            result = self._execute_with_retry(
                "SELECT name FROM sqlite_master WHERE type='table'", 
                fetch_all=True
            )
            
            if result:
                info['tables'] = [table[0] for table in result]
                info['table_count'] = len(info['tables'])
                
        except Exception as e:
            self.logger.error(self.__class__.__name__, f"Failed to get database info: {e}")
        
        return info
    
    @abstractmethod
    def _init_database(self):
        """Initialize database tables specific to this manager. Must be implemented by subclasses."""
        pass


class DatabaseUtils:
    """
    Utility class for common database operations that don't require instance state.
    """
    
    @staticmethod
    def normalize_timestamp(timestamp: Optional[str] = None) -> str:
        """
        Normalize timestamp to ISO format string.
        
        Args:
            timestamp: Optional datetime string or None for current time
            
        Returns:
            str: ISO format timestamp string
        """
        if timestamp is None:
            return datetime.now().isoformat()
        
        if isinstance(timestamp, str):
            return timestamp
        
        if isinstance(timestamp, datetime):
            return timestamp.isoformat()
        
        return datetime.now().isoformat()
    
    @staticmethod
    def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
        """
        Parse ISO format timestamp string to datetime object.
        
        Args:
            timestamp_str: ISO format timestamp string
            
        Returns:
            datetime: Parsed datetime object or None if parsing failed
        """
        try:
            return datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def validate_path(file_path: str) -> Optional[str]:
        """
        Validate and normalize a file path.
        
        Args:
            file_path: Path to validate
            
        Returns:
            str: Normalized path or None if invalid
        """
        if not file_path:
            return None
        
        try:
            return os.path.abspath(file_path)
        except Exception:
            return None 