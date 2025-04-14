# OPlayer Integration Documentation

## Introduction
This document provides a tutorial on how the OPlayer integration works within the music player application. It allows users to upload the currently playing media file directly to an OPlayer device via its FTP server.

## Key Components

1.  **Player Page (`player_page.py`)**: Contains the user interface elements for initiating the upload.
2.  **OPlayer Service (`oplayer_service.py`)**: Manages the connection and file transfer logic using FTP.
3.  **FTP Upload Thread (`oplayer_service.py`)**: Handles the actual file upload in a background thread to prevent blocking the UI.
4.  **Upload Status Overlay (`upload_status_overlay.py`)**: Displays visual feedback to the user about the upload progress and status.
5.  **Round Button (`round_button.py`)**: The "OP" button used to trigger the upload.

## How it Works: Step-by-Step

1.  **Initiating Upload**: 
    *   The user clicks the round "OP" button located in the top-left corner of the `PlayerPage`.
    *   The `_on_oplayer_upload_clicked` method in `PlayerPage` is triggered.

2.  **Getting Media Path**: 
    *   The method first checks if the `persistent_player` (the main player instance) is available.
    *   It then retrieves the file path of the currently playing media using `self.persistent_player.backend.get_current_media_path()`.
    *   If no media is playing or the path cannot be retrieved, an error message is shown to the user.

3.  **Testing Connection**: 
    *   Before attempting the upload, `self.oplayer_service.test_connection()` is called.
    *   This method attempts to connect to the configured OPlayer FTP server (`host` and `port` stored in settings) using an anonymous login.
    *   It performs a simple directory listing (`nlst`) to verify the connection.
    *   If the connection test fails, a critical error message is displayed.

4.  **Starting the Upload**: 
    *   If the connection test is successful, `self.oplayer_service.upload_file(media_path)` is called.
    *   The `OPlayerService` emits the `upload_started` signal with the filename.
    *   It creates an instance of `FTPUploadThread`, passing the host, port, and file path.
    *   The service connects the thread's signals (`progress_updated`, `upload_completed`, `upload_failed`) to its own internal slots (`_on_progress_updated`, etc.).
    *   The `upload_thread.start()` method is called, initiating the upload in the background.

5.  **Background FTP Upload (`FTPUploadThread`)**: 
    *   The `run` method of the thread executes.
    *   It establishes an FTP connection to the OPlayer device using `ftplib`.
    *   It logs in anonymously.
    *   The file is opened in binary read mode (`'rb'`).
    *   `ftp.storbinary` is used to upload the file.
        *   A `callback` function is provided to `storbinary`.
        *   This callback calculates the progress percentage based on the amount of data transferred and the total file size.
        *   The `progress_updated` signal is emitted with the percentage.
    *   Upon successful completion, the FTP connection is closed, and the `upload_completed` signal is emitted.
    *   If any exception occurs during the process, the `upload_failed` signal is emitted with an error message.

6.  **UI Feedback (`PlayerPage` & `UploadStatusOverlay`)**: 
    *   The `PlayerPage` listens to signals from the `OPlayerService`:
        *   `upload_started`: Calls `self.upload_status.show_upload_started(filename)` to display the initial status.
        *   `upload_progress`: Calls `self.upload_status.show_upload_progress(percentage)` to update the progress bar/text.
        *   `upload_completed`: Calls `self.upload_status.show_upload_completed(filename)` to show a success message.
        *   `upload_failed`: Calls `self.upload_status.show_upload_failed(error_msg)` to display the error.
    *   The `UploadStatusOverlay` widget is responsible for rendering the visual feedback (e.g., text messages, progress bar) centered near the top of the `PlayerPage`.
    *   The overlay automatically hides after a short duration upon completion or failure.

## Configuration

*   The OPlayer FTP server **Host IP** and **Port** are managed by the `SettingsManager`.
*   Default values are set in `OPlayerService` (`192.168.0.107` and `2121`).
*   These settings are stored under the keys `oplayer/ftp_host` and `oplayer/ftp_port`.
*   The `OPlayerService` provides an `update_connection_settings` method, although currently there is no UI to call this. The connection test implicitly uses the stored settings.

## Error Handling

*   Checks for a valid media path before starting.
*   Performs a connection test before attempting upload.
*   Handles file-not-found errors.
*   Catches exceptions during the FTP process within the `FTPUploadThread` and signals failures back to the UI.
*   Displays user-friendly error messages via `QMessageBox` for connection failures and via the `UploadStatusOverlay` for upload process failures.
