"""
MusicPicks module for classifying music files using Groq API.
This module handles API calls to Groq for music classification.
"""
import os
import sys
import groq
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
groq_api_key = os.getenv("GROQ_API_KEY")


class MusicClassifier:
    """
    Class for classifying music files using Groq API.
    """
    def __init__(self):
        """Initialize the classifier with the Groq API client."""
        self.client = None
        try:
            # Ensure API key exists before trying to create client
            if not groq_api_key:
                raise ValueError("GROQ_API_KEY not found in environment.")
            self.client = groq.Client(api_key=groq_api_key)
        except Exception as e:
            print(f"Failed to initialize Groq client: {e}")
            self.client = None

    def is_api_ready(self):
        """Check if the API client is properly initialized."""
        return self.client is not None

    def classify_files(self, filenames, batch_callback=None, error_callback=None):
        """
        Classify music files as classical or not.
        
        Args:
            filenames: List of file paths to classify
            batch_callback: Optional callback for batch results
            error_callback: Optional callback for errors
            
        Returns:
            List of classified files (paths that are likely classical music)
        """
        if not self.client:
            error_msg = "Groq client not initialized."
            if error_callback:
                error_callback(error_msg)
            else:
                print(error_msg)
            return []
        
        classified_files = []
        batch_size = 30
        model_name = "llama-3.3-70b-versatile"

        for i in range(0, len(filenames), batch_size):
            batch = filenames[i:i + batch_size]
            if not batch:  # Skip empty batches
                continue
                
            batch_filenames_only = [os.path.basename(f) for f in batch]
            
            # Create a numbered list of filenames for the prompt
            prompt_list = "\n".join([f"{idx + 1}. {name}" for idx, name in enumerate(batch_filenames_only)])
            
            prompt = (
                f"You are an expert in classical music who can identify classical music files by their filenames.\n\n"
                f"Classical music files often contain:\n"
                f"- Names of classical composers (e.g., Mozart, Beethoven, Bach, Tchaikovsky, Chopin, Vivaldi, Handel)\n"
                f"- Classical music terms (e.g., Symphony, Sonata, Concerto, Nocturne, Étude, Prelude, Fugue)\n"
                f"- Opus numbers (e.g., Op. 9, BWV 847)\n"
                f"- Classical music notation (e.g., Adagio, Allegro, Andante)\n\n"
                f"Examples of classical music files:\n"
                f"- 'Beethoven_Symphony_No_9_Ode_to_Joy.mp3' (YES)\n"
                f"- 'Mozart_Piano_Concerto_21.flac' (YES)\n"
                f"- 'Tchaikovsky_Swan_Lake_Suite.wav' (YES)\n"
                f"- 'pop_summer_hit_2023.mp3' (NO)\n"
                f"- 'rock_guitar_solo.mp3' (NO)\n\n"
                f"Analyze the following list of filenames. For each filename, determine if it is likely a classical music file. "
                f"Respond with 'Yes' or 'No' for each filename. Your response must be a numbered list matching the input, "
                f"with each line containing only the number, a period, a space, and then 'Yes' or 'No'. For example:\n"
                f"1. Yes\n2. No\n3. Yes\n\nFilenames:\n{prompt_list}"
            )

            try:
                print(f"Sending batch {(i // batch_size) + 1} of {(len(filenames) + batch_size - 1) // batch_size} to Groq...")
                chat_completion = self.client.chat.completions.create(
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    model=model_name,
                )
                response_content = chat_completion.choices[0].message.content
                
                # Parse the response robustly
                lines = response_content.strip().split('\n')
                print(f"Received response for batch {(i // batch_size) + 1}:\n{response_content[:200]}...")
                
                batch_classified_files = []  # Store files classified in this batch
                
                for line_num, line in enumerate(lines):
                    line = line.strip()
                    if not line: continue  # Skip empty lines
                    try:
                        parts = line.split('. ', 1)
                        if len(parts) == 2 and parts[0].isdigit():
                            list_num = int(parts[0])
                            answer = parts[1].strip().lower()
                            
                            # Calculate the original index in the full filenames list
                            original_file_index = i + list_num - 1 
                            
                            if 0 <= original_file_index < len(filenames):
                                if answer == "yes":
                                    file_path = filenames[original_file_index]
                                    classified_files.append(file_path)
                                    batch_classified_files.append(file_path)
                                elif answer == "no":
                                    pass
                                else:
                                    print(f"Warning: Unexpected answer '{answer}' for file index {original_file_index} (list num {list_num}) in response line: '{line}'")
                            else:
                                print(f"Warning: Parsed list number {list_num} is out of range for the current batch/overall file list. Line: '{line}'")
                        else:
                            print(f"Warning: Could not parse response line format: '{line}'")
                            
                    except Exception as parse_err:
                        print(f"Error parsing response line: '{line}'. Error: {parse_err}")
                
                # Call the batch callback if provided
                if batch_classified_files and batch_callback:
                    batch_callback(batch_classified_files)

            except groq.APIConnectionError as e:
                error_msg = f"Groq Connection Error: {e}"
                if error_callback:
                    error_callback(error_msg)
                else:
                    print(error_msg)
                return []  # Stop processing on connection error
                
            except groq.RateLimitError as e:
                error_msg = f"Groq Rate Limit Error: {e}. Try again later."
                if error_callback:
                    error_callback(error_msg)
                else:
                    print(error_msg)
                return []  # Stop processing on rate limit error
                
            except groq.APIStatusError as e:
                # Provide more detail from the API status error
                error_detail = f"Groq API Error (Status {e.status_code}): {e.message}"
                if hasattr(e, 'body') and e.body and 'error' in e.body:
                    error_detail += f" - {e.body['error'].get('message', 'No additional details.')}"
                if error_callback:
                    error_callback(error_detail)
                else:
                    print(error_detail)
                return []  # Stop processing on API status error
                
            except Exception as e:
                error_msg = f"Unexpected Groq API Error: {e}"
                if error_callback:
                    error_callback(error_msg)
                else:
                    print(error_msg)
                return []  # Stop processing on other errors

        return classified_files