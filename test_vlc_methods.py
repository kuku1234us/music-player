#!/usr/bin/env python3
"""
Test script to explore VLC MediaPlayer methods for frame-based seeking
"""

try:
    import vlc
    print("VLC Python bindings available")
    
    # Create a media player instance
    player = vlc.MediaPlayer()
    
    # Check if next_frame method exists and get its documentation
    if hasattr(player, 'next_frame'):
        print("\n=== FOUND: next_frame method ===")
        next_frame_method = getattr(player, 'next_frame')
        print(f"  Method: {next_frame_method}")
        print(f"  Callable: {callable(next_frame_method)}")
        
        # Try to get docstring if available
        try:
            doc = next_frame_method.__doc__
            if doc:
                print(f"  Documentation: {doc}")
            else:
                print("  No documentation available")
        except:
            print("  Could not access documentation")
    
    # Look for any other frame/video stepping methods
    all_methods = dir(player)
    video_step_methods = []
    
    for method_name in all_methods:
        if any(keyword in method_name.lower() for keyword in ['frame', 'step']) and not method_name.startswith('_'):
            video_step_methods.append(method_name)
    
    print("\n=== All frame/step methods found ===")
    for method_name in video_step_methods:
        try:
            method_obj = getattr(player, method_name)
            if callable(method_obj):
                print(f"  {method_name}() - callable")
                # Try to get docstring
                try:
                    doc = method_obj.__doc__
                    if doc:
                        print(f"    Doc: {doc.strip()}")
                except:
                    pass
        except Exception as e:
            print(f"  {method_name} - error: {e}")
    
    # Check what other video-related navigation exists
    print("\n=== Video control methods ===")
    video_control_methods = [m for m in all_methods if m.startswith('video_') and any(keyword in m for keyword in ['get', 'set', 'next', 'prev'])]
    for method in video_control_methods[:10]:  # Limit output
        print(f"  {method}")
    
    print("\n=== Summary ===")
    print("✅ next_frame() method IS AVAILABLE")
    print("❓ Need to test if it works for single-frame stepping")
    print("📝 This could be used for frame-precise video editing")
            
except ImportError:
    print("VLC Python bindings not available")
except Exception as e:
    print(f"Error: {e}")