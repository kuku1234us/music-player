# 1) Intent & Rationale

**What we want**  
Create a new sidebar page called **“Vid Processing”** in the MusicPlayer app (built on `qt_base_app`). This page batch‑converts multi‑panel landscape clips (portrait video repeated side‑by‑side) **back into single portrait videos** and optionally **merges** the results into one portrait file.

**Why this matters**

- The owner collects portrait dance videos that platforms often rebroadcast in **landscape** by repeating the portrait stream **2×, 3× (most common), or 4×**.
- These are painful to watch on iPhone; we need a **one‑pass, folder‑based workflow** to crop the correct middle (or chosen) panel, normalize to 9:16, and produce outputs with **uniform codecs/fps/audio** for seamless merge.
- The page must be **fast, minimal, and self‑evident**, reuse existing base components (`BaseTableModel`, `BaseTableView`, `RoundButton`, `BaseProgressOverlay`), and preserve the app’s succinct, elegant UI.
- **Key enhancements**: Users can scrub through the video to pick the best preview frame, view high-resolution popups of crops, and select output resolutions (720p/1080p) with automatic padding.

---

# 2) User Stories

- **US1 – Scan & preview**: As a user, I select a folder; the page lists the videos with a small original frame and a computed portrait preview.
- **US2 – Scrub & Verify**: I can click on a timeline within the row to change the preview timestamp, ensuring the crop works for the whole video. I can click thumbnails to see a high-resolution popup.
- **US3 – Minimal controls per row**: For each row I adjust four numbers: **Split count**, **Idx** (tile index), **X‑offset**, **Width +delta**; the preview updates immediately.
- **US4 – Batch options**: I can choose the output resolution (720p, 1080p, or Original) and whether to **Merge Output** via top-bar controls. If merge is selected, I can optionally **Cleanup Singles** to keep only the merged file.
- **US5 – Process**: I click **Process**; selected rows are cropped, scaled (with padding if needed), encoded uniformly (H.264/AAC), and saved to an output folder.
- **US6 – Merge**: If "Merge Output" is checked, the app automatically concatenates valid outputs into a single file after processing. If "Cleanup Singles" is also checked, the individual clips are deleted after a successful merge.
- **US7 – Speed & feedback**: I see per‑file progress via a centralized overlay, and can **Stop** processing at any time.

---

# 3) Target Inputs & Outputs

**In‑scope sources**: mp4/mov/mkv/webm (verified via ffprobe).  
**Outputs per file**: `{basename}.mp4` (H.264 30fps, yuv420p, AAC 128k stereo, 48kHz).  
**Resolution**: User selectable:

- **720p**: Height 1280, Width auto (scaled & padded).
- **1080p**: Height 1920, Width auto (scaled & padded).
- **Original**: Preserves cropped dimensions (mod 2).
  **Merged output**: `{foldername}_merged_{YYYYMMDD-HHMM}.mp4` (concatenated from individual outputs).

---

# 4) Page Layout Overview

**Top Bar**:
`[☐ Merge Output] [☐ Cleanup Singles]                                     [ Output Resolution: 720p ▼ ]`
_(Cleanup Singles is hidden unless Merge Output is checked)_

**Table**:

```
+------------------------------------------------ Vid Processing -----------------------------------------------+
| [☐]  [Original Thumb]   {Video Title}       [ Split ] [ Idx ] [  X  ] [  +  ]           [ Cropped Preview ]   |
|      (Click -> Popup)   {Res • FPS}         [   3   ] [  1  ] [  0  ] [  0  ]           (Click -> Popup)      |
|                         [ Timeline ------]                                                                    |
+---------------------------------------------------------------------------------------------------------------+
               ^                ^                 ^        ^       ^        ^                    ^
               |                |                 |        |       |        |                    |
            Include       Title & Scrub       Split     Tile    X-Off    W-Delta       Live portrait preview
```

**Floating actions (RoundButtons, right→left, bottom‑right overlay)**:  
`[Open Out] [Process/Stop] [Scan] [Folder]`

---

# 5) Data Model (per row)

