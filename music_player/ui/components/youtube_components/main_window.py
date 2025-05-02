"""
Main window for the YouTube Master application.
"""
import os
import sys
import time

from youtubemaster.utils.logger import Logger

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit, QComboBox,
    QFileDialog, QProgressBar, QStatusBar, QMessageBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QMetaObject, Q_ARG
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon

from youtubemaster.utils.config import config
from youtubemaster.ui.VideoInput import VideoInput
from youtubemaster.ui.YoutubeProgress import YoutubeProgress
from youtubemaster.models.DownloadManager import DownloadManager
from youtubemaster.ui.DownloadQueue import DownloadQueue

class ThemeManager:
    """Manages the application theme."""
    
    @staticmethod
    def apply_dark_theme(app):
        """Apply dark theme to the application."""
        # Get colors from config
        background = config.get('ui.theme.dark.background', '#1E1E1E')
        text_color = config.get('ui.theme.dark.text', '#FFFFFF')
        accent = config.get('ui.theme.dark.accent', '#007ACC')
        
        button_bg = config.get('ui.theme.dark.button.background', '#3C3C3C')
        button_text = config.get('ui.theme.dark.button.text', '#FFFFFF')
        button_hover = config.get('ui.theme.dark.button.hover', '#505050')
        
        input_bg = config.get('ui.theme.dark.input.background', '#3C3C3C')
        input_text = config.get('ui.theme.dark.input.text', '#FFFFFF')
        input_border = config.get('ui.theme.dark.input.border', '#555555')
        
        scrollbar_bg = config.get('ui.theme.dark.scrollbar.background', '#1E1E1E')
        scrollbar_handle = config.get('ui.theme.dark.scrollbar.handle', '#3C3C3C')
        
        # Create palette
        palette = QPalette()
        
        # Set colors
        palette.setColor(QPalette.ColorRole.Window, QColor(background))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(text_color))
        palette.setColor(QPalette.ColorRole.Base, QColor(input_bg))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(background))
        palette.setColor(QPalette.ColorRole.Text, QColor(input_text))
        palette.setColor(QPalette.ColorRole.Button, QColor(button_bg))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(button_text))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(accent))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(text_color))
        
        # Apply palette
        app.setPalette(palette)
        
        # Set stylesheet for more detailed control
        app.setStyleSheet(f"""
            QMainWindow {{
                background-color: {background};
                color: {text_color};
            }}
            
            QWidget {{
                background-color: {background};
                color: {text_color};
            }}
            
            QPushButton {{
                background-color: {button_bg};
                color: {button_text};
                border: 1px solid {input_border};
                padding: 5px;
                border-radius: {config.get('ui.theme.dark.border_radius.button', '5px')};
            }}
            
            QPushButton:hover {{
                background-color: {button_hover};
            }}
            
            QPushButton:pressed {{
                background-color: {accent};
            }}
            
            QPushButton:disabled {{
                background-color: {config.get('ui.theme.dark.button.disabled.background', '#2A2A2A')};
                color: {config.get('ui.theme.dark.button.disabled.text', '#808080')};
            }}
            
            QLineEdit, QTextEdit, QComboBox {{
                background-color: {input_bg};
                color: {input_text};
                border: 1px solid {input_border};
                padding: 3px;
                border-radius: {config.get('ui.theme.dark.border_radius.input', '5px')};
            }}
            
            QProgressBar {{
                border: 1px solid {input_border};
                border-radius: 5px;
                text-align: center;
            }}
            
            QProgressBar::chunk {{
                background-color: {accent};
            }}
            
            QScrollBar:vertical {{
                background-color: {scrollbar_bg};
                width: 14px;
                margin: 14px 0px 14px 0px;
            }}
            
            QScrollBar::handle:vertical {{
                background-color: {scrollbar_handle};
                min-height: 20px;
                border-radius: 5px;
                margin: 2px;
            }}
            
            QScrollBar:horizontal {{
                background-color: {scrollbar_bg};
                height: 14px;
                margin: 0px 14px 0px 14px;
            }}
            
            QScrollBar::handle:horizontal {{
                background-color: {scrollbar_handle};
                min-width: 20px;
                border-radius: 5px;
                margin: 2px;
            }}
        """)

