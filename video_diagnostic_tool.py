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
from typing import List, Dict, Any, Tuple
import argparse
from datetime import datetime

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
    
    # Basic stream information (include extradata_md5 and tags)
    streams_data = run_ffprobe_command(
        file_path,
        '-show_streams',
        '-show_entries',
        'stream=index,codec_type,codec_name,profile,level,width,height,pix_fmt,r_frame_rate,avg_frame_rate,time_base,sample_aspect_ratio,display_aspect_ratio,field_order,color_space,color_transfer,color_primaries,codec_tag_string,codec_tag,extradata_md5,is_avc,nal_length_size,sample_rate,channels,channel_layout,sample_fmt,bit_rate,nb_frames'
    )
    if streams_data and 'streams' in streams_data:
        for stream in streams_data['streams']:
            if stream.get('codec_type') == 'video':
                info['video_stream'] = stream
            elif stream.get('codec_type') == 'audio':
                info['audio_stream'] = stream
    
    # Format information (include container brands if present)
    format_data = run_ffprobe_command(
        file_path,
        '-show_format',
        '-show_entries',
        'format=format_name,format_long_name,duration,size,bit_rate,start_time,nb_streams,filename:format_tags=major_brand,minor_version,compatible_brands'
    )
    if format_data and 'format' in format_data:
        info['format'] = format_data['format']
    
    # Frame information (first 60 frames)
    frames_data = run_ffprobe_command(file_path, '-show_frames', '-select_streams', 'v:0', '-read_intervals', '%+#60')
    if frames_data and 'frames' in frames_data:
        info['frames'] = frames_data['frames']
    
    return info


def _to_fps(fps_expr: str) -> float:
    try:
        if not fps_expr:
            return 0.0
        if '/' in fps_expr:
            num, den = fps_expr.split('/')
            num_f = float(num)
            den_f = float(den)
            return num_f / den_f if den_f else 0.0
        return float(fps_expr)
    except Exception:
        return 0.0


