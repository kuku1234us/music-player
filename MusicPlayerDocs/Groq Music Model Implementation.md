# Groq Music Model Implementation Plan

## 1. Introduction: Why Use an LLM for Classification?

This document outlines the plan to integrate a music classification feature into the Music Player application using the Groq API and a Large Language Model (LLM). Currently, organizing music often relies solely on manual playlist creation or basic folder structures. While effective, identifying specific genres or moods across a large, inconsistently named library can be tedious.

By leveraging an LLM like Llama 3 via the fast Groq API, we can analyze filenames to automatically classify tracks based on various criteria (e.g., "Classical", "Jazz", "Happy Vocal"). This allows users to quickly filter large pools of potential tracks (like those added to the Selection Pool) and find music matching a specific need or mood, even if the filenames aren't perfectly structured. This feature aims to enhance music discovery and playlist creation within the application.

This plan follows a structured approach, starting with configuration, moving to the core AI logic implementation, and finally integrating the feature into the user interface.

## 2. Step 1: Throttling Configuration (Backend Setup)

**Goal:** To ensure our application respects the Groq API's rate limits (specifically the free tier limit of 30 requests per minute) to prevent errors and ensure stable operation.

**Rationale:** Calling an external API repeatedly without considering its limits can lead to temporary blocks (rate limiting) or even permanent restrictions. By implementing client-side throttling, we proactively manage our request rate, staying within the allowed limits.

**Implementation:**

1.  **Define Configuration:** We will add a new section to our main configuration file, `music_player/resources/music_player_config.yaml`, to store throttling parameters. This allows for easy adjustment without changing the code.

    ```yaml
    # Inside music_player_config.yaml (add this section)
    
    ai:
      groq:
        # Max requests per minute allowed by Groq (free tier is 30)
        # We set slightly lower to be safe.
        requests_per_minute: 28 
        # Number of filenames to send in each API call
        batch_size: 30 
    ```

2.  **Access Configuration:** The core AI logic module (`groq_music_model.py`, detailed in Step 2) will use the application's `SettingsManager` to read these values at runtime.
    *   `SettingsManager.instance().get('ai/groq/requests_per_minute', 28, SettingType.INT)`
    *   `SettingsManager.instance().get('ai/groq/batch_size', 30, SettingType.INT)`

