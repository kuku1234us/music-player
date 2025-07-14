# Yt-dlp Automatic Update System

## Overview

The yt-dlp automatic update system ensures our Music Player application always uses the latest version of yt-dlp.exe on Windows 10 systems. This system provides seamless, background updates while minimizing user disruption and network usage.

## Core Requirements

### 1. Fixed Installation Path

- **Target Location**: `C:\yt-dlp\yt-dlp.exe`
- **Rationale**: Predictable path for reliable management, independent of system PATH
- **Fallback**: If C: drive unavailable, use application directory + `\yt-dlp\`

### 2. URL-Based Version Management

- **Version Identifier**: Download URLs serve as primary version identifiers
- **Future-Proof**: Works regardless of yt-dlp's versioning scheme changes
- **Comparison Logic**: Different URLs = update needed (simple and reliable)
- **Display**: Extract human-readable versions from URLs when possible

### 3. Update Frequency Control

- **Maximum Frequency**: Once per day (24-hour minimum interval)
- **Trigger**: Only before initiating yt-dlp downloads (lazy evaluation)
- **Persistence**: Last update check time stored in database (not YAML/settings)

### 4. User Experience

- **Background Operation**: Updates happen transparently
- **Progress Indication**: Show update status during download initiation
- **Graceful Degradation**: Continue with existing version if update fails

## Integration Point Analysis

### Why Not UI-Based Integration

The application has two download initiation paths:

1. **User Interface**: `YoutubePage._on_add_download_clicked()` or `auto_add_download()`
2. **Chrome Extension**: Direct protocol handler calls

Both paths converge at `DownloadManager.add_download()` → `_process_queue()` → `CLIDownloadWorker` creation.

### Correct Integration Point

**Location**: `DownloadManager._process_queue()` (around line 430-435)
**Timing**: Before `CLIDownloadWorker(url, format_options, output_dir)` creation
**Rationale**: This catches ALL download attempts regardless of source (UI or extension)

```python
# In DownloadManager._process_queue()
for url, format_options, output_dir in urls_to_process:

    # Check for yt-dlp updates if needed (NEW)
    if YtDlpUpdater.should_check_for_update():
        YtDlpUpdater.check_and_update_async()

    # Create worker (existing code)
    thread = QThread(parent=self)
    worker = CLIDownloadWorker(url, format_options, output_dir)
    # ... rest of existing code
```

## Architecture Overview

### Component Structure

```
YtDlpUpdater
├── UpdateChecker (GitHub API interaction)
├── VersionManager (version comparison & validation)
├── FileDownloader (download & installation)
├── PathManager (file system operations)
├── DatabaseManager (update tracking persistence)
└── SettingsIntegration (UI preferences only)
```

### Integration Points

1. **DownloadManager**: Calls update check before CLIDownloadWorker creation
2. **Database**: Stores last update timestamp and version info in SQLite
3. **SettingsManager**: Stores user preferences (enabled/disabled, intervals)
4. **Logger**: Records update activities and errors
5. **UI Components**: Shows update progress/status when needed

## Technical Implementation Design

### 1. GitHub Releases API Integration

#### Release Discovery

- **Endpoint**: `https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest`
- **Fallback**: Parse HTML from `https://github.com/yt-dlp/yt-dlp/releases` if API fails
- **Data Extraction**:
  - Release version tag (e.g., "2025.06.30")
  - Asset download URLs
  - Release date/timestamp
  - Release notes (optional)

#### Asset Identification

From GitHub releases assets, identify:

- **Primary Target**: `yt-dlp.exe` (Windows executable)
- **SHA Checksums**: `SHA2-256SUMS` for integrity verification
- **Download URL Pattern**: `https://github.com/yt-dlp/yt-dlp/releases/download/{version}/yt-dlp.exe`

### 2. Version Management

#### URL-Based Version Strategy

Instead of relying on potentially changing version string formats, we use download URLs as version identifiers:

```python
def compare_versions(current_url: str, latest_url: str) -> bool:
    """
    Compare versions using download URLs as identifiers.
    This approach is future-proof regardless of yt-dlp's versioning scheme.

    Returns True if URLs are different (update needed)
    """
```

