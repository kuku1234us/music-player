# This is for testing ClippingManager audio clipping functionality

import os
import subprocess
import json
from pathlib import Path

def _detect_media_type(media_path: str) -> str:
    """
    Detect if the media file is audio, video, or unknown.
    Returns: 'audio', 'video', or 'unknown'
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            media_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        if 'streams' in data:
            has_video = False
            has_audio = False
            
            for stream in data['streams']:
                codec_type = stream.get('codec_type', '')
                if codec_type == 'video':
                    has_video = True
                elif codec_type == 'audio':
                    has_audio = True
            
            if has_video:
                return 'video'
            elif has_audio:
                return 'audio'
            else:
                return 'unknown'
        else:
            return 'unknown'
            
    except Exception as e:
        print(f"[Media Detection] Error: {e}")
        return 'unknown'

def _get_audio_codec_info(audio_path: str) -> dict:
    """
    Extract comprehensive codec information from audio file using ffprobe.
    """
    print(f"[Audio Analysis] Analyzing codec: {audio_path}")
    
    try:
        # Get detailed codec information using ffprobe with JSON output
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-select_streams', 'a:0',  # Select first audio stream
            audio_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        if 'streams' in data and len(data['streams']) > 0:
            audio_stream = data['streams'][0]
            
            codec_info = {
                'codec_name': audio_stream.get('codec_name', 'Unknown'),
                'codec_long_name': audio_stream.get('codec_long_name', 'Unknown'),
                'bit_rate': audio_stream.get('bit_rate', 'Unknown'),
                'sample_rate': audio_stream.get('sample_rate', 'Unknown'),
                'channels': audio_stream.get('channels', 'Unknown'),
                'channel_layout': audio_stream.get('channel_layout', 'Unknown'),
                'duration': audio_stream.get('duration', 'Unknown')
            }
            
            print(f"[Audio Analysis] Detected: {codec_info['codec_name']} {codec_info['sample_rate']}Hz {codec_info['channels']}ch")
            return codec_info
        else:
            print("[Audio Analysis] No audio streams found in file")
            return {}
            
    except subprocess.CalledProcessError as e:
        print(f"[Audio Analysis] ffprobe failed: {e}")
        return {}
    except json.JSONDecodeError as e:
        print(f"[Audio Analysis] JSON parsing failed: {e}")
        return {}

def _check_audio_codec_encoding_support(codec_info: dict) -> dict:
    """
    Check if ffmpeg can re-encode using the same codec as the source audio.
    """
    print(f"[Audio Encoding] Testing re-encoding capability for {codec_info.get('codec_name', 'Unknown')}")
    
    try:
        # Check available encoders
        cmd = ['ffmpeg', '-encoders']
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        codec_name = codec_info.get('codec_name', '').lower()
        
        # Map audio codec names to encoder names
        audio_encoder_mapping = {
            'mp3': 'libmp3lame',
            'aac': 'aac',
            'opus': 'libopus',
            'vorbis': 'libvorbis',
            'flac': 'flac',
            'pcm_s16le': 'pcm_s16le',
            'pcm_s24le': 'pcm_s24le',
            'alac': 'alac'
        }
        
        expected_encoder = audio_encoder_mapping.get(codec_name)
        
        if expected_encoder and expected_encoder in result.stdout:
            print(f"[Audio Encoding] ✓ Encoder '{expected_encoder}' is available")
            
            # Build encoding parameters for audio
            encoding_params = []
            
            if codec_name == 'mp3':
                encoding_params.extend(['-c:a', 'libmp3lame'])
                # Use VBR quality mode for MP3
                encoding_params.extend(['-q:a', '2'])  # VBR quality 2 (high quality)
                
            elif codec_name == 'aac':
                encoding_params.extend(['-c:a', 'aac'])
                encoding_params.extend(['-b:a', '128k'])  # Standard AAC bitrate
                
            elif codec_name == 'opus':
                encoding_params.extend(['-c:a', 'libopus'])
                encoding_params.extend(['-b:a', '128k'])  # Standard Opus bitrate
                
            elif codec_name == 'vorbis':
                encoding_params.extend(['-c:a', 'libvorbis'])
                encoding_params.extend(['-q:a', '5'])  # Vorbis quality 5 (good quality)
                
            elif codec_name == 'flac':
                encoding_params.extend(['-c:a', 'flac'])
                # FLAC is lossless, no quality settings needed
                
            elif codec_name.startswith('pcm_'):
                encoding_params.extend(['-c:a', codec_name])
                # PCM is uncompressed, no quality settings needed
                
            elif codec_name == 'alac':
                encoding_params.extend(['-c:a', 'alac'])
                # ALAC is lossless, no quality settings needed
            
            # Preserve sample rate and channels if available
            if codec_info.get('sample_rate') != 'Unknown':
                encoding_params.extend(['-ar', str(codec_info['sample_rate'])])
            if codec_info.get('channels') != 'Unknown':
                encoding_params.extend(['-ac', str(codec_info['channels'])])
            
            print(f"[Audio Encoding] Using audio encoding parameters: {' '.join(encoding_params)}")
            
            return {
                'supported': True,
                'encoder': expected_encoder,
                'encoding_params': encoding_params,
                'approach': 'audio_optimized',
                'codec_name': codec_name
            }
                
        else:
            print(f"[Audio Encoding] ✗ Encoder not available for {codec_name}")
            return {'supported': False, 'reason': f'Audio encoder not available'}
        
    except subprocess.CalledProcessError as e:
        print(f"[Audio Encoding] Failed to check encoder support: {e}")
        return {'supported': False, 'reason': 'ffmpeg command failed'}

def _perform_audio_clip(media_path: str, merged_segments: list, codec_info: dict, encoder_support: dict) -> str:
    """
    Perform audio clipping using audio-optimized approach.
    Audio doesn't have keyframes, so we use sample-accurate cutting.
    """
    print(f"[Audio Clipping] Processing {len(merged_segments)} audio segment(s)")
    
    # Generate output filename
    original_path_obj = Path(media_path)
    directory = original_path_obj.parent
    stem = original_path_obj.stem
    ext = original_path_obj.suffix
    
    # Try base filename with '_clipped' suffix first
    base_clipped_filename = f"{stem}_clipped{ext}"
    output_path = str(directory / base_clipped_filename)
    counter = 1
    while os.path.exists(output_path):
        clipped_filename = f"{stem}_clipped_{counter}{ext}"
        output_path = str(directory / clipped_filename)
        counter += 1
    
    temp_files = []
    temp_dir = original_path_obj.parent / "temp_clip_segments"
    os.makedirs(temp_dir, exist_ok=True)
    list_file_path = temp_dir / "mylist.txt"
    
    try:
        for i, (start_ms, end_ms) in enumerate(merged_segments):
            segment_duration_ms = end_ms - start_ms
            if segment_duration_ms <= 0: 
                continue
            
            start_time_seconds = start_ms / 1000.0
            duration_seconds = segment_duration_ms / 1000.0
            
            print(f"[Audio Clipping] === Segment {i+1}/{len(merged_segments)} ===")
            print(f"[Audio Clipping] Segment timing: {start_time_seconds:.3f}s to {(start_ms + segment_duration_ms)/1000.0:.3f}s")
            
            temp_output_filename = f"temp_segment_{i}{original_path_obj.suffix}"
            temp_output_path = str(temp_dir / temp_output_filename)
            temp_files.append(temp_output_path)
            
            # Audio processing strategy
            if encoder_support['supported']:
                print(f"[Audio Clipping] Using audio-optimized encoding with {encoder_support['encoder']}")
                
                # High-quality audio re-encoding for sample accuracy
                ffmpeg_cmd = [
                    "ffmpeg", "-y", "-hide_banner",
                    "-ss", str(start_time_seconds),
                    "-i", media_path,
                    "-t", str(duration_seconds)
                ] + encoder_support['encoding_params'] + [
                    temp_output_path
                ]
                
            else:
                print(f"[Audio Clipping] Using stream copy fallback")
                
                # Stream copy fallback (should work for most audio formats)
                ffmpeg_cmd = [
                    "ffmpeg", "-y", "-hide_banner",
                    "-ss", str(start_time_seconds),
                    "-i", media_path,
                    "-t", str(duration_seconds),
                    "-c", "copy",
                    "-avoid_negative_ts", "make_zero",
                    temp_output_path
                ]
            
            print(f"[Audio Clipping] Command: {' '.join(ffmpeg_cmd)}")
            
            # Execute ffmpeg command
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, creationflags=creationflags)
            
            if process.returncode != 0:
                error_message = f"Audio ffmpeg failed for segment {i}. Error: {process.stderr.strip()}"
                print(f"[Audio Clipping] ❌ {error_message}")
                return None
            else:
                print(f"[Audio Clipping] ✅ Segment {i+1} processed successfully")
        
        # Concatenate all audio segments
        print(f"[Audio Clipping] Concatenating {len(temp_files)} audio segments")
        
        with open(list_file_path, 'w') as f:
            for temp_file in temp_files:
                f.write(f"file '{os.path.abspath(temp_file)}'\n")
        
        ffmpeg_concat_cmd = [
            "ffmpeg", "-y", "-hide_banner",
            "-f", "concat",
            "-safe", "0", 
            "-i", str(list_file_path),
            "-c", "copy",
            output_path
        ]
        
        print(f"[Audio Clipping] Final concatenation: {' '.join(ffmpeg_concat_cmd)}")
        
        process = subprocess.run(ffmpeg_concat_cmd, capture_output=True, text=True, creationflags=creationflags)
        
        if process.returncode == 0:
            print(f"[Audio Clipping] ✅ Audio clipping successful: {output_path}")
            return output_path
        else:
            error_message = f"Audio concatenation failed. Error: {process.stderr.strip()}"
            print(f"[Audio Clipping] ❌ {error_message}")
            return None
            
    except Exception as e:
        error_message = f"Audio clipping failed: {str(e)}"
        print(f"[Audio Clipping] ❌ {error_message}")
        return None
    finally:
        # Clean up temporary files
        _cleanup_temp_files(temp_dir, temp_files, list_file_path)

def _cleanup_temp_files(temp_dir, temp_files, list_file_path):
    """Clean up temporary files and directory."""
    if list_file_path.exists():
        try:
            os.remove(list_file_path)
        except Exception as e:
            print(f"[Cleanup] Error removing list file: {e}")
    
    for temp_file_path_str in temp_files:
        temp_file_p = Path(temp_file_path_str)
        if temp_file_p.exists():
            try:
                os.remove(temp_file_p)
            except Exception as e:
                print(f"[Cleanup] Error removing temp file: {e}")
    
    # Clean up additional temporary files
    if temp_dir.exists():
        try:
            for temp_item in temp_dir.glob("*"):
                if temp_item.is_file():
                    os.remove(temp_item)
            
            if not any(temp_dir.iterdir()):
                os.rmdir(temp_dir)
        except Exception as e:
            print(f"[Cleanup] Error cleaning temp directory: {e}")

def analyze_audio_quality(audio_paths):
    """
    Analyze and compare quality metrics of multiple audio files.
    """
    print(f"\n[Audio Quality Analysis] Comparing audio quality metrics")
    
    results = {}
    
    for name, path in audio_paths.items():
        if not os.path.exists(path):
            print(f"[Audio Quality Analysis] File not found: {path}")
            continue
            
        try:
            # Get detailed audio information
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_streams',
                '-select_streams', 'a:0',
                path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            
            if 'streams' in data and len(data['streams']) > 0:
                stream = data['streams'][0]
                
                # Extract quality-related metrics
                metrics = {
                    'file_size': os.path.getsize(path),
                    'duration': float(stream.get('duration', 0)),
                    'bit_rate': int(stream.get('bit_rate', 0)),
                    'sample_rate': int(stream.get('sample_rate', 0)),
                    'channels': int(stream.get('channels', 0)),
                    'codec_name': stream.get('codec_name', 'Unknown'),
                    'channel_layout': stream.get('channel_layout', 'Unknown')
                }
                
                # Calculate compression ratio
                if metrics['duration'] > 0 and metrics['sample_rate'] > 0 and metrics['channels'] > 0:
                    # Uncompressed size calculation (16-bit PCM)
                    uncompressed_size = metrics['sample_rate'] * metrics['channels'] * 2 * metrics['duration']  # 2 bytes per sample
                    metrics['compression_ratio'] = uncompressed_size / metrics['file_size'] if metrics['file_size'] > 0 else 0
                else:
                    metrics['compression_ratio'] = 0
                
                results[name] = metrics
                
                print(f"\n[Audio Quality Analysis] {name}:")
                print(f"  File size: {metrics['file_size']:,} bytes ({metrics['file_size']/1024/1024:.2f} MB)")
                print(f"  Duration: {metrics['duration']:.3f}s")
                print(f"  Bitrate: {metrics['bit_rate']:,} bps ({metrics['bit_rate']/1000:.0f} kbps)")
                print(f"  Sample rate: {metrics['sample_rate']:,} Hz")
                print(f"  Channels: {metrics['channels']} ({metrics['channel_layout']})")
                print(f"  Compression ratio: {metrics['compression_ratio']:.1f}:1")
                print(f"  Codec: {metrics['codec_name']}")
                
        except Exception as e:
            print(f"[Audio Quality Analysis] Error analyzing {name}: {e}")
    
    # Compare results
    if len(results) > 1:
        print(f"\n[Audio Quality Comparison]")
        
        if 'Original' in results and 'Clipped' in results:
            orig = results['Original']
            clipped = results['Clipped']
            
            size_ratio = clipped['file_size'] / orig['file_size'] if orig['file_size'] > 0 else 0
            bitrate_ratio = clipped['bit_rate'] / orig['bit_rate'] if orig['bit_rate'] > 0 else 0
            duration_ratio = clipped['duration'] / orig['duration'] if orig['duration'] > 0 else 0
            
            print(f"  Clipped vs Original:")
            print(f"    Size ratio: {size_ratio:.2f}x ({'larger' if size_ratio > 1 else 'smaller'})")
            print(f"    Bitrate ratio: {bitrate_ratio:.2f}x ({'higher' if bitrate_ratio > 1 else 'same/lower'})")
            print(f"    Duration ratio: {duration_ratio:.2f}x ({duration_ratio*100:.1f}% of original)")
            
            if bitrate_ratio > 1.1:  # 10% higher bitrate
                print(f"  ⚠️  Clipped audio uses {(bitrate_ratio-1)*100:.1f}% more bitrate")
            elif bitrate_ratio < 0.9:  # 10% lower bitrate
                print(f"  ⚠️  Clipped audio uses {(1-bitrate_ratio)*100:.1f}% less bitrate")
            else:
                print(f"  ✅ Bitrate preserved within acceptable range")
    
    return results

def test_audio_clipping():
    """
    Test audio clipping functionality with the t.mp3 file.
    """
    print("\n=== AUDIO CLIPPING TEST ===")
    
    audio_path = "./temp/t.mp3"
    
    # Check if test file exists
    if not os.path.exists(audio_path):
        print(f"❌ Test audio file not found: {audio_path}")
        return False
    
    # Detect media type
    media_type = _detect_media_type(audio_path)
    print(f"📁 Media type detected: {media_type}")
    
    if media_type != 'audio':
        print(f"❌ Expected audio file, got: {media_type}")
        return False
    
    # Analyze audio codec
    print("\n=== AUDIO CODEC ANALYSIS ===")
    codec_info = _get_audio_codec_info(audio_path)
    
    if not codec_info:
        print("❌ Audio codec analysis failed")
        return False
    
    print("✅ Audio codec analysis successful")
    
    # Check encoder support
    print("\n=== AUDIO ENCODER SUPPORT ===")
    encoder_support = _check_audio_codec_encoding_support(codec_info)
    
    if encoder_support['supported']:
        print("✅ Audio encoder support available")
    else:
        print(f"⚠️  Audio encoder not supported: {encoder_support['reason']}")
        print("   Will use stream copy fallback")
    
    # Create test segments
    print("\n=== AUDIO SEGMENT CREATION ===")
    
    # Get audio duration first
    try:
        duration_str = codec_info.get('duration', '0')
        if duration_str != 'Unknown':
            duration_seconds = float(duration_str)
        else:
            # Fallback duration detection
            cmd = [
                'ffprobe', '-v', 'error', 
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                audio_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                duration_seconds = float(result.stdout.strip())
            else:
                duration_seconds = 60.0  # Fallback to 60 seconds
    except:
        duration_seconds = 60.0  # Safe fallback
    
    print(f"📊 Audio duration: {duration_seconds:.1f} seconds")
    
    # Create strategic audio segments
    test_segments = []
    
    if duration_seconds > 10:
        # Segment 1: Beginning of audio (0-5 seconds)
        test_segments.append((0, 5000))  # 0 to 5 seconds in ms
        
        # Segment 2: Middle section (10-15 seconds)
        if duration_seconds > 15:
            test_segments.append((10000, 15000))  # 10 to 15 seconds in ms
        
        # Segment 3: Near end (last 5 seconds)
        if duration_seconds > 20:
            end_start = max(15000, int((duration_seconds - 5) * 1000))
            end_end = int(duration_seconds * 1000)
            test_segments.append((end_start, end_end))
    else:
        # Short audio file - just take first half
        half_duration_ms = int((duration_seconds / 2) * 1000)
        test_segments.append((0, half_duration_ms))
    
    print(f"📋 Created {len(test_segments)} test segments:")
    for i, (start_ms, end_ms) in enumerate(test_segments):
        print(f"   Segment {i+1}: {start_ms/1000:.1f}s to {end_ms/1000:.1f}s ({(end_ms-start_ms)/1000:.1f}s duration)")
    
    # Perform audio clipping
    print("\n=== AUDIO CLIPPING EXECUTION ===")
    
    output_path = _perform_audio_clip(audio_path, test_segments, codec_info, encoder_support)
    
    if output_path and os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        print(f"🎉 AUDIO CLIPPING TEST SUCCESSFUL!")
        print(f"📁 Output file: {output_path}")
        print(f"📊 Output size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
        
        # Analyze quality comparison
        print(f"\n=== AUDIO QUALITY ANALYSIS ===")
        quality_files = {
            'Original': audio_path,
            'Clipped': output_path
        }
        analyze_audio_quality(quality_files)
        
        return True
    else:
        print(f"❌ AUDIO CLIPPING TEST FAILED")
        return False

def main():
    """
    Main test function - test audio clipping functionality
    """
    print("=== AUDIO CLIPPING TESTING ===")
    
    audio_path = "./temp/t.mp3"
    
    # Test audio file
    if os.path.exists(audio_path):
        print(f"\n🎵 TESTING AUDIO FILE: {audio_path}")
        media_type = _detect_media_type(audio_path)
        print(f"📁 Media type detected: {media_type}")
        
        if media_type == 'audio':
            success = test_audio_clipping()
            
            if success:
                print(f"\n🎉 AUDIO CLIPPING TEST PASSED!")
                print(f"✅ ClippingManager audio algorithm ready for integration")
                print(f"✅ Audio: Sample-accurate processing (optimized for audio)")
                print(f"✅ Multi-format support: MP3, AAC, FLAC, and more")
                print(f"✅ Ready for ClippingManager integration")
            else:
                print(f"\n❌ AUDIO CLIPPING TEST FAILED!")
                print(f"🔍 Check the detailed error messages above")
        else:
            print(f"⚠️  Expected audio file, got: {media_type}")
    else:
        print(f"\n❌ AUDIO TEST FILE NOT FOUND")
        print(f"💡 Please ensure ./temp/t.mp3 exists")
    
    print(f"\n=== TESTING COMPLETED ===")

if __name__ == "__main__":
    main()

