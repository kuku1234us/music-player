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
    def generate_format_string(resolution=None, use_https=True, use_m4a=True, subtitle_lang=None, use_cookies=False, prefer_best_video=False, prefer_avc=False):
        """
        Generate the yt-dlp format string based on the provided parameters.
        
        Args:
            resolution (int, optional): Target video resolution (720, 1080, None for audio only or best)
            use_https (bool): Whether to prefer HTTPS protocol
            use_m4a (bool): Whether to prefer M4A/MP4 formats
            subtitle_lang (str, optional): Language code for subtitles (e.g., 'en', 'es', etc.) or None to disable
            use_cookies (bool): Whether to use Firefox cookies to bypass YouTube bot verification
            prefer_best_video (bool): If True, prefer best video quality regardless of resolution
            prefer_avc (bool): If True, prefer AVC codec (H.264) for better device compatibility
            
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
        
        print(f"DEBUG: YtDlpModel.generate_format_string called with: resolution={resolution}, use_https={use_https}, use_m4a={use_m4a}, subtitle_lang={subtitle_lang}, use_cookies={use_cookies}, prefer_best_video={prefer_best_video}, prefer_avc={prefer_avc}")
        
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
        
        # Add more flexible subtitle format handling, only for video downloads
        is_video_download = resolution is not None or prefer_best_video
        if subtitle_lang and is_video_download:
            format_options['writesubtitles'] = True
            format_options['writeautomaticsub'] = True  # Include auto-generated subtitles
            
            # Helper to expand language codes for English and Chinese
            def expand_subtitle_lang(lang):
                l = lang.lower()
                # English
                if l in ['en', 'english']:
                    return ['en', 'en-GB', 'en-US', 'en-en-GB']
                # Simplified Chinese
                elif l in ['zh', 'zh-cn', 'zh-hans']:
                    return ['zh', 'zh-CN', 'zh-Hans', 'zh-Hans-CN', 'zh-Hans-en-GB']
                # Traditional Chinese
                elif l in ['zh-tw', 'zh-hant']:
                    return ['zh-TW', 'zh-Hant', 'zh-Hant-TW', 'zh-Hant-en-GB']
                # All
                elif l == 'all':
                    return ['all']
                # Fallback: just return as is
                else:
                    return [lang]

            # Set the language(s) to download, with robust expansion for English and Chinese
            if isinstance(subtitle_lang, list):
                expanded_langs = []
                for lang in subtitle_lang:
                    expanded_langs.extend(expand_subtitle_lang(lang))
                # Remove duplicates while preserving order
                seen = set()
                expanded_langs = [x for x in expanded_langs if not (x in seen or seen.add(x))]
                format_options['subtitleslangs'] = expanded_langs
                print(f"DEBUG: Multiple subtitle languages requested: {expanded_langs}")
            else:
                expanded_langs = expand_subtitle_lang(subtitle_lang)
                format_options['subtitleslangs'] = expanded_langs
                print(f"DEBUG: Subtitle language(s) requested: {expanded_langs}")
                
            # Accept multiple subtitle formats in order of preference
            format_options['subtitlesformat'] = 'srt/vtt/ttml/best'
            
            # Embed subtitles for video downloads (this check is now redundant but safe to keep)
            if resolution or prefer_best_video:
                format_options['embedsubtitles'] = True
        
        # Determine codec filtering based on parameters
        codec_filter = ""
        if prefer_avc:
            # Prefer AVC codec (H.264) for better device compatibility
            codec_filter = "[vcodec^=avc]"
            print(f"DEBUG: Using AVC codec filter for better compatibility")
        elif not prefer_best_video:
            # If not using best video and not explicitly preferring AVC, exclude AV1 for compatibility
            codec_filter = "[vcodec!*=av01]"
            print(f"DEBUG: Excluding AV1 codec for better compatibility")
        
        # Prepare protocol and format constraints
        protocol_constraint = "[protocol=https]" if use_https else ""
        video_format_constraint = "[ext=mp4]" if use_m4a else ""
        audio_format_constraint = "[ext=m4a]" if use_m4a else ""
        
        # Prepare audio part of format string
        audio_str = "bestaudio"
        if use_https:
            audio_str += protocol_constraint
        if use_m4a:
            audio_str += audio_format_constraint
        
        if resolution and not prefer_best_video:
            # Resolution-specific format with improved handling for portrait/landscape videos
            print(f"DEBUG: Generating video format with target resolution: {resolution}p")
            
            # Build video format string parts with codec filter applied to each option separately
            if resolution == 720:
                # For 720p - try exact height=720 (landscape) or width=720 (portrait) or height<=720
                video_parts = []
                
                # Option 1: Exact height match (landscape) WITH AUDIO
                part1 = f"bestvideo[height=720]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str}"
                video_parts.append(part1)
                
                # Option 2: Exact width match (portrait) WITH AUDIO
                part2 = f"bestvideo[width=720]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str}"
                video_parts.append(part2)
                
                # Option 3: Height <= resolution (fallback) WITH AUDIO
                part3 = f"bestvideo[height<=720]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str}"
                video_parts.append(part3)
                
                # Join all video+audio options with "/"
                format_str = "/".join(video_parts)
                
            elif resolution == 1080:
                # For 1080p
                video_parts = []
                part1 = f"bestvideo[height=1080]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str}"
                part2 = f"bestvideo[width=1080]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str}"
                part3 = f"bestvideo[height<=1080]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str}"
                video_parts.extend([part1, part2, part3])
                format_str = "/".join(video_parts)
                
            elif resolution == 1440:
                # For 1440p
                video_parts = []
                part1 = f"bestvideo[height=1440]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str}"
                part2 = f"bestvideo[width=1440]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str}"
                part3 = f"bestvideo[height<=1440]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str}"
                video_parts.extend([part1, part2, part3])
                format_str = "/".join(video_parts)
                
            elif resolution == 2160:
                # For 4K
                video_parts = []
                part1 = f"bestvideo[height=2160]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str}"
                part2 = f"bestvideo[width=2160]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str}"
                part3 = f"bestvideo[height<=2160]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str}"
                video_parts.extend([part1, part2, part3])
                format_str = "/".join(video_parts)
                
            else:
                # For other resolutions
                format_str = f"bestvideo[height<={resolution}]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str}"
            
            # Build fallback options with codec filter applied to each option separately
            if resolution == 720:
                fallback_parts = []
                part1 = f"best[height=720]{codec_filter}{protocol_constraint}{video_format_constraint}"
                part2 = f"best[width=720]{codec_filter}{protocol_constraint}{video_format_constraint}"
                part3 = f"best[height<=720]{codec_filter}{protocol_constraint}{video_format_constraint}"
                fallback_parts.extend([part1, part2, part3])
                fallback = "/".join(fallback_parts)
                
            elif resolution == 1080:
                fallback_parts = []
                part1 = f"best[height=1080]{codec_filter}{protocol_constraint}{video_format_constraint}"
                part2 = f"best[width=1080]{codec_filter}{protocol_constraint}{video_format_constraint}"
                part3 = f"best[height<=1080]{codec_filter}{protocol_constraint}{video_format_constraint}"
                fallback_parts.extend([part1, part2, part3])
                fallback = "/".join(fallback_parts)
                
            elif resolution == 1440:
                fallback_parts = []
                part1 = f"best[height=1440]{codec_filter}{protocol_constraint}{video_format_constraint}"
                part2 = f"best[width=1440]{codec_filter}{protocol_constraint}{video_format_constraint}"
                part3 = f"best[height<=1440]{codec_filter}{protocol_constraint}{video_format_constraint}"
                fallback_parts.extend([part1, part2, part3])
                fallback = "/".join(fallback_parts)
                
            elif resolution == 2160:
                fallback_parts = []
                part1 = f"best[height=2160]{codec_filter}{protocol_constraint}{video_format_constraint}"
                part2 = f"best[width=2160]{codec_filter}{protocol_constraint}{video_format_constraint}"
                part3 = f"best[height<=2160]{codec_filter}{protocol_constraint}{video_format_constraint}"
                fallback_parts.extend([part1, part2, part3])
                fallback = "/".join(fallback_parts)
                
            else:
                fallback = f"best[height<={resolution}]{codec_filter}{protocol_constraint}{video_format_constraint}"
            
            # Complete format string with proper audio merging
            format_str = f"{format_str}/{fallback}/best"
            format_options["format"] = format_str
            
            # Force MP4 output if m4a is selected
            if use_m4a:
                format_options["merge_output_format"] = "mp4"
            
            # Add subtitle embedding postprocessor if we're downloading subtitles
            if subtitle_lang:
                format_options["postprocessors"] = [
                    {"key": "FFmpegEmbedSubtitle"}
                ]
                
            print(f"DEBUG: Resolution-specific format string: {format_str}")
                
        elif prefer_best_video:
            # Best video format - no resolution limiting
            print(f"DEBUG: Generating best video format")
            format_str = f"bestvideo{codec_filter}{protocol_constraint}{video_format_constraint}"
            
            # Complete format string with audio and fallbacks
            fallback = f"best{codec_filter}{protocol_constraint}{video_format_constraint}"
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
                
            print(f"DEBUG: Best video format string: {format_str}")
            
        else:
            print(f"DEBUG: Generating audio-only format")
            # Audio only format with robust fallbacks. Remove protocol constraint.
            # Prefer Opus/WebM first, then M4A/MP4, then any audio-only.
            if use_m4a:
                format_str = (
                    "bestaudio[acodec*=opus]/"
                    "bestaudio[ext=webm]/"
                    "bestaudio[ext=m4a]/"
                    "bestaudio[ext=mp4]/"
                    "bestaudio/best[vcodec=none]"
                )
            else:
                format_str = (
                    "bestaudio[acodec*=opus]/"
                    "bestaudio[ext=webm]/"
                    "bestaudio/best[vcodec=none]"
                )

            format_options["format"] = format_str
            
            # Note: For audio-only selections, we do NOT force merge_output_format here.
            # The worker already skips merge-output-format for pure audio selections.
            
            # Hint yt-dlp to use a non-web client to avoid SABR and expose HLS audio
            try:
                if 'youtube' in format_options.get('extractor_args', {}):
                    format_options['extractor_args']['youtube']['player_client'] = 'android-sdkless'
                else:
                    format_options.setdefault('extractor_args', {}).setdefault('youtube', {})['player_client'] = 'android-sdkless'
                print("DEBUG: Using youtube:player_client=android-sdkless for audio-only to avoid SABR and PO token")
            except Exception:
                pass
            
            print(f"DEBUG: Audio-only format string: {format_str}")
        
        print(f"DEBUG: Final format options: {format_options}")
        return format_options
    
    @staticmethod
    def get_preset_options(preset_name):
        """
        Return predefined option sets for common download scenarios.
        
        Args:
            preset_name (str): Name of the preset to retrieve 
                              ('audio_default', 'video_720p_default', 'best_video_default')
        
        Returns:
            dict: Dictionary containing format options for the specified preset
        """
        if preset_name == "audio_default":
            return YtDlpModel.generate_format_string(
                resolution=None,  # Audio only
                use_https=False,
                use_m4a=True,
                subtitle_lang=None,
                use_cookies=False
            )
        elif preset_name == "video_720p_default":
            return YtDlpModel.generate_format_string(
                resolution=720,
                use_https=True,
                use_m4a=True,
                subtitle_lang=['en', 'zh'],  # Include English and Chinese subtitles
                use_cookies=True,
                prefer_avc=True  # Specifically prefer AVC codec for better device compatibility
            )
        elif preset_name == "best_video_default":
            # This preset doesn't limit resolution, getting the best quality available
            return YtDlpModel.generate_format_string(
                resolution=None,  # No resolution limit
                use_https=True,
                use_m4a=False,
                subtitle_lang=['en', 'zh'],  # Include English and Chinese subtitles
                use_cookies=True,
                prefer_best_video=True,  # Indicates we want best video
                prefer_avc=False   # Don't restrict codecs for best quality
            )
        else:
            print(f"Warning: Unknown preset '{preset_name}'. Returning empty options.")
            return {}
    
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