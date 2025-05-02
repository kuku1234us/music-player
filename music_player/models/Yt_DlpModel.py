"""
yt-dlp model Encapsulates logic that deals with yt-dlp
"""
import sys

class YtDlpModel:
    """
    Model for yt-dlp operations and format string generation.
    This class encapsulates all the logic related to creating format strings
    for the yt-dlp command line tool.
    """

    @staticmethod
    def generate_format_string(resolution=None, use_https=True, use_m4a=True, subtitle_lang=None, use_cookies=False):
        """
        Generate the yt-dlp format string based on the provided parameters.
        
        Args:
            resolution (int, optional): Video resolution (1080, 720, 480, None for audio only)
            use_https (bool): Whether to prefer HTTPS protocol
            use_m4a (bool): Whether to prefer M4A/MP4 formats
            subtitle_lang (str, optional): Language code for subtitles (e.g., 'en', 'es', etc.) or None to disable
            use_cookies (bool): Whether to use Firefox cookies to bypass YouTube bot verification
            
        Returns:
            dict: Dictionary with format options for yt-dlp
        """
        format_options = {}
        
        # Add modern browser-based extraction method to fix PhantomJS warnings
        format_options['extractor_args'] = {
            'youtube': {
                # No specific player client requirement
            }
        }
        
        print(f"DEBUG: YtDlpModel.generate_format_string called with: resolution={resolution}, use_https={use_https}, use_m4a={use_m4a}, subtitle_lang={subtitle_lang}, use_cookies={use_cookies}")
        
        # Add browser cookies option if enabled
        if use_cookies:
            import os
            
            # Use the existing cookie file in the Docs directory
            # Get the base directory of the application
            if getattr(sys, 'frozen', False):
                # Running as compiled executable
                base_dir = os.path.dirname(sys.executable)
            else:
                # Running from script
                import pathlib
                base_dir = pathlib.Path(__file__).parent.parent.parent.parent.absolute()
                
            # Path to the cookie file
            cookie_file = os.path.join(base_dir, 'Docs', 'yt_cookies.txt')
            
            if os.path.exists(cookie_file):
                format_options['cookies'] = cookie_file
                print(f"DEBUG: Using existing cookie file: {cookie_file}")
            else:
                print(f"DEBUG: Cookie file not found at: {cookie_file}")
                # Fallback to standard method
                format_options['cookies_from_browser'] = 'firefox'
                print("DEBUG: Falling back to standard firefox cookie extraction")
        
        # Add more flexible subtitle format handling
        if subtitle_lang:
            format_options['writesubtitles'] = True
            format_options['writeautomaticsub'] = True  # Include auto-generated subtitles
            
            # Set the language(s) to download
            if isinstance(subtitle_lang, list):
                # If subtitle_lang is a list (e.g., ['zh-CN', 'zh-TW'] for Chinese)
                format_options['subtitleslangs'] = subtitle_lang
                print(f"DEBUG: Multiple subtitle languages requested: {subtitle_lang}")
            elif subtitle_lang.lower() == 'all':
                format_options['subtitleslangs'] = ['all']
            else:
                format_options['subtitleslangs'] = [subtitle_lang]
                
            # Accept multiple subtitle formats in order of preference
            format_options['subtitlesformat'] = 'srt/vtt/ttml/best'
            
            # Embed subtitles for video downloads
            if resolution:
                format_options['embedsubtitles'] = True
        
        if resolution:
            print(f"DEBUG: Generating video format with resolution: {resolution}")
            # Video format - exclude AV1 codec for iOS compatibility
            format_str = f"bestvideo[height<={resolution}][vcodec!*=av01]"
            if use_https:
                format_str += "[protocol=https]"
            if use_m4a:
                format_str += "[ext=mp4]"
            
            # Audio format
            audio_str = "bestaudio"
            if use_https:
                audio_str += "[protocol=https]"
            if use_m4a:
                audio_str += "[ext=m4a]"
            
            # Fall back options - also exclude AV1 in fallback
            fallback = f"best[height<={resolution}][vcodec!*=av01]"
            if use_https:
                fallback += "[protocol=https]"
            if use_m4a and resolution:
                fallback += "[ext=mp4]"
            
            # Complete format string
            format_str = f"{format_str}+{audio_str}/{fallback}/best"
            format_options["format"] = format_str
            
            # Force MP4 output if m4a is selected
            if use_m4a:
                format_options["merge_output_format"] = "mp4"
                
            # Add subtitle embedding postprocessor if we're downloading subtitles
            if subtitle_lang:
                format_options["postprocessors"] = [
                    {"key": "FFmpegEmbedSubtitle"}
                ]
                
            print(f"DEBUG: Video format string: {format_str}")
            
        else:
            print(f"DEBUG: Generating audio-only format")
            # Audio only format
            format_str = "bestaudio"
            if use_https:
                format_str += "[protocol=https]"
            if use_m4a:
                format_str += "[ext=m4a]"
                format_options["merge_output_format"] = "m4a"
            else:
                format_str += "/best"
            
            format_options["format"] = format_str
                
            print(f"DEBUG: Audio-only format string: {format_str}")
        
        print(f"DEBUG: Final format options: {format_options}")
        return format_options
    
    @staticmethod
    def get_video_formats(video_url):
        """
        Get available formats for a video URL.
        This would call yt-dlp to list available formats.
        
        Not implemented yet - placeholder for future functionality.
        """
        # This would use subprocess to call yt-dlp -F video_url
        # and parse the results
        pass
    
    @staticmethod
    def generate_download_options(format_options, output_path=None, output_template=None):
        """
        Generate full download options for yt-dlp.
        
        Args:
            format_options (dict): Format options from generate_format_string
            output_path (str, optional): Output directory path
            output_template (str, optional): Output filename template
            
        Returns:
            dict: Complete options dictionary for yt-dlp
        """
        options = format_options.copy()
        
        if output_path:
            options["paths"] = {"home": output_path}
            
        if output_template:
            options["outtmpl"] = {"default": output_template}
            
        return options 