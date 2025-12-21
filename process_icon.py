# resize_icon.py
import os
from PIL import Image

from qt_base_app.models.logger import Logger

def resize_icons():
    """
    Loads the microphone.png icon and creates resized versions (16, 48, 128).
    """
    source_folder = "musicplayerdl-audio"
    # Use the existing largest icon as the source of truth.
    source_icon_name = "microphone_128.png"
    source_icon_path = os.path.join(source_folder, source_icon_name)

    output_sizes = [16, 48, 128]
    output_filenames = {
        16: "microphone_16.png",
        48: "microphone_48.png",
        128: "microphone_128.png",
    }

    # Check if source file exists
    if not os.path.exists(source_icon_path):
        Logger.instance().error(caller="process_icon", msg=f"Source icon '{source_icon_path}' not found.")
        return

    try:
        with Image.open(source_icon_path) as img:
            Logger.instance().info(caller="process_icon", msg=f"Opened '{source_icon_path}'. Original size: {img.size}")

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
                Logger.instance().info(caller="process_icon", msg=f"Saved resized icon: '{output_path}' ({size}x{size})")

        Logger.instance().info(caller="process_icon", msg="Icon resizing complete.")

    except Exception as e:
        Logger.instance().error(caller="process_icon", msg=f"An error occurred during resizing: {e}", exc_info=True)

if __name__ == "__main__":
    resize_icons()