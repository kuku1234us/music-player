# music_player/ai/groq_music_model.py

import os
import json
import time
import groq # Import groq
from typing import List, Dict, Optional, Any, Callable # Added Callable

# Import SettingsManager and SettingType
from qt_base_app.models.settings_manager import SettingsManager, SettingType
from music_player.models.playlist import get_default_working_dir

# Import the QSettings key constant
from music_player.models.settings_defs import GROQ_API_QSETTINGS_KEY

# Helper function to generate prompt (could be moved to MusicPicks or kept here)
# (Using the version defined previously in the plan documentation)
def generate_prompt(config: dict, batch_filenames: list) -> str:
    """Generates the full LLM prompt from a config dictionary and filenames."""

    prompt_lines = []

    # 1. Role
    prompt_lines.append(f"You are an {config.get('role', 'expert classifier')}.")
    prompt_lines.append("") # Add newline

    # 2. Positive Characteristics
    if config.get("positive_characteristics"):
        prompt_lines.append(f"{config.get('target_label', 'Target')} files often contain:")
        for char in config["positive_characteristics"]:
            prompt_lines.append(f"- {char}")
        prompt_lines.append("")

    # 3. Negative Characteristics (Optional)
    if config.get("negative_characteristics"):
        prompt_lines.append(f"Files less likely to be {config.get('target_label', 'Target')} might contain:")
        for char in config["negative_characteristics"]:
            prompt_lines.append(f"- {char}")
        prompt_lines.append("")

    # 4. Examples (Few-Shot)
    prompt_lines.append("Examples:")
    if config.get("positive_examples"):
        for example in config["positive_examples"]:
            prompt_lines.append(f"- '{example}' (YES)")
    if config.get("negative_examples"):
        for example in config["negative_examples"]:
            prompt_lines.append(f"- '{example}' (NO)")
    prompt_lines.append("")

    # 5. Task and Output Format
    prompt_lines.append(f"Analyze the following list of filenames. For each filename, determine if it is likely a {config.get('target_label', 'Target')} file. ")
    prompt_lines.append("Respond with 'Yes' or 'No' for each filename. Your response must be a numbered list matching the input, with each line containing only the number, a period, a space, and then 'Yes' or 'No'. For example:")
    prompt_lines.append("1. Yes\n2. No\n3. Yes") # Static example format
    prompt_lines.append("")

    # 6. Input Data
    prompt_lines.append("Filenames:")
    for idx, name in enumerate(batch_filenames):
        prompt_lines.append(f"{idx + 1}. {name}")

    return "\n".join(prompt_lines)

