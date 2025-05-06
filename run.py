#!/usr/bin/env python
"""
Entry point script to run the Music Player application.
Handles single instance logic and protocol URL parsing.
"""
import sys
import os
import urllib.parse
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication # Need QApplication for early socket check

# --- Add project root to path ---
# Get the absolute path of the directory containing run.py
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# --------------------------------

from qt_base_app.app import create_application, run_application
from qt_base_app.models import SettingsManager # Import SettingsManager
from music_player.ui.dashboard import MusicPlayerDashboard
# Import app defaults (adjust path if needed, assuming models dir exists)
from music_player.models.settings_defs import MUSIC_PLAYER_DEFAULTS

# --- Define Application Info ---
ORG_NAME = "MusicPlayer"
APP_NAME = "MusicPlayer"
APPLICATION_ID = "MusicPlayer-SingleInstance" # Unique ID for socket communication

# Define a listener object for cross-instance communication
class SingleInstanceListener(QObject):
    url_received = pyqtSignal(str, str) # url, format_type

def parse_protocol_url(url):
    """
    Parse a musicplayerdl protocol URL to extract format type and target URL.
    Returns a tuple of (format_type, url_to_download)
    """
    if not url.startswith('musicplayerdl://'):
        return None, None
        
    protocol_path = url.replace('musicplayerdl://', '')
    format_type = "video"  # Default format type
    url_to_download = None
    
    if protocol_path.startswith('audio/'):
        format_type = "audio"
        url_part = protocol_path[len('audio/'):] # Get part after prefix
        url_to_download = urllib.parse.unquote(url_part)
    elif protocol_path.startswith('video/'):
        format_type = "video"
        url_part = protocol_path[len('video/'):]
        url_to_download = urllib.parse.unquote(url_part)
    elif protocol_path.startswith('best/'):
        format_type = "best"
        url_part = protocol_path[len('best/'):]
        url_to_download = urllib.parse.unquote(url_part)
    else:
        # Assume legacy format or just URL (treat as video)
        url_to_download = urllib.parse.unquote(protocol_path)
    
    return format_type, url_to_download

