#!/usr/bin/env python3
"""
Simple diagnostic script for Douyin video merge issues
Usage: python check_douyin_videos.py /path/to/video/directory
"""

import subprocess
import json
import os
import sys
from pathlib import Path

def get_video_info(file_path):
    """Get basic video information using ffprobe"""
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_streams', '-show_format', file_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            print(f"❌ Error probing {Path(file_path).name}: {result.stderr}")
            return None
    except Exception as e:
        print(f"❌ Exception probing {Path(file_path).name}: {e}")
        return None

def check_corruption(file_path):
    """Check for corruption by trying to decode the file"""
    cmd = ['ffmpeg', '-v', 'error', '-i', file_path, '-f', 'null', '-']
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return {
            'corrupted': result.returncode != 0,
            'errors': result.stderr.strip() if result.stderr else None
        }
    except subprocess.TimeoutExpired:
        return {'corrupted': True, 'errors': 'Timeout during check'}
    except Exception as e:
        return {'corrupted': True, 'errors': str(e)}

def analyze_videos(video_files):
    """Analyze all video files for consistency and corruption"""
    print(f"Analyzing {len(video_files)} video files...\n")
    
    results = []
    frame_rates = set()
    resolutions = set()
    video_codecs = set()
    audio_codecs = set()
    
    for i, file_path in enumerate(video_files, 1):
        filename = Path(file_path).name
        print(f"[{i}/{len(video_files)}] Checking: {filename}")
        
        # Get video info
        info = get_video_info(file_path)
        if not info:
            results.append({'file': filename, 'status': 'ERROR', 'details': 'Could not read file info'})
            continue
        
        # Extract video stream info
        video_stream = None
        audio_stream = None
        
        for stream in info.get('streams', []):
            if stream.get('codec_type') == 'video':
                video_stream = stream
            elif stream.get('codec_type') == 'audio':
                audio_stream = stream
        
        if not video_stream:
            results.append({'file': filename, 'status': 'ERROR', 'details': 'No video stream found'})
            continue
        
        # Check corruption
        corruption_check = check_corruption(file_path)
        
        # Collect information
        fps_str = video_stream.get('r_frame_rate', '0/1')
        try:
            num, den = map(int, fps_str.split('/'))
            fps = round(num / den, 2) if den != 0 else 0
        except:
            fps = 0
        
        width = video_stream.get('width', 0)
        height = video_stream.get('height', 0)
        resolution = f"{width}x{height}"
        
        video_codec = video_stream.get('codec_name', 'unknown')
        audio_codec = audio_stream.get('codec_name', 'unknown') if audio_stream else 'none'
        
        duration = float(info.get('format', {}).get('duration', 0))
        
        # Store for consistency checking
        frame_rates.add(fps)
        resolutions.add(resolution)
        video_codecs.add(video_codec)
        audio_codecs.add(audio_codec)
        
        result = {
            'file': filename,
            'fps': fps,
            'resolution': resolution,
            'video_codec': video_codec,
            'audio_codec': audio_codec,
            'duration': round(duration, 2),
            'corrupted': corruption_check['corrupted'],
            'corruption_errors': corruption_check['errors']
        }
        
        if corruption_check['corrupted']:
            print(f"  ❌ CORRUPTED: {corruption_check['errors']}")
        else:
            print(f"  ✅ OK: {fps}fps, {resolution}, {video_codec}")
        
        results.append(result)
    
    # Print summary
    print("\n" + "="*60)
    print("ANALYSIS SUMMARY")
    print("="*60)
    
    # Check consistency
    issues = []
    if len(frame_rates) > 1:
        issues.append(f"Frame rate mismatch: {sorted(frame_rates)}")
    
    if len(resolutions) > 1:
        issues.append(f"Resolution mismatch: {sorted(resolutions)}")
    
    if len(video_codecs) > 1:
        issues.append(f"Video codec mismatch: {sorted(video_codecs)}")
    
    if len(audio_codecs) > 1:
        issues.append(f"Audio codec mismatch: {sorted(audio_codecs)}")
    
    corrupted_files = [r for r in results if r.get('corrupted')]
    
    if issues:
        print("CONSISTENCY ISSUES:")
        for issue in issues:
            print(f"  ❌ {issue}")
    else:
        print("✅ All files have consistent properties")
    
    if corrupted_files:
        print(f"\nCORRUPTED FILES ({len(corrupted_files)}):")
        for result in corrupted_files:
            print(f"  ❌ {result['file']}")
            if result['corruption_errors']:
                print(f"     Error: {result['corruption_errors']}")
    else:
        print("\n✅ No corruption detected")
    
    # Recommendations
    print("\nRECOMMENDations:")
    if issues or corrupted_files:
        print("  • Re-encode all files with consistent settings before merging")
        print("  • Use this command to fix each file:")
        print("    ffmpeg -i input.mp4 -c:v libx264 -crf 23 -r 30 -c:a aac -ar 44100 output.mp4")
        if corrupted_files:
            print("  • Corrupted files should be re-trimmed from original sources")
    else:
        print("  • Files appear consistent. Issue may be in merge process.")
        print("  • Try adding -vsync cfr flag to merge command")
        print("  • Consider forcing keyframes: -force_key_frames 'expr:gte(t,n_forced*2)'")
    
    return results

def main():
    if len(sys.argv) != 2:
        print("Usage: python check_douyin_videos.py <directory_path>")
        print("Example: python check_douyin_videos.py /path/to/trimmed/videos")
        sys.exit(1)
    
    directory = Path(sys.argv[1])
    if not directory.is_dir():
        print(f"Error: {directory} is not a valid directory")
        sys.exit(1)
    
    # Find video files
    video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v']
    video_files = []
    
    for ext in video_extensions:
        video_files.extend(directory.glob(f"*{ext}"))
        video_files.extend(directory.glob(f"*{ext.upper()}"))
    
    video_files = [str(f) for f in sorted(video_files)]
    
    if not video_files:
        print(f"No video files found in {directory}")
        sys.exit(1)
    
    analyze_videos(video_files)

if __name__ == "__main__":
    main() 