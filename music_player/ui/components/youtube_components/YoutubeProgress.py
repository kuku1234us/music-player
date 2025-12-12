"""
YouTube progress component for displaying download progress with thumbnails.
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QProgressBar, QPushButton, QFrame, QSizePolicy
)
from qt_base_app.models.logger import Logger
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QFont, QColor, QPalette, QCursor

class TitleProgressBar(QFrame):
    """A custom progress bar that displays text and fills with a background color."""
    
    def __init__(self, parent=None):
        """Initialize the title progress bar."""
        super().__init__(parent)
        
        # Set fixed height
        self.setFixedHeight(20)
        
        # Set frame properties - explicitly use a border
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Plain)
        
        # Create a child frame for the progress fill
        self.progress_fill = QFrame(self)
        self.progress_fill.setGeometry(1, 1, 0, self.height() - 2)  # Initial size with border offset
        
        # Set the progress fill with reversed gradient (darker on left, brighter on right)
        self.progress_fill.setStyleSheet("""
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,  /* Direction: left to right */
                stop:0 #00213A,  /* Start with very dark blue */
                stop:1 #007ACC   /* End with bright blue */
            );
        """)
        
        # Create layout for the text
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 0, 5, 0)
        
        # Create label for title
        self.title_label = QLabel("Loading...")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        # Use smaller font for title
        font = self.title_label.font()
        font.setPointSize(7)
        self.title_label.setFont(font)
        
        # Add to layout
        self.layout.addWidget(self.title_label)
        
        # Ensure text appears on top of the progress fill
        self.title_label.raise_()
        
        # Set the border and background
        self.setStyleSheet("""
            TitleProgressBar {
                border: 1px solid #555555;
                background-color: #1E1E1E;
            }
            
            QLabel {
                background-color: transparent;
                color: white;
            }
        """)
        
        # Initialize progress value
        self.progress_value = 0
    
    def set_title(self, title):
        """Set the title text."""
        if not title:
            return
        
        # Only update the title if we have a valid title or if current title is a loading placeholder
        current_title = self.title_label.text()
        
        # If we have a real title (not a loading placeholder), always use it
        if title and not (title.startswith("Loading") or title == "Downloading..."):
            self.title_label.setText(title)
            return
        
        # Don't replace a real title with a generic Loading placeholder
        if (title.startswith("Loading") or title == "Downloading...") and current_title and not (
                current_title.startswith("Loading") or current_title == "Downloading..."):
            return
        
        # If we have a placeholder and current title is also a placeholder, update it
        if (title.startswith("Loading") or title == "Downloading...") and (
                not current_title or current_title.startswith("Loading") or current_title == "Downloading..."):
            self.title_label.setText(title)
            return
        
        # Fallback case - shouldn't normally reach here
        self.title_label.setText(title)
    
    def set_progress(self, value):
        """Set the progress value (0-100)."""
        self.progress_value = max(0, min(100, value))
        
        # Update the progress fill position and size
        # Fill from left to right instead of right to left
        fill_width = int((self.width() - 2) * (self.progress_value / 100.0))
        self.progress_fill.setGeometry(
            1,                  # Start from left edge + 1px border
            1,                  # 1px from top border
            fill_width,         # Width based on progress
            self.height() - 2   # Height with 1px margin top and bottom
        )
    
    def resizeEvent(self, event):
        """Handle resize events to update the progress fill."""
        super().resizeEvent(event)
        # Update the progress fill when the widget is resized
        self.set_progress(self.progress_value)

class YoutubeProgress(QWidget):
    """
    Component displaying YouTube video download progress with thumbnail.
    
    Signals:
        cancel_requested: When the user clicks the cancel button
        dismiss_requested: When the user dismisses an error
        navigate_to_file_requested: When the user clicks on a completed download thumbnail
        play_file_requested: When the user right-clicks on a completed download thumbnail
    """
    
    cancel_requested = pyqtSignal(str)
    dismiss_requested = pyqtSignal(str)
    navigate_to_file_requested = pyqtSignal(str, str)  # Emits (output_path, filename)
    play_file_requested = pyqtSignal(str)  # Emits full filepath to play
    
    def __init__(self, url, title=None, parent=None):
        """Initialize the YouTube progress component."""
        super().__init__(parent)
        
        # Store URL
        self.url = url
        self.output_path = None
        self.downloaded_filename = None
        
        # Set size policy
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        # Create layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Create thumbnail container with relative positioning for the cancel button
        self.thumbnail_container = QFrame()
        self.thumbnail_container.setFrameShape(QFrame.Shape.NoFrame)
        self.thumbnail_container.setFixedSize(160, 90)  # Half the original size
        
        # Use absolute layout for thumbnail container
        self.thumbnail_container.setLayout(QVBoxLayout())
        self.thumbnail_container.layout().setContentsMargins(0, 0, 0, 0)
        
        # Create thumbnail label
        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(160, 90)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setStyleSheet("background-color: #2A2A2A;")
        self.thumbnail.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))  # Add cursor to indicate clickable
        self.thumbnail_container.layout().addWidget(self.thumbnail)
        
        # Create cancel button as overlay
        self.cancel_button = QPushButton("×")  # Using multiplication sign as X
        self.cancel_button.setFixedSize(20, 20)  # Slightly smaller button
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 0.7);
                color: white;
                border-radius: 10px;
                font-weight: bold;
                font-size: 14px;
                padding: 0px 0px 3px 0px; /* Adjust padding to center the × character */
                text-align: center;
            }
            QPushButton:hover {
                background-color: rgba(255, 0, 0, 0.8);
            }
        """)
        self.cancel_button.clicked.connect(self.on_cancel_clicked)
        
        # Position cancel button at top-right of thumbnail
        self.cancel_button.setParent(self.thumbnail_container)
        self.cancel_button.move(135, 5)  # Adjust position for smaller thumbnail
        
        # Create dismiss button for errors
        self.dismiss_button = QPushButton("Dismiss")
        self.dismiss_button.setFixedHeight(20)
        self.dismiss_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(153, 0, 0, 0.8);
                color: white;
                border-radius: 3px;
                font-weight: bold;
                font-size: 8pt;
                padding: 0px 5px;
            }
            QPushButton:hover {
                background-color: rgba(204, 0, 0, 0.9);
            }
        """)
        self.dismiss_button.clicked.connect(self.on_dismiss_clicked)
        self.dismiss_button.hide()  # Hidden by default
        
        # Create title progress bar
        self.progress_bar = TitleProgressBar()
        self.progress_bar.setFixedWidth(160)  # Match thumbnail width
        
        if title:
            self.progress_bar.set_title(title)
        
        # Create stats overlay for showing download progress details
        self.stats_overlay = QLabel("Waiting...")
        self.stats_overlay.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        self.stats_overlay.setWordWrap(True)
        self.stats_overlay.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.7);
            color: white;
            padding: 3px;
            border-radius: 2px;
            font-size: 8pt;
        """)
        self.stats_overlay.setParent(self.thumbnail_container)
        self.stats_overlay.move(4, 52)  # Adjust position for smaller thumbnail
        self.stats_overlay.setFixedSize(152, 34)  # Adjust size proportionally
        self.stats_overlay.hide()  # Hide initially until we have stats
        
        # Add widgets to layout
        self.layout.addWidget(self.thumbnail_container)
        self.layout.addWidget(self.progress_bar)
        self.layout.addWidget(self.dismiss_button)
        
        # Initialize stats and status
        self.stats = ""
        self.status = "Queued"
    
    def set_thumbnail(self, pixmap):
        """Set the thumbnail image."""
        if isinstance(pixmap, QPixmap):
            # Scale pixmap to FILL the label (expanding if needed)
            scaled_pixmap = pixmap.scaled(
                160, 90,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,  # Changed from KeepAspectRatio
                Qt.TransformationMode.SmoothTransformation
            )
            
            # If the scaled image is larger than the container, center-crop it
            if scaled_pixmap.width() > 160 or scaled_pixmap.height() > 90:
                x = (scaled_pixmap.width() - 160) / 2 if scaled_pixmap.width() > 160 else 0
                y = (scaled_pixmap.height() - 90) / 2 if scaled_pixmap.height() > 90 else 0
                scaled_pixmap = scaled_pixmap.copy(int(x), int(y), 160, 90)
            
            self.thumbnail.setPixmap(scaled_pixmap)
        elif isinstance(pixmap, str) and os.path.isfile(pixmap):
            # Load from file path
            self.set_thumbnail(QPixmap(pixmap))
        else:
            # Reset thumbnail
            self.thumbnail.clear()
    
    def set_progress(self, progress):
        """Set the progress value (0-100)."""
        self.progress_bar.set_progress(progress)
    
    def set_title(self, title):
        """Set the title text."""
        if not title:
            return
        
        # Only update the title if we have a valid title or if current title is a loading placeholder
        current_title = self.progress_bar.title_label.text()
        
        # If we have a real title (not a loading placeholder), always use it
        if title and not (title.startswith("Loading") or title == "Downloading..."):
            self.progress_bar.set_title(title)
            return
        
        # Don't replace a real title with a generic Loading placeholder
        if (title.startswith("Loading") or title == "Downloading...") and current_title and not (
                current_title.startswith("Loading") or current_title == "Downloading..."):
            return
        
        # If we have a placeholder and current title is also a placeholder, update it
        if (title.startswith("Loading") or title == "Downloading...") and (
                not current_title or current_title.startswith("Loading") or current_title == "Downloading..."):
            self.progress_bar.set_title(title)
            return
        
        # Fallback case - shouldn't normally reach here
        self.progress_bar.set_title(title)
    
    def set_status(self, status):
        """Set the status text and update the overlay based on status."""
        self.status = status
        
        # Reset any error/cancel highlighting first
        self.thumbnail_container.setStyleSheet("QFrame { border: none; background-color: #2A2A2A; }") # Reset border
        self.progress_bar.setStyleSheet(""" 
            TitleProgressBar { 
                border: 1px solid #555555; 
                background-color: #1E1E1E; 
            } 
            QLabel { 
                background-color: transparent; 
                color: white; 
            }
        """) # Reset progress bar style
        
        # Show appropriate overlay message based on status
        if status == "Starting":
            self.set_stats("Processing started...")
            self.dismiss_button.hide()
        elif status == "Queued":
            self.set_stats("Waiting in queue...")
            self.dismiss_button.hide()
        elif status == "Complete":
            self.set_stats("Download completed")
            self.dismiss_button.hide()
            # Make cursor a hand to indicate clickable when completed
            self.thumbnail.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        elif status == "Error":
            # Don't override error message if already set
            if not self.stats or not self.stats.startswith("Error"):
                self.set_stats("Error occurred")
            self.highlight_error() # Apply error visual style
            self.dismiss_button.show()
            # Reset cursor to default for error state
            self.thumbnail.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        elif status == "Already Exists":
            # Special handling for already existing files
            self.set_stats("Already Exists")
            self.highlight_already_exists() # Apply special visual style
            self.dismiss_button.show()
            self.thumbnail.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        elif status == "Cancelled": # <-- Add handling for Cancelled
            self.set_stats("Cancelled")
            self.highlight_cancelled() # Apply cancelled visual style
            self.dismiss_button.show() # Allow dismissing cancelled items
            # Reset cursor to default for cancelled state
            self.thumbnail.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        else: # Default case
             self.set_stats(status) # Show other statuses like 'Downloading' if needed
             self.dismiss_button.hide()
             self.thumbnail.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
    
    def highlight_already_exists(self):
        """Apply special styling to highlight already exists state."""
        # Add subtle yellow-brown border to thumbnail
        self.thumbnail_container.setStyleSheet("""
            QFrame { 
                border: 2px solid #8e7102; 
                background-color: #2A2A2A; 
            }
        """)
        
        # Change progress bar to subtle yellow-brown color
        self.progress_bar.setStyleSheet("""
            TitleProgressBar { 
                 border: 1px solid #8e7102; 
                 background-color: #3A3A1A; 
            }
            QLabel { 
                 background-color: transparent; 
                 color: #DDDDDD;
            }
        """)
        
        # Make the already exists message noticeable but subtle
        self.stats_overlay.setStyleSheet("""
            background-color: rgba(142, 113, 2, 0.85);
            color: white;
            padding: 3px;
            border-radius: 2px;
            font-size: 8pt;
            font-weight: bold;
        """)
        
        # Show dismiss button
        self.dismiss_button.show()
    
    def set_stats(self, stats):
        """Set the stats text and show the overlay."""
        self.stats = stats
        
        # Set text and ensure it's visible
        self.stats_overlay.setText(stats)
        self.stats_overlay.show()
    
    def highlight_error(self):
        """Apply special styling to highlight error state."""
        # Add red border to thumbnail to visually indicate error
        self.thumbnail_container.setStyleSheet("""
            QFrame { 
                border: 2px solid #CC0000; 
                background-color: #2A2A2A; 
            }
        """)
        
        # Change progress bar to error color
        self.progress_bar.setStyleSheet("""
            TitleProgressBar { 
                 border: 1px solid #CC0000; 
                 background-color: #3A1A1A; 
            }
            QLabel { 
                 background-color: transparent; 
                 color: #AAAAAA; /* Dim text slightly */
            }
        """)
        
        # Make the error message more noticeable
        self.stats_overlay.setStyleSheet("""
            background-color: rgba(153, 0, 0, 0.85);
            color: white;
            padding: 3px;
            border-radius: 2px;
            font-size: 8pt;
            font-weight: bold;
        """)
        
        # Show dismiss button
        self.dismiss_button.show()
    
    def highlight_cancelled(self):
        """Apply special styling to highlight cancelled state."""
        # Add grey border to thumbnail 
        self.thumbnail_container.setStyleSheet("""
            QFrame { 
                border: 2px solid #888888; 
                background-color: #2A2A2A; 
            }
        """)
        
        # Change progress bar to greyed-out color
        self.progress_bar.setStyleSheet("""
            TitleProgressBar { 
                 border: 1px solid #888888; 
                 background-color: #333333; 
            }
            QLabel { 
                 background-color: transparent; 
                 color: #999999; /* Dim text */
            }
        """)
        
        # Make the cancelled message noticeable but distinct from error
        self.stats_overlay.setStyleSheet("""
            background-color: rgba(80, 80, 80, 0.85);
            color: #DDDDDD;
            padding: 3px;
            border-radius: 2px;
            font-size: 8pt;
            font-weight: normal; /* Less emphasis than error */
        """)
        
        # Show dismiss button
        self.dismiss_button.show()
    
    def on_cancel_clicked(self):
        """Handle cancel button click."""
        self.cancel_requested.emit(self.url)
    
    def on_dismiss_clicked(self):
        """Handle dismiss button click."""
        self.dismiss_requested.emit(self.url)
    
    def sizeHint(self):
        """Return the preferred size for the widget."""
        return QSize(160, 110)  # 160x90 thumbnail + 20 for progress bar (was 120)

    def set_url(self, url):
        """Set the YouTube URL."""
        if not url:
            self.clear()
            return
        
        self.url = url
        # We'll let the DownloadManager handle fetching the thumbnail
    
    def clear(self):
        """Clear the thumbnail and progress."""
        self.thumbnail.clear()
        self.progress_bar.set_progress(0)
        self.stats = ""
        self.stats_overlay.hide()
        self.status = "Queued"
    
    def resizeEvent(self, event):
        """Handle resize events to update progress indicator position."""
        super().resizeEvent(event)
        # Update the progress indicator position when resized
        self.progress_bar.resizeEvent(event)

    def set_url(self, url):
        """Set the YouTube URL."""
        if not url:
            self.clear()
            return
        
        self.url = url
        # We'll let the DownloadManager handle fetching the thumbnail
    
    def clear(self):
        """Clear the thumbnail and progress."""
        self.thumbnail.clear()
        self.progress_bar.set_progress(0)
        self.stats = ""
        self.stats_overlay.hide()
        self.status = "Queued"
    
    def resizeEvent(self, event):
        """Handle resize events to scale the thumbnail."""
        super().resizeEvent(event)
        if hasattr(self, 'base_pixmap') and self.base_pixmap is not None:
            # Re-scale the pixmap when the widget is resized
            scaled_pixmap = self.base_pixmap.scaled(
                self.thumbnail.width(),
                self.thumbnail.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.set_thumbnail(scaled_pixmap)

    def set_output_path(self, path, filename=None):
        """Set the output path for the downloaded file."""
        self.output_path = path
        self.downloaded_filename = filename
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release event to navigate to the downloaded file or play it."""
        # Only proceed if the download is complete and we have an output path
        if self.status == "Complete" and self.output_path and self.thumbnail.underMouse():
            if event.button() == Qt.MouseButton.LeftButton:
                # Left click - navigate to the file in browser
                Logger.instance().debug(caller="YoutubeProgress", msg=f"Requesting navigation to file - path: {self.output_path}, filename: {self.downloaded_filename}")
                self.navigate_to_file_requested.emit(self.output_path, self.downloaded_filename or "")
            elif event.button() == Qt.MouseButton.RightButton:
                # Right click - play the file
                if self.downloaded_filename:
                    filepath = os.path.join(self.output_path, self.downloaded_filename)
                    if os.path.exists(filepath):
                        Logger.instance().debug(caller="YoutubeProgress", msg=f"Requesting to play file: {filepath}")
                        self.play_file_requested.emit(filepath)
                    else:
                        Logger.instance().debug(caller="YoutubeProgress", msg=f"Cannot play file - file does not exist: {filepath}")
        elif self.status != "Complete" and self.thumbnail.underMouse():
            Logger.instance().debug(caller="YoutubeProgress", msg=f"Cannot handle click - download not complete. Status: {self.status}")
        elif not self.output_path and self.thumbnail.underMouse():
            Logger.instance().debug(caller="YoutubeProgress", msg=f"Cannot handle click - no output path set for: {self.url}")
        
        super().mouseReleaseEvent(event)
    
    def _open_file_location(self):
        """Open Windows Explorer to the downloaded file if completed."""
        if self.status == "Complete" and self.output_path:
            try:
                # Log the full path information for debugging
                Logger.instance().debug(caller="YoutubeProgress", msg=f"Opening file location - URL: {self.url}")
                Logger.instance().debug(caller="YoutubeProgress", msg=f"Output path: {self.output_path}")
                Logger.instance().debug(caller="YoutubeProgress", msg=f"Filename: {self.downloaded_filename}")
                
                if os.path.isdir(self.output_path):
                    # If we have a specific filename, select it in Explorer
                    if self.downloaded_filename and os.path.exists(os.path.join(self.output_path, self.downloaded_filename)):
                        # Normalize the path to ensure all slashes are consistent
                        filepath = os.path.normpath(os.path.join(self.output_path, self.downloaded_filename))
                        Logger.instance().debug(caller="YoutubeProgress", msg=f"Opening file with explorer: {filepath}")
                        
                        # Use explorer.exe with /select to highlight the file 
                        # Always use double quotes around the filepath to handle spaces and special characters
                        cmd = f'explorer.exe /select,"{filepath}"'
                        
                        # Use os.system - simpler and more reliable for Explorer
                        os.system(cmd)
                    else:
                        # Just open the directory if we don't have a filename
                        Logger.instance().debug(caller="YoutubeProgress", msg=f"Opening directory: {self.output_path}")
                        dir_path = os.path.normpath(self.output_path)
                        os.startfile(dir_path)
                    return True
                else:
                    Logger.instance().error(caller="YoutubeProgress", msg=f"Error: Output path is not a directory: {self.output_path}")
            except Exception as e:
                Logger.instance().error(caller="YoutubeProgress", msg=f"Error opening file location: {str(e)}")
        elif self.status != "Complete":
            Logger.instance().debug(caller="YoutubeProgress", msg=f"Cannot open file location - download not complete. Status: {self.status}")
        elif not self.output_path:
            Logger.instance().debug(caller="YoutubeProgress", msg=f"Cannot open file location - no output path set for: {self.url}")
        return False 