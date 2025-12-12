"""
Download queue component for displaying current downloads.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel,
    QSizePolicy, QHBoxLayout, QSpinBox, QPushButton
)
from qt_base_app.models.logger import Logger
from PyQt6.QtCore import Qt, pyqtSignal, QSize
import os

# --- Fixed Imports ---
from .FlowLayout import FlowLayout
from music_player.models import DownloadManager
from .YoutubeProgress import YoutubeProgress
# Import SettingsManager and relevant keys/types
from qt_base_app.models.settings_manager import SettingsManager, SettingType
from music_player.models.settings_defs import YT_MAX_CONCURRENT_KEY, DEFAULT_YT_MAX_CONCURRENT
# --------------------

class DownloadQueue(QScrollArea):
    """
    A component that displays a queue of YouTube downloads with thumbnails and progress.
    
    Signals:
        navigate_to_file: Emitted when a user clicks on a completed download thumbnail
                          Passes (output_path, filename) for navigation to Browser page
        play_file: Emitted when a user right-clicks on a completed download thumbnail
                   Passes filepath to play the file
    """
    
    navigate_to_file = pyqtSignal(str, str)  # Emits (output_path, filename)
    play_file = pyqtSignal(str)  # Emits filepath to play the file
    
    def __init__(self, download_manager):
        """Initialize the download queue."""
        super().__init__()
        
        # Store reference to download manager
        self.download_manager = download_manager
        # Get SettingsManager instance
        self.settings = SettingsManager.instance()
        
        # Configure the scroll area
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Create container widget and layout
        self.container = QWidget()
        self.container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Create header layout
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 5)
        
        # Queue label
        queue_label = QLabel("Download Queue")
        queue_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(queue_label)
        
        # Concurrent downloads control
        concurrent_layout = QHBoxLayout()
        concurrent_label = QLabel("Max Concurrent:")
        concurrent_layout.addWidget(concurrent_label)
        
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setMinimum(1)
        self.concurrent_spin.setMaximum(5)
        # Load initial value from settings
        initial_max = self.settings.get(YT_MAX_CONCURRENT_KEY, DEFAULT_YT_MAX_CONCURRENT, SettingType.INT)
        self.concurrent_spin.setValue(initial_max)
        # Connect to download manager setter (existing)
        self.concurrent_spin.valueChanged.connect(self.download_manager.set_max_concurrent)
        # Connect to save function (new)
        self.concurrent_spin.valueChanged.connect(self._save_max_concurrent)
        concurrent_layout.addWidget(self.concurrent_spin)
        
        header_layout.addLayout(concurrent_layout)
        
        # Add Clear Completed button
        self.clear_completed_button = QPushButton("Clear Completed")
        self.clear_completed_button.clicked.connect(self.clear_completed_downloads)
        header_layout.addWidget(self.clear_completed_button)
        
        header_layout.addStretch()
        
        # Use FlowLayout for the downloads grid
        self.flow_layout = FlowLayout()
        self.flow_layout.setSpacing(10)  # Add some space between items
        
        # Main layout to contain header and flow layout
        main_layout = QVBoxLayout(self.container)
        main_layout.addLayout(header_layout)
        main_layout.addLayout(self.flow_layout)
        main_layout.addStretch()  # Add stretch at the end to push everything to the top
        
        # Set the container as the widget for the scroll area
        self.setWidget(self.container)
        
        # Connect signals from download manager
        self.download_manager.queue_updated.connect(self.update_queue)
        self.download_manager.download_started.connect(self.on_download_started)
        self.download_manager.download_progress.connect(self.on_download_progress)
        self.download_manager.download_complete.connect(self.on_download_complete)
        self.download_manager.download_error.connect(self.on_download_error)
        
        # Create a dictionary to track progress components
        self.progress_components = {}
        
        # Initial queue update
        self.update_queue()
    
    def _create_cancel_handler(self, url):
        """Create a function that captures the URL parameter correctly."""
        return lambda: self.on_cancel_clicked(url)
    
    def _create_dismiss_handler(self, url):
        """Create a function that captures the URL parameter correctly for dismiss action."""
        return lambda: self.on_dismiss_clicked(url)
    
    def _on_navigate_to_file_requested(self, output_path, filename):
        """
        Handle navigation request from a YoutubeProgress component.
        Forwards the request to any attached slot via the navigate_to_file signal.
        """
        Logger.instance().debug(caller="DownloadQueue", msg=f"[DownloadQueue] Navigation request received for: {output_path}/{filename}")
        self.navigate_to_file.emit(output_path, filename)
    
    def _on_play_file_requested(self, filepath):
        """
        Handle play file request from a YoutubeProgress component.
        Forwards the request to any attached slot via the play_file signal.
        """
        Logger.instance().debug(caller="DownloadQueue", msg=f"[DownloadQueue] Play file request received for: {filepath}")
        self.play_file.emit(filepath)
    
    def update_queue(self):
        """Update the display of the download queue."""
        # Clear existing progress components that are no longer in the queue
        urls_in_queue = set(self.download_manager.get_all_urls())
        urls_to_remove = set(self.progress_components.keys()) - urls_in_queue
        
        for url in urls_to_remove:
            if url in self.progress_components:
                component = self.progress_components.pop(url)
                # Remove from layout and delete
                self.flow_layout.removeWidget(component)
                component.deleteLater()
        
        # Add new items to the queue
        for url in urls_in_queue:
            if url not in self.progress_components:
                # Get download status and metadata
                status = self.download_manager.get_status(url)
                progress = self.download_manager.get_progress(url)
                title = self.download_manager.get_title(url) or "Loading..."
                thumbnail = self.download_manager.get_thumbnail(url)
                
                # Create progress component
                progress_component = YoutubeProgress(url, title)
                
                # Set up component with initial data
                # Order matters: thumbnail first, then status, progress, and title last
                if thumbnail:
                    progress_component.set_thumbnail(thumbnail)
                    
                progress_component.set_status(status)
                progress_component.set_progress(progress)
                
                # Set title last to ensure it's not overridden
                progress_component.set_title(title)
                
                # Connect the cancel signal with explicit URL capture
                progress_component.cancel_requested.connect(
                    self._create_cancel_handler(url)
                )
                
                # Connect the dismiss signal with explicit URL capture
                progress_component.dismiss_requested.connect(
                    self._create_dismiss_handler(url)
                )
                
                # Connect the new navigation signal
                progress_component.navigate_to_file_requested.connect(
                    self._on_navigate_to_file_requested
                )
                
                # Connect the new play file signal
                progress_component.play_file_requested.connect(
                    self._on_play_file_requested
                )
                
                # Add to layout and dictionary
                self.flow_layout.addWidget(progress_component)
                self.progress_components[url] = progress_component
            else:
                # Update existing component with latest data
                component = self.progress_components[url]
                
                # Get latest metadata
                title = self.download_manager.get_title(url)
                thumbnail = self.download_manager.get_thumbnail(url)
                status = self.download_manager.get_status(url)
                progress = self.download_manager.get_progress(url)
                
                # Update component with latest data
                # Order matters: thumbnail first, then status, progress, and title last
                if thumbnail and not component.thumbnail.pixmap():
                    component.set_thumbnail(thumbnail)
                
                if status:
                    component.set_status(status)
                    
                component.set_progress(progress)
                
                # Set title last to ensure it's not overridden
                if title and not title.startswith("Loading:"):
                    component.set_title(title)
    
    def on_download_started(self, url, title, thumbnail):
        """Handle download started signal."""
        if url in self.progress_components:
            component = self.progress_components[url]
            
            # Get current title before any updates
            current_title = component.progress_bar.title_label.text()
            
            # First apply the thumbnail if available
            if thumbnail and not thumbnail.isNull():
                component.set_thumbnail(thumbnail)
            
            # Set status (this will update the status overlay)
            status = self.download_manager.get_status(url) or "Starting"
            component.set_status(status)
            
            # Set progress
            progress = self.download_manager.get_progress(url) or 0
            component.set_progress(progress)
            
            # Skip complex logic and directly set the title when we have a real title
            if title and not (title.startswith("Loading") or title == "Downloading..."):
                # Directly set title in the progress bar, bypassing all logic
                component.progress_bar.set_title(title)
            # Only set placeholder title if we don't already have a real title
            elif current_title and not (current_title.startswith("Loading") or current_title == "Downloading..."):
                # Keep existing title
                pass
            else:
                # Use placeholder
                component.progress_bar.set_title(title or "Downloading...")
    
    def on_download_progress(self, url, progress, status_text):
        """Handle download progress signal."""
        if url in self.progress_components:
            component = self.progress_components[url]
            component.set_progress(progress)
            if status_text:
                component.set_stats(status_text)
    
    def on_download_complete(self, url, output_dir=None, filename=None):
        """Handle download completion signal."""
        # Important transition message
        Logger.instance().debug(caller="DownloadQueue", msg=f"Download complete - URL: {url}")
        
        if url in self.progress_components:
            component = self.progress_components[url]
            component.set_progress(100)
            component.set_status("Complete")
            component.set_stats("Download completed")
            
            # Set the output path and filename for file explorer access
            if output_dir:
                component.set_output_path(output_dir, filename)
                # Verify the file exists - keep this as a warning message
                if filename:
                    filepath = os.path.join(output_dir, filename)
                    if not os.path.exists(filepath):
                        Logger.instance().warning(caller="DownloadQueue", msg=f"WARNING: File does not exist at expected path: {filepath}")
            else:
                Logger.instance().warning(caller="DownloadQueue", msg=f"WARNING: No output directory provided for {url}")
        else:
            Logger.instance().warning(caller="DownloadQueue", msg=f"WARNING: No component found for URL: {url}")
    
    def on_download_error(self, url, error_message):
        """Handle download error signal."""
        # Keep error messages
        Logger.instance().error(caller="DownloadQueue", msg=f"Error for URL: {url} - {error_message}")
        
        if url in self.progress_components:
            component = self.progress_components[url]
            status = self.download_manager.get_status(url)
            component.set_status(status if status else "Error")            
            # component.set_status("Error")
            
            # Truncate very long error messages for UI display
            if len(error_message) > 100:
                display_message = error_message[:97] + "..."
            else:
                display_message = error_message
                
            component.set_stats(display_message)
            
            # Set progress to 0 to visually indicate error state
            component.set_progress(0)
            
            # Apply a visual indicator for error state
            component.highlight_error()
        
        # Force an update of the UI
        self.update_queue()
    
    def on_cancel_clicked(self, url):
        """Handle cancel button click with explicit URL parameter."""
        try:
            # Process the URL to ensure it's valid
            if url and isinstance(url, str):
                self.download_manager.cancel_download(url)
            else:
                Logger.instance().error(caller="DownloadQueue", msg=f"Error: Invalid URL for cancellation: {url}")
        except Exception as e:
            Logger.instance().error(caller="DownloadQueue", msg=f"Error cancelling download: {e}")
    
    def on_dismiss_clicked(self, url):
        """Handle dismiss button click for error items."""
        try:
            # Process the URL to ensure it's valid
            if url and isinstance(url, str):
                self.download_manager.dismiss_error(url)
            else:
                Logger.instance().error(caller="DownloadQueue", msg=f"Error: Invalid URL for dismiss: {url}")
        except Exception as e:
            Logger.instance().error(caller="DownloadQueue", msg=f"Error dismissing download: {e}")
    
    def clear_completed_downloads(self):
        """Clear all completed downloads from the queue."""
        urls_to_remove = []
        
        # Find all completed downloads
        for url, component in self.progress_components.items():
            if component.status == "Complete":
                urls_to_remove.append(url)
        
        # Cancel each download (which removes it from the UI)
        for url in urls_to_remove:
            self.download_manager.cancel_download(url)
    
    def _save_max_concurrent(self, value):
        """Save the max concurrent downloads setting."""
        self.settings.set(YT_MAX_CONCURRENT_KEY, value, SettingType.INT)
        # QSettings typically syncs on destruction or periodically,
        # immediate sync is usually not required unless critical.
        # self.settings.sync()
        Logger.instance().debug(caller="DownloadQueue", msg=f"[DownloadQueue] Max concurrent downloads saved: {value}")