**Rationale**: URL-based versioning ensures our system works regardless of how yt-dlp chooses to version their releases (YYYY.MM.DD, semantic versioning, etc.).

#### Version Storage - Database Approach

**Database Table**: `yt_dlp_updates` (similar to `playback_positions`)
**Location**: Same SQLite database as PlaybackPositionManager
**Schema**:

```sql
CREATE TABLE IF NOT EXISTS yt_dlp_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    current_download_url TEXT NOT NULL,    -- Primary version identifier
    current_version_string TEXT,           -- Optional: from yt-dlp --version
    latest_checked_url TEXT NOT NULL,      -- Latest URL found from GitHub
    latest_version_string TEXT,            -- Optional: extracted version info
    last_check_time TEXT NOT NULL,         -- ISO format datetime
    last_update_time TEXT,                 -- ISO format datetime, NULL if never updated
    install_path TEXT NOT NULL,
    backup_path TEXT,
    check_count INTEGER NOT NULL DEFAULT 1,
    update_count INTEGER NOT NULL DEFAULT 0,
    last_error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
```

**Key Changes**:

- `current_download_url`: Primary version identifier (replaces version string comparison)
- `current_version_string`: Optional field for display purposes
- `latest_checked_url`: Latest download URL from GitHub
- `latest_version_string`: Optional extracted version for user display

### 3. Download & Installation Process

#### Pre-Download Validation

1. **Network Connectivity**: Verify GitHub access
2. **Disk Space**: Check available space (minimum 50MB)
3. **Permissions**: Verify write access to target directory
4. **Current Process**: Ensure yt-dlp.exe not currently running

#### Download Process

```python
class YtDlpDownloader:
    def download_with_progress(self, url: str, target_path: str) -> bool:
        """
        Download with progress tracking and integrity verification.

        Steps:
        1. Download to temporary file (.tmp)
        2. Verify SHA256 checksum
        3. Atomic move to final location
        4. Update database with new version info
        """
```

#### Installation Strategy

1. **Temporary Download**: `C:\yt-dlp\yt-dlp.exe.tmp`
2. **Backup Creation**: `C:\yt-dlp\yt-dlp.exe.backup`
3. **Atomic Replacement**: Rename operations for consistency
4. **Database Update**: Record successful update with timestamp
5. **Rollback Capability**: Restore backup on failure

### 4. Error Handling & Recovery

#### Network Error Scenarios

- **GitHub API Unavailable**: Fallback to HTML parsing
- **Download Interruption**: Resume capability with Range headers
- **Rate Limiting**: Exponential backoff with jitter

#### File System Error Scenarios

- **Permission Denied**: Attempt UAC elevation or fallback location
- **Disk Full**: Clean temporary files and retry
- **Corrupted Download**: Checksum verification and re-download

#### Graceful Degradation

- **Update Failure**: Continue with existing yt-dlp.exe
- **Missing Executable**: Prompt user for manual installation
- **Old Version**: Show warning but allow operation

## Database Integration (Refactored Architecture)

### Database Manager Design

The yt-dlp update system uses a refactored database architecture that eliminates code duplication and provides a solid foundation for future database features.

```python
# Base database functionality (music_player/models/database.py)
class BaseDatabaseManager(ABC):
    """
    Abstract base class providing common database functionality:
    - Singleton pattern implementation
    - Database connection management with retry logic
    - Thread-safe operations
    - Common utility methods
    """

# Specific implementation for yt-dlp updates
class YtDlpUpdateManager(BaseDatabaseManager):
    """
    Database manager for yt-dlp update tracking.
    Inherits common functionality from BaseDatabaseManager.
    """

    def _init_database(self):
        """Initialize the yt-dlp update tracking table."""
        # Create yt-dlp specific tables using inherited methods
        pass
```

### Database Architecture Benefits

- **Code Reuse**: ~200 lines of duplicate code eliminated
- **Consistency**: All database operations follow the same patterns
- **Extensibility**: Easy to add new database managers for future features
- **Maintainability**: Common database logic centralized in one place

### Database Operations