class DownloadThread(QThread):
    """Worker thread for downloading videos."""
    
    # Signals for progress updates
    progress_signal = pyqtSignal(str)
    percentage_signal = pyqtSignal(float)  # New signal for percentage updates
    finished_signal = pyqtSignal(bool, str)
    alert_signal = pyqtSignal(str)  # New signal for the alert
    
    def __init__(self, url, format_id, output_dir):
        """Initialize the download thread."""
        super().__init__()
        self.url = url
        self.format_id = format_id
        self.output_dir = output_dir
        self.cancelled = False
        
        # Initialize and set up the logger
        try:
            self.logger = Logger()
            # Import config (which should be already configured)
            from youtubemaster.utils.config import config
            # Set up the logger with configuration
            self.logger.setup_logger(config)
        except Exception as e:
            print(f"Could not initialize logger: {e}")
            self.logger = None  # Fallback
    
    def run(self):
        """Run the download process."""
        try:
            # Emit signal to show alert from main thread
            self.alert_signal.emit(f"main_window DownloadThread invoked for URL: {self.url}")
            
            # Add a console log as well for additional verification
            print("ALERT: main_window DownloadThread invoked for URL:", self.url)
            
            from yt_dlp import YoutubeDL
            from yt_dlp.utils import DownloadError
            import time
            import os
            import glob
            
            if self.logger:
                self.logger.info(f"Starting download for: {self.url}")
            
            self.progress_signal.emit("Extracting info for: " + self.url)
            
            # Add debug information
            self.progress_signal.emit(f"Python version: {sys.version}")
            self.progress_signal.emit(f"Using format: {self.format_id}")
            self.progress_signal.emit(f"Output directory: {self.output_dir}")
            
            # Keep track of files before download
            files_before = set(os.listdir(self.output_dir))
            
            # Modify the progress hook to capture filenames
            def progress_hook(d):
                if self.cancelled:
                    raise Exception("Download cancelled by user")
                
                if d['status'] == 'downloading':
                    try:
                        # Use the raw progress data available in the dictionary
                        # Instead of trying to parse the formatted string with ANSI codes
                        percentage = None
                        
                        # Try to calculate percentage directly from bytes
                        downloaded_bytes = d.get('downloaded_bytes', 0)
                        total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                        
                        if total_bytes > 0:
                            percentage = (downloaded_bytes / total_bytes) * 100
                            self.percentage_signal.emit(percentage)
                        
                        # Format a clean progress message for the log
                        percent_str = d.get('_percent_str', '0%')
                        speed = d.get('_speed_str', 'N/A')
                        eta = d.get('_eta_str', 'N/A')
                        
                        # Remove ANSI color codes for clean display
                        # ANSI codes follow pattern: ESC[ ... m
                        import re
                        clean_percent = re.sub(r'\x1b\[[0-9;]*m', '', percent_str)
                        clean_speed = re.sub(r'\x1b\[[0-9;]*m', '', speed)
                        clean_eta = re.sub(r'\x1b\[[0-9;]*m', '', eta)
                        
                        # Create a clean, easily parsed progress message
                        progress_msg = f"Downloading: {clean_percent} at {clean_speed}, ETA: {clean_eta}"
                        self.progress_signal.emit(progress_msg)
                        
                    except Exception as e:
                        # If there's any error in progress reporting, log it but don't fail
                        if self.logger:
                            self.logger.warning(f"Progress reporting error: {str(e)}")
                
                elif d['status'] == 'finished':
                    filename = d.get('filename', '')
                    if filename and os.path.exists(filename):
                        self.progress_signal.emit(f"Finished downloading {filename}")
            
            # Get format options
            format_options = self.format_id if isinstance(self.format_id, dict) else {"format": self.format_id}
            
            # Configure yt-dlp options
            ydl_opts = {
                'format': format_options.get('format'),
                'outtmpl': os.path.join(self.output_dir, '%(title)s.%(ext)s'),
                'progress_hooks': [progress_hook],
                'quiet': False,
                'no_warnings': False,
                'no_color': True,
                'no_mtime': True,  # Don't use the media timestamp
                # Add more robust error handling
                'ignoreerrors': False,  # Don't ignore errors...
                'abort_on_unavailable_fragment': False,  # ...but don't abort on unavailable fragments
                'skip_unavailable_fragments': True,  # Skip unavailable fragments
                'retries': 10,  # Increase retry attempts
                'fragment_retries': 10,  # Retry fragments up to 10 times
                'file_access_retries': 5,  # Retry file access operations
            }
            
            # Add extractor-specific arguments for advanced YouTube handling
            # This is important to fix the PhantomJS warning and improve format extraction
            ydl_opts['extractor_args'] = format_options.get('extractor_args', {})
            
            # Add format_sort only if it exists in format_options
            if 'format_sort' in format_options:
                ydl_opts['format_sort'] = format_options['format_sort']
            
            # If merge_output_format is set, add it to ydl_opts
            if 'merge_output_format' in format_options:
                ydl_opts['merge_output_format'] = format_options['merge_output_format']
            
            # Add subtitle options if present in format_options
            if 'writesubtitles' in format_options:
                ydl_opts['writesubtitles'] = format_options['writesubtitles']
            
            if 'writeautomaticsub' in format_options:
                ydl_opts['writeautomaticsub'] = format_options['writeautomaticsub']
            
            if 'subtitleslangs' in format_options:
                ydl_opts['subtitleslangs'] = format_options['subtitleslangs']
            
            if 'subtitlesformat' in format_options:
                ydl_opts['subtitlesformat'] = format_options['subtitlesformat']
            
            if 'embedsubtitles' in format_options:
                ydl_opts['embedsubtitles'] = format_options['embedsubtitles']
            
            if 'postprocessors' in format_options:
                ydl_opts['postprocessors'] = format_options['postprocessors']
            
            # First extract video info
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                self.progress_signal.emit(f"Found video: {info.get('title', 'Unknown title')}")
                duration_seconds = info.get('duration')
                if duration_seconds:
                    minutes = duration_seconds // 60
                    seconds = duration_seconds % 60
                    self.progress_signal.emit(f"Duration: {minutes}:{seconds:02d}")
                
                # Start actual download
                self.progress_signal.emit("Starting download...")
                ydl.download([self.url])
            
            # Find new files after download
            files_after = set(os.listdir(self.output_dir))
            new_files = files_after - files_before
            
            # Update modification time of the final files
            current_time = time.time()
            for filename in new_files:
                filepath = os.path.join(self.output_dir, filename)
                if os.path.isfile(filepath):
                    try:
                        # Set both access time and modification time to current time
                        os.utime(filepath, (current_time, current_time))
                        self.progress_signal.emit(f"Updated timestamp for {filename}")
                    except Exception as e:
                        self.progress_signal.emit(f"Failed to update timestamp: {str(e)}")
            
            self.finished_signal.emit(True, "Download completed successfully!")
            
        except DownloadError as e:
            self.logger.error(f"Download error: {str(e)}")
            self.finished_signal.emit(False, f"Download failed: {str(e)}")
        except Exception as e:
            error_msg = str(e)
            if self.logger:
                self.logger.error(f"Error during download: {error_msg}")
            self.finished_signal.emit(False, f"Error: {error_msg}")

    def cancel_download(self):
        self.cancelled = True