class GroqMusicModel:
    """
    Orchestrates music classification using Groq API.
    Handles prompt loading, configuration, throttling, API calls, and batch processing.
    """
    def __init__(self):
        """
        Initializes the GroqMusicModel.
        """
        # Get SettingsManager instance
        self.settings = SettingsManager.instance()
        
        self.prompt_configs: List[Dict[str, Any]] = []
        self.groq_client: Optional[groq.Client] = None 
        self.api_ready: bool = False
        
        # --- Load settings from SettingsManager's YAML config --- 
        self.model_name: str = self.settings.get_yaml_config('ai.groq.model_name', "llama-3.1-8b-instant")
        self.batch_size: int = self.settings.get_yaml_config('ai.groq.batch_size', 30)
        requests_per_minute: int = self.settings.get_yaml_config('ai.groq.requests_per_minute', 28)
        
        if requests_per_minute > 0:
            self._min_request_interval_seconds: float = 60.0 / requests_per_minute
        else:
            self._min_request_interval_seconds: float = 2.0 # Default if invalid RPM
            
        print(f"AI Config: Model={self.model_name}, BatchSize={self.batch_size}, Interval={self._min_request_interval_seconds:.2f}s")
        # ---------------------------------------------------------
        
        # --- Get Groq API Key using SettingsManager (QSettings key) ---
        self.groq_api_key = self.settings.get(GROQ_API_QSETTINGS_KEY, '', SettingType.STRING) 
        # -----------------------------------------------------------
        
        self._load_prompt_configs()
        self._initialize_groq_client()

    def _load_prompt_configs(self):
        """Loads AI prompt configurations from the JSON file."""
        try:
            # Determine path relative to working directory
            working_dir = get_default_working_dir()
            prompts_path = working_dir / "playlists" / "aiprompts.json"
            
            if not prompts_path.exists():
                print(f"Warning: AI prompts file not found at {prompts_path}")
                return
                
            with open(prompts_path, 'r', encoding='utf-8') as f:
                self.prompt_configs = json.load(f)
            print(f"Successfully loaded {len(self.prompt_configs)} AI prompt configurations.")
        except json.JSONDecodeError as e:
            print(f"Error parsing aiprompts.json: {e}")
            self.prompt_configs = []
        except Exception as e:
            print(f"Error loading AI prompts: {e}")
            self.prompt_configs = []

    def _initialize_groq_client(self):
        """Initializes the Groq client and checks API readiness."""
        try:
            # Use the key retrieved in __init__
            if not self.groq_api_key: 
                raise ValueError("GROQ API Key not found via SettingsManager (check Preferences).")
            self.groq_client = groq.Client(api_key=self.groq_api_key)
            self.api_ready = True 
            print("Groq API client initialized successfully.")
        except Exception as e:
            print(f"Failed to initialize Groq client: {e}")
            self.groq_client = None
            self.api_ready = False

    def get_available_prompts(self) -> List[str]:
        """Returns a list of target labels for the loaded prompts."""
        if not self.prompt_configs:
            return []
        return [config.get("target_label", f"Unnamed Prompt {i+1}") for i, config in enumerate(self.prompt_configs)]

    def get_prompt_config_by_label(self, label: str) -> Optional[Dict[str, Any]]:
        """Finds and returns the prompt configuration matching the label."""
        for config in self.prompt_configs:
            if config.get("target_label") == label:
                return config
        return None

    def classify_filenames(
        self, 
        filenames: List[str], 
        prompt_config: Dict[str, Any], 
        worker_cancelled_check = lambda: False,
        progress_callback = None,
        error_callback = None
    ) -> List[str]:
        """
        Classifies filenames using the selected prompt, handling batching, throttling, and API calls.

        Args:
            filenames (List[str]): List of full file paths to classify.
            prompt_config (Dict[str, Any]): The configuration dictionary for the chosen prompt.
            worker_cancelled_check (Callable[[], bool]): Function to call to check if cancellation was requested.
            progress_callback (Callable[[int, int], None]): Callback for progress (current_index, total_files).
            error_callback (Callable[[str], None]): Callback for reporting errors.

        Returns:
            List[str]: List of full file paths classified as matching the prompt's target.
        """
        if not self.api_ready or not self.groq_client:
            msg = "Groq API not ready."
            if error_callback: error_callback(msg)
            else: print(msg)
            return []

        if not prompt_config or not filenames:
            return [] # Nothing to do

        classified_paths = []
        last_request_time = 0
        total_files = len(filenames)

        print(f"Starting classification for '{prompt_config.get('target_label', 'Unknown')}' with {total_files} files using {self.model_name}.")

        for i in range(0, total_files, self.batch_size):
            # --- Cancellation Check --- 
            if worker_cancelled_check():
                print("[GroqMusicModel] Cancellation requested, stopping classification.")
                break # Exit the loop
            # ------------------------
            
            batch_full_paths = filenames[i : i + self.batch_size]
            if not batch_full_paths: continue

            # --- Throttling --- 
            current_time = time.time()
            if last_request_time != 0: # Don't wait before the first request
                elapsed_since_last = current_time - last_request_time
                wait_time = self._min_request_interval_seconds - elapsed_since_last
                if wait_time > 0:
                    print(f"[GroqMusicModel] Throttling: Waiting {wait_time:.2f} seconds.")
                    # Allow interruption during sleep
                    for _ in range(int(wait_time * 10)): # Check every 100ms
                         if worker_cancelled_check(): break
                         time.sleep(0.1)
                    if worker_cancelled_check(): 
                        print("[GroqMusicModel] Cancellation requested during sleep.")
                        break
            # ------------------

            # --- Cancellation Check (After potential sleep) --- 
            if worker_cancelled_check():
                print("[GroqMusicModel] Cancellation requested before batch processing.")
                break # Exit the loop
            # ------------------------

            last_request_time = time.time() # Record time before API call

            # Generate the prompt for this specific batch using filenames only
            # --- Add logging ---
            print("[GroqMusicModel] Extracting basenames...")
            # -------------------
            batch_filenames_only = [os.path.basename(f) for f in batch_full_paths]
            # --- Add logging ---
            print("[GroqMusicModel] Generating prompt string...")
            # -------------------
            prompt_string = generate_prompt(prompt_config, batch_filenames_only)
            # --- Add logging ---
            print("[GroqMusicModel] Prompt string generated.")
            # -------------------

            # --- DEBUG: Print the final prompt --- 
            print("-" * 20 + " PROMPT START " + "-" * 20)
            print(prompt_string)
            print("-" * 20 + " PROMPT END " + "-" * 22)
            # -------------------------------------

            try:
                # === API Call and Parsing Logic Moved Here ===
                print(f"[GroqMusicModel] Processing batch {i // self.batch_size + 1} / {(total_files + self.batch_size - 1) // self.batch_size}")
                
                # --- Add logging before API call ---
                print("[GroqMusicModel] Attempting Groq API call...")
                # -------------------------------------
                
                chat_completion = self.groq_client.chat.completions.create(
                    messages=[
                        {"role": "user", "content": prompt_string}
                    ],
                    model=self.model_name,
                )
                
                # --- Add logging after API call ---
                print("[GroqMusicModel] Groq API call finished.")
                # -----------------------------------
                
                response_content = chat_completion.choices[0].message.content
                
                # Parse the response robustly
                lines = response_content.strip().split('\n')
                # print(f"Received response content:\n{response_content[:300]}...") # Optional detailed logging
                
                for line_num, line in enumerate(lines):
                    line = line.strip()
                    if not line: continue
                    try:
                        parts = line.split('. ', 1)
                        if len(parts) == 2 and parts[0].isdigit():
                            list_num = int(parts[0])
                            answer = parts[1].strip().lower()
                            batch_index = list_num - 1 
                            
                            if 0 <= batch_index < len(batch_full_paths):
                                if answer == "yes":
                                    file_path = batch_full_paths[batch_index] # Use full path
                                    classified_paths.append(file_path)
                                elif answer == "no":
                                    pass # Correctly identified as not matching
                                else:
                                    # Just print parsing warnings
                                    print(f"Warning: Unexpected answer '{answer}' for batch index {batch_index} (list num {list_num}) in line: '{line}'")
                            else:
                                print(f"Warning: Parsed list number {list_num} out of range for current batch size {len(batch_full_paths)}. Line: '{line}'")
                        else:
                            print(f"Warning: Could not parse response line format: '{line}'")
                    except Exception as parse_err:
                         print(f"Error parsing response line: '{line}'. Error: {parse_err}")
                # ==============================================

            # === Exception Handling Moved Here ===
            except groq.APIConnectionError as e:
                msg = f"Groq Connection Error: {e}"
                if error_callback: error_callback(msg)
                else: print(msg)
                print("[GroqMusicModel] Halting classification due to connection error.")
                break # Stop processing further batches
            except groq.RateLimitError as e:
                msg = f"Groq Rate Limit Error: {e}."
                if error_callback: error_callback(msg)
                else: print(msg)
                print("[GroqMusicModel] Halting classification due to rate limit.")
                break # Stop processing further batches
            except groq.APIStatusError as e:
                error_detail = f"Groq API Error (Status {e.status_code}): {e.message}"
                if hasattr(e, 'body') and e.body and 'error' in e.body:
                    error_detail += f" - {e.body['error'].get('message', 'No additional details.')}"
                if error_callback: error_callback(error_detail)
                else: print(error_detail)
                print("[GroqMusicModel] Halting classification due to API status error.")
                break # Stop processing further batches
            except Exception as e:
                msg = f"Unexpected Error during batch processing: {e}"
                if error_callback: error_callback(msg)
                else: print(msg)
                print("[GroqMusicModel] Halting classification due to unexpected error.")
                break # Stop processing further batches
            # ======================================
            
            # Update progress after processing batch
            if progress_callback:
                current_processed = min(i + self.batch_size, total_files)
                progress_callback(current_processed, total_files)

        # --- Loop Finished --- 
        print(f"Finished classification. Found {len(classified_paths)} matching files.")
        return classified_paths 