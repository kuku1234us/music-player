#!/usr/bin/env python3
"""
Video Diagnostic Tool for Douyin Merge Issues
Analyzes video files to identify potential concatenation problems
"""

import subprocess
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

def run_ffprobe_command(file_path: str, *args) -> Dict[str, Any]:
    """Run ffprobe command and return JSON output"""
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json'] + list(args) + [file_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            print(f"FFprobe error for {file_path}: {result.stderr}")
            return {}
    except Exception as e:
        print(f"Error running ffprobe on {file_path}: {e}")
        return {}

def get_video_info(file_path: str) -> Dict[str, Any]:
    """Get comprehensive video information"""
    info = {}
    
    # Basic stream information
    streams_data = run_ffprobe_command(file_path, '-show_streams')
    if streams_data and 'streams' in streams_data:
        for stream in streams_data['streams']:
            if stream.get('codec_type') == 'video':
                info['video_stream'] = stream
            elif stream.get('codec_type') == 'audio':
                info['audio_stream'] = stream
    
    # Format information
    format_data = run_ffprobe_command(file_path, '-show_format')
    if format_data and 'format' in format_data:
        info['format'] = format_data['format']
    
    # Frame information (first 100 frames)
    frames_data = run_ffprobe_command(file_path, '-show_frames', '-select_streams', 'v:0', '-read_intervals', '%+#100')
    if frames_data and 'frames' in frames_data:
        info['frames'] = frames_data['frames']
    
    return info

def analyze_video_consistency(video_files: List[str]) -> Dict[str, Any]:
    """Analyze consistency across multiple video files"""
    analysis = {
        'files_analyzed': len(video_files),
        'issues_found': [],
        'recommendations': [],
        'file_details': {}
    }
    
    video_infos = []
    
    print("Analyzing video files...")
    for i, file_path in enumerate(video_files):
        print(f"  {i+1}/{len(video_files)}: {Path(file_path).name}")
        info = get_video_info(file_path)
        video_infos.append((file_path, info))
        analysis['file_details'][file_path] = info
    
    if not video_infos:
        analysis['issues_found'].append("No valid video information found")
        return analysis
    
    # Check frame rates
    frame_rates = []
    for file_path, info in video_infos:
        if 'video_stream' in info:
            fps_str = info['video_stream'].get('r_frame_rate', '0/1')
            try:
                num, den = map(int, fps_str.split('/'))
                fps = num / den if den != 0 else 0
                frame_rates.append((file_path, fps))
            except:
                frame_rates.append((file_path, 0))
    
    unique_fps = set(fps for _, fps in frame_rates)
    if len(unique_fps) > 1:
        analysis['issues_found'].append(f"Frame rate mismatch: {unique_fps}")
        analysis['recommendations'].append("Use '-r' flag to force consistent frame rate")
    
    # Check resolutions
    resolutions = []
    for file_path, info in video_infos:
        if 'video_stream' in info:
            width = info['video_stream'].get('width', 0)
            height = info['video_stream'].get('height', 0)
            resolutions.append((file_path, f"{width}x{height}"))
    
    unique_resolutions = set(res for _, res in resolutions)
    if len(unique_resolutions) > 1:
        analysis['issues_found'].append(f"Resolution mismatch: {unique_resolutions}")
        analysis['recommendations'].append("Use scaling filter to normalize resolutions")
    
    # Check codecs
    video_codecs = []
    audio_codecs = []
    for file_path, info in video_infos:
        if 'video_stream' in info:
            video_codecs.append(info['video_stream'].get('codec_name', 'unknown'))
        if 'audio_stream' in info:
            audio_codecs.append(info['audio_stream'].get('codec_name', 'unknown'))
    
    unique_video_codecs = set(video_codecs)
    unique_audio_codecs = set(audio_codecs)
    
    if len(unique_video_codecs) > 1:
        analysis['issues_found'].append(f"Video codec mismatch: {unique_video_codecs}")
    if len(unique_audio_codecs) > 1:
        analysis['issues_found'].append(f"Audio codec mismatch: {unique_audio_codecs}")
    
    # Check keyframe patterns
    print("\nAnalyzing keyframe patterns...")
    keyframe_issues = []
    for file_path, info in video_infos:
        if 'frames' in info:
            frames = info['frames']
            if frames:
                first_frame = frames[0]
                if first_frame.get('key_frame') != 1:
                    keyframe_issues.append(f"{Path(file_path).name}: First frame is not a keyframe")
            else:
                keyframe_issues.append(f"{Path(file_path).name}: No frame data available")
    
    if keyframe_issues:
        analysis['issues_found'].extend(keyframe_issues)
        analysis['recommendations'].append("Force keyframes at start: add '-force_key_frames 0' to encoding")
    
    return analysis

def check_file_corruption(file_path: str) -> Dict[str, Any]:
    """Check for file corruption using ffmpeg"""
    print(f"\nChecking corruption in: {Path(file_path).name}")
    
    # Use ffmpeg to decode without output to check for errors
    cmd = ['ffmpeg', '-v', 'error', '-i', file_path, '-f', 'null', '-']
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        corruption_info = {
            'file': file_path,
            'errors_found': result.stderr.strip() if result.stderr else None,
            'return_code': result.returncode,
            'is_corrupted': result.returncode != 0 or bool(result.stderr.strip())
        }
        return corruption_info
    except subprocess.TimeoutExpired:
        return {
            'file': file_path,
            'errors_found': 'Timeout during corruption check',
            'return_code': -1,
            'is_corrupted': True
        }
    except Exception as e:
        return {
            'file': file_path,
            'errors_found': str(e),
            'return_code': -1,
            'is_corrupted': True
        }