```python
class VidProcItem(TypedDict):
    path: Path
    title: str            # display name
    size_in: QSize        # W×H from ffprobe
    fps: float
    duration: float
    codec_v: str
    codec_a: str | None

    # User controls
    split: int            # e.g. 3 (required)
    tile_index: int       # 0-based index of selected tile (e.g. 1 for middle of 3)
    x_offset: int         # pixels relative to selected tile's left (can be negative)
    width_delta: int      # pixels added to the tile width (can be negative)
    preview_time: float   # timestamp for preview generation (seconds)

    # Clipping (Optional)
    clip_start: float | None # Start timestamp (seconds)
    clip_end: float | None   # End timestamp (seconds)

    # Derived
    crop_rect: QRect      # computed from split/tile_index/x/width_delta
    out_size: QSize       # final portrait size

    included: bool
    status: Literal['pending','processing','ok','error','skipped']
    out_path: Path | None
    log_tail: str         # last ffmpeg log lines for UI tooltip

    # Cache
    thumb_in: QImage | None
    thumb_out: QImage | None
```

**Table columns**

- **0: Include** (Checkbox)
- **1: Original** (Thumbnail, clickable)
- **2: Title & Info** (Title, Res/FPS, `VideoTimeline` widget)
- **3: Controls** (Split, Idx, X, + Group)
- **4: Preview** (Thumbnail, clickable)
- **5: Status** (Text/State)

---

# 6) Crop Calculation (deterministic)

Let input frame be `W×H`. Horizontal split `S` ⇒ base tile width `Tw = floor(W / S)`.  
**Selected tile (Idx)**: User selectable via "Idx" spinbox.

- **Default Logic**:
  - If `S` is odd (e.g. 3), default is middle (index `S // 2`).
  - If `S` is even (e.g. 2), default is right-of-center (index `S // 2`).

**Effective tile width** `Wtile = Tw + width_delta`.  
**Tile X** = `x = Tw * idx + x_offset` where `idx` is the 0-based tile index.  
**Portrait lock 9:16**: center‑crop inside the tile to 9:16:

```python
out_w = min(Wtile, int(H * 9/16))
out_h = min(H,     int(Wtile * 16/9))
# center within the tile
x2 = x + (Wtile - out_w)//2
y2 = (H - out_h)//2
crop = (out_w, out_h, x2, y2)
```

**Scaling & Padding**:

- If **720p/1080p** selected: Scale to fit height, pad width if necessary to maintain aspect ratio without distortion.
- If **Original**: Scale to nearest mod-2 dimensions.

---

# 7) ffmpeg/ffprobe Commands

**Probe**

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,avg_frame_rate \
        -show_entries format=duration -of json "{in}"
```

**Thumbnail (Low Res & High Res)**

```bash
# Low res (for table)
ffmpeg -y -ss {ts} -i "{in}" -frames:v 1 -vf "scale=360:-2" "{tmp}/in_{id}.jpg"

# High res (for popup - extracted on demand)
ffmpeg -y -ss {ts} -i "{in}" -frames:v 1 -q:v 2 "{tmp}/in_full_{id}.jpg"
```

**Per‑file encode (with scaling/padding)**

```bash
# Example for fixed height (e.g. 1920)
ffmpeg -y -ss {clip_start} -to {clip_end} -i "{in}" -vf "crop={w}:{h}:{x}:{y},scale=-2:1920:force_original_aspect_ratio=decrease,pad=-1:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p" \
       -r 30 -c:v libx264 -preset veryfast -crf 20 -c:a aac -b:a 128k -ar 48000 -ac 2 \
       "{out}.mp4"
```

_Note: `-ss` and `-to` are optional. If used, they provide frame-accurate cutting because re-encoding is active._

**Merge**

```bash
# list.txt with:  file 'path1.mp4'\nfile 'path2.mp4' ...
ffmpeg -f concat -safe 0 -i list.txt -c copy "{merged}.mp4"
```

---

# 8) UI/UX Specification

## 8.1 Table Row

```
[☐]  ║  [ Original ]   {Video Title}      [ Split ][ Idx ][ X ][ + ]   ║  [ Preview ]   ║ Status
     ║  (Clickable)    {Res • FPS}        [   3   ][  1  ][ 0 ][ 0 ]   ║  (Clickable)   ║
     ║                 [ Timeline ---- ]                               ║                ║