```python
def get_last_check_time(self) -> Optional[datetime]:
    """Get the last update check timestamp from database."""

def get_current_version_info(self) -> Optional[Dict[str, str]]:
    """Get current version info with both URL and version string."""

def record_check_attempt(self, latest_url: str, latest_version_string: str,
                        current_url: str, current_version_string: str,
                        install_path: str) -> bool:
    """Record an update check attempt with URL-based versioning."""

def record_update_success(self, new_download_url: str, new_version_string: str,
                         install_path: str, backup_path: str = None) -> bool:
    """Record a successful update with new URL and version info."""

def record_update_error(self, error_message: str) -> None:
    """Record an update error in database."""
```

### Settings Manager Integration (UI Preferences Only)

```python
YT_DLP_UPDATER_SETTINGS = {
    # Update behavior (stored in QSettings for UI preferences)
    'yt_dlp_updater/enabled': (True, SettingType.BOOL),
    'yt_dlp_updater/auto_update': (True, SettingType.BOOL),
    'yt_dlp_updater/check_interval_hours': (24, SettingType.INT),

    # Path configuration (stored in QSettings for user preferences)
    'yt_dlp_updater/install_path': ('C:\\yt-dlp\\yt-dlp.exe', SettingType.PATH),
    'yt_dlp_updater/backup_path': ('C:\\yt-dlp\\yt-dlp.exe.backup', SettingType.PATH),

    # Network settings (stored in QSettings for user preferences)
    'yt_dlp_updater/timeout_seconds': (30, SettingType.INT),
    'yt_dlp_updater/max_retries': (3, SettingType.INT),

    # NOTE: Version tracking and timestamps are stored in DATABASE, not QSettings
}
```

### Update Frequency Logic

```python
def should_check_for_update() -> bool:
    """
    Determine if update check is needed based on:
    - Update enabled setting (from QSettings)
    - Time since last check from DATABASE (24-hour minimum)
    - Force update flag (for manual updates)
    """
    settings = SettingsManager.instance()

    if not settings.get('yt_dlp_updater/enabled', True, SettingType.BOOL):
        return False

    # Get last check time from DATABASE (not QSettings)
    db_manager = YtDlpUpdateManager.instance()
    last_check = db_manager.get_last_check_time()

    if last_check is None:
        return True

    time_since_check = datetime.now() - last_check
    check_interval = settings.get('yt_dlp_updater/check_interval_hours', 24, SettingType.INT)

    return time_since_check.total_seconds() >= (check_interval * 3600)

def compare_versions_by_url(current_url: str, latest_url: str) -> bool:
    """
    Compare versions using normalized URLs.
    Returns True if update is needed (URLs are different).
    """
    if not current_url or not latest_url:
        return True  # If we can't compare, assume update needed

    # Normalize URLs for consistent comparison
    current_normalized = normalize_url(current_url)
    latest_normalized = normalize_url(latest_url)

    return current_normalized != latest_normalized
```

## User Interface Integration

### 1. DownloadManager Integration

#### Download Initiation Flow

```python
# In DownloadManager._process_queue()
def _process_queue(self):
    """Process the download queue and start new QObject workers in QThreads."""
    # ... existing code for urls_to_process ...

    # Process outside lock
    for url, format_options, output_dir in urls_to_process:

        # Check for yt-dlp updates BEFORE creating worker (NEW)
        if YtDlpUpdater.instance().should_check_for_update():
            self.logger.info("DownloadManager", "Checking for yt-dlp updates...")
            update_result = YtDlpUpdater.instance().check_and_update_async()
            if update_result.updated:
                display_version = VersionManager().format_version_for_display(update_result.latest_url)
                self.logger.info("DownloadManager", f"Updated yt-dlp to {display_version}")

        # Create worker (existing code)
        thread = QThread(parent=self)
        worker = CLIDownloadWorker(url, format_options, output_dir)
        # ... rest of existing code
```

#### UpdateResult Structure

```python
class UpdateResult(NamedTuple):
    success: bool
    updated: bool
    current_url: str          # Current download URL
    latest_url: str           # Latest download URL
    current_version: str      # Current version string (display)
    latest_version: str       # Latest version string (display)
    error_message: str = ""
```