class AnalyzeThread(QThread):
    """Worker thread for analyzing video formats."""
    
    # Signals for updates
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)
    
    def __init__(self, url):
        """Initialize the analyze thread."""
        super().__init__()
        self.url = url
        # Initialize logger
        try:
            self.logger = Logger()
            from youtubemaster.utils.config import config
            self.logger.setup_logger(config)
        except Exception as e:
            print(f"Could not initialize logger: {e}")
            self.logger = None
    
    def run(self):
        """Run the analysis process."""
        try:
            from yt_dlp import YoutubeDL
            from yt_dlp.utils import DownloadError
            import io
            from contextlib import redirect_stdout
            
            if self.logger:
                self.logger.info(f"Analyzing formats for: {self.url}")
            
            self.progress_signal.emit(f"Analyzing URL: {self.url}")
            
            # Configure yt-dlp options for listing formats
            ydl_opts = {
                'listformats': True,
                'quiet': False,
                'no_warnings': False,
                'no_color': True
            }
            
            # Capture stdout to get the format listing
            captured_output = io.StringIO()
            
            with redirect_stdout(captured_output):
                # Run yt-dlp to get format info
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(self.url, download=False)
            
            # Get the captured output and send it to the UI
            output = captured_output.getvalue()
            
            # Split the output by lines and emit each line to show progress
            for line in output.split('\n'):
                if line.strip():  # Only emit non-empty lines
                    self.progress_signal.emit(line)
            
            self.finished_signal.emit(True, "Analysis completed")
            
        except DownloadError as e:
            error_msg = str(e)
            if self.logger:
                self.logger.error(f"Analysis error: {error_msg}")
            self.progress_signal.emit(f"Error: {error_msg}")
            self.finished_signal.emit(False, f"Analysis failed: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            if self.logger:
                self.logger.error(f"Error during analysis: {error_msg}")
            self.progress_signal.emit(f"Error: {error_msg}")
            self.finished_signal.emit(False, f"Error: {error_msg}")

class MainWindow(QMainWindow):
    """Main window of the application."""
    
    def __init__(self):
        """Initialize the main window."""
        super().__init__()
        
        # Initialize the download manager
        self.download_manager = DownloadManager()
        
        # Set window properties
        self.setWindowTitle("YouTube Master")
        self.setMinimumSize(800, 600)
        
        # Set font
        font_family = config.get('ui.font.family', 'Calibri')
        font_size = config.get('ui.font.size', 10)
        font = QFont(font_family, font_size)
        self.setFont(font)
        
        # Create central widget and layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)
        
        # Create input section
        self.create_input_section()
        
        # Create output section
        self.create_output_section()
        
        # Create status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")
        
        # Initialize download thread as None
        self.download_thread = None
    
    def create_input_section(self):
        """Create the input section of the UI."""
        # Create VideoInput component
        self.video_input = VideoInput()
        # Connect the add_clicked signal to the on_add_clicked method
        self.video_input.add_clicked.connect(self.on_add_clicked)
        # Connect the enter_pressed signal to the on_add_clicked method
        self.video_input.enter_pressed.connect(self.on_add_clicked)
        self.main_layout.addWidget(self.video_input)
        
        # Output directory section
        output_layout = QHBoxLayout()
        
        output_label = QLabel("Output Directory:")
        output_layout.addWidget(output_label)
        
        self.output_dir_input = QLineEdit()
        self.output_dir_input.setText(config.output_directory)
        output_layout.addWidget(self.output_dir_input)
        
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.on_browse_clicked)
        output_layout.addWidget(browse_button)
        
        self.main_layout.addLayout(output_layout)
    
    def create_output_section(self):
        """Create the output section of the UI."""
        # Create download queue with expanding size policy
        self.download_queue = DownloadQueue(self.download_manager)
        self.download_queue.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.main_layout.addWidget(self.download_queue)
        
        # Log output area with fixed height
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.log_output.setPlaceholderText("Logs will appear here...")
        self.log_output.setFixedHeight(80)  # Set fixed height (smaller than before)
        self.log_output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)  # Fixed height policy
        self.main_layout.addWidget(self.log_output)
        
        # Connect download manager's log_message signal to update_log
        self.download_manager.log_message.connect(self.update_log)
    
    def on_analyze_clicked(self):
        """Handle analyze button click."""
        url = self.video_input.get_url()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a valid URL.")
            return
            
        self.log_output.clear()
        self.statusBar.showMessage("Analyzing video...")
        
        # Show progress bar in indeterminate mode
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.show()
        
        # Disable analyze button during analysis
        self.download_button.setEnabled(False)
        
        # Start analysis thread
        self.analyze_thread = AnalyzeThread(url)
        self.analyze_thread.progress_signal.connect(self.update_progress)
        self.analyze_thread.finished_signal.connect(self.analysis_finished)
        self.analyze_thread.start()
    
    def on_browse_clicked(self):
        """Handle browse button click."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", 
            self.output_dir_input.text()
        )
        
        if directory:
            self.output_dir_input.setText(directory)
            config.output_directory = directory
    
    def on_add_clicked(self):
        """Handle add button click."""
        url = self.video_input.get_url()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a valid URL.")
            return
        
        format_id = self.video_input.get_format_options()
        output_dir = self.output_dir_input.text()
        
        if not os.path.isdir(output_dir):
            QMessageBox.warning(self, "Error", "Please select a valid output directory.")
            return
        
        # Add to download queue
        added = self.download_manager.add_download(url, format_options=format_id, output_dir=output_dir)
        
        if added:
            # Clear URL field for next entry
            self.video_input.set_url("")
            self.statusBar.showMessage(f"Added to download queue: {url}")
        else:
            self.statusBar.showMessage("URL already in queue")
    
    def update_progress(self, message):
        """Update the progress in the log (used for analyze thread)."""
        self.log_output.append(message)
        
        # Auto-scroll to bottom
        cursor = self.log_output.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.log_output.setTextCursor(cursor)
    
    def download_finished(self, success, message):
        """Handle download completion."""
        self.progress_bar.hide()
        self.cancel_button.hide()
        
        # Clear the stats overlay
        self.youtube_progress.set_stats("")
        
        # Re-enable UI elements
        self.video_input.setEnabled(True)
        self.output_dir_input.setEnabled(True)
        self.download_button.setEnabled(True)
        
        if success:
            self.statusBar.showMessage("Download completed")
            self.log_output.append(message)
        else:
            self.statusBar.showMessage("Download failed")
            self.log_output.append(message)
            QMessageBox.warning(self, "Download Failed", message)
    
    def on_cancel_clicked(self):
        """Handle cancel button click."""
        if self.download_thread and self.download_thread.isRunning():
            # Terminate the thread
            self.download_thread.terminate()
            self.download_thread.wait()
            
            # Update UI
            self.progress_bar.hide()
            self.cancel_button.hide()
            self.statusBar.showMessage("Download cancelled")
            self.log_output.append("Download cancelled by user")
            
            # Re-enable UI elements
            self.video_input.setEnabled(True)
            self.output_dir_input.setEnabled(True)
            self.download_button.setEnabled(True)
    
    def update_progress_bar(self, percentage):
        """Update the progress bar with actual download percentage"""
        self.progress_bar.setValue(int(percentage))
        self.youtube_progress.set_progress(percentage)
    
    def analysis_finished(self, success, message):
        """Handle analysis completion."""
        self.progress_bar.hide()
        
        # Re-enable analyze button
        self.download_button.setEnabled(True)
        
        if success:
            self.statusBar.showMessage("Analysis completed")
        else:
            self.statusBar.showMessage("Analysis failed")
            QMessageBox.warning(self, "Analysis Failed", message)
    
    def update_log(self, message):
        """Update the log with a message."""
        self.log_output.append(message)
        
        # Auto-scroll to bottom
        cursor = self.log_output.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.log_output.setTextCursor(cursor)
    
    def auto_add_download(self, url, format_type="video"):
        """
        Automatically add a URL to the download queue.
        Used when the application is launched with a URL argument.
        
        Args:
            url (str): The video URL to download
            format_type (str): The format type ("video" or "audio")
        """
        if not url:
            return False
        
        # Handle protocol URLs from Chrome extension
        if url.startswith('youtubemaster://'):
            # Extract the actual YouTube URL from the protocol URL
            protocol_path = url.replace('youtubemaster://', '')
            
            # Check if it's the format with format type
            if '/' in protocol_path and protocol_path.split('/', 1)[0] in ['video', 'audio']:
                _, protocol_url = protocol_path.split('/', 1)
                url = protocol_url  # Use the clean YouTube URL
            else:
                # Legacy format - just the YouTube URL after the protocol
                url = protocol_path
            
            self.log_output.append(f"Processed protocol URL: {url}")
        
        # Set the URL in the input field (this will show the proper title in UI)
        self.video_input.set_url(url)
        
        # First set the appropriate format in the UI - this ensures buttons are in correct state
        if format_type == "audio":
            # Set format for audio only
            self.video_input.set_format_audio_only()
        else:  # default to video
            # Set format for 720p video (default)
            self.video_input.set_format_video_720p()
        
        # Get the format options AFTER setting the format in the UI
        format_options = self.video_input.get_format_options()
        
        output_dir = self.output_dir_input.text()
        
        # Validate output directory
        if not os.path.isdir(output_dir):
            self.log_output.append(f"Error: Invalid output directory '{output_dir}'")
            return False
        
        # Add to download queue
        added = self.download_manager.add_download(
            url, 
            format_options=format_options, 
            output_dir=output_dir
        )
        
        if added:
            # Clear URL field for next entry
            self.video_input.set_url("")
            self.statusBar.showMessage(f"Added to download queue: {url}")
            self.log_output.append(f"Auto-added URL to download queue: {url} ({format_type} format)")
            return True
        else:
            self.statusBar.showMessage("URL already in queue")
            self.log_output.append(f"URL already in queue: {url}")
            return False

    # Add new method to show alert
    def show_thread_alert(self, message):
        """Show an alert message box."""
        QMessageBox.information(self, "Thread Alert", message)
        print(f"Alert shown: {message}")
        
    # This method should be called when creating a DownloadThread
    def create_download_thread(self, url, format_id, output_dir):
        """Create and configure a download thread."""
        self.download_thread = DownloadThread(url, format_id, output_dir)
        
        # Connect signals
        self.download_thread.progress_signal.connect(self.update_progress)
        self.download_thread.percentage_signal.connect(self.update_progress_bar)
        self.download_thread.finished_signal.connect(self.download_finished)
        self.download_thread.alert_signal.connect(self.show_thread_alert)
        
        return self.download_thread 