def main():
    """Main entry point for the Music Player application."""
    
    # Must create QApplication temporarily for QLocalSocket, even if we exit early
    # It won't show a window unless run_application is called.
    temp_app_for_socket = QApplication.instance() # Check if already exists (e.g., testing)
    if temp_app_for_socket is None:
        temp_app_for_socket = QApplication(sys.argv)
    
    # --- Check for command line arguments ---
    raw_arg = None if len(sys.argv) <= 1 else sys.argv[1]
    
    # --- Single Instance Check ---
    # Always try to connect to an existing instance first
    socket = QLocalSocket()
    socket.connectToServer(APPLICATION_ID)

    # If connection succeeds, send arg and exit
    if socket.waitForConnected(500):
        print("[Run] Another instance is running.")
        
        # If we have a command line argument, pass it to the existing instance
        if raw_arg:
            print(f"[Run] Sending raw argument to existing instance: {raw_arg}")
            socket.write(raw_arg.encode())
            socket.flush()
            if not socket.waitForBytesWritten(1000):
                print("[Run Warning] Timeout waiting for bytes written to socket.", file=sys.stderr)
        
        socket.close()
        return 0 # Exit this instance successfully

    # --- No Existing Instance Found - Proceed with Full App Initialization ---
    print("[Run] No other instance detected. Starting main application.")
    
    # Now parse the protocol URL if one was provided
    url_to_download = None
    format_type = "video"  # Default format type
    
    if raw_arg and raw_arg.startswith('musicplayerdl://'):
        format_type, url_to_download = parse_protocol_url(raw_arg)
        print(f"[Run] Parsed protocol URL: {url_to_download} (Type: {format_type})")

    # Define Resource Paths (relative to project_root/run.py)
    config_path = os.path.join("music_player", "resources", "music_player_config.yaml")
    icon_base = os.path.join("music_player", "resources", "play") # Base name for icons
    fonts_dir_rel = "fonts" # Relative path to fonts dir from project root

    # Create application using the framework function
    # Note: create_application handles QApplication creation if needed,
    # so we don't strictly need the temp_app_for_socket anymore, but it doesn't hurt.
    app, window = create_application(
        window_class=MusicPlayerDashboard,
        organization_name=ORG_NAME,
        application_name=APP_NAME,
        config_path=config_path,
        icon_paths=[f"{icon_base}.ico", f"{icon_base}.png"],
        fonts_dir=fonts_dir_rel,
        font_mappings={
            "Geist-Regular.ttf": "default",
            "GeistMono-Regular.ttf": "monospace",
            "ICARubrikBlack.ttf": "title"
        }
        # Any **window_kwargs for MusicPlayerDashboard would go here
    )

    # --- Setup Server to Listen for Subsequent Instances ---
    server = QLocalServer()
    # Ensure any leftover server socket is removed (important on unclean shutdowns)
    if not QLocalServer.removeServer(APPLICATION_ID):
         print(f"[Run Warning] Could not remove existing server lock for {APPLICATION_ID}. Might be in use?", file=sys.stderr)
         
    if not server.listen(APPLICATION_ID):
        print(f"[Run Error] Failed to start local server {APPLICATION_ID}: {server.errorString()}", file=sys.stderr)
        # Decide if this is critical. Probably is for single-instance logic.
        # return 1 # Exit if server fails

    listener = SingleInstanceListener() # Instantiate our signal holder

    def handle_new_connection():
        print("[Run Server] New connection received.")
        conn_socket = server.nextPendingConnection()
        if conn_socket:
            if conn_socket.waitForReadyRead(1000):
                # Read the raw data sent from the second instance
                raw_data = conn_socket.readAll().data().decode()
                print(f"[Run Server] Received raw argument: {raw_data}")
                
                # Only process if it's a protocol URL
                if raw_data.startswith('musicplayerdl://'):
                    format_type, url = parse_protocol_url(raw_data)
                    
                    if format_type and url and url.startswith("http"):
                        print(f"[Run Server] Parsed protocol URL: {url} (Type: {format_type})")
                        listener.url_received.emit(url, format_type)
                    else:
                        print(f"[Run Server Warning] Failed to parse protocol URL: {raw_data}", file=sys.stderr)
                else:
                    print(f"[Run Server Warning] Received non-protocol URL data: {raw_data}", file=sys.stderr)
                
                conn_socket.disconnectFromServer() # Close connection after reading
            else:
                 print("[Run Server Warning] Timeout waiting for data on new connection.", file=sys.stderr)
                 conn_socket.abort() # Close immediately if no data read
        else:
             print("[Run Server Error] Failed to get next pending connection.", file=sys.stderr)

    server.newConnection.connect(handle_new_connection)
    print(f"[Run] Server listening on {APPLICATION_ID}")

    # --- Connect Listener Signal to Main Window Slot ---
    # We assume MusicPlayerDashboard will have a slot `handle_protocol_url(str, str)`
    try:
        if hasattr(window, 'handle_protocol_url') and callable(window.handle_protocol_url):
            listener.url_received.connect(window.handle_protocol_url)
            print("[Run] Connected listener signal to window.handle_protocol_url")
        else:
            print("[Run Error] Main window object does not have the required 'handle_protocol_url' method.", file=sys.stderr)
            # This is likely a critical error for protocol handling.
            # Consider exiting or disabling the feature gracefully.
            # return 1
    except Exception as e:
        print(f"[Run Error] Failed to connect listener signal: {e}", file=sys.stderr)
        # return 1
    # ------------------------------------------------

    # --- Register application-specific defaults ---
    try:
        settings = SettingsManager.instance()
        settings.set_defaults(MUSIC_PLAYER_DEFAULTS)
    except Exception as e:
         print(f"[ERROR][run] Failed to set application defaults: {e}", file=sys.stderr)
         # Consider exiting if defaults are critical
         # sys.exit(1)
    # ---------------------------------------------

    # --- Handle URL Passed on Initial Launch ---
    if url_to_download:
        print("[Run] Handling URL from initial launch...")
        if hasattr(window, 'handle_protocol_url') and callable(window.handle_protocol_url):
            window.handle_protocol_url(url_to_download, format_type)
        else:
             print("[Run Error] Cannot handle initial URL: Main window missing 'handle_protocol_url' method.", file=sys.stderr)
    # -------------------------------------------

    # Run the application event loop
    exit_code = run_application(app, window)
    
    # Clean up server on exit
    server.close()
    print("[Run] Server closed.")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main()) 