3.  **Calculate Delay:** Based on these settings, the AI module will calculate the minimum delay required between sending batches to the API. The formula is:
    *   `batches_per_minute = requests_per_minute / items_per_batch` (Note: This isn't quite right, it should be `requests_per_minute` directly as each batch is one request)
    *   Corrected: `max_requests_per_minute = config_value`
    *   `minimum_seconds_per_request = 60.0 / max_requests_per_minute`
    *   This `minimum_seconds_per_request` value will be used in the throttling logic (Step 2).

## 3. Step 2: Implement the AI Prompting Model (`groq_music_model.py`)

**Goal:** To create a central module that handles loading prompt configurations, interacting with the `MusicClassifier`, managing the API call loop with throttling, and returning classified results.

**Rationale:** Separating this orchestration logic from the basic API interaction (`MusicPicks.py`) and the UI (`SelectionPoolWidget`) makes the code cleaner, easier to test, and more maintainable. It acts as a bridge between the user's request and the actual AI classification.

**Implementation:**

1.  **Create `music_player/ai/groq_music_model.py`:** This new file will contain the primary logic.

2.  **Define `GroqMusicModel` Class:**
    *   **`__init__(self)`:**
        *   Load and parse `aiprompts.json`.
            *   Determine the path: Use `SettingsManager` to get the working directory, then append `/playlists/aiprompts.json`. Handle potential `FileNotFoundError` or `json.JSONDecodeError`. Store the loaded list of prompt configurations (dictionaries).
        *   Instantiate `MusicClassifier` from `music_player.ai.MusicPicks`. Store it (e.g., `self.classifier`).
        *   Check `self.classifier.is_api_ready()`. Store this status (e.g., `self.api_ready`). If not ready, subsequent operations should be disabled.
        *   Load throttling settings (`requests_per_minute`, `batch_size`) from `SettingsManager` as described in Step 1.
        *   Calculate and store the `_min_request_interval_seconds = 60.0 / requests_per_minute`.
        *   **(Configuration Note):** Consider adding `model_name` to the `ai.groq` config section in `music_player_config.yaml` if a single model should be used globally. Alternatively, for more flexibility, the model name could be defined per-prompt within `aiprompts.json` (e.g., adding an optional `"model_name": "llama-3.1-8b-instant"` key). The implementation below assumes the model is currently defined within `MusicPicks.py`, but this should be revisited based on the desired configuration strategy.
    *   **`get_available_prompts(self) -> List[str]`:**
        *   Iterate through the loaded prompt configurations.
        *   Return a list of the `target_label` values from each configuration. This will populate the UI dropdown. Handle the case where loading failed.
    *   **`get_prompt_config_by_label(self, label: str) -> dict | None`:**
        *   Find and return the full configuration dictionary that matches the given `target_label`. Needed by the UI to pass the correct config to the classification method.
    *   **Modify `MusicPicks.MusicClassifier.classify_files`:**
        *   **Change Signature:** Update the method signature in `MusicPicks.py` to accept the chosen `prompt_config: dict` as an argument instead of hardcoding the classical prompt logic.
        *   **Generate Prompt:** Inside `classify_files`, use the passed `prompt_config` and the `generate_prompt` function (which we previously designed, perhaps move this function into `MusicPicks.py` or keep it utility) to create the dynamic prompt string based on the config's role, characteristics, examples, etc.
        *   **Remove Hardcoding:** Remove the hardcoded classical music rules, examples, and model name from `classify_files`. The model name could potentially be added to the `prompt_config` structure or remain a parameter configurable via `music_player_config.yaml`. Let's keep using the model defined in `MusicPicks.py` for now (`llama-3.3-70b-versatile`).
    *   **`classify_filenames(self, filenames: List[str], prompt_config: dict, progress_callback=None, error_callback=None) -> List[str]`:** (This will be the core method, likely called by a background thread).
        *   Check `self.api_ready`. Return empty list or raise error if not ready.
        *   Check if `prompt_config` is valid.
        *   **(Error Handling Strategy Note):** Define how specific errors should be handled. Consider implementing 1-2 automatic retries with exponential backoff for `RateLimitError` and `APIConnectionError`. Decide if batch-level parsing errors (from `error_handler`) should halt the entire process or just be logged while allowing other batches to proceed.
        *   Initialize `last_request_time = 0`.
        *   Initialize an empty list `classified_paths = []`.
        *   Get `batch_size` from settings (or use the value stored during `__init__`).
        *   **Loop through `filenames` in batches:**
            *   `current_time = time.time()`
            *   `elapsed_since_last = current_time - last_request_time`
            *   `wait_time = self._min_request_interval_seconds - elapsed_since_last`
            *   **Throttling:** If `wait_time > 0` and this isn't the first batch (`last_request_time != 0`), call `time.sleep(wait_time)`.
            *   Record `last_request_time = time.time()` *before* making the API call.
            *   Call `self.classifier.classify_files(batch, prompt_config, batch_callback=internal_batch_handler, error_callback=error_callback)`.
                *   **Note:** The existing `classify_files` in `MusicPicks` already loops internally. We need to decide: either `GroqMusicModel` handles batching *and* throttling OR `MusicPicks` handles batching and `GroqMusicModel` just adds throttling *between* calls to `MusicPicks`. Let's adapt `MusicPicks`:
                    *   Modify `MusicPicks.classify_files` to process *only one batch* at a time and return the classified files for *that batch*. Remove its internal batching loop.
                    *   The `classify_filenames` method in `GroqMusicModel` will now contain the primary loop, iterate through filenames in batches defined by settings, apply the `time.sleep` logic between batches, and call the modified `MusicPicks.classify_files` for each batch, accumulating the results.
            *   Update progress via `progress_callback` (e.g., percentage complete).
            *   Append results for the batch to `classified_paths`.
            *   Handle errors reported by `error_callback`. If a significant error occurs (like connection or rate limit), potentially stop processing and return partial results or an empty list.
        *   Return the final `classified_paths`.

## 4. Step 3: UI Integration (`SelectionPoolWidget`)

**Goal:** To provide a user interface within the Selection Pool for selecting an AI prompt and triggering the classification process, displaying the results by filtering the pool.

**Rationale:** The classification feature needs a clear entry point for the user. Integrating it directly into the `SelectionPoolWidget` makes sense as it operates on the tracks currently staged there. We must also ensure the UI remains responsive during the potentially long-running API calls.

**Implementation:**

1.  **Modify `music_player/ui/components/playlist_components/selection_pool.py`:**
    *   **Import:** `from music_player.ai.groq_music_model import GroqMusicModel` and potentially `from PyQt6.QtCore import QThread, pyqtSignal, QObject`.
    *   **`__init__`:**
        *   Instantiate the model: `self.groq_model = GroqMusicModel()`.
        *   Check readiness: `self.ai_enabled = self.groq_model.api_ready`. Print a warning if not enabled.
    *   **Add UI Elements to `_setup_ui` (in `header_layout`):**
        *   `self.ai_prompt_combo = QComboBox()`
        *   `self.ai_run_button = IconButton(icon_name='fa5s.magic', tooltip='Classify pool using selected AI prompt')`
        *   `self.ai_clear_filter_button = IconButton(icon_name='fa5s.times-circle', tooltip='Clear AI filter')`
        *   Populate `self.ai_prompt_combo`:
            *   Get prompts: `prompt_labels = self.groq_model.get_available_prompts()`.
            *   Add placeholder: `self.ai_prompt_combo.addItem("-- Select AI Filter --")`
            *   Add items: `self.ai_prompt_combo.addItems(prompt_labels)`.
        *   Disable combo and buttons if `not self.ai_enabled`.
        *   Hide clear button initially: `self.ai_clear_filter_button.hide()`
        *   **Add Progress Overlay Widget:**
            *   Create a simple `QWidget` (e.g., `self.progress_overlay`) as a direct child of `self.pool_table` (or potentially `self` if it should cover the header too).
            *   Style it with a semi-transparent background (e.g., `background-color: rgba(0, 0, 0, 0.7); border-radius: 4px;`).
            *   Add a `QLabel` inside the overlay to show text like "Processing..." and potentially a loading spinner icon (e.g., using `qta.SpinningIcon`).
            *   Ensure the overlay uses `raise_()` to be on top and `setGeometry()` to match the dimensions of the area it covers (e.g., `self.pool_table.geometry()`).
            *   Initially hide the overlay: `self.progress_overlay.hide()`.
    *   **Connect Signals in `_connect_signals`:**
        *   `self.ai_run_button.clicked.connect(self._on_classify_requested)`
        *   `self.ai_clear_filter_button.clicked.connect(self._clear_ai_filter)`
    *   **Implement Background Processing (`_on_classify_requested` and Worker Thread):**
        *   **Define Worker Class:** Create a simple `QObject` worker class (e.g., `ClassificationWorker`) within the file or imported.
            ```python
            class ClassificationWorker(QObject):
                finished = pyqtSignal(list) # Emits list of matching file paths
                error = pyqtSignal(str)
                progress = pyqtSignal(int) # Emit progress percentage (0-100)

                def __init__(self, model, filenames, config):
                    super().__init__()
                    self.groq_model = model
                    self.filenames = filenames
                    self.prompt_config = config
                    self.is_cancelled = False # Flag to signal cancellation

                def run(self):
                    classified_paths = [] # Accumulate results here
                    batch_size = self.groq_model.settings.get('ai/groq/batch_size', 30, SettingType.INT) # Get batch size
                    last_request_time = 0
                    min_interval = self.groq_model._min_request_interval_seconds # Use pre-calculated interval
                    
                    try:
                        # Loop and call the refactored MusicPicks.classify_files for each batch
                        for i in range(0, len(self.filenames), batch_size):
                            # --- Cancellation Check --- 
                            if self.is_cancelled:
                                print("[Worker] Cancellation requested, stopping.")
                                break # Exit the loop
                            # ------------------------
                            
                            batch = self.filenames[i:i + batch_size]
                            if not batch: continue

                            # --- Throttling --- 
                            current_time = time.time()
                            if last_request_time != 0: # Don't wait before the first request
                                elapsed_since_last = current_time - last_request_time
                                wait_time = min_interval - elapsed_since_last
                                if wait_time > 0:
                                    print(f"[Worker] Throttling: Waiting {wait_time:.2f} seconds.")
                                    time.sleep(wait_time)
                            # ------------------

                            # --- Cancellation Check (After potential sleep) --- 
                            if self.is_cancelled:
                                print("[Worker] Cancellation requested after sleep, stopping.")
                                break # Exit the loop
                            # ------------------------

                            last_request_time = time.time() # Record time before API call

                            # Callback to handle errors from *within* the batch processing
                            batch_errors = []
                            def error_handler(msg):
                               print(f"[Worker] Error during batch processing: {msg}")
                               batch_errors.append(msg)
                               # Decide if error is fatal; maybe set self.is_cancelled = True ?

                            # Call the modified MusicPicks method (assuming it processes one batch)
                            batch_results = self.groq_model.classifier.classify_files(
                                batch, 
                                self.prompt_config,
                                error_callback=error_handler 
                                # Assuming MusicPicks no longer handles batching/callbacks itself
                                # batch_callback=None # No longer needed from MusicPicks?
                            )
                            
                            # Handle errors that occurred *during* the batch processing
                            if batch_errors:
                                 # Combine errors and emit them? Or handle differently?
                                 self.error.emit("Errors occurred during batch: " + "; ".join(batch_errors))
                                 # Decide if we should continue or stop after batch errors
                                 # if fatal_error_occurred: self.is_cancelled = True

                            if batch_results:
                                 classified_paths.extend(batch_results)

                            # Emit progress after processing each batch
                            progress_percent = int(((i + len(batch)) / len(self.filenames)) * 100)
                            self.progress.emit(progress_percent)

                        # --- Loop Finished --- 
                        if not self.is_cancelled:
                           self.finished.emit(classified_paths)
                        else:
                           self.finished.emit([]) # Emit empty list if cancelled
                           
                    except Exception as e:
                        # Catch errors in the worker's main execution
                        print(f"[Worker] Unhandled exception: {e}")
                        self.error.emit(f"Worker thread error: {e}")
                        # Ensure finished is emitted even on unhandled exception?
                        if not self.is_cancelled: # Avoid double emit if cancelled caused exception
                            self.finished.emit([]) # Emit empty list on error too?
            ```
        *   **`_on_classify_requested(self)` Slot:**
            *   Check if AI is enabled: `if not self.ai_enabled: return`.
            *   Get selected prompt label from `self.ai_prompt_combo.currentText()`. 
            *   **Add Check:** `if self.ai_prompt_combo.currentIndex() == 0: return` # Check if default item is selected
            *   Get the corresponding config: `prompt_config = self.groq_model.get_prompt_config_by_label(selected_label)`. Handle if `None`.
            *   Get *currently visible* filenames from `self.pool_table`...
            *   Handle empty pool case...
            *   **Change Button State (Start):**
                *   Disconnect `self.ai_run_button.clicked` from `_on_classify_requested`.
                *   Set icon: `self.ai_run_button.setIcon(qta.icon('fa5s.stop'))` (or similar stop icon).
                *   Set tooltip: `self.ai_run_button.setToolTip('Stop AI classification')`.
                *   Connect `self.ai_run_button.clicked` to `self._on_stop_classification_requested`.
                *   Keep button enabled: `self.ai_run_button.setEnabled(True)`.
            *   **Show Overlay:** ...
            *   **Start Thread:** ... (Ensure worker has `is_cancelled` flag)

            *   **Add `_on_stop_classification_requested(self)` Slot:**
                *   Check if `self.classification_thread` and its worker exist and are running.
                *   `if hasattr(self, 'classification_thread') and self.classification_thread.isRunning():`
                    *   Access the worker instance (this might require storing a reference to the worker when the thread starts, e.g., `self.classification_worker = worker`).
                    *   `if hasattr(self, 'classification_worker') and self.classification_worker:`
                        *   `print("[UI] Stop requested. Signalling worker...")`
                        *   `self.classification_worker.is_cancelled = True`
                    *   **(Optional) Change Button State Immediately (to indicate request received):**
                        *   Maybe disable the button temporarily: `self.ai_run_button.setEnabled(False)`
                        *   Set tooltip: `self.ai_run_button.setToolTip('Stopping...')`
                    *   **(Do NOT quit/terminate thread forcefully here, let the worker finish cleanly)**

            *   **Implement Result/Error Slots:**
                *   **`_on_classification_finished(self, matching_paths: list)`:**
                    *   **Hide Overlay:** ...
                    *   **Reset Button State (Finish/Cancel):**
                        *   Set icon: `self.ai_run_button.setIcon(qta.icon('fa5s.magic'))`.
                        *   Set tooltip: `self.ai_run_button.setToolTip('Classify pool using selected AI prompt')`.
                        *   Safely disconnect `self.ai_run_button.clicked` from `_on_stop_classification_requested` (use try-except block).
                        *   Connect `self.ai_run_button.clicked` back to `_on_classify_requested` (use try-except block).
                        *   Enable button: `self.ai_run_button.setEnabled(self.ai_enabled)`.
                    *   **(Important): Clean up worker/thread references:**
                        *   `if hasattr(self, 'classification_worker'): self.classification_worker = None`
                        *   `if hasattr(self, 'classification_thread'): self.classification_thread = None`
                    *   Convert `matching_paths` to a set for efficient lookup.
                    *   Filter the table: Iterate through `self.pool_table` rows. Get the path for each row. Hide the row (`setRowHidden(True)`) if its path is *not* in the `matching_paths` set. Show rows (`setRowHidden(False)`) if their path *is* in the set.
                    *   **Show Clear Button:** `self.ai_clear_filter_button.show()`.
                *   **`_on_classification_error(self, error_message: str)`:**
                    *   **Hide Overlay:** ...
                    *   **Reset Button State (Error):** (Same logic as in `_on_classification_finished` to reset button)
                    *   **(Important): Clean up worker/thread references:** (Same logic as in `_on_classification_finished`)
                    *   Show error using `QMessageBox.critical(...)`.

## 5. Conclusion and Next Steps

This plan provides a comprehensive approach to integrating Groq-based AI classification into the Music Player. By following these steps, we will add configuration for rate limiting, implement a robust AI model layer with throttling, modify the existing classifier, and integrate the feature seamlessly into the Selection Pool UI using background threads for responsiveness.

**Next steps involve:**

1.  Implementing the configuration changes in `music_player_config.yaml`.
2.  Developing the `GroqMusicModel` class in `groq_music_model.py`.
3.  Refactoring `MusicPicks.py` as described.
4.  Implementing the UI changes and threading logic in `SelectionPoolWidget`.
5.  Thorough testing, including handling API errors, empty pools, and UI responsiveness.
