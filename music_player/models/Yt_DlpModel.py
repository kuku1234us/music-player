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
        
        # print(f"DEBUG: YtDlpModel.generate_format_string called with: resolution={resolution}, use_https={use_https}, use_m4a={use_m4a}, subtitle_lang={subtitle_lang}, use_cookies={use_cookies}, prefer_best_video={prefer_best_video}, prefer_avc={prefer_avc}")
        
        # Add browser cookies option if enabled
        if use_cookies:
            # Use standard firefox cookie extraction
            format_options['cookies_from_browser'] = 'firefox'
            # print("DEBUG: Using firefox cookie extraction")
        
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
                # print(f"DEBUG: Multiple subtitle languages requested: {expanded_langs}")
            else:
                expanded_langs = expand_subtitle_lang(subtitle_lang)
                format_options['subtitleslangs'] = expanded_langs
                # print(f"DEBUG: Subtitle language(s) requested: {expanded_langs}")
                
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
            # print(f"DEBUG: Using AVC codec filter for better compatibility")
        elif not prefer_best_video:
            # If not using best video and not explicitly preferring AVC, exclude AV1 for compatibility
            codec_filter = "[vcodec!*=av01]"
            # print(f"DEBUG: Excluding AV1 codec for better compatibility")
        
        # Prepare protocol and format constraints
        protocol_constraint = "[protocol=https]" if use_https else ""
        video_format_constraint = "[ext=mp4]" if use_m4a else ""
        audio_format_constraint = "[ext=m4a]" if use_m4a else ""
        
        # Prepare audio part of format string
        # Relax audio constraints to ensure we get *some* audio if specific types fail
        # For the primary selectors, we'll use a more permissive audio selector to avoid
        # failing the whole HTTPS match just because the specific audio format/protocol wasn't found.
        audio_str_permissive = "bestaudio" 
        
        audio_str_strict = "bestaudio"
        if use_https:
            audio_str_strict += protocol_constraint
        if use_m4a:
            audio_str_strict += audio_format_constraint
        
        # Use permissive audio string for main selectors to prioritize video protocol
        audio_str = audio_str_permissive
        
        # Add fallback for audio if the specific one fails
        audio_fallback = "/bestaudio"

        if resolution and not prefer_best_video:
            # Resolution-specific format with improved handling for portrait/landscape videos
            # Strategy: Prioritize HTTPS for the target resolution, then fallback to ANY protocol for that resolution
            # This avoids slow m3u8 downloads unless necessary, while still enforcing resolution.
            
            # Build video format string parts with codec filter applied to each option separately
            if resolution == 720:
                # For 720p - try exact height=720 (landscape) or width=720 (portrait) or height<=720
                video_parts = []
                
                # --- TIER 1: HTTPS PREFERRED (Fast) ---
                # Use PERMISSIVE audio here to ensure we grab the HTTPS video even if audio isn't perfectly matched
                # Option 1: Exact height match (landscape) - HTTPS
                video_parts.append(f"bestvideo[height=720]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str_permissive}")
                # Option 2: Exact width match (portrait) - HTTPS
                video_parts.append(f"bestvideo[width=720]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str_permissive}")
                
                # --- TIER 2: ANY PROTOCOL (Fallback if HTTPS missing, e.g. only m3u8 available) ---
                # Option 1b: Exact height match (landscape) - ANY PROTOCOL
                video_parts.append(f"bestvideo[height=720]{codec_filter}{video_format_constraint}+{audio_str_permissive}")
                # Option 2b: Exact width match (portrait) - ANY PROTOCOL
                video_parts.append(f"bestvideo[width=720]{codec_filter}{video_format_constraint}+{audio_str_permissive}")
                
                # --- TIER 3: LOOSE RESOLUTION MATCH (HTTPS Preferred) ---
                # Option 3: Height <= resolution (fallback) - HTTPS
                video_parts.append(f"bestvideo[height<=720]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str_permissive}")
                
                # --- TIER 4: LOOSE RESOLUTION MATCH (Any Protocol) ---
                # Option 3b: Height <= resolution (fallback) - ANY PROTOCOL
                video_parts.append(f"bestvideo[height<=720]{codec_filter}{video_format_constraint}+{audio_str_permissive}")
                
                # Join all video+audio options with "/"
                # Append fallback audio options to each part
                video_parts = [f"{p}{audio_fallback}" for p in video_parts]
                format_str = "/".join(video_parts)
                
            elif resolution == 1080:
                # For 1080p
                video_parts = []
                # Tier 1: HTTPS
                video_parts.append(f"bestvideo[height=1080]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str_permissive}")
                video_parts.append(f"bestvideo[width=1080]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str_permissive}")
                # Tier 2: Any Protocol
                video_parts.append(f"bestvideo[height=1080]{codec_filter}{video_format_constraint}+{audio_str_permissive}")
                video_parts.append(f"bestvideo[width=1080]{codec_filter}{video_format_constraint}+{audio_str_permissive}")
                # Tier 3: Loose HTTPS
                video_parts.append(f"bestvideo[height<=1080]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str_permissive}")
                # Tier 4: Loose Any
                video_parts.append(f"bestvideo[height<=1080]{codec_filter}{video_format_constraint}+{audio_str_permissive}")
                
                video_parts = [f"{p}{audio_fallback}" for p in video_parts]
                format_str = "/".join(video_parts)
                
            elif resolution == 1440:
                # For 1440p
                video_parts = []
                # Tier 1: HTTPS
                video_parts.append(f"bestvideo[height=1440]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str_permissive}")
                video_parts.append(f"bestvideo[width=1440]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str_permissive}")
                # Tier 2: Any Protocol
                video_parts.append(f"bestvideo[height=1440]{codec_filter}{video_format_constraint}+{audio_str_permissive}")
                video_parts.append(f"bestvideo[width=1440]{codec_filter}{video_format_constraint}+{audio_str_permissive}")
                # Tier 3: Loose HTTPS
                video_parts.append(f"bestvideo[height<=1440]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str_permissive}")
                # Tier 4: Loose Any
                video_parts.append(f"bestvideo[height<=1440]{codec_filter}{video_format_constraint}+{audio_str_permissive}")
                
                video_parts = [f"{p}{audio_fallback}" for p in video_parts]
                format_str = "/".join(video_parts)
                
            elif resolution == 2160:
                # For 4K
                video_parts = []
                # Tier 1: HTTPS
                video_parts.append(f"bestvideo[height=2160]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str_permissive}")
                video_parts.append(f"bestvideo[width=2160]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str_permissive}")
                # Tier 2: Any Protocol
                video_parts.append(f"bestvideo[height=2160]{codec_filter}{video_format_constraint}+{audio_str_permissive}")
                video_parts.append(f"bestvideo[width=2160]{codec_filter}{video_format_constraint}+{audio_str_permissive}")
                # Tier 3: Loose HTTPS
                video_parts.append(f"bestvideo[height<=2160]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str_permissive}")
                # Tier 4: Loose Any
                video_parts.append(f"bestvideo[height<=2160]{codec_filter}{video_format_constraint}+{audio_str_permissive}")
                
                video_parts = [f"{p}{audio_fallback}" for p in video_parts]
                format_str = "/".join(video_parts)
                
            else:
                # For other resolutions
                # Prefer HTTPS, then fallback to any
                format_str = f"bestvideo[height<={resolution}]{codec_filter}{protocol_constraint}{video_format_constraint}+{audio_str_permissive}{audio_fallback}/"
                format_str += f"bestvideo[height<={resolution}]{codec_filter}{video_format_constraint}+{audio_str_permissive}{audio_fallback}"
            
            # Build fallback options (best effort)
            # Use strict audio here if we've fallen this far, or keep permissive? Let's use strict for fallbacks to try and get m4a if possible
            # Actually, permissive is safer.
            if resolution == 720:
                fallback_parts = []
                # HTTPS fallbacks
                fallback_parts.append(f"best[height=720]{codec_filter}{protocol_constraint}{video_format_constraint}")
                fallback_parts.append(f"best[width=720]{codec_filter}{protocol_constraint}{video_format_constraint}")
                fallback_parts.append(f"best[height<=720]{codec_filter}{protocol_constraint}{video_format_constraint}")
                # Any protocol fallbacks
                fallback_parts.append(f"best[height=720]{codec_filter}{video_format_constraint}")
                fallback_parts.append(f"best[width=720]{codec_filter}{video_format_constraint}")
                fallback_parts.append(f"best[height<=720]{codec_filter}{video_format_constraint}")
                fallback = "/".join(fallback_parts)
                
            elif resolution == 1080:
                fallback_parts = []
                # HTTPS
                fallback_parts.append(f"best[height=1080]{codec_filter}{protocol_constraint}{video_format_constraint}")
                fallback_parts.append(f"best[width=1080]{codec_filter}{protocol_constraint}{video_format_constraint}")
                fallback_parts.append(f"best[height<=1080]{codec_filter}{protocol_constraint}{video_format_constraint}")
                # Any
                fallback_parts.append(f"best[height=1080]{codec_filter}{video_format_constraint}")
                fallback_parts.append(f"best[width=1080]{codec_filter}{video_format_constraint}")
                fallback_parts.append(f"best[height<=1080]{codec_filter}{video_format_constraint}")
                fallback = "/".join(fallback_parts)
                
            elif resolution == 1440:
                fallback_parts = []
                # HTTPS
                fallback_parts.append(f"best[height=1440]{codec_filter}{protocol_constraint}{video_format_constraint}")
                fallback_parts.append(f"best[width=1440]{codec_filter}{protocol_constraint}{video_format_constraint}")
                fallback_parts.append(f"best[height<=1440]{codec_filter}{protocol_constraint}{video_format_constraint}")
                # Any
                fallback_parts.append(f"best[height=1440]{codec_filter}{video_format_constraint}")
                fallback_parts.append(f"best[width=1440]{codec_filter}{video_format_constraint}")
                fallback_parts.append(f"best[height<=1440]{codec_filter}{video_format_constraint}")
                fallback = "/".join(fallback_parts)
                
            elif resolution == 2160:
                fallback_parts = []
                # HTTPS
                fallback_parts.append(f"best[height=2160]{codec_filter}{protocol_constraint}{video_format_constraint}")
                fallback_parts.append(f"best[width=2160]{codec_filter}{protocol_constraint}{video_format_constraint}")
                fallback_parts.append(f"best[height<=2160]{codec_filter}{protocol_constraint}{video_format_constraint}")
                # Any
                fallback_parts.append(f"best[height=2160]{codec_filter}{video_format_constraint}")
                fallback_parts.append(f"best[width=2160]{codec_filter}{video_format_constraint}")
                fallback_parts.append(f"best[height<=2160]{codec_filter}{video_format_constraint}")
                fallback = "/".join(fallback_parts)
                
            else:
                fallback = f"best[height<={resolution}]{codec_filter}{protocol_constraint}{video_format_constraint}/"
                fallback += f"best[height<={resolution}]{codec_filter}{video_format_constraint}"
            
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
                
            # print(f"DEBUG: Resolution-specific format string: {format_str}")
                
        elif prefer_best_video:
            # Best video format - no resolution limiting
            # print(f"DEBUG: Generating best video format")
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
                
            # print(f"DEBUG: Best video format string: {format_str}")
            
        else:
            # print(f"DEBUG: Generating audio-only format")
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
                # print("DEBUG: Using youtube:player_client=android-sdkless for audio-only to avoid SABR and PO token")
            except Exception:
                pass
            
            # print(f"DEBUG: Audio-only format string: {format_str}")
        
        # print(f"DEBUG: Final format options: {format_options}")
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