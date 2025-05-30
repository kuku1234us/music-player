# Music Player Hotkeys

This document lists all available keyboard shortcuts for the Music Player application.

## Playback Controls

| Key           | Function          | Description                                        |
| ------------- | ----------------- | -------------------------------------------------- |
| `Space`       | Toggle Play/Pause | Start playback if paused/stopped, pause if playing |
| `Media Play`  | Play              | Start playback                                     |
| `Media Pause` | Pause             | Pause playback                                     |
| `Media Stop`  | Stop              | Stop playback completely                           |

## Navigation Controls

### Timeline Navigation

| Key                   | Function                 | Description                                                           |
| --------------------- | ------------------------ | --------------------------------------------------------------------- |
| `Left Arrow`          | Seek Backward            | Jump backward by the configured seek interval (default: 3 seconds)    |
| `Right Arrow`         | Seek Forward             | Jump forward by the configured seek interval (default: 3 seconds)     |
| `Shift + Left Arrow`  | Fast Seek Backward       | **NEW** - Jump backward by 2x the seek interval (default: 6 seconds)  |
| `Shift + Right Arrow` | Fast Seek Forward        | **NEW** - Jump forward by 2x the seek interval (default: 6 seconds)   |
| `Ctrl + Left Arrow`   | Ultra Fast Seek Backward | **NEW** - Jump backward by 4x the seek interval (default: 12 seconds) |
| `Ctrl + Right Arrow`  | Ultra Fast Seek Forward  | **NEW** - Jump forward by 4x the seek interval (default: 12 seconds)  |
| `A`                   | Frame Backward           | **NEW** - Move backward by exactly one frame (~33ms @ 30fps)          |
| `F`                   | Frame Forward            | **NEW** - Move forward by exactly one frame (~33ms @ 30fps)           |

> **Note:** The seek interval for all arrow-based navigation can be configured in Preferences. Frame navigation (A/F keys) always moves by one frame regardless of this setting.

## Volume Controls

| Key          | Function    | Description           |
| ------------ | ----------- | --------------------- |
| `Up Arrow`   | Volume Up   | Increase volume by 5% |
| `Down Arrow` | Volume Down | Decrease volume by 5% |
| `+` (Plus)   | Volume Up   | Increase volume by 5% |
| `-` (Minus)  | Volume Down | Decrease volume by 5% |

## Playback Speed Controls

| Key | Function       | Description                           |
| --- | -------------- | ------------------------------------- |
| `[` | Decrease Speed | Decrease playback speed by 0.10x      |
| `]` | Increase Speed | Increase playback speed by 0.10x      |
| `0` | Reset Speed    | Reset playback speed to normal (1.0x) |

## Video Controls

| Key   | Function           | Description                                    |
| ----- | ------------------ | ---------------------------------------------- |
| `F12` | Toggle Full Screen | Enter/exit full-screen mode for video playback |

## Clipping Controls

### Basic Clipping

| Key | Function     | Description                                                  |
| --- | ------------ | ------------------------------------------------------------ |
| `B` | Mark Begin   | Mark the current position as the beginning of a clip segment |
| `E` | Mark End     | Mark the current position as the end of a clip segment       |
| `C` | Perform Clip | Create a new media file with the marked segments             |

### Multi-Segment Clipping Management

| Key                 | Function            | Description                               |
| ------------------- | ------------------- | ----------------------------------------- |
| `Shift + B`         | Clear Pending Begin | Clear the current pending begin marker    |
| `Shift + E`         | Clear Last Segment  | Remove the last added segment             |
| `Shift + Delete`    | Clear All Segments  | Clear all segments and pending markers    |
| `Shift + Backspace` | Clear All Segments  | Alternative key for clearing all segments |

## Multi-Segment Clipping Workflow

1. **Mark First Segment:**

   - Press `B` to set the beginning of your first segment
   - Seek to the end position of the first segment
   - Press `E` to complete the first segment

2. **Mark Additional Segments:**

   - Seek to the beginning of your next segment
   - Press `B` to set a new pending begin marker
   - Seek to the end of this segment
   - Press `E` to complete this segment
   - Repeat for as many segments as needed

3. **Manage Segments:**

   - Use `Shift + B` to cancel a pending begin marker
   - Use `Shift + E` to remove the last segment you added
   - Use `Shift + Delete` to start over and clear everything

4. **Create the Clip:**
   - Press `C` to merge all segments into a single output file
   - The segments will be automatically sorted and merged if they overlap

## Usage Notes

- **State Requirements:** Most navigation and clipping hotkeys only work when media is loaded and the player is in playing or paused state
- **Navigation Hierarchy:** The player provides multiple levels of seeking precision:
  - **Frame-level:** A/F keys move by exactly one frame (~33ms)
  - **Normal:** Left/Right arrows use the configured seek interval (default: 3 seconds)
  - **Fast:** Shift+Left/Right use 2x the seek interval (default: 6 seconds)
  - **Ultra Fast:** Ctrl+Left/Right use 4x the seek interval (default: 12 seconds)
- **Frame Navigation:** The A/F keys use a default of 30 FPS for frame calculation. For videos with different frame rates, the movement may not be perfectly frame-accurate
- **Clipping Output:** Clipped files are saved in the same directory as the original with a naming pattern like `filename(1).ext`, `filename(2).ext`, etc.
- **Hardware Acceleration:** Full-screen mode benefits from hardware acceleration when available

## Settings Integration

- **Seek Interval:** The Left/Right arrow seek distance can be configured in Preferences → Seek interval
- **Volume Range:** Volume controls support a range of 0-200% for enhanced audio
- **Repeat Modes:** Use the UI controls for different repeat modes (All, One, Random)
