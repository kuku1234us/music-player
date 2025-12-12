"""
Download manager for handling multiple YouTube downloads.
"""
import os
import threading
import time
from typing import Dict, List, Optional, Any, Tuple
from queue import Queue

from PyQt6.QtCore import QObject, pyqtSignal, QThread, QMutex, QUrl, QTimer, pyqtSlot
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

from qt_base_app.models.logger import Logger
from .SiteModel import SiteModel
from .CLIDownloadWorker import CLIDownloadWorker

# Import yt-dlp updater for automatic updates
try:
    from .yt_dlp_updater.updater import YtDlpUpdater
    from .yt_dlp_updater.version_manager import VersionManager
    YTDLP_UPDATER_AVAILABLE = True
except ImportError as e:
    # Log the import error but don't fail
    Logger.instance().warning(caller="DownloadManager", msg=f"Warning: yt-dlp updater not available: {e}")
    YTDLP_UPDATER_AVAILABLE = False

class DownloadManager(QObject):
    """Manager for handling multiple YouTube downloads."""
    
    # Define signals
    queue_updated = pyqtSignal()
    download_started = pyqtSignal(str, str, QPixmap)  # url, title, thumbnail
    download_progress = pyqtSignal(str, float, str)  # url, progress percentage, status text
    download_complete = pyqtSignal(str, str, str)  # url, output_dir, filename
    download_error = pyqtSignal(str, str)  # url, error message
    
    def __init__(self, parent=None):
        """Initialize the download manager."""
        super().__init__(parent)
        
        # Store worker instances and their threads separately
        self._workers: Dict[str, CLIDownloadWorker] = {} # Map URL to worker instance
        self._threads: Dict[str, QThread] = {}          # Map URL to thread instance
        
        self._queue = []  
        self._active = {}  # Now {url: worker_instance} for active downloads
        self._completed = []  
        self._errors = []  
        self._metadata = {} 
        self._max_concurrent = 2
        self._mutex = QMutex()
        self.logger = Logger.instance()
        # Track active count separately
        self._active_worker_count = 0 
        
        # Quick metadata fetch thread tracking (remains the same)
        self._quick_metadata_threads = {} 
        
        # yt-dlp update tracking
        self._update_check_in_progress = False
        self._last_update_check_time = None
    
    def get_max_concurrent(self):
        """Get the maximum number of concurrent downloads."""
        return self._max_concurrent
    
    def set_max_concurrent(self, value):
        """Set the maximum number of concurrent downloads."""
        self._max_concurrent = max(1, min(5, value))  # Constrain between 1-5
        self._process_queue()  # Start new downloads if possible
    
    def add_download(self, url, format_options=None, output_dir=None):
        """
        Add a URL to the download queue.
        
        Args:
            url (str): The URL to download
            format_options (dict or str): Format options for yt-dlp
            output_dir (str): The output directory for downloaded files
        
        Returns:
            bool: True if added, False if already in queue
        """
        clean_url = SiteModel.get_clean_url(url)
        
        Logger.instance().debug(caller="DownloadManager", msg=f"DEBUG: add_download called with URL: {url}, clean_url: {clean_url}")
        Logger.instance().debug(caller="DownloadManager", msg=f"DEBUG: Format options received: {format_options}")
        
        self._mutex.lock()
        is_new = False
        try:
            # Check if already in queue
            if (clean_url in self._queue or 
                clean_url in self._active or 
                clean_url in self._completed or
                clean_url in self._errors):
                Logger.instance().debug(caller="DownloadManager", msg=f"DEBUG: URL already in queue: {clean_url}")
                return False
            
            # Add to queue
            self._queue.append(clean_url)
            Logger.instance().debug(caller="DownloadManager", msg=f"DEBUG: Added to queue: {clean_url}")
            is_new = True
            
            # Initialize metadata
            self._metadata[clean_url] = {
                'url': clean_url,
                'title': f"Loading...",
                'status': 'Queued',
                'progress': 0,
                'thumbnail': None,
                'format_options': format_options or 'best',
                'output_dir': output_dir or os.path.expanduser('~/Downloads')
            }
            
            Logger.instance().debug(caller="DownloadManager", msg=f"DEBUG: Metadata initialized with format_options: {self._metadata[clean_url]['format_options']}")
        finally:
            self._mutex.unlock()
        
        if is_new:
            # Emit signal
            self.queue_updated.emit()
            
            # Fetch metadata in background thread
            # Always fetch metadata for all URLs, even ones that were from the protocol handler
            # This ensures we get proper titles for Chrome extension URLs
            Logger.instance().info(caller="DownloadManager", msg=f"DEBUG: Starting quick metadata fetch for: {clean_url}")
            self._fetch_quick_metadata_threaded(clean_url)
            
            # Process queue (will start download if slots available)
            self._process_queue()
            
            return True
        
        return False
    
    def _fetch_quick_metadata_threaded(self, url):
        """
        Start a thread to quickly fetch basic metadata without blocking the UI.
        This is a lightweight alternative to the full _fetch_metadata method.
        """
        class QuickMetadataThread(QThread):
            # Define signals for thread-safe communication
            metadata_ready = pyqtSignal(str, str, QPixmap)
            
            def __init__(self, url, format_options=None, parent=None):
                super().__init__(parent)
                self.url = url
                self.format_options = format_options or {}
                
            def run(self):
                try:
                    # Extract video ID using SiteModel
                    video_id = SiteModel.extract_video_id(self.url)
                    
                    if not video_id:
                        # If we can't extract a video ID, just return
                        return
                    
                    # Try to get title and thumbnail using SiteModel with retries
                    max_retries = 3
                    retry_count = 0
                    title, pixmap = None, None
                    
                    while retry_count < max_retries and not title:
                        try:
                            title, pixmap = SiteModel.get_video_metadata(self.url)
                            if not title:
                                retry_count += 1
                                if retry_count < max_retries:
                                    import time
                                    time.sleep(2)  # Wait before retrying
                                    continue
                                else:
                                    # Use a generic title with the platform detected after max retries
                                    site = SiteModel.detect_site(self.url)
                                    title = f"Loading: {site} video"
                        except Exception:
                            retry_count += 1
                            if retry_count < max_retries:
                                import time
                                time.sleep(2)  # Wait before retrying
                            else:
                                # Use a generic title after max retries
                                site = SiteModel.detect_site(self.url)
                                title = f"Loading: {site} video"
                    
                    if not title:
                        # Use a generic title with the platform detected
                        site = SiteModel.detect_site(self.url)
                        title = f"Loading: {site} video"
                    
                    if pixmap:
                        # Scale the pixmap before sending it
                        scaled_pixmap = pixmap.scaled(
                            160, 90,
                            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        
                        # Center-crop if too big
                        if scaled_pixmap.width() > 160 or scaled_pixmap.height() > 90:
                            x = (scaled_pixmap.width() - 160) // 2 if scaled_pixmap.width() > 160 else 0
                            y = (scaled_pixmap.height() - 90) // 2 if scaled_pixmap.height() > 90 else 0
                            scaled_pixmap = scaled_pixmap.copy(int(x), int(y), 160, 90)
                        
                        # Emit signal with metadata
                        self.metadata_ready.emit(self.url, title, scaled_pixmap)
                    else:
                        # Always emit signal with title even if no thumbnail
                        # This ensures the title gets updated in the UI
                        self.metadata_ready.emit(self.url, title, QPixmap())
                
                except Exception as e: # Restore the except block
                    # Log the error but don't fail - metadata isn't critical
                    # We can use print here as it's isolated in a thread and logger might not be easily accessible
                    Logger.instance().error(caller="DownloadManager", msg=f"[QuickMetadataThread ERROR] URL={self.url}: {str(e)}")
                    
                    # Still emit a signal with a generic title so the UI can show something
                    site = SiteModel.detect_site(self.url)
                    title = f"Loading: {site} video {video_id}" if video_id else f"Loading: {site} video"
                    self.metadata_ready.emit(self.url, title, QPixmap())
        
        # Get the format options for the URL
        format_options = None
        if url in self._metadata and 'format_options' in self._metadata[url]:
            format_options = self._metadata[url]['format_options']
        
        # Create and configure the thread
        thread = QuickMetadataThread(url, format_options, self)
        
        # Connect signals
        thread.metadata_ready.connect(self._on_quick_metadata_ready)
        
        # Store thread reference to prevent garbage collection
        if not hasattr(self, '_quick_metadata_threads'):
            self._quick_metadata_threads = {}
        self._quick_metadata_threads[url] = thread
        
        # Start the thread
        thread.start()
    
    def _on_quick_metadata_ready(self, url, title, pixmap):
        """Handle completion of quick metadata fetch."""
        Logger.instance().debug(caller="DownloadManager", msg=f"DEBUG: Quick metadata ready for {url}: title={title}, has thumbnail={not pixmap.isNull()}")
        
        # --- Prepare data under lock ---
        emit_signal = False
        meta_title_to_emit = title # Use received title by default
        meta_thumbnail_to_emit = pixmap or QPixmap()
        
        self._mutex.lock()
        try:
            if url in self._metadata:
                # Only update title if it's better than the loading placeholder
                # or if the current title is a placeholder
                current_title = self._metadata[url].get('title', '')
                if (title and not title.startswith("Loading:") or 
                    current_title.startswith("Loading")):
                    Logger.instance().debug(caller="DownloadManager", msg=f"DEBUG: Updating title for {url} from '{current_title}' to '{title}'")
                    self._metadata[url]['title'] = title
                    meta_title_to_emit = title # Use the updated title
                else:
                    meta_title_to_emit = current_title # Keep the existing title for emit
                
                # Update thumbnail if we have one
                if not pixmap.isNull():
                    self._metadata[url]['thumbnail'] = pixmap
                    meta_thumbnail_to_emit = pixmap # Use the updated thumbnail
                else:
                    # If no new pixmap, use existing one if available
                    existing_thumb = self._metadata[url].get('thumbnail')
                    if existing_thumb:
                         meta_thumbnail_to_emit = existing_thumb
                         
                emit_signal = True # Mark that we need to emit the signal
        finally:
            self._mutex.unlock()
        
        # --- Emit signal outside lock --- 
        if emit_signal:
            self.download_started.emit(url, meta_title_to_emit, meta_thumbnail_to_emit)
            # Debug log that we emitted the signal
            Logger.instance().info(caller="DownloadManager", msg=f"DEBUG: Emitted download_started signal for {url} with title '{meta_title_to_emit}'")
        
        # Clean up thread (this part is fine outside lock)
        if hasattr(self, '_quick_metadata_threads') and url in self._quick_metadata_threads:
            thread = self._quick_metadata_threads[url]
            if not thread.isRunning():
                thread.deleteLater()
                del self._quick_metadata_threads[url]
                
    def _fetch_quick_metadata(self, url):
        """
        DEPRECATED: Use _fetch_quick_metadata_threaded instead.
        This synchronous version is kept for backward compatibility.
        """
        # Start threaded version instead
        self._fetch_quick_metadata_threaded(url)
    
    def cancel_download(self, url):
        """Cancel a download or remove a completed/errored/queued download."""
        worker_to_cancel: Optional[CLIDownloadWorker] = None
        thread_to_manage: Optional[QThread] = None
        url_to_cancel = url
        need_queue_update = False
        need_process_queue = False
        metadata_removed = False
        
        self._mutex.lock()
        try:
            Logger.instance().debug(caller="DownloadManager", msg=f"DEBUG: Cancelling/Removing download for URL: {url}")
            
            # Check if download is active
            if url in self._active:
                worker_to_cancel = self._active[url] # Get worker reference, but don't remove yet
                if url in self._threads:
                    thread_to_manage = self._threads[url] # Get thread reference, but don't remove yet
                else: 
                    thread_to_manage = None

                # Don't decrement active count or remove from dictionaries yet
                # Mark as cancelling in metadata instead
                need_queue_update = True
                if url in self._metadata:
                    self._metadata[url]['status'] = 'Cancelling' # Mark as cancelling instead of cancelled
                    self._metadata[url]['cancelling'] = True     # Add explicit flag for checking
            
            # For non-active items, proceed with immediate removal as before
            elif url in self._queue:
                self._queue.remove(url)
                need_queue_update = True
                if url in self._metadata: del self._metadata[url]; metadata_removed = True
            elif url in self._errors:
                self._errors.remove(url)
                need_queue_update = True
                if url in self._metadata: del self._metadata[url]; metadata_removed = True
                Logger.instance().error(caller="DownloadManager", msg=f"DEBUG: Removed error item: {url}")
            elif url in self._completed:
                self._completed.remove(url)
                need_queue_update = True
                if url in self._metadata: del self._metadata[url]; metadata_removed = True
                Logger.instance().info(caller="DownloadManager", msg=f"DEBUG: Removed completed download: {url}")
            elif url in self._metadata: # Case where it might be only in metadata (e.g., after completion/error but before UI refresh)
                Logger.instance().debug(caller="DownloadManager", msg=f"DEBUG: Removing metadata only for URL: {url}")
                del self._metadata[url]
                metadata_removed = True
                need_queue_update = True
            else:
                Logger.instance().debug(caller="DownloadManager", msg=f"DEBUG: URL not found in any collection: {url}")
        finally:
            self._mutex.unlock()
        
        # --- Actions outside lock --- 
        if worker_to_cancel is not None:
            Logger.instance().debug(caller="DownloadManager", msg=f"DEBUG: Cancel signaled for worker: {url_to_cancel}")
            worker_to_cancel.cancel() # Ask worker to stop its internal process
            # Thread management is handled via finished signal connections

        if need_queue_update:
            self.queue_updated.emit()
        if need_process_queue:
            self._process_queue() # Check if a new download can start
    
    def get_all_urls(self):
        """Get all URLs in the queue, active downloads, completed downloads, and error downloads."""
        self._mutex.lock()
        try:
            # Get keys from _active dict which now holds worker instances
            return list(self._queue) + list(self._active.keys()) + list(self._completed) + list(self._errors)
        finally:
            self._mutex.unlock()
    
    def get_status(self, url):
        """Get the status of a download."""
        if url in self._metadata:
            return self._metadata[url]['status']
        return None
    
    def get_progress(self, url):
        """Get the progress percentage of a download."""
        if url in self._metadata:
            return self._metadata[url]['progress']
        return 0
    
    def get_title(self, url):
        """Get the title of a video."""
        if url in self._metadata:
            return self._metadata[url]['title']
        return None
    
    def get_thumbnail(self, url):
        """Get the thumbnail for a video."""
        if url in self._metadata:
            return self._metadata[url]['thumbnail']
        return None
    
    def get_output_path(self, url):
        """Get the output directory for a completed download."""
        if url in self._metadata:
            return self._metadata[url].get('output_dir')
        return None
    
    def get_output_filename(self, url):
        """Get the filename of a completed download."""
        if url in self._metadata:
            return self._metadata[url].get('filename')
        return None
    
    def _process_queue(self):
        """Process the download queue and start new QObject workers in QThreads."""
        urls_to_process = []
        urls_to_update = []
        
        self._mutex.lock()
        try:
            # Use the separate active worker count
            available_slots = self._max_concurrent - self._active_worker_count 
            urls_to_start = min(available_slots, len(self._queue))
            
            for _ in range(urls_to_start):
                url = self._queue.pop(0)
                metadata = self._metadata[url]
                format_options = metadata['format_options']
                output_dir = metadata['output_dir']
                urls_to_process.append((url, format_options, output_dir))
                metadata['status'] = 'Starting'
                metadata['stats'] = 'Initializing...'
                urls_to_update.append(url)
                # Add placeholder to _active here, will be replaced after worker creation
                self._active[url] = None 
                self._active_worker_count += 1 # Increment active count
        finally:
            self._mutex.unlock()
        
        for url in urls_to_update:
            self.download_progress.emit(url, 0, "Initializing...")
        
        # Check for yt-dlp updates before starting downloads (synchronously, timestamp-gated)
        if urls_to_process and YTDLP_UPDATER_AVAILABLE:
            try:
                from .yt_dlp_updater.updater import YtDlpUpdater
                updater = YtDlpUpdater.instance()
                if updater.should_check_for_update():
                    self.logger.info("DownloadManager", "Checking for yt-dlp updates before starting downloads...")
                    result = updater.check_and_update_async(force_check=False)
                    if not result.success and result.error_message:
                        self.logger.warning("DownloadManager", f"yt-dlp update check failed: {result.error_message}")
                    elif result.updated:
                        self.logger.info("DownloadManager", f"yt-dlp updated to {result.latest_version or result.current_version}")
                    else:
                        self.logger.debug("DownloadManager", "yt-dlp already up to date before starting downloads")
                else:
                    self.logger.debug("DownloadManager", "Skipping yt-dlp update check (interval not reached)")
            except Exception as e:
                self.logger.warning("DownloadManager", f"yt-dlp synchronous update encountered an error: {e}")
        
        # Process outside lock
        for url, format_options, output_dir in urls_to_process:
            
            # Create worker (QObject) and thread (QThread)
            # Set parent for the QThread to self (DownloadManager)
            thread = QThread(parent=self) 
            # Worker should NOT have a parent before being moved
            worker = CLIDownloadWorker(url, format_options, output_dir)
            
            # Move worker to the thread
            worker.moveToThread(thread)
            
            # Connect worker signals to manager slots (run in main thread)
            worker.progress_signal.connect(self._on_progress)
            worker.complete_signal.connect(self._on_complete)
            worker.error_signal.connect(self._on_error)
            worker.processing_signal.connect(self._on_processing)
            # Connect worker finished to manager's cleanup slot and thread quit
            worker.finished.connect(lambda u=url: self._on_worker_finished(u)) # Pass url 
            worker.finished.connect(thread.quit)
            # Connect thread finished to cleanup for worker and thread
            thread.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            # Connect thread started to worker's run slot
            thread.started.connect(worker.run)
            
            # Store worker and thread references (before starting thread)
            self._mutex.lock()
            try:
                # Replace placeholder in _active with actual worker
                if url in self._active:
                    self._active[url] = worker
                self._threads[url] = thread # Store thread reference
            finally:
                self._mutex.unlock()

            # Start the thread (which will trigger worker.run)
            thread.start()
        
        if urls_to_process:
            self.queue_updated.emit()
        
    # --- Signal Handlers from Worker --- 
    # These run in the main thread because the signals are connected
    # across threads by Qt's auto-connection type.
    
    def _on_progress(self, url, progress, status_text):
        """Handle progress updates from download threads."""
        if url in self._metadata:
            self._metadata[url]['progress'] = progress
            self._metadata[url]['stats'] = status_text
            self.download_progress.emit(url, progress, status_text)
    
    def _on_complete(self, url, output_dir, filename):
        """Handle download completion signal from worker."""
        Logger.instance().debug(caller="DownloadManager", msg=f"Download complete signal received - URL: {url}")
        Logger.instance().debug(caller="DownloadManager", msg=f"Output directory: {output_dir}")
        Logger.instance().debug(caller="DownloadManager", msg=f"Filename: {filename}")
        # File existence check remains useful here
        if filename:
            filepath = os.path.join(output_dir, filename) if output_dir else None
            if not filepath or not os.path.exists(filepath):
                Logger.instance().warning(caller="DownloadManager", msg=f"WARNING: File does not exist at expected path: {filepath}")
        
        # --- Update state under lock --- 
        need_queue_update = False
        self._mutex.lock()
        try:
            if url in self._metadata:
                self._metadata[url]['status'] = 'Complete'
                self._metadata[url]['progress'] = 100
                self._metadata[url]['output_dir'] = output_dir
                self._metadata[url]['filename'] = filename
                need_queue_update = True # Need to update UI state
                
            if url not in self._completed: # Add to completed list
                self._completed.append(url)
        finally:
            self._mutex.unlock()
            
        # --- Emit signals outside lock --- 
        self.download_complete.emit(url, output_dir, filename) # Emit specific completion
        if need_queue_update:
            self.queue_updated.emit() # Let UI know general state changed
    
    def _on_error(self, url, error_message):
        """Handle download error signal from worker."""
        Logger.instance().error(caller="DownloadManager", msg=f"DEBUG: _on_error signal received for URL: {url} with message: {error_message}")
        
        # --- Update state under lock --- 
        need_queue_update = False
        self._mutex.lock()
        try:
            if url not in self._errors: # Add to error list
                self._errors.append(url)
            if url in self._metadata: # Update metadata
                # Check if this is an "Already Exists" message
                if error_message == "Already Exists":
                    self._metadata[url]['status'] = 'Already Exists'
                    Logger.instance().debug(caller="DownloadManager", msg=f"DEBUG: Setting status for {url} to 'Already Exists'")
                else:
                    self._metadata[url]['status'] = 'Error'
                    Logger.instance().error(caller="DownloadManager", msg=f"DEBUG: Setting status for {url} to 'Error' (message was: {error_message})")
                    
                self._metadata[url]['stats'] = error_message
                self._metadata[url]['dismissable'] = True
                need_queue_update = True # Need to update UI state
        finally:
            self._mutex.unlock()
        
        # --- Emit signals outside lock --- 
        self.download_error.emit(url, error_message)
        if need_queue_update:
            self.queue_updated.emit() # Let UI know general state changed
    
    def _on_processing(self, url, message):
        """Handle processing started signal from download thread."""
        if url in self._metadata:
            self._metadata[url]['stats'] = message
            self.download_progress.emit(url, 0, message)
    
    # --- Slot for Worker Finished Signal --- 
    @pyqtSlot(str) # Add slot decorator
    def _on_worker_finished(self, url: str):
        """Handles cleanup when a worker's finished signal is received."""
        self.logger.debug(caller="DownloadManager", msg=f"_on_worker_finished triggered for URL: {url}")
        need_process_queue = False
        was_cancelling = False
        need_queue_update = False # Use a single flag
        
        # --- Update state under lock --- 
        self._mutex.lock()
        try:
            # Check if this was marked for cancellation
            if url in self._metadata and self._metadata[url].get('cancelling', False):
                was_cancelling = True
                self.logger.debug(caller="DownloadManager", msg=f"Worker {url} was being cancelled")
                
            # Remove from active dict and thread dict - always do this when worker finishes
            if url in self._active:
                del self._active[url]
                self._active_worker_count = max(0, self._active_worker_count - 1)
                self.logger.debug(caller="DownloadManager", msg=f"Removed worker {url} from active. Count: {self._active_worker_count}")
                need_process_queue = True # Check if new downloads can start
            else:
                # Only log as warning if this wasn't expected (i.e., not a cancellation)
                if not was_cancelling:
                    self.logger.warning(caller="DownloadManager", msg=f"Worker finished for {url}, but it wasn't in the active dictionary.")

            if url in self._threads:
                del self._threads[url] # Remove thread reference
            else:
                # Only log as warning if this wasn't expected (i.e., not a cancellation)
                if not was_cancelling:
                    self.logger.warning(caller="DownloadManager", msg=f"Thread for finished worker {url} not found in dictionary.")
                 
            # If this was a cancelled download, update status and move to errors
            if was_cancelling:
                if url in self._metadata:
                    self._metadata[url]['status'] = 'Cancelled'
                    # Remove the temporary 'cancelling' flag
                    if 'cancelling' in self._metadata[url]: 
                        del self._metadata[url]['cancelling']
                    # Add to errors list so it can be dismissed
                    if url not in self._errors:
                        self._errors.append(url)
                    self.logger.debug(caller="DownloadManager", msg=f"Marked {url} as Cancelled and moved to errors list.")
                    need_queue_update = True # Need UI update
                else:
                     self.logger.warning(caller="DownloadManager", msg=f"Metadata for cancelled URL {url} was missing.")
                
        finally:
            self._mutex.unlock()
        
        # --- Actions outside lock --- 
        # Emit queue update if needed (covers cancellation finish)
        if need_queue_update:
             self.queue_updated.emit() 
             
        # Process queue outside the lock if a slot opened up
        if need_process_queue:
            self.logger.debug(caller="DownloadManager", msg=f"Processing queue after worker finished for {url}")
            self._process_queue()

    def dismiss_error(self, url):
        """Dismiss an error item from the queue."""
        self._mutex.lock()
        try:
            if url in self._errors:
                self._errors.remove(url)
                
            if url in self._metadata:
                del self._metadata[url]
            
            Logger.instance().error(caller="DownloadManager", msg=f"DEBUG: Dismissed error for URL: {url}")
        finally:
            self._mutex.unlock()
        
        self.queue_updated.emit()

    # --- Shutdown Method --- 
    def shutdown(self):
        """Gracefully shut down all active download threads."""
        self.logger.info(caller="DownloadManager", msg="Shutdown requested. Stopping active downloads...")
        
        # Create copies of keys to avoid modification during iteration
        active_urls = list(self._active.keys())
        
        if not active_urls:
            self.logger.info(caller="DownloadManager", msg="No active downloads to shut down.")
            return

        threads_to_wait_for = []
        self._mutex.lock()
        try:
            for url in active_urls:
                if url in self._active and url in self._threads:
                    worker = self._active[url]
                    thread = self._threads[url]
                    threads_to_wait_for.append(thread)
                    
                    self.logger.info(caller="DownloadManager", msg=f"Signaling cancel and quit for worker/thread: {url}")
                    # Signal worker to cancel its internal process
                    worker.cancel() 
                    # Ask the thread's event loop to exit
                    thread.quit() 
                else:
                    self.logger.warning(caller="DownloadManager", msg=f"Inconsistency during shutdown for URL: {url}. Worker or thread not found.")
        finally:
            self._mutex.unlock()

        # Wait for threads to finish outside the lock
        self.logger.info(caller="DownloadManager", msg=f"Waiting for {len(threads_to_wait_for)} threads to finish...")
        all_finished = True
        for thread in threads_to_wait_for:
            if thread.isRunning(): # Check if it hasn't already finished
                if not thread.wait(5000): # Wait up to 5 seconds per thread
                    self.logger.warning(caller="DownloadManager", msg=f"Thread {thread.objectName() if thread.objectName() else thread} did not finish gracefully within timeout during shutdown.")
                    # Force termination if wait fails
                    # thread.terminate() 
                    # thread.wait() # Wait after terminate
                    all_finished = False
            else:
                self.logger.debug(caller="DownloadManager", msg=f"Thread {thread.objectName() if thread.objectName() else thread} already finished.")
                
        if all_finished:
             self.logger.info(caller="DownloadManager", msg="All active download threads finished gracefully.")
        else:
             self.logger.warning(caller="DownloadManager", msg="Some download threads did not finish gracefully during shutdown.") 

    def _check_ytdlp_update_async(self):
        """
        Check for yt-dlp updates asynchronously without blocking downloads.
        This method ensures updates are checked only once per session and 
        doesn't interfere with download operations.
        """
        if not YTDLP_UPDATER_AVAILABLE:
            return
        
        # Avoid multiple simultaneous update checks
        if self._update_check_in_progress:
            return
        
        # Throttle update checks - only check once per hour
        current_time = time.time()
        if (self._last_update_check_time is not None and 
            current_time - self._last_update_check_time < 3600):  # 1 hour
            return
        
        self._update_check_in_progress = True
        self._last_update_check_time = current_time
        
        class YtDlpUpdateThread(QThread):
            """Background thread for yt-dlp update checking."""
            update_result = pyqtSignal(bool, bool, str, str)  # success, updated, current_version, latest_version
            
            def __init__(self, parent=None):
                super().__init__(parent)
                
            def run(self):
                try:
                    updater = YtDlpUpdater.instance()
                    
                    # Check if update checking is enabled
                    if not updater.should_check_for_update():
                        self.update_result.emit(True, False, "", "No check needed")
                        return
                    
                    # Perform the update check and installation
                    result = updater.check_and_update_async(force_check=False)
                    
                    self.update_result.emit(
                        result.success,
                        result.updated, 
                        result.current_version,
                        result.latest_version
                    )
                    
                except Exception as e:
                    # Log error but don't fail the download process
                    self.update_result.emit(False, False, "", f"Update check failed: {e}")
        
        # Create and start update thread
        update_thread = YtDlpUpdateThread(parent=self)
        update_thread.update_result.connect(self._on_ytdlp_update_result)
        update_thread.finished.connect(update_thread.deleteLater)
        update_thread.start()
    
    def _on_ytdlp_update_result(self, success: bool, updated: bool, current_version: str, latest_version: str):
        """Handle the result of yt-dlp update check."""
        self._update_check_in_progress = False
        
        if not success:
            self.logger.warning("DownloadManager", f"yt-dlp update check failed: {latest_version}")
            return
        
        if updated:
            # Log successful update
            version_display = latest_version or "latest"
            self.logger.info("DownloadManager", f"yt-dlp updated to {version_display}")
            
            # Log update completion for downloads about to start
            if self._queue or self._active:
                self.logger.info("DownloadManager", "yt-dlp update completed, downloads will use updated version")
            
        else:
            # Log that no update was needed (debug level)
            if current_version:
                self.logger.debug("DownloadManager", f"yt-dlp is up to date: {current_version}")
            else:
                self.logger.debug("DownloadManager", "yt-dlp update check completed, no update needed")
                
    def get_ytdlp_update_status(self) -> Dict[str, Any]:
        """
        Get current yt-dlp update status for debugging/UI purposes.
        
        Returns:
            Dict: Status information about yt-dlp updater
        """
        if not YTDLP_UPDATER_AVAILABLE:
            return {
                'available': False,
                'error': 'yt-dlp updater not available'
            }
        
        try:
            updater = YtDlpUpdater.instance()
            status = updater.get_update_status()
            
            return {
                'available': True,
                'check_in_progress': self._update_check_in_progress,
                'last_check_time': self._last_update_check_time,
                'enabled': status.get('enabled', False),
                'auto_update': status.get('auto_update', False),
                'current_version': status.get('current_version', 'unknown'),
                'file_exists': status.get('file_exists', False),
                'path_valid': status.get('path_valid', False),
                'should_check': status.get('should_check', False)
            }
            
        except Exception as e:
            return {
                'available': True,
                'error': f'Failed to get update status: {e}'
            } 