#### Status Display Options

- **Update Available**: Log message: "Downloading yt-dlp update..."
- **Update Complete**: Log message: "Updated to yt-dlp v{extracted_version}"
- **Update Failed**: Log message: "Update failed, using existing version"
- **No Update Needed**: Silent operation

**Note**: Version display uses `VersionManager.format_version_for_display()` which extracts readable version info from URLs when possible, or shows URL hashes as fallback.

### 2. Preferences Page

#### Update Settings Section

```yaml
Update Settings:
  - Enable automatic updates: [✓]
  - Check interval: [24] hours
  - Installation path: [C:\yt-dlp\] [Browse...]
  - Current version: v2025.06.30 (extracted from URL/version string)
  - Current URL: https://github.com/.../2025.06.30/yt-dlp.exe (from database)
  - Last check: 2 hours ago (from database)
  - [Check Now] [Reset to Defaults]
```

### 3. Status/Logging Integration

#### Update Notifications

- **Progress**: Logger: "Updating yt-dlp... downloading..."
- **Success**: Logger: "yt-dlp updated to v{extracted_version}"
- **Error**: Logger: "yt-dlp update failed: [error details]"

**Version Display Strategy**:

1. **Primary**: Extract version from URL path (e.g., "2025.06.30" from `.../download/2025.06.30/...`)
2. **Secondary**: Use `yt-dlp --version` output if available
3. **Fallback**: Show URL hash if version extraction fails

## Implementation Phases

### Phase 1: Core Infrastructure & Database ✅ COMPLETED

1. ✅ Create `YtDlpUpdater` class with URL-based update checking
2. ✅ Extend PlaybackPositionManager database with yt-dlp update table
3. ✅ Implement GitHub releases API integration with HTML fallback
4. ✅ Add URL-based version comparison logic (future-proof)
5. ✅ Add settings integration for UI preferences
6. ✅ **Database Architecture Refactoring**: Created `BaseDatabaseManager` and eliminated code duplication

**Key Achievements**:

- **URL-based versioning system** that works regardless of yt-dlp's version format changes
- **Database refactoring** that eliminated ~400 lines of duplicate code and created a foundation for future database features
- **Future-proof architecture** that supports easy addition of new database managers

### Phase 2: Download & Installation ✅ COMPLETED

1. ✅ Implement secure download with progress tracking
2. ✅ Add checksum verification
3. ✅ Create atomic installation process
4. ✅ Implement backup and rollback
5. ✅ Add database recording of all update events

**Key Achievements**:

- **Secure Download System**: `FileDownloader` class with progress tracking, retry logic, and robust error handling
- **Checksum Verification**: Mandatory SHA256 verification for download integrity
- **Atomic Installation**: `FileInstaller` class with atomic file operations, backup creation, and rollback capability
- **Event Tracking**: Comprehensive database recording of download start/complete, installation start/complete, and all errors
- **Path Management**: `PathManager` class for installation path validation, permission checking, and version detection

**New Components**:

- **file_manager.py** (`FileDownloader`, `FileInstaller`, `PathManager`):

  - Progress-tracked downloads with resume capability
  - SHA256 checksum verification
  - Atomic installation with backup/rollback
  - Path validation and permission checking
  - File locking detection and version extraction

- **Enhanced Database Recording**:
  - Download metrics (size, speed, time, checksum)
  - Installation events with version tracking
  - Comprehensive error logging and recovery tracking
  - Backup and rollback event recording

**Updated Components**:

- **updater.py**: Now uses `FileDownloader` and `FileInstaller` for all file operations
- **update_database_manager.py**: Added event recording methods for granular tracking
- **Eliminated Legacy Code**: Removed old `_download_file` method in favor of new file management system

### Phase 3: DownloadManager Integration ✅ COMPLETED

1. ✅ Add update check to `DownloadManager._process_queue()`
2. ✅ Implement async update checking to avoid blocking downloads
3. ✅ Add logging integration for update status
4. ✅ Test both UI and Chrome extension download paths

**Key Achievements**:

- **Seamless Integration**: Update check automatically triggers before any download starts, regardless of source (UI or Chrome extension)
- **Non-blocking Operation**: Asynchronous update checking ensures downloads start immediately while updates happen in background
- **Throttled Updates**: Smart throttling prevents excessive update checks (maximum once per hour)
- **Comprehensive Logging**: Update status, success, and failure messages logged through the application's logging system
- **Error Resilience**: Update failures don't prevent downloads from proceeding with existing yt-dlp version

**Technical Implementation**:

- **Integration Point**: Added update check in `DownloadManager._process_queue()` before `CLIDownloadWorker` creation
- **Async Thread**: Custom `YtDlpUpdateThread` performs update checking without blocking download operations
- **Status Tracking**: `_update_check_in_progress` and `_last_update_check_time` prevent duplicate checks
- **Unified Path**: Both UI downloads (`YoutubePage._on_add_download_clicked()`) and Chrome extension downloads (`YoutubePage.auto_add_download()`) use the same integration point
- **Graceful Degradation**: System continues to function even if yt-dlp updater components are not available

**Integration Flow Verified**:

1. **UI Downloads**: `YoutubePage` → `DownloadManager.add_download()` → `_process_queue()` → Update Check → Worker Creation
2. **Chrome Extension**: Protocol Handler → `Dashboard.handle_protocol_url()` → `YoutubePage.auto_add_download()` → Same path as UI downloads
3. **Update Check**: Asynchronous thread checks for updates, downloads latest version if needed, logs results
4. **Download Continuation**: Downloads proceed with updated or existing yt-dlp version

### Phase 4: UI Integration & Advanced Features

1. Add preferences section for update settings
2. Implement manual update trigger
3. Add update history display (from database)
4. Create update notification system
5. Add update scheduling options

## File Structure

```
music_player/
├── models/
│   ├── database.py              # 🆕 Base database functionality
│   ├── position_manager.py      # ♻️ Refactored to inherit from BaseDatabaseManager
│   ├── yt_dlp_updater/
│   │   ├── __init__.py
│   │   ├── updater.py                    # ♻️ Updated to use file_manager components
│   │   ├── github_client.py              # GitHub API interaction
│   │   ├── version_manager.py            # Version comparison logic
│   │   ├── file_manager.py               # ✅ Download and installation (Phase 2 COMPLETED)
│   │   ├── update_database_manager.py    # ♻️ Renamed from database_manager.py, inherits from BaseDatabaseManager
│   │   └── settings_integration.py       # Settings definitions
│   └── settings_defs.py         # Add updater settings
├── ui/
│   ├── pages/
│   │   ├── youtube_page.py      # No changes needed (uses DownloadManager)
│   │   └── preference_page.py   # Add update settings section (TODO: Phase 4)
│   └── components/
│       └── update_status.py     # Optional: Update progress widget (TODO: Phase 4)
└── resources/
    └── yt_dlp_updater_config.yaml # Default configuration (optional)
```

### Database Refactoring Benefits ✅ COMPLETED

- **Base Database Class**: `BaseDatabaseManager` provides common functionality
- **Code Elimination**: ~400 lines of duplicate database code removed
- **Singleton Pattern**: Class-specific singleton implementation for multiple managers
- **Error Handling**: Centralized retry logic and transaction management
- **Future-Proof**: Easy to add new database managers for future features

### Refactored Components

1. **BaseDatabaseManager** (`database.py`):

   - Abstract base class for all database managers
   - Common connection, retry, and transaction logic
   - Utility methods for schema management

2. **PlaybackPositionManager** (`position_manager.py`):

   - Inherits from `BaseDatabaseManager`
   - Focuses on playback position business logic
   - ~200 lines of duplicate code removed

3. **YtDlpUpdateManager** (`update_database_manager.py`):
   - Renamed from `database_manager.py` for clarity
   - Inherits from `BaseDatabaseManager`
   - Focuses on update tracking business logic
   - ~200 lines of duplicate code removed

## Security Considerations

### 1. Download Integrity

- **SHA256 Verification**: Mandatory checksum validation
- **HTTPS Only**: Enforce encrypted connections
- **Signature Verification**: Optional GPG signature checking

### 2. File System Security

