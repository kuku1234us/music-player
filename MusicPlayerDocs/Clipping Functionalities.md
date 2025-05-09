# Introduction

The media clipping functionality allows users to easily cut out unwanted portions from the currently playing audio or video file. This feature enables users to create shorter, more focused clips from their media directly within the application.

# Hotkeys and Usage

The clipping process is controlled by three primary hotkeys:

*   **`b` - Mark Beginning:**
    *   When a media file is playing, pressing the `b` key marks the current playback position on the timeline as the "Beginning" of the desired clip.
    *   If a "Beginning" point is already set, pressing `b` again will update it to the new current playback position.

*   **`e` - Mark End:**
    *   Similarly, pressing the `e` key marks the current playback position as the "End" of the desired clip.
    *   If an "End" point is already set, pressing `e` again will update it to the new current playback position.
    *   The "End" point must be after the "Beginning" point. If an "End" point is marked before the "Beginning" point, the action might be ignored, or an appropriate visual cue/message should be provided.

*   **`c` - Clip Media:**
    *   This hotkey becomes active once at least a "Beginning" or an "End" point has been marked.
        *   If only "Beginning" is marked, the clip will be from the "Beginning" point to the end of the media.
        *   If only "End" is marked, the clip will be from the start of the media to the "End" point.
        *   If both are marked, the clip will be from "Beginning" to "End".
    *   Pressing `c` initiates the clipping process using the marked points.

# Visual Changes to Timeline

To provide clear visual feedback to the user, the player timeline will be updated as "Beginning" and "End" points are marked:

*   **Marked Points:** The "Beginning" and "End" points themselves should be visually distinct on the timeline (e.g., with markers or different colored lines).
*   **Unwanted Portions:** The sections of the timeline *before* the marked "Beginning" and *after* the marked "End" should be visually differentiated to indicate they will be excluded from the clip. This could be achieved by dimming these areas, using a different background color, or a strikethrough effect.
*   **Selected Region:** The segment between the "Beginning" and "End" points (or from the start/to the end if one is not set) should clearly represent the portion that will be kept.

# Clipping Mechanism

The actual clipping of the media file is handled as follows:

*   **Tool:** The `ffmpeg` command-line interface (CLI) tool is used for the clipping operation.
*   **No Re-encoding:** To ensure speed and preserve quality, `ffmpeg` will be instructed to perform the clip without re-encoding the audio or video streams (e.g., using `-c copy`).
*   **Output File:**
    *   A new media file is created for the clipped segment.
    *   The original file remains untouched.
    *   The new filename is generated based on the original filename:
        *   It takes the stem of the original filename.
        *   It appends `(x)` to the stem, where `x` is an integer starting from 1.
        *   The system will check for existing files with the same pattern (e.g., `original_stem(1).mp3`, `original_stem(2).mp3`) and use the earliest available integer for `x`. For example, if `original_stem(1).mp3` exists, the new file will be `original_stem(2).mp3`.
        *   The original file extension is preserved.
        *   Example: If the original file is `MySong.mp3` and `MySong(1).mp3` already exists, clipping it will create `MySong(2).mp3`.

# Post-Clipping Behavior

Once `ffmpeg` has successfully processed and created the new clipped media file:

*   **Automatic Playback:** The newly created clipped file will automatically be loaded into the main player.
*   **Playback State:** Playback of the new clip will commence from the beginning of the clipped segment.
*   **Timeline Reset:** The "Beginning" and "End" markers on the timeline will be cleared, as they pertained to the original, unclipped file.
*   **Focus:** The player should ideally regain focus.

This comprehensive process ensures a user-friendly way to edit media files directly within the application.
