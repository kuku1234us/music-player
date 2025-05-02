# resize_icon.py
import os
from PIL import Image

def resize_icons():
    """
    Loads the microphone.png icon and creates resized versions (16, 48, 128).
    """
    source_folder = "youtube-master-audio"
    source_icon_name = "microphone.png"
    source_icon_path = os.path.join(source_folder, source_icon_name)

    output_sizes = [16, 48, 128]
    output_filenames = {
        16: "microphone_16.png",
        48: "microphone_48.png",
        128: "microphone_128.png",
    }

    # Check if source file exists
    if not os.path.exists(source_icon_path):
        print(f"Error: Source icon '{source_icon_path}' not found.")
        return

    try:
        with Image.open(source_icon_path) as img:
            print(f"Opened '{source_icon_path}'. Original size: {img.size}")

            # Ensure the image has an alpha channel for transparency if needed
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            for size in output_sizes:
                output_filename = output_filenames[size]
                output_path = os.path.join(source_folder, output_filename)

                # Resize the image - LANCZOS is generally best for downscaling
                resized_img = img.resize((size, size), Image.Resampling.LANCZOS)

                # Save the resized image
                resized_img.save(output_path)
                print(f"Saved resized icon: '{output_path}' ({size}x{size})")

        print("Icon resizing complete.")

    except Exception as e:
        print(f"An error occurred during resizing: {e}")

if __name__ == "__main__":
    resize_icons()