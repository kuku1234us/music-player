"""
FFmpeg utilities for video compression.
Simplified version assuming FFmpeg is available via system PATH.
"""
import subprocess
import re
import os
from typing import Optional, Tuple
from pathlib import Path

def validate_ffmpeg_path(ffmpeg_path: str = "ffmpeg") -> Tuple[bool, str]:
    """
    Validate that FFmpeg is available and working.
    
    Args:
        ffmpeg_path: Path to FFmpeg executable (default: "ffmpeg")
        
    Returns:
        Tuple[bool, str]: (is_valid, error_message)
    """
    try:
        result = subprocess.run(
            [ffmpeg_path, "-version"], 
            capture_output=True, 
            text=True, 
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        if result.returncode != 0:
            return False, f"FFmpeg returned non-zero exit code: {result.returncode}"
        
        # Check for required codecs in the output
        output = result.stdout.lower()
        required_codecs = ['libx264']  # Only need libx264 for video encoding, audio is copied
        missing_codecs = []
        
        for codec in required_codecs:
            if codec not in output:
                missing_codecs.append(codec)
        
        if missing_codecs:
            return False, f"Missing required codecs: {', '.join(missing_codecs)}"
        
        return True, ""
        
    except subprocess.TimeoutExpired:
        return False, "FFmpeg command timed out"
    except FileNotFoundError:
        return False, f"FFmpeg not found: {ffmpeg_path}"
    except Exception as e:
        return False, f"Error validating FFmpeg: {str(e)}"

def get_ffmpeg_version(ffmpeg_path: str = "ffmpeg") -> Optional[str]:
    """
    Get FFmpeg version string.
    
    Args:
        ffmpeg_path: Path to FFmpeg executable
        
    Returns:
        str: Version string, or None if not available
    """
    try:
        result = subprocess.run(
            [ffmpeg_path, "-version"], 
            capture_output=True, 
            text=True, 
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        if result.returncode == 0:
            # Extract version from first line
            version_match = re.search(r'ffmpeg version (\S+)', result.stdout)
            if version_match:
                return version_match.group(1)
        
        return None
        
    except Exception:
        return None

def get_video_resolution(input_path: str, ffmpeg_path: str = "ffmpeg") -> Optional[Tuple[int, int]]:
    """
    Get video resolution (width, height) using ffprobe.

    Args:
        input_path: Path to input video file
        ffmpeg_path: Path to FFmpeg executable (used to find ffprobe)

    Returns:
        Optional[Tuple[int, int]]: (width, height) or None if not available
    """
    ffprobe_path = ffmpeg_path.replace("ffmpeg", "ffprobe")
    try:
        cmd = [
            ffprobe_path,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            input_path
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            encoding='utf-8',
            errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if result.returncode == 0 and result.stdout.strip():
            width, height = map(int, result.stdout.strip().split('x'))
            return width, height
        return None
    except Exception as e:
        print(f"[FFmpegUtils] Error getting video resolution: {e}")
        return None

def check_ffmpeg_requirements(ffmpeg_path: str = "ffmpeg") -> dict:
    """
    Check if FFmpeg meets requirements for video compression.
    
    Args:
        ffmpeg_path: Path to FFmpeg executable
        
    Returns:
        Dict: Status information
    """
    result = {
        'ffmpeg_found': False,
        'ffmpeg_path': ffmpeg_path,
        'ffmpeg_version': None,
        'is_valid': False,
        'error_message': '',
        'recommendations': []
    }
    
    # Validate FFmpeg
    is_valid, error_msg = validate_ffmpeg_path(ffmpeg_path)
    
    if is_valid:
        result['ffmpeg_found'] = True
        result['is_valid'] = True
        result['ffmpeg_version'] = get_ffmpeg_version(ffmpeg_path)
    else:
        result['error_message'] = error_msg
        if "not found" in error_msg.lower():
            result['recommendations'].append("Install FFmpeg and add it to system PATH")
        elif "missing required codecs" in error_msg.lower():
            result['recommendations'].append("Install FFmpeg build with libx264 and aac codec support")
        else:
            result['recommendations'].append("Check FFmpeg installation")
    
    return result

def get_video_duration(input_path: str, ffmpeg_path: str = "ffmpeg") -> Optional[float]:
    """
    Get video duration in seconds using FFmpeg.
    
    Args:
        input_path: Path to input video file
        ffmpeg_path: Path to FFmpeg executable
        
    Returns:
        Optional[float]: Duration in seconds, or None if not available
    """
    try:
        # Use ffprobe for duration detection as it's faster and more reliable
        cmd = [ffmpeg_path.replace("ffmpeg", "ffprobe"), "-v", "quiet", "-show_entries", 
               "format=duration", "-of", "csv=p=0", input_path]
        
        # Try ffprobe first (faster)
        try:
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=15,  # Reduced timeout for ffprobe
                encoding='utf-8', 
                errors='replace',  # Handle encoding issues gracefully
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode == 0 and result.stdout.strip():
                duration = float(result.stdout.strip())
                if duration > 0:
                    return duration
        except (ValueError, subprocess.TimeoutExpired):
            pass  # Fall back to ffmpeg method
        
        # Fallback to ffmpeg method with increased timeout for complex files
        cmd = [ffmpeg_path, "-i", input_path, "-f", "null", "-"]
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=60,  # Increased timeout for complex Unicode filenames
            encoding='utf-8', 
            errors='replace',  # Handle encoding issues gracefully
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        # Parse duration from FFmpeg output (it goes to stderr)
        duration_match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', result.stderr)
        if duration_match:
            hours, minutes, seconds = duration_match.groups()
            total_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
            return total_seconds
        
        return None
        
    except Exception as e:
        print(f"[FFmpegUtils] Error getting video duration: {e}")
        return None

def validate_and_normalize_path(file_path: str) -> str:
    """
    Validate and normalize a file path for FFmpeg command usage.
    
    Args:
        file_path: Input file path
        
    Returns:
        str: Normalized file path
        
    Raises:
        Exception: If path is invalid or inaccessible
    """
    if not file_path:
        raise Exception("File path is empty")
    
    # Convert to Path object for better handling
    try:
        path_obj = Path(file_path)
        
        # Resolve any relative paths and symlinks
        normalized_path = path_obj.resolve()
        
        # Check if file exists
        if not normalized_path.exists():
            raise Exception(f"File does not exist: {file_path}")
        
        # Check if it's actually a file
        if not normalized_path.is_file():
            raise Exception(f"Path is not a file: {file_path}")
        
        # Return as string with forward slashes normalized to backslashes on Windows
        return str(normalized_path)
        
    except Exception as e:
        raise Exception(f"Invalid file path '{file_path}': {e}")

def build_compression_command(input_path: str, output_path: str, ffmpeg_path: str = "ffmpeg", rotate: Optional[str] = None) -> list:
    """
    Build the FFmpeg command for video compression with a uniform, merge-friendly spec.

    Targets:
    - Exact canvas: 1280x720 (landscape) or 720x1280 (portrait) via scale+pad
    - Video: H.264 (libx264), yuv420p, CRF 20, preset medium, CFR 30fps, GOP=60, no scene cut
    - Audio: AAC LC, 48 kHz, 2 channels, 192 kbps
    - Hygiene: +faststart, avoid_negative_ts=make_zero, fixed track timescale

    Args:
        input_path: Path to input video file
        output_path: Path to output video file
        ffmpeg_path: Path to FFmpeg executable
        rotate: Optional rotation ('cw' | 'ccw') applied before scaling

    Returns:
        List[str]: FFmpeg command arguments
    """
    # Validate and normalize input path
    validated_input = validate_and_normalize_path(input_path)

    # Decide target canvas and scaling based on orientation
    resolution = get_video_resolution(validated_input, ffmpeg_path)
    target_w, target_h = 1280, 720  # default landscape canvas
    if resolution:
        width, height = resolution
        if width < height:  # portrait
            target_w, target_h = 720, 1280

    # Compose filter chain: optional transpose first, then scale+pad to exact canvas
    vf_filters = []
    if rotate:
        if rotate == 'cw':
            vf_filters.append('transpose=1')  # 90 degrees clockwise
        elif rotate == 'ccw':
            vf_filters.append('transpose=2')  # 90 degrees counter-clockwise
    vf_filters.append(
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2"
    )
    vf_chain = ','.join(vf_filters)

    # Ensure output directory exists
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Fixed GOP for 30fps
    gop = "60"

    return [
        ffmpeg_path,
        "-i", validated_input,
        "-vf", vf_chain,
        # Video encoding - uniform spec
        "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-r", "30", "-vsync", "cfr", "-video_track_timescale", "90000", "-g", gop, "-sc_threshold", "0",
        # Audio encoding - uniform spec
        "-map", "0:v:0", "-map", "0:a?",
        "-c:a", "aac", "-profile:a", "aac_low", "-ar", "48000", "-ac", "2", "-b:a", "192k",
        # Hygiene
        "-movflags", "+faststart", "-avoid_negative_ts", "make_zero",
        # Output
        "-y", str(Path(output_path))
    ]

def build_rotation_copy_command(input_path: str, output_path: str, direction: str, ffmpeg_path: str = "ffmpeg") -> list:
    """
    Build FFmpeg command to rotate video by metadata without re-encoding (stream copy).

    Args:
        input_path: Path to input video file
        output_path: Path to output video file (ideally same extension as input)
        direction: 'cw' for 90° clockwise, 'ccw' for 90° counter-clockwise
        ffmpeg_path: Path to FFmpeg executable

    Returns:
        List[str]: FFmpeg command arguments
    """
    validated_input = validate_and_normalize_path(input_path)
    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    degrees = '90' if direction == 'cw' else '270'
    ext = Path(output_path).suffix.lower()
    cmd = [
        ffmpeg_path,
        "-i", validated_input,
        "-map", "0",
        "-c", "copy",
        "-metadata:s:v:0", f"rotate={degrees}",
        "-avoid_negative_ts", "make_zero",
        "-y",
    ]
    # Add faststart only for MP4/MOV family
    if ext in {".mp4", ".mov", ".m4v"}:
        cmd.extend(["-movflags", "+faststart"]) 
    cmd.append(str(Path(output_path)))
    return cmd

def build_rotation_reencode_command(input_path: str, output_path: str, direction: str, ffmpeg_path: str = "ffmpeg") -> list:
    """
    Build FFmpeg command to rotate video by re-encoding (when metadata rotation is not supported).

    Args:
        input_path: Path to input video file
        output_path: Path to output video file
        direction: 'cw' or 'ccw'
        ffmpeg_path: Path to FFmpeg executable

    Returns:
        List[str]: FFmpeg command arguments
    """
    validated_input = validate_and_normalize_path(input_path)
    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    transpose = '1' if direction == 'cw' else '2'
    ext = Path(output_path).suffix.lower()
    cmd = [
        ffmpeg_path,
        "-i", validated_input,
        "-vf", f"transpose={transpose}",
        "-c:a", "copy",
        "-c:s", "copy",
        "-map", "0",
        "-avoid_negative_ts", "make_zero",
        "-y",
    ]
    # Choose video codec based on container
    if ext == ".webm":
        cmd.extend(["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0"])  # efficient VP9 reencode
    else:
        cmd.extend(["-c:v", "libx264", "-crf", "20", "-preset", "medium"])  # default H.264
    if ext in {".mp4", ".mov", ".m4v"}:
        cmd.extend(["-movflags", "+faststart"]) 
    cmd.append(str(Path(output_path)))
    return cmd

def parse_ffmpeg_progress(line: str, total_duration: Optional[float]) -> Optional[float]:
    """
    Parse FFmpeg output to extract progress percentage.
    
    Args:
        line: Line of FFmpeg output
        total_duration: Total video duration in seconds
        
    Returns:
        Optional[float]: Progress value between 0.0 and 1.0, or None
    """
    if not total_duration:
        return None
    
    # Parse time=00:01:23.45 format
    time_match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
    if time_match:
        hours, minutes, seconds = time_match.groups()
        current_time = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        progress = min(current_time / total_duration, 1.0)
        return progress
    
    # Alternative format: time=123.45 (seconds only)
    time_match2 = re.search(r'time=(\d+\.\d+)', line)
    if time_match2:
        current_time = float(time_match2.group(1))
        progress = min(current_time / total_duration, 1.0)
        return progress
    
    return None

def parse_ffmpeg_error(stderr: str, return_code: int) -> str:
    """
    Parse FFmpeg error output to provide meaningful error messages.
    
    Args:
        stderr: FFmpeg stderr output
        return_code: Process return code
        
    Returns:
        str: Human-readable error message
    """
    # Common error patterns
    error_patterns = [
        (r"No such file or directory", "Input file not found or inaccessible"),
        (r"Permission denied", "Permission denied - check file/directory permissions"),
        (r"Invalid data found", "Invalid or corrupted video file"),
        (r"Decoder .* not found", "Required video decoder not available"),
        (r"Encoder .* not found", "Required video encoder not available"),
        (r"Unknown encoder", "Video encoder not supported"),
        (r"No space left on device", "Insufficient disk space"),
        (r"Cannot allocate memory", "Insufficient memory for compression"),
    ]
    
    # Check for known error patterns
    for pattern, message in error_patterns:
        if re.search(pattern, stderr, re.IGNORECASE):
            return f"{message} (FFmpeg error code: {return_code})"
    
    # Extract last error line from stderr
    if stderr:
        lines = stderr.strip().split('\n')
        for line in reversed(lines):
            if line.strip() and not line.startswith('frame='):
                return f"FFmpeg error: {line.strip()} (code: {return_code})"
    
    return f"FFmpeg failed with return code {return_code}" 