# Introduction

This document outlines the recommended approach for implementing full-screen video playback functionality for the `VideoWidget`. The strategy focuses on using a dedicated manager class to handle full-screen transitions and on-screen playback controls, aiming for a user experience similar to modern video players.

## Core Mechanism: `showFullScreen()` and `showNormal()`

The fundamental Qt methods for managing full-screen state remain crucial:
- `QWidget.showFullScreen()`: Makes the widget (and its window) occupy the entire screen without any window decorations.
- `QWidget.showNormal()`: Restores the widget to its previous state (windowed).

A boolean flag, say `is_full_screen`, will be maintained by the `FullScreenManager` (described below) to track the current mode and toggle appropriately.

## Dedicated Full-Screen Manager Approach

This approach involves creating a new class, `FullScreenManager`, to be located in `music_player/ui/components/player_components/full_screen_video.py`. This class will be solely responsible for orchestrating the full-screen video experience.

### `FullScreenManager` Initialization and Integration

The `FullScreenManager` would typically be instantiated by a central UI controller or the main application window – whichever class has access to both the `VideoWidget` instance and the `MainPlayer` instance. These references would be passed to the `FullScreenManager` upon its creation (e.g., via its constructor or dedicated setter methods). This allows the manager to perform re-parenting on the correct `VideoWidget` and to connect the on-screen controls to `MainPlayer`'s playback logic.

### Responsibilities of `FullScreenManager`:

1.  **Host Window Creation:**
    *   It will create and manage a dedicated, frameless top-level window (e.g., `FullScreenVideoHostWindow`, which could be an internal class within `FullScreenManager` or a simple `QWidget` configured with `Qt.WindowType.FramelessWindowHint` and potentially `Qt.WindowType.Window`). This host window serves as the temporary parent for the `VideoWidget` during full-screen playback.

2.  **`VideoWidget` Re-parenting:**
    *   **Why Re-parent?** We choose to re-parent the existing `VideoWidget` instead of creating a new one for full-screen mode. Think of it like moving your living room TV to a special home cinema wall temporarily, rather than buying a second TV just for movies. This approach is more efficient, as it reuses the existing video display and its associated VLC instance, ensuring playback state (like current position and loaded media) remains consistent without complex synchronization or reinitialization.
    *   **Process:**
        *   When entering full screen:
            *   Store the `VideoWidget`'s original parent and its layout-specific properties (e.g., its index in the layout, stretch factors, size policy if it was modified from default).
            *   Hide the `VideoWidget` from its current layout/parent (e.g., by removing it from its layout and calling `video_widget.setParent(None)` before re-parenting).
            *   Re-parent the `VideoWidget` to the `FullScreenVideoHostWindow` (e.g., `video_widget.setParent(full_screen_host_window)`).
            *   Add the `VideoWidget` to a layout within `FullScreenVideoHostWindow` (e.g., a `QVBoxLayout` with `addWidget`) to ensure it fills the host window.
        *   When exiting full screen:
            *   Remove `VideoWidget` from `FullScreenVideoHostWindow`'s layout and re-parent it back to its original parent.
            *   Restore it in its original layout, applying any stored layout properties. Making it visible again.

    *   **Visualizing Re-parenting (Conceptual ASCII Diagram):**
        ```
        Before Full Screen:

        ApplicationMainWindow
        |-- MainLayout
        |   |-- (Other UI Elements like Menus, Sidebars, etc.)
        |   |-- VideoWidgetContainer (e.g., a QFrame or specific layout area)
        |   |   |-- VideoWidget (Original Parent: VideoWidgetContainer)
        |   |-- MainPlayer (Manages PlayerWidget, Backend, etc.)
        |       |-- PlayerWidget (UI Controls)

        --------------------------------------------------------------------

        During Full Screen (Conceptual):

        FullScreenVideoHostWindow (Top-level, Frameless, Black Background)
        |-- HostWindowLayout (e.g., QVBoxLayout)
        |   |-- VideoWidget (Re-parented, New Parent: FullScreenVideoHostWindow)
        |
        |-- OnScreenControlsPanel (Overlay, child of FullScreenVideoHostWindow)
            |-- (Play/Pause Button, Timeline, Volume, Exit FS Button etc.)

        (ApplicationMainWindow and its original children might be hidden or still visible underneath)
        ```