def generate_detailed_report(video_files: List[str], output_file: str = "video_diagnostic_report.txt"):
    """Generate a detailed diagnostic report"""
    
    print("=" * 60)
    print("VIDEO DIAGNOSTIC TOOL - DOUYIN MERGE ANALYSIS")
    print("=" * 60)
    
    # Analyze consistency
    analysis = analyze_video_consistency(video_files)
    
    # Check for corruption
    print("\nChecking for file corruption...")
    corruption_results = []
    for file_path in video_files:
        corruption_info = check_file_corruption(file_path)
        corruption_results.append(corruption_info)
    
    # Generate report
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("VIDEO DIAGNOSTIC REPORT\n")
        f.write("=" * 50 + "\n\n")
        
        f.write(f"Files Analyzed: {analysis['files_analyzed']}\n")
        f.write(f"Report Generated: {subprocess.run(['date'], capture_output=True, text=True).stdout.strip()}\n\n")
        
        # Issues Summary
        f.write("ISSUES FOUND:\n")
        f.write("-" * 20 + "\n")
        if analysis['issues_found']:
            for issue in analysis['issues_found']:
                f.write(f"• {issue}\n")
        else:
            f.write("No consistency issues detected.\n")
        f.write("\n")
        
        # Recommendations
        f.write("RECOMMENDATIONS:\n")
        f.write("-" * 20 + "\n")
        if analysis['recommendations']:
            for rec in analysis['recommendations']:
                f.write(f"• {rec}\n")
        else:
            f.write("No specific recommendations.\n")
        f.write("\n")
        
        # Corruption Results
        f.write("CORRUPTION CHECK RESULTS:\n")
        f.write("-" * 30 + "\n")
        corrupted_files = []
        for result in corruption_results:
            file_name = Path(result['file']).name
            if result['is_corrupted']:
                f.write(f"❌ {file_name}: CORRUPTED\n")
                if result['errors_found']:
                    f.write(f"   Error: {result['errors_found']}\n")
                corrupted_files.append(result['file'])
            else:
                f.write(f"✅ {file_name}: OK\n")
        f.write("\n")
        
        if corrupted_files:
            f.write("CORRUPTED FILES TO INVESTIGATE:\n")
            f.write("-" * 35 + "\n")
            for file_path in corrupted_files:
                f.write(f"• {file_path}\n")
            f.write("\n")
        
        # Detailed File Information
        f.write("DETAILED FILE INFORMATION:\n")
        f.write("-" * 30 + "\n")
        for file_path, info in analysis['file_details'].items():
            f.write(f"\nFile: {Path(file_path).name}\n")
            f.write("-" * len(Path(file_path).name) + "\n")
            
            if 'video_stream' in info:
                vs = info['video_stream']
                f.write(f"Video Codec: {vs.get('codec_name', 'unknown')}\n")
                f.write(f"Resolution: {vs.get('width', 'unknown')}x{vs.get('height', 'unknown')}\n")
                f.write(f"Frame Rate: {vs.get('r_frame_rate', 'unknown')}\n")
                f.write(f"Bit Rate: {vs.get('bit_rate', 'unknown')}\n")
            
            if 'audio_stream' in info:
                aus = info['audio_stream']
                f.write(f"Audio Codec: {aus.get('codec_name', 'unknown')}\n")
                f.write(f"Sample Rate: {aus.get('sample_rate', 'unknown')}\n")
                f.write(f"Channels: {aus.get('channels', 'unknown')}\n")
            
            if 'format' in info:
                fmt = info['format']
                f.write(f"Duration: {fmt.get('duration', 'unknown')} seconds\n")
                f.write(f"Size: {fmt.get('size', 'unknown')} bytes\n")
    
    print(f"\nDetailed report saved to: {output_file}")
    
    # Print summary
    print("\nSUMMARY:")
    print("-" * 20)
    if analysis['issues_found']:
        print("Issues found:")
        for issue in analysis['issues_found']:
            print(f"  • {issue}")
    
    corrupted_count = sum(1 for r in corruption_results if r['is_corrupted'])
    if corrupted_count > 0:
        print(f"  • {corrupted_count} corrupted file(s) detected")
    
    if not analysis['issues_found'] and corrupted_count == 0:
        print("No obvious issues detected. The problem may be more subtle.")
        print("Consider checking the original merge output file for corruption.")

def main():
    if len(sys.argv) < 2:
        print("Usage: python video_diagnostic_tool.py <video_file1> [video_file2] ...")
        print("   or: python video_diagnostic_tool.py <directory_with_videos>")
        sys.exit(1)
    
    video_files = []
    
    # Handle directory or individual files
    for arg in sys.argv[1:]:
        path = Path(arg)
        if path.is_dir():
            # Find all video files in directory
            for ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm']:
                video_files.extend(list(path.glob(f"*{ext}")))
                video_files.extend(list(path.glob(f"*{ext.upper()}")))
        elif path.is_file():
            video_files.append(str(path))
        else:
            print(f"Warning: {arg} not found")
    
    if not video_files:
        print("No video files found!")
        sys.exit(1)
    
    video_files = [str(f) for f in video_files]
    video_files.sort()
    
    print(f"Found {len(video_files)} video files to analyze")
    
    generate_detailed_report(video_files)

if __name__ == "__main__":
    main() 