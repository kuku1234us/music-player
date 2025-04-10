# OPlayer Integration Plan

## Introduction
This document outlines the plan for integrating OPlayer functionality into our music player application. The primary goal is to enable users to upload currently playing media files directly to their OPlayer device through its web interface.

## Target Environment
- OPlayer Web Interface: `http://192.168.0.107:50000/`
- Upload endpoint expected at: `http://192.168.0.107:50000/upload`
- Protocol: HTTP multipart/form-data
- Field name for file upload: "file"

## Implementation Components

### 1. Backend Changes Required
- Use existing `get_current_media_path()` from VLCBackend to retrieve the current media file path
- Implement file upload functionality to OPlayer
- Add error handling for:
  - File system access issues
  - Network connectivity problems
  - Invalid file states
  - Server response errors

### 2. Frontend Implementation
#### UI Components
- Add "Upload to OPlayer" button in PlayerWidget
  - Position: Adjacent to player controls
  - Styling: Match existing theme and control aesthetics
  - State: Disabled when no media is playing
- Progress indicator for upload status
- Success/Error notification system

#### User Experience
- Visual feedback during upload process
- Clear error messaging
- Upload progress indication
- Success confirmation

### 3. Upload Process Flow
1. Button Click Handler:
   - Verify current playback state
   - Get current playing file path from VLC
   - Validate file accessibility
2. File Upload:
   - Create FormData with file
   - Send to OPlayer endpoint
   - Monitor and display upload progress
   - Handle response
3. Status Handling:
   - Show success notification on completion
   - Display error message if upload fails
   - Update UI state accordingly

### 4. Technical Implementation Details
#### Upload Mechanism
- Use multipart/form-data format
- Field name: "file" (matching OPlayer's requirements)
- Handle large file uploads appropriately

#### Error Handling
- No media playing
- File access errors
- Network connectivity issues
- Upload size limits
- Server response errors
- Timeout handling

### 5. Future Considerations
#### Settings and Configuration
- Add OPlayer connection settings
  - IP address configuration
  - Port configuration
  - Connection testing functionality

#### Additional Features
- Upload history tracking
- Large file upload optimization
- Connection status indicator
- Auto-retry functionality
- Upload queue management

## Implementation Phases
1. **Phase 1: Basic Integration**
   - Add upload button to player UI
   - Implement file access functionality
   - Basic upload logic

2. **Phase 2: Enhanced Functionality**
   - Progress indication
   - Error handling
   - Status notifications

3. **Phase 3: Advanced Features**
   - Settings management
   - Upload history
   - Connection management
   - Performance optimizations

## Testing Requirements
- File upload functionality
- Network error scenarios
- Large file handling
- UI responsiveness
- Progress indication accuracy
- Error message clarity
- Device compatibility