3.  **Host Window State Management:**
    *   Call `full_screen_host_window.showFullScreen()` to enter full-screen mode.
    *   To exit, call `full_screen_host_window.showNormal()`, then `full_screen_host_window.hide()` (or `close()` if it's to be destroyed and recreated each time, though keeping an instance might be more efficient).

4.  **Coordination:**
    *   Provide methods to be called by `MainPlayer` (or a UI controller) to initiate/terminate full-screen mode.
    *   Manage the creation, visibility, and interaction of the on-screen controls.

### Triggering Full Screen:

-   **F12 Key (Toggle):** The primary method to enter and exit full-screen mode will be the F12 key. This key press should ideally be handled globally by `MainPlayer` (possibly by extending its `HotkeyHandler` or through an event filter on the main application window). When F12 is pressed, `MainPlayer` will call the appropriate method on the `FullScreenManager` to toggle the full-screen state.
-   **VideoWidget Interaction (e.g., Double-Click):** The `VideoWidget` itself might also detect a trigger (e.g., via its `mouseDoubleClickEvent` method). Instead of directly manipulating window states, it should emit a signal (e.g., `fullScreenRequested`). `MainPlayer` (or a relevant UI controller) would connect to this signal and delegate the request to its `FullScreenManager` instance, effectively providing another way to toggle full-screen mode.

### Exiting Full Screen:

-   **ESC Key (Exit Only):** The `FullScreenVideoHostWindow` (or the `FullScreenManager` if it installs an event filter on the host window) must capture the `Qt.Key.Key_Escape`. This key will exclusively serve to exit full-screen mode and return to the normal view.
-   **F12 Key (Toggle):** As mentioned above, F12 will also exit full-screen mode if it's currently active, due to its toggle behavior managed by `MainPlayer`.
-   **On-Screen Control Button:** A dedicated button on the on-screen controls panel will provide a mouse-clickable way to exit full-screen mode.

## On-Screen Controls in Full-Screen Mode

To provide a user-friendly experience, playback controls should be available as an overlay when the video is in full-screen mode.

### Purpose:
Provide essential playback controls without permanently obscuring the video content, enhancing usability in an immersive viewing environment.

### Container and Appearance:
-   The `FullScreenVideoHostWindow` will contain a dedicated panel or custom widget (`OnScreenControlsPanel`) for these controls.
-   This panel will be styled to overlay the video, typically positioned towards the bottom of the screen. It might have a semi-transparent background to blend smoothly with the video content.
-   The `FullScreenVideoHostWindow` itself might require a background color (e.g., black) to ensure no underlying desktop or window content is visible if the video's aspect ratio results in letterboxing. The `OnScreenControlsPanel` will need distinct styling using Qt StyleSheets to achieve the desired overlay effect, ensuring controls are clearly visible against varying video content.

### Auto-Hide Behavior:
-   **Visibility Logic:**
    *   Controls become visible when the mouse cursor moves over the video area within the `FullScreenVideoHostWindow`.
    *   Controls automatically hide after a short period of mouse inactivity (e.g., 2-5 seconds).
-   **Implementation Sketch:**
    *   The `FullScreenVideoHostWindow` (or the `FullScreenManager` if it handles events for the host window) must have mouse tracking enabled: `full_screen_host_window.setMouseTracking(True)`.
    *   Its `mouseMoveEvent` implementation will:
        *   Make the `OnScreenControlsPanel` visible (e.g., `self.on_screen_controls_panel.show()`).
        *   If the mouse cursor was hidden, restore it (e.g., `self.unsetCursor()`).
        *   (Re)start a `QTimer` instance (e.g., `self.hide_controls_timer.start()`).
    *   The `hide_controls_timer` (a `QTimer` with `singleShot=True`) will be connected to a slot that hides the `OnScreenControlsPanel` (e.g., `self.on_screen_controls_panel.hide()`).
    *   Optionally, this timer's timeout can also trigger hiding the mouse cursor (`self.setCursor(Qt.CursorShape.BlankCursor)`) after the controls have been hidden for a moment or along with them.
    *   *Conceptual Snippet for Auto-Hide Logic (illustrative):*
        ```python
        # Conceptual: Inside FullScreenVideoHostWindow or managed by FullScreenManager
        # def __init__(self, ...):
        #     # ...
        #     self.setMouseTracking(True)
        #     self.on_screen_controls_panel = OnScreenControlsPanelWidget(self)
        #     self.on_screen_controls_panel.hide()
        #     self.hide_controls_timer = QTimer(self)
        #     self.hide_controls_timer.setInterval(3000) # 3 seconds
        #     self.hide_controls_timer.setSingleShot(True)
        #     self.hide_controls_timer.timeout.connect(self.hide_all_overlays)

        # def mouseMoveEvent(self, event: QMouseEvent):
        #     self.show_all_overlays()
        #     self.hide_controls_timer.start()
        #     super().mouseMoveEvent(event)

        # def show_all_overlays(self):
        #     self.unsetCursor() # Ensure cursor is visible
        #     self.on_screen_controls_panel.show()

        # def hide_all_overlays(self):
        #     self.on_screen_controls_panel.hide()
        #     self.setCursor(Qt.CursorShape.BlankCursor) # Hide cursor too
        ```

### Control Elements (Leveraging `PlayerWidget` from `main_player.py`):

The `OnScreenControlsPanel` should be a new custom widget. It can achieve its functionality by:
    a. **Composition:** Instantiating and arranging individual, perhaps simplified or re-styled, components from `PlayerWidget` (like its buttons, sliders).
    b. **Replication:** Creating new, streamlined UI elements that replicate the essential functionality and connecting them to `MainPlayer`'s existing slots or `VLCBackend` methods for control.
    c. **Adaptation:** Potentially, a heavily modified and simplified version of `PlayerWidget` itself could be adapted if its layout can be made suitable for a compact overlay. (Approach 'a' or 'b' are often cleaner for distinct overlay controls).

**Essential Controls to Replicate/Adapt:**
-   **Play/Pause Button:** To toggle playback.
-   **Timeline/Seekbar:** Visually represent current playback position and total duration; allow user to seek by clicking or dragging.
-   **Volume Control:** A slider for adjustment and/or a mute button.
-   **Exit Full-Screen Button:** A clearly marked button (e.g., an icon) to return to the normal windowed view.

**Potential Additional Controls (depending on features and space):**
-   **Next/Previous Track Buttons:** If playback is part of a playlist managed by `MainPlayer`.
-   **Subtitle Selection Menu/Button:** If the video has subtitles and this feature is exposed.
-   **Repeat Mode Toggle Button.**
-   **Playback Speed Control.**

### Signaling and Interaction for On-Screen Controls:

-   The `FullScreenManager` is responsible for creating, showing, hiding, and managing this `OnScreenControlsPanel` within the `FullScreenVideoHostWindow`.
-   Crucially, signals emitted by these on-screen controls (e.g., play button `clicked()`, seekbar `sliderMoved()` or a custom `seekRequested(int_position)` signal, volume slider `valueChanged()`) must be connected by the `FullScreenManager` to the appropriate slots in the `MainPlayer` instance. `MainPlayer` remains the central authority for controlling playback via `VLCBackend`.
    *   Example Connection: `on_screen_play_button.clicked.connect(main_player_instance._on_play_requested)`
    *   Example Connection: `on_screen_timeline.user_seeked.connect(main_player_instance._on_position_changed)`

## Event Handling and Focus Management for Consistent Hotkeys

Ensuring that all hotkeys defined in `hotkey_handler.py` (which operate on `MainPlayer` and `VideoWidget`) continue to function seamlessly in full-screen mode is paramount for a good user experience.

-   **ESC Key for Exiting:** The `FullScreenVideoHostWindow` (or `FullScreenManager` via an event filter) must directly handle `Qt.Key.Key_Escape` to exit full-screen mode. This event should typically be consumed here and not propagated further for other hotkey actions.

-   **F12 Key for Toggling:** As this is the primary toggle, it's best handled by `MainPlayer` (e.g., by adding it to `hotkey_handler.py` or an application event filter). This ensures F12 works consistently to toggle full-screen, regardless of which window has focus (main application or full-screen host).

-   **Standard Playback Hotkeys (Space, Arrows, Volume, etc.):**
    *   **Global Handling Preferred:** The most robust solution is if `MainPlayer`'s `HotkeyHandler` already processes these standard playback hotkeys in a global manner (e.g., through an event filter installed on `QApplication.instance()`, or because `MainPlayer` is part of the main window which naturally processes unhandled key events). If so, these hotkeys should continue to work without special intervention from the `FullScreenVideoHostWindow`.
    *   **Focus and Event Forwarding (If Necessary):** If the `FullScreenVideoHostWindow` (being a top-level window) captures all keyboard input when active, and global handling isn't in place, a mechanism for forwarding relevant key events is required. The `FullScreenVideoHostWindow` should:
        1.  Process keys it explicitly manages (like ESC).
        2.  For all other key events that correspond to actions in `hotkey_handler.py`, it should forward these events to `MainPlayer` (or the main application window, which would then route them appropriately). This allows `MainPlayer`'s `HotkeyHandler` to process them as usual.
        *Alternatively, the `VideoWidget`, when re-parented into the `FullScreenVideoHostWindow`, must be given focus, and the `FullScreenVideoHostWindow` should ensure unhandled key events bubble up or are passed to it if the `VideoWidget`'s own `keyPressEvent` (which uses `hotkey_handler`) is meant to be the primary recipient.*
    *   The goal is to avoid duplicating hotkey logic. The existing `hotkey_handler.py` should remain the single source of truth for playback control actions. The `FullScreenManager` and `FullScreenVideoHostWindow` must facilitate, not obstruct, its operation.

## VLC Instance and `winId` Update

-   When `VideoWidget` is re-parented into `FullScreenVideoHostWindow`, its platform-specific window ID (`winId()`) will change. This is because the `winId()` is tied to the top-level native window context; `FullScreenVideoHostWindow` is a new, distinct top-level window from the main application window where `VideoWidget` originally resided. Thus, moving `VideoWidget` between these two contexts necessarily changes the `winId()` that VLC must use.
-   The VLC media player instance, managed by `VLCBackend`, is associated with a specific window ID for rendering video (via `vlc.MediaPlayer.set_hwnd()`).
-   The `FullScreenManager`, in coordination with `MainPlayer` (which interfaces with `VLCBackend`), must ensure that `VLCBackend.set_video_output()` is called with the new `winId()` of the `VideoWidget`. This call should be made *after* the `VideoWidget` has been re-parented and the `FullScreenVideoHostWindow` is shown and visible, as the `winId()` might not be valid or stable before that point.
-   Similarly, when exiting full screen, the `winId()` should be updated again: either to the `VideoWidget`'s `winId()` in its original parent (if video continues) or set to `None` (or `0`) via `VLCBackend.set_video_output(None)` if the video display is to be detached or hidden.

This dedicated manager approach provides a clear separation of concerns, making the full-screen functionality more robust, maintainable, and extensible, aligning with good software design principles.

## Full-Screen Toggle Event Flow (F12 Key)

Understanding the sequence of events when toggling full-screen mode is crucial for debugging and further development. The F12 key serves as the primary toggle. Below is a detailed breakdown of what happens under the hood.

### Entering Full Screen (F12 Press in In-App Mode)

When the user is viewing video content within the main application window (in-app mode) and presses F12, the following sequence is initiated to transition to an immersive full-screen experience:

1.  **F12 Key Detection**:
    *   The `MainPlayer` (typically through its integrated `HotkeyHandler` or via an event filter on the main application window) captures the F12 key press. This centralized handling ensures F12 works globally within the application.

2.  **Delegation to `FullScreenManager`**:
    *   Upon detecting F12, `MainPlayer` invokes the `toggle_full_screen()` method on its `FullScreenManager` instance. Since the player is not currently in full-screen, this effectively calls `FullScreenManager.enter_full_screen()`.

3.  **`FullScreenManager.enter_full_screen()` Orchestration**:
    *   **State Preservation**: The manager first saves the `VideoWidget`'s current state within `PlayerPage`. This includes:
        *   Its original parent widget (e.g., the `QStackedWidget` in `PlayerPage`).
        *   Its current visibility, geometry, and layout details (like its index and stretch factor within the original parent's layout).
        *   The `VideoWidget` is then programmatically removed from its current layout in `PlayerPage`. This prepares it to be moved.
    *   **Re-parenting `VideoWidget`**: The `VideoWidget` is re-parented to the `FullScreenVideoHostWindow`. Think of this like temporarily moving your TV from the living room stand to a dedicated cinema room wall. The `VideoWidget` instance itself isn't destroyed and recreated; it's the same widget, just in a new temporary home.
        *   `self._video_widget_ref.setParent(self._host_window)`
    *   **Integrating into Host Layout**: The `VideoWidget` is added to the layout of the `FullScreenVideoHostWindow`, configured to fill the entire host window.
    *   **Displaying the Host Window**:
        *   The `FullScreenVideoHostWindow` (now containing the `VideoWidget`) is shown in true full-screen mode using `self._host_window.showFullScreen()`.
        *   The host window is activated, raised to the top, and given input focus. The `VideoWidget` geometry is explicitly set to match the host window's content area.
    *   **VLC `winId` Update**: This is a critical step. When a widget is re-parented and shown in a new top-level window, its underlying window system identifier (`winId()`) changes. VLC needs this `winId` to know where to draw the video.
        *   `MainPlayer` (via `FullScreenManager`) calls `VLCBackend.set_video_output()` (or a similar method like `_set_vlc_window_handle`) with the `VideoWidget`'s *new* `winId()`. This must happen *after* the `FullScreenVideoHostWindow` is visible and the `VideoWidget` is part of it.
    *   **Internal State Update**: `FullScreenManager` sets its internal `_is_full_screen` flag to `True`.

At this point, the video is playing full-screen, and the `FullScreenVideoHostWindow` is responsible for handling input like the ESC key for exiting.

### Exiting Full Screen (F12 Press in Full-Screen Mode)

When F12 is pressed while in full-screen mode, the application transitions back to the normal in-app view:

1.  **F12 Key Detection**:
    *   Similar to entering, `MainPlayer`'s global F12 handler detects the key. Alternatively, if the `FullScreenVideoHostWindow` has focus, it might detect F12 and signal `FullScreenManager`. The global handler in `MainPlayer` is generally more robust for a toggle.

2.  **Delegation to `FullScreenManager`**:
    *   `MainPlayer` calls `FullScreenManager.toggle_full_screen()`. Since `_is_full_screen` is true, this routes to `FullScreenManager.exit_full_screen()`.

3.  **`FullScreenManager.exit_full_screen()` Orchestration**:
    *   **Removing from Host**: The `VideoWidget` is removed from the `FullScreenVideoHostWindow`'s layout.
    *   **Detaching `VideoWidget`**: The `VideoWidget`'s parent is set to `None` (`self._video_widget_ref.setParent(None)`). It's now "homeless" momentarily, waiting to be re-adopted by `PlayerPage`.
    *   **Hiding Host Window**: The `FullScreenVideoHostWindow` is first set to `showNormal()` (to exit the OS's full-screen mode gracefully) and then hidden using `self._host_window.hide()`.
    *   **VLC `winId` Update (Detachment)**: `MainPlayer` (via `FullScreenManager`) calls `VLCBackend.set_video_output(None)`. This tells VLC to stop trying to render to the `VideoWidget`'s old `winId` (which is associated with the now-hidden host window).
    *   **Restoring Focus**: Focus is explicitly returned to the main application window.
    *   **Internal State Update**: `FullScreenManager` sets `_is_full_screen` to `False` and emits the `did_exit_full_screen` signal.

4.  **`MainPlayer` Coordinates `PlayerPage` Update**:
    *   `MainPlayer` typically has a slot connected to `FullScreenManager.did_exit_full_screen` or reacts directly. This often involves calling a method like `_sync_player_page_display()` to ensure the UI reflects the current state.

5.  **`PlayerPage.show_video_view()` Re-integrates `VideoWidget`**:
    *   This method is called by `MainPlayer` to restore the video display within `PlayerPage`.
    *   **Re-parenting**: `self.video_widget.setParent(self.media_display_stack)` makes the `VideoWidget` a child of the `QStackedWidget` in `PlayerPage`.
    *   **Re-adding to Stack**: `self.media_display_stack.addWidget(self.video_widget)` is crucial. It re-registers the `VideoWidget` with the `QStackedWidget`'s layout and page management system. This step is vital to avoid the "widget not contained in stack" errors and ensure correct resizing.
    *   **Making Visible**: `self.media_display_stack.setCurrentWidget(self.video_widget)` makes it the active page. Its visibility is ensured, and `update()`/`updateGeometry()` calls trigger a layout pass, resizing it correctly within `PlayerPage`.

6.  **`MainPlayer` Re-attaches VLC to `VideoWidget` in `PlayerPage`**:
    *   Once `VideoWidget` is visible and correctly sized within `PlayerPage`, `MainPlayer` must again update VLC's output.
    *   It calls `VLCBackend.set_video_output()` with the `VideoWidget`'s `winId()`. This `winId` is now relative to its place within the `PlayerPage` and the main application window.

The video playback now seamlessly continues within the `PlayerPage`, scaled correctly, and all application controls are accessible again.

This two-way process of detaching, re-parenting, and re-integrating the `VideoWidget`, coupled with timely `winId` updates for VLC, is fundamental to the full-screen functionality.

## Implementation Milestones Checklist

- [x] **1. `FullScreenManager` Class Foundation:**
    - [x] Create `music_player/ui/components/player_components/full_screen_video.py` with basic `FullScreenManager` class structure.
    - [x] Implement the `FullScreenVideoHostWindow` (internal class or configured `QWidget`): set frameless flags, basic layout for `VideoWidget` and `OnScreenControlsPanel`.
    - [x] Implement core `is_full_screen` boolean state tracking within `FullScreenManager`.

- [x] **2. Core Full-Screen Mechanics:**
    - [x] Implement `VideoWidget` re-parenting logic in `FullScreenManager`:
        - [x] Method to store original parent/layout details & move `VideoWidget` to `FullScreenVideoHostWindow`.
        - [x] Method to restore `VideoWidget` to its original parent and layout.
    - [x] Implement `FullScreenVideoHostWindow` state management in `FullScreenManager`:
        - [x] Method to call `showFullScreen()` on host window.
        - [x] Method to call `showNormal()` and `hide()` on host window.
    - [x] Integrate `VLCBackend.set_video_output()` calls in `FullScreenManager` for `winId` changes (on entering full screen after host window is visible, and on exiting).

- [x] **3. Integration with `MainPlayer` and `VideoWidget`:**
    - [x] Instantiate `FullScreenManager` in `MainPlayer` (or designated UI controller).
    - [x] Pass necessary references (e.g., `VideoWidget` instance, `MainPlayer` instance) to `FullScreenManager`.
    - [x] Modify `VideoWidget` to emit `fullScreenRequested` signal (e.g., on `mouseDoubleClickEvent`).
    - [x] In `MainPlayer`, connect `VideoWidget.fullScreenRequested` to a slot that calls `FullScreenManager.toggle_full_screen()` (or similar method).

- [ ] **4. Hotkey Implementation:**
    - [ ] **F12 (Toggle Full Screen):**
        - [ ] Add F12 key detection to `MainPlayer` (via `HotkeyHandler` or event filter).
        - [ ] Connect F12 action to `FullScreenManager.toggle_full_screen()`.
    - [ ] **ESC (Exit Full Screen Only):**
        - [ ] Implement ESC key press handling in `FullScreenVideoHostWindow` (or `FullScreenManager`) to directly call `FullScreenManager.exit_full_screen()` (or similar method).

- [ ] **5. On-Screen Controls Panel (`OnScreenControlsPanel`):**
    - [ ] Create the `OnScreenControlsPanel` custom widget class.
    - [ ] Design and implement its layout with placeholders for essential controls (Play/Pause, Timeline, Volume, Exit Full-Screen button).
    - [ ] Implement the actual control UI elements, reusing/adapting from `PlayerWidget` or creating new ones.
    - [ ] Connect signals from these on-screen controls to appropriate slots/methods in `MainPlayer` (connections managed or facilitated by `FullScreenManager`).
    - [ ] Style `OnScreenControlsPanel` for an overlay appearance.

- [ ] **6. Auto-Hide Behavior for On-Screen Controls:**
    - [ ] Enable `setMouseTracking(True)` on `FullScreenVideoHostWindow`.
    - [ ] Implement `mouseMoveEvent` in `FullScreenVideoHostWindow` (or `FullScreenManager`).
    *   Implement `QTimer` logic (`hide_controls_timer`) to show/hide `OnScreenControlsPanel` and optionally the mouse cursor.

- [ ] **7. Ensuring Consistent Standard Hotkey Operation:**
    - [ ] Review existing hotkey (`hotkey_handler.py`) propagation when `FullScreenVideoHostWindow` is active.
    - [ ] If necessary, implement event forwarding from `FullScreenVideoHostWindow` to `MainPlayer` for standard playback hotkeys OR ensure `VideoWidget`/`MainPlayer` reliably receives these events through focus management or global event filters.
    - [ ] Verify all hotkeys (play/pause, seek, volume, speed, etc.) function correctly in full-screen mode.

- [ ] **8. Styling and Final Polish:**
    - [ ] Set a default background color (e.g., black) for `FullScreenVideoHostWindow`.
    - [ ] Refine the visual appearance and transitions of `OnScreenControlsPanel`.
    - [ ] Ensure smooth visual transitions when entering/exiting full-screen mode.

- [ ] **9. Comprehensive Testing and Refinement:**
    - [ ] Test all entry/exit methods for full screen (F12, ESC, double-click, on-screen button).
    - [ ] Test all `OnScreenControlsPanel` functionalities.
    - [ ] Verify auto-hide behavior for controls and cursor.
    - [ ] Test video aspect ratio, rendering, and performance with various files/resolutions.
    - [ ] Identify and resolve any focus-related issues or event conflicts.