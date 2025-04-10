"""
Service for handling OPlayer device interactions.
"""
import os
import ftplib
from PyQt6.QtCore import QObject, pyqtSignal, QThread, pyqtSlot
import re
import mimetypes

from qt_base_app.models.settings_manager import SettingsManager, SettingType

class FTPUploadThread(QThread):
    """
    Thread for handling FTP uploads to avoid blocking the UI.
    """
    progress_updated = pyqtSignal(int)
    upload_completed = pyqtSignal(str)
    upload_failed = pyqtSignal(str)
    
    def __init__(self, host, port, file_path, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.file_path = file_path
        self.file_size = os.path.getsize(file_path)
        self.filename = os.path.basename(file_path)
        
    def run(self):
        """Execute the FTP upload in a separate thread"""
        try:
            # Set up the FTP client
            print(f"[FTPUploadThread] Connecting to FTP server at {self.host}:{self.port}")
            ftp = ftplib.FTP()
            ftp.connect(self.host, self.port)
            ftp.login()  # Anonymous login, no username or password needed
            
            # Change to the appropriate directory if needed
            # For OPlayer, we'll upload to the root directory
            print(f"[FTPUploadThread] Connected to FTP server successfully")
            
            # Define callback function to track upload progress
            bytes_transferred = 0
            
            def callback(data):
                nonlocal bytes_transferred
                bytes_transferred += len(data)
                progress = int((bytes_transferred / self.file_size) * 100)
                self.progress_updated.emit(progress)
                print(f"[FTPUploadThread] Upload progress: {progress}%")
            
            # Open the file for binary reading
            with open(self.file_path, 'rb') as file:
                # Start the upload with progress tracking
                print(f"[FTPUploadThread] Uploading {self.filename}...")
                ftp.storbinary(f'STOR {self.filename}', file, 8192, callback)
            
            # Close the FTP connection
            ftp.quit()
            
            # Emit completion signal
            print(f"[FTPUploadThread] Upload completed successfully: {self.filename}")
            self.upload_completed.emit(self.filename)
            
        except Exception as e:
            error_msg = f"Upload failed: {str(e)}"
            print(f"[FTPUploadThread] Error: {error_msg}")
            self.upload_failed.emit(error_msg)
            
class OPlayerService(QObject):
    """
    Service class for handling OPlayer device interactions.
    Manages file uploads and connection status.
    """
    
    # Signals for upload status
    upload_started = pyqtSignal(str)  # Emits filename
    upload_progress = pyqtSignal(int)  # Emits percentage
    upload_completed = pyqtSignal(str)  # Emits filename
    upload_failed = pyqtSignal(str)    # Emits error message
    
    # Default OPlayer FTP settings
    DEFAULT_HOST = "192.168.0.107"
    DEFAULT_PORT = 2121
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Initialize settings manager
        self.settings = SettingsManager.instance()
        
        # Set default values if they don't exist
        if not self.settings.contains("oplayer/ftp_host"):
            self.settings.set("oplayer/ftp_host", self.DEFAULT_HOST, SettingType.STRING)
            
        if not self.settings.contains("oplayer/ftp_port"):
            self.settings.set("oplayer/ftp_port", self.DEFAULT_PORT, SettingType.INT)
            
        self.settings.sync()
        
        # Get current values
        self.host = self.settings.get("oplayer/ftp_host", self.DEFAULT_HOST, SettingType.STRING)
        self.ftp_port = self.settings.get("oplayer/ftp_port", self.DEFAULT_PORT, SettingType.INT)
        
        print(f"[OPlayerService] Initialized with FTP server: {self.host}:{self.ftp_port}")
        self.upload_thread = None
        
    def update_connection_settings(self, host=None, port=None):
        """
        Update the OPlayer connection settings.
        
        Args:
            host (str, optional): New FTP host address
            port (int, optional): New FTP port
            
        Returns:
            bool: True if settings were updated, False otherwise
        """
        updated = False
        
        if host is not None and host != self.host:
            self.host = host
            self.settings.set("oplayer/ftp_host", host, SettingType.STRING)
            updated = True
            
        if port is not None and port != self.ftp_port:
            self.ftp_port = port
            self.settings.set("oplayer/ftp_port", port, SettingType.INT)
            updated = True
            
        if updated:
            self.settings.sync()
            print(f"[OPlayerService] Updated connection settings: {self.host}:{self.ftp_port}")
            
        return updated
        
    def _get_mimetype(self, file_path):
        """Helper method to determine the correct MIME type for a file"""
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            # Default to a generic binary type if we can't determine it
            mime_type = 'application/octet-stream'
            
            # Try to use a more specific type for common audio formats
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.mp3':
                mime_type = 'audio/mpeg'
            elif ext in ['.m4a', '.aac']:
                mime_type = 'audio/aac'
            elif ext == '.flac':
                mime_type = 'audio/flac'
            elif ext == '.wav':
                mime_type = 'audio/wav'
        
        print(f"[OPlayerService] File MIME type: {mime_type}")
        return mime_type
        
    def upload_file(self, file_path):
        """
        Upload a file to the OPlayer device via FTP.
        
        Args:
            file_path (str): Path to the file to upload
            
        Returns:
            bool: True if upload started successfully, False otherwise
        """
        print(f"[OPlayerService] Attempting to upload file: {file_path}")
        
        if not os.path.exists(file_path):
            error_msg = f"File not found: {file_path}"
            print(f"[OPlayerService] Error: {error_msg}")
            self.upload_failed.emit(error_msg)
            return False
            
        try:
            # Get file size and info
            file_size = os.path.getsize(file_path)
            filename = os.path.basename(file_path)
            print(f"[OPlayerService] File size: {file_size} bytes")
            print(f"[OPlayerService] Starting upload of: {filename} via FTP")
            
            # Emit upload started signal
            self.upload_started.emit(filename)
            
            # Create and start the upload thread
            self.upload_thread = FTPUploadThread(self.host, self.ftp_port, file_path, self)
            self.upload_thread.progress_updated.connect(self._on_progress_updated)
            self.upload_thread.upload_completed.connect(self._on_upload_completed)
            self.upload_thread.upload_failed.connect(self._on_upload_failed)
            self.upload_thread.start()
            
            return True
            
        except Exception as e:
            error_msg = f"Upload failed: {str(e)}"
            print(f"[OPlayerService] Error: {error_msg}")
            self.upload_failed.emit(error_msg)
            return False
            
    @pyqtSlot(int)
    def _on_progress_updated(self, progress):
        """Handle progress updates from the upload thread"""
        self.upload_progress.emit(progress)
        
    @pyqtSlot(str)
    def _on_upload_completed(self, filename):
        """Handle upload completed signal from the thread"""
        self.upload_completed.emit(filename)
        
    @pyqtSlot(str)
    def _on_upload_failed(self, error_msg):
        """Handle upload failed signal from the thread"""
        self.upload_failed.emit(error_msg)
            
    def test_connection(self):
        """
        Test the connection to the OPlayer device via FTP.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        print(f"[OPlayerService] Testing connection to FTP server at {self.host}:{self.ftp_port}")
        try:
            # Try to connect to the FTP server
            ftp = ftplib.FTP()
            ftp.connect(self.host, self.ftp_port, timeout=5)
            ftp.login()  # Anonymous login
            
            # List files to verify connection works
            files = ftp.nlst()
            print(f"[OPlayerService] Connection test successful. Found {len(files)} files.")
            
            # Close the connection
            ftp.quit()
            return True
            
        except Exception as e:
            print(f"[OPlayerService] Connection test failed with error: {str(e)}")
            return False 