```

- **Timeline**: Clicking the timeline updates `preview_time` in the model, triggering a regeneration of both the "Original" thumbnail (at that time) and the "Preview" crop.
- **Controls**: Spinboxes have labels **stacked above** them (0 spacing).
  - **Idx Control**: Range `0` to `Split-1`. Updates intelligently when Split changes.
- **Thumbnails**: Clicking either thumbnail opens an **ImagePopup**.

### 8.1.1 Merge Output & Cleanup Singles

- **Merge Output**: If checked, processes all files then runs a concat pass.
- **Cleanup Singles**: If checked (only available when Merge is checked), deletes the individual processed `.mp4` files after the merge succeeds, keeping only the final combined video.

## 8.2 Image Popup

- **Behavior**: Opens a frameless, dark-themed modal dialog.
- **Resolution**: Initially shows the low-res cached image. A background thread (`HighResImageWorker`) fetches the full-resolution frame using ffmpeg.
- **Display**: The image scales to fit 95% of the screen size if too large, otherwise displays 1:1.
- **Interaction**: Clicking anywhere on the popup closes it.

## 8.3 RoundButtons (Overlay)

Order right→left:  
`[Open Out] [Process] [Scan] [Folder]`

- **Folder**: Select input directory (auto-saves to settings).
- **Scan**: Scans directory, probes files.
- **Process**:
  - Starts batch processing of included items.
  - Icon changes to **Stop** (Square) while running.
  - Clicking **Stop** cancels all active/queued tasks.
- **Open Out**: Opens the output directory.

---

# 9) Architecture & Components

- **Page class**: `VidProcessingPage(QWidget)`.
- **Model**: `VidProcTableModel`. Handles `preview_time`, `tile_index`, and `crop_rect` calculations.
- **Delegates**:
  - `ThumbDelegate`: Renders images, handles clicks for `ImagePopup`.
  - `ControlGroupDelegate`: Manages the 4-spinbox layout and data binding.
  - `TitleInfoDelegate`: Manages `TitleInfoWidget` containing labels and `VideoTimeline`.
- **Managers**:
  - `VidProcManager`:
    - **Versioning**: Assigns incrementing IDs to preview requests to prevent race conditions (UI ignores stale results).
    - **Threading**: Uses `QThreadPool` for probing and thumbnails. Uses single-threaded pool for encoding (sequential processing).
- **Workers**:
  - `ProbeWorker`, `EncodeWorker`, `MergeWorker`.
  - `HighResImageWorker` (QThread): Dedicated thread for fetching popup images without freezing UI.
- **Overlays**:
  - `BaseProgressOverlay`: Used for Scanning, Preview generation, and Processing progress.

---

# 10) Concurrency & Cancellation

- **Preview Generation**: Asynchronous. Fast "scrubbing" or control changes generate multiple requests; the Manager ensures versioning so only the latest relevant result updates the UI.
- **Processing**: Sequential (one by one) to avoid saturating CPU/Disk, but runs in background thread.
- **Cancellation**:
  - `VidProcManager.cancel_all_processing()` terminates active `subprocess.Popen` instances and clears the queue.
  - UI shows "Cancelled" overlay which auto-hides after 2 seconds.

---

# 11) Error Handling

- **Process Errors**: Failed items are marked `error`. Manager logs details. `BaseProgressOverlay` can show error states.
- **Merge Errors**: If merge fails (e.g. codec mismatch), error is displayed in overlay.
- **Resiliency**: If a file cannot be probed, it is skipped or shown with error status in the table.

---

# 13) Proposed Feature: Start/End Clipping

## 13.1 Intent

Allow users to trim the beginning and end of each video to remove unwanted intros or outros before processing.

## 13.2 User Interaction

- **Selection**: The user selects a row in the table.
- **Hotkeys**:
  - Press **'b'**: Marks the current `preview_time` as the **Start Point** (Beginning).
  - Press **'e'**: Marks the current `preview_time` as the **End Point**.
- **Visual Feedback**: The `VideoTimeline` shows markers or a highlighted "active" region indicating the clip range. The inactive parts (before 'b' and after 'e') are dimmed.

## 13.3 Technical Implementation Plan

- **Data Model**: Update `VidProcItem` to include `clip_start` (float) and `clip_end` (float).
- **UI Logic**:
  - `VidProcessingPage` overrides `keyPressEvent`.
  - On 'b'/'e' press: Fetch current `preview_time` of the selected row.
  - Update Model: Set `clip_start`/`clip_end`. Ensure logic: `start < end`.
- **Component**: Update `VideoTimeline` (in `music_player/ui/components/video_timeline.py`) to support rendering a clip range (start/end markers).
- **FFmpeg**:
  - `VidProcManager` injects `-ss {start}` and `-to {end}` into the main encoding command.
  - **Keyframes vs Exact**: Since we are re-encoding (`libx264`), we can use **frame-accurate cutting**. We do _not_ need to snap to keyframes. FFmpeg handles this automatically when decoding and re-encoding.
  - `Start Time`: If set, passed as `-ss {clip_start}` **before** input `-i` (fast seek) OR combined with `-to` logic carefully to ensure frame accuracy. (Note: `-ss` before `-i` in modern FFmpeg with transcoding is accurate).
  - `End Time`: Passed as `-to {clip_end}`.
