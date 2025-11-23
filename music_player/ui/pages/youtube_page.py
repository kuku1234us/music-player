# ./music_player/ui/pages/youtube_page.py

"""
Page for downloading YouTube videos and audio.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog
from PyQt6.QtCore import pyqtSlot, pyqtSignal
from PyQt6.QtGui import QPixmap # Import QPixmap for signals
import os # For default path
from pathlib import Path # For default path

from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.models.settings_manager import SettingsManager, SettingType
# Import the download dir key and default
from music_player.models.settings_defs import YT_DOWNLOAD_DIR_KEY, DEFAULT_YT_DOWNLOAD_DIR
# Import Logger
from qt_base_app.models.logger import Logger

# --- Import Models and Components ---
from music_player.models import DownloadManager
from music_player.models.Yt_DlpModel import YtDlpModel  # Import YtDlpModel for presets
from music_player.ui.components.youtube_components.VideoInput import VideoInput 
from music_player.ui.components.youtube_components.DownloadQueue import DownloadQueue

# --- Remove local key def ---
# YT_DOWNLOAD_DIR_KEY = 'youtube_downloader/download_dir' # Moved to settings_defs
# ---------------------------

class YoutubePage(QWidget):
    """
    Page widget for the YouTube Downloader feature.
    
    Signals:
        navigate_to_file: Emitted when a user clicks on a completed download thumbnail
                          Passes (output_path, filename) for navigation to Browser page
        play_file: Emitted when a user right-clicks on a completed download thumbnail
                   Passes filepath to play the file
    """
    # Add signals
    navigate_to_file = pyqtSignal(str, str)  # Emits (output_path, filename)
    play_file = pyqtSignal(str)  # Emits filepath to play the file
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("youtubePage")
        self.setProperty('page_id', 'youtube_downloader')
        self.theme = ThemeManager.instance()
        self.settings = SettingsManager.instance()
        # Get logger instance
        self.logger = Logger.instance()
        self.download_manager = DownloadManager(parent=self)
        self._setup_ui()
        self._connect_signals()
        # Use logger
        # self.logger.info(self.__class__.__name__, "Initialized.")

    def _setup_ui(self):
        """Set up the user interface layout and widgets."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(10)

        # --- Video Input Component --- 
        self.video_input = VideoInput(self)
        self.main_layout.addWidget(self.video_input)
        # -----------------------------

        # --- REMOVED Output Directory Row --- 
        # The directory is now set in Preferences
        # ----------------------------------

        # --- Download Queue Component ---
        self.download_queue = DownloadQueue(self.download_manager)
        self.main_layout.addWidget(self.download_queue)
        # ------------------------------

        # REMOVED Load initial output directory call

        # Use logger
        # self.logger.info(self.__class__.__name__, "UI setup complete.") 

    def _connect_signals(self):
        """Connect signals and slots for the page."""
        # --- UI component signals to YoutubePage slots ---
        # Connect input signals to the method that adds to DownloadManager
        self.video_input.add_clicked.connect(self._on_add_download_clicked)
        self.video_input.enter_pressed.connect(self._on_add_download_clicked)
        
        # --- DownloadManager signals --- 
        # REMOVE connections to YoutubePage slots.
        # DownloadQueue connects directly to DownloadManager internally.
        # self.download_manager.download_started.connect(self._on_download_started)
        # self.download_manager.download_progress.connect(self._on_download_progress)
        # self.download_manager.download_complete.connect(self._on_download_complete)
        # self.download_manager.download_error.connect(self._on_download_error)
        # self.download_manager.queue_updated.connect(self._on_queue_updated)
        
        # Connect the navigation signal from DownloadQueue to our own signal
        self.download_queue.navigate_to_file.connect(self.navigate_to_file)
        # self.logger.info(self.__class__.__name__, "Connected download_queue.navigate_to_file signal")
        
        # Connect the play file signal from DownloadQueue to our own signal
        self.download_queue.play_file.connect(self.play_file)
        # self.logger.info(self.__class__.__name__, "Connected download_queue.play_file signal")

    @pyqtSlot()
    def _on_add_download_clicked(self):
        """Handle the add download action."""
        url = self.video_input.get_url()
        if not url:
            # Use logger
            self.logger.warning(self.__class__.__name__, "Add download clicked, but no URL entered.")
            return
            
        format_options = self.video_input.get_format_options()
        # Get output directory from settings instead of QLineEdit
        output_dir = self.settings.get(YT_DOWNLOAD_DIR_KEY, DEFAULT_YT_DOWNLOAD_DIR, SettingType.PATH)
        output_dir_str = str(output_dir) # Ensure it's a string for os.path.isdir
        
        # Validate the directory obtained from settings
        if not output_dir_str or not os.path.isdir(output_dir_str):
            # Use logger
            self.logger.error(self.__class__.__name__, f"Download directory '{output_dir_str}' from settings is invalid or does not exist.")
            # Optionally inform the user to set it in Preferences
            # QMessageBox.warning(self, "Invalid Directory", "Download directory not set or invalid. Please set it in Preferences.")
            return # Prevent adding download if dir is invalid
            
        # Use logger
        self.logger.info(self.__class__.__name__, f"Adding download: URL={url}, Dir={output_dir_str}, Options={format_options}")
        self.download_manager.add_download(url, format_options, output_dir_str)
        
        # Optionally clear URL input after adding
        self.video_input.url_input.clear()

    def auto_add_download(self, url: str, format_type: str):
        """
        Adds a download initiated via the protocol handler.
        
        Args:
            url (str): URL to download from
            format_type (str): Type of media to download ('audio', 'video', or 'best')
        """
        # Use logger
        self.logger.info(self.__class__.__name__, f"Auto adding download: URL={url}, Type={format_type}")
        
        # 1. Update the VideoInput field visually
        if hasattr(self.video_input, 'set_url'):
            self.video_input.set_url(url)
        else:
             # Use logger for warning
             self.logger.warning(self.__class__.__name__, "VideoInput does not have set_url method. Cannot update UI field.")
             # Fallback: Try setting the text directly if possible (might need access to url_input)
             if hasattr(self.video_input, 'url_input'):
                  self.video_input.url_input.setText(url)
             else:
                  # Use logger for warning
                  self.logger.warning(self.__class__.__name__, "Cannot access VideoInput's QLineEdit to set URL.")
        
        # 2. Determine download options using YtDlpModel presets
        if format_type == "audio":
            self.logger.info(self.__class__.__name__, 
                           "Using audio_default preset for protocol download.")
            options = YtDlpModel.get_preset_options("audio_default")
        elif format_type == "video":
            self.logger.info(self.__class__.__name__, 
                           "Using video_720p_default preset for protocol download.")
            options = YtDlpModel.get_preset_options("video_720p_default")
        elif format_type == "best" or format_type == "best-video":
            self.logger.info(self.__class__.__name__, 
                           "Using best_video_default preset for protocol download.")
            options = YtDlpModel.get_preset_options("best_video_default")
        else:
            self.logger.error(self.__class__.__name__, 
                             f"Unknown format_type '{format_type}'. Cannot determine options.")
            return  # Don't proceed if type is unknown

        # 3. Get output directory from settings
        output_dir = self.settings.get(YT_DOWNLOAD_DIR_KEY, DEFAULT_YT_DOWNLOAD_DIR, SettingType.PATH)
        output_dir_str = str(output_dir)
        
        # Validate the directory
        if not output_dir_str or not os.path.isdir(output_dir_str):
            # Use logger
            self.logger.error(self.__class__.__name__, 
                             f"Download directory '{output_dir_str}' is invalid or missing.")
            return
        
        # 4. Call DownloadManager
        self.logger.info(self.__class__.__name__, 
                        f"Adding download: URL={url}, Dir={output_dir_str}")
        self.download_manager.add_download(url, options, output_dir_str)
        
        # Do NOT clear URL input here, as the user didn't type it

    def showEvent(self, event):
        """Handle event when the page is shown."""
        super().showEvent(event)
        # REMOVED Load output directory setting when page is shown
        # Use logger
        self.logger.info(self.__class__.__name__, "Shown.")