def build_signature(info: Dict[str, Any]) -> Dict[str, Any]:
    """Build a strict signature dict for concat-by-copy compatibility checks."""
    v = info.get('video_stream') or {}
    a = info.get('audio_stream') or {}
    fmt = info.get('format') or {}
    fps = _to_fps(v.get('avg_frame_rate') or v.get('r_frame_rate'))
    signature = {
        'vcodec': v.get('codec_name'),
        'vprofile': v.get('profile'),
        'vlevel': v.get('level'),
        'width': v.get('width'),
        'height': v.get('height'),
        'pix_fmt': v.get('pix_fmt'),
        'fps': round(fps, 3),
        'time_base': v.get('time_base'),
        'sar': v.get('sample_aspect_ratio'),
        'dar': v.get('display_aspect_ratio'),
        'color_space': v.get('color_space'),
        'color_transfer': v.get('color_transfer'),
        'color_primaries': v.get('color_primaries'),
        'codec_tag': v.get('codec_tag_string') or v.get('codec_tag'),
        'is_avc': v.get('is_avc'),
        'nal_length_size': v.get('nal_length_size'),
        'extradata_md5': v.get('extradata_md5'),
        'acodec': a.get('codec_name'),
        'sample_rate': a.get('sample_rate'),
        'channels': a.get('channels'),
        'channel_layout': a.get('channel_layout'),
        'sample_fmt': a.get('sample_fmt'),
        'container': fmt.get('format_name'),
        'major_brand': (fmt.get('tags') or {}).get('major_brand') if isinstance(fmt.get('tags'), dict) else None,
        'compatible_brands': (fmt.get('tags') or {}).get('compatible_brands') if isinstance(fmt.get('tags'), dict) else None,
    }
    return signature

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

    # Concat-by-copy compatibility signature check
    print("\nBuilding concat compatibility signatures...")
    signatures = {}
    for file_path, info in video_infos:
        signatures[file_path] = build_signature(info)
    analysis['signatures'] = signatures

    # Group identical signatures
    def sig_key(sig: Dict[str, Any]) -> str:
        return json.dumps(sig, sort_keys=True)
    groups: Dict[str, List[str]] = {}
    for fp, sig in signatures.items():
        key = sig_key(sig)
        groups.setdefault(key, []).append(fp)
    if len(groups) > 1:
        analysis['issues_found'].append(f"Multiple concat-incompatible signatures detected: {len(groups)} groups")
        # Majority group size
        majority_key, majority_files = max(groups.items(), key=lambda kv: len(kv[1]))
        analysis['recommendations'].append(
            f"Normalize outliers to match majority group ({len(majority_files)}/{len(video_infos)} files)."
        )
        # Highlight critical mismatches (profile/level/pix_fmt/fps/audio)
        fields_to_compare = ['vcodec','vprofile','vlevel','width','height','pix_fmt','fps','acodec','sample_rate','channels','channel_layout']
        # Compute reference
        ref = json.loads(majority_key)
        diffs = {}
        for fp, sig in signatures.items():
            for fld in fields_to_compare:
                if str(sig.get(fld)) != str(ref.get(fld)):
                    diffs.setdefault(fld, set()).add(f"{Path(fp).name}:{sig.get(fld)}")
        if diffs:
            analysis['issues_found'].append(f"Key field differences: " + ", ".join(sorted(diffs.keys())))
    else:
        analysis['recommendations'].append("All inputs share an identical signature for concat-by-copy.")
    
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
        f.write(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
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
                if isinstance(fmt.get('tags'), dict):
                    tags = fmt['tags']
                    if 'major_brand' in tags:
                        f.write(f"Major Brand: {tags.get('major_brand')}\n")
                    if 'compatible_brands' in tags:
                        f.write(f"Compatible Brands: {tags.get('compatible_brands')}\n")

            # Signature excerpt
            sig = build_signature(info)
            f.write("Signature Summary:\n")
            for k in ['vcodec','vprofile','vlevel','width','height','pix_fmt','fps','acodec','sample_rate','channels','channel_layout','codec_tag','is_avc','nal_length_size','extradata_md5']:
                f.write(f"  {k}: {sig.get(k)}\n")
    
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

def parse_concat_filelist(filelist_path: str) -> List[str]:
    files: List[str] = []
    try:
        with open(filelist_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or not line.lower().startswith("file "):
                    continue
                # Expected format: file 'C:\\path\\to\\file.mp4'
                # Extract between single quotes if present
                if "'" in line:
                    try:
                        start = line.index("'") + 1
                        end = line.rindex("'")
                        path = line[start:end]
                        files.append(path)
                    except ValueError:
                        pass
                else:
                    # Fallback: after the first space
                    parts = line.split(maxsplit=1)
                    if len(parts) == 2:
                        files.append(parts[1])
    except Exception as e:
        print(f"Error reading filelist: {e}")
    return files


def main():
    parser = argparse.ArgumentParser(description='Video Diagnostic Tool for Douyin Merge Issues')
    parser.add_argument('inputs', nargs='+', help='Video files, directories, or concat filelist.txt')
    parser.add_argument('--out', default='video_diagnostic_report.txt', help='Output report file')
    parser.add_argument('--use-hardcoded', action='store_true', help='Use hardcoded Douyin test file list')
    args = parser.parse_args()

    # Hardcoded list from the user's test
    HARDCODED_FILES: List[str] = [
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1753199425_7529934176583011641.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1753285763_7530304989303770425.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1753373331_7530681087405755706.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1753545919_7531422353328196923.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1753633071_7531796660491537721.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1753805109_7532535570934779195.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1753888322_7532892972179885369.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1753977373_7533275433820769596.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1754062365_7533640482476379452.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1754408850_7535128609397738811.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1754582568_7535874722565213497.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1754755031_7536615444515720505.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1754841191_7536985506867006777.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1755272688_7538838765789449531.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1755533314_7539958147004681529.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1755705581_7540698031538146618.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1755879519_7541445094835588411.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1756050802_7542180747717676346.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1756134276_7542539270830607675.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1750951072_7520277581493620026.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1752069368_7525080620122672441.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1756224228_7542925608746667321.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\normalized_9c134fc7-2c89-49dd-a7f0-7a40a676e9dd.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\normalized_98d360e1-ef4b-4045-864a-fa31ac061fe3.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\normalized_57757e67-755f-478f-82e0-dc3500e7a482.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\normalized_a6b09d37-ef72-4593-960f-f58b4ccfedc0.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\1756207174_7542852367919271225.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\normalized_de700022-c86d-4b16-9c53-9c32680b6e80.mp4",
        r"Z:\AAAAA01\DouyinDirectory\portrait\test\normalized_f787dd14-0c92-47c7-9ac4-7e518ee7be44.mp4",
    ]

    # Collect files
    video_files: List[str] = []
    if args.use_hardcoded:
        video_files = list(HARDCODED_FILES)
    else:
        for input_path in args.inputs:
            p = Path(input_path)
            if p.is_file() and p.suffix.lower() == '.txt':
                # Try concat filelist format
                parsed = parse_concat_filelist(str(p))
                if parsed:
                    video_files.extend(parsed)
                    continue
            if p.is_dir():
                for ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm']:
                    video_files.extend([str(fp) for fp in p.glob(f"*{ext}")])
                    video_files.extend([str(fp) for fp in p.glob(f"*{ext.upper()}")])
            elif p.is_file():
                video_files.append(str(p))
            else:
                print(f"Warning: {input_path} not found")

    if not video_files:
        print("No video files found!")
        sys.exit(1)

    video_files = sorted(video_files)
    print(f"Found {len(video_files)} video files to analyze")

    generate_detailed_report(video_files, output_file=args.out)

if __name__ == "__main__":
    main() 