- **Path Validation**: Prevent directory traversal attacks
- **Permission Checks**: Verify write permissions before operations
- **Atomic Operations**: Prevent partial file corruption

### 3. Network Security

- **User-Agent**: Identify as legitimate application
- **Rate Limiting**: Respect GitHub API limits
- **Timeout Handling**: Prevent hanging connections

### 4. Database Security

- **SQLite File Permissions**: Restrict access to update tracking database
- **Input Validation**: Sanitize all database inputs
- **Transaction Safety**: Use proper transaction handling for update records

## Testing Strategy

### 1. Unit Tests

- Version comparison algorithms
- Database operations (CRUD for update records)
- Settings integration
- Error handling scenarios
- File system operations

### 2. Integration Tests

- GitHub API interaction
- Download and installation process
- DownloadManager integration (both UI and extension paths)
- Database persistence across application restarts
- Settings persistence

### 3. System Tests

- End-to-end update scenarios
- Network failure simulation
- File system permission testing
- Chrome extension + update interaction
- Performance under load

## Performance Considerations

### 1. Network Efficiency

- **Conditional Requests**: Use ETag/Last-Modified headers
- **Compression**: Support gzip encoding
- **Connection Reuse**: HTTP connection pooling
- **Async Operations**: Non-blocking update checks

### 2. Resource Usage

- **Background Downloads**: Non-blocking UI operations
- **Memory Management**: Stream large files to disk
- **CPU Usage**: Efficient checksum calculations
- **Database Performance**: Indexed queries, minimal locks

### 3. User Experience

- **Fast Startup**: Async update checks in background
- **Minimal Interruption**: Downloads continue with existing version if update fails
- **Progress Feedback**: Real-time download status via logging

## Monitoring & Diagnostics

### 1. Logging

- Update check attempts and results
- Download progress and completion
- Error conditions and recovery actions
- Performance metrics (download speed, time)
- Database operation results

### 2. Database Metrics

- Update success/failure rates (queryable from database)
- Average download times (stored in database)
- Version adoption timeline (historical data)
- Error frequency analysis (from database records)

### 3. User Feedback

- Update notification preferences (in settings)
- Manual update trigger usage (logged to database)
- Error reporting and diagnostics (stored in database)
- Performance satisfaction metrics

## Key Design Decisions & Rationale

### URL-Based Versioning Strategy

**Problem**: Traditional version parsing (e.g., YYYY.MM.DD) makes assumptions about yt-dlp's future versioning scheme.

**Solution**: Use download URLs as primary version identifiers.

**Benefits**:

1. **Future-Proof**: Works regardless of version format changes
2. **Reliable**: URL changes guarantee a new release
3. **Simple**: String comparison instead of complex parsing
4. **Robust**: No dependency on version string formats

**Implementation**:

```python
# Traditional approach (fragile):
if parse_version("2025.06.30") > parse_version("2025.06.29"):
    update_needed = True

# URL-based approach (robust):
if current_url != latest_url:
    update_needed = True
```

### Database-First Architecture

**Design**: Store all tracking data in SQLite database, settings only for user preferences.

**Rationale**:

- **Persistence**: Update history survives app restarts
- **Performance**: Indexed queries for statistics
- **Reliability**: ACID transactions for data integrity
- **Scalability**: Can track unlimited update history

### Integration Strategy

**Point**: `DownloadManager._process_queue()` before `CLIDownloadWorker` creation

**Rationale**:

- Catches both UI and Chrome extension downloads
- Minimal performance impact (lazy evaluation)
- Clean separation of concerns

## Future Enhancements

### 1. Advanced Features

- **Delta Updates**: Download only changed portions
- **Multiple Sources**: Mirror support for reliability
- **Rollback UI**: Easy version downgrade option from database history
- **Update Scheduling**: Specific time-based updates

### 2. Enterprise Features

- **Group Policy**: Centralized update management
- **Update Approval**: Manual review before installation
- **Offline Updates**: Local update server support
- **Compliance Reporting**: Update audit trails from database

### 3. Cross-Platform Support

- **macOS Support**: Homebrew integration
- **Linux Support**: Package manager integration
- **Universal Installer**: Platform-specific deployment
