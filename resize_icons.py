from PIL import Image
import os

# Define the source image path
source_image_path = os.path.join('musicplayerdl-best', 'youtube.png')

# Define target sizes
sizes = [16, 48, 128]

# Check if source image exists
if not os.path.exists(source_image_path):
    print(f"Error: Source image '{source_image_path}' not found.")
    exit(1)

# Open the source image
try:
    source_image = Image.open(source_image_path)
    print(f"Loaded source image: {source_image_path} ({source_image.width}x{source_image.height})")
except Exception as e:
    print(f"Error loading image: {e}")
    exit(1)

# Create resized versions
for size in sizes:
    # Define the target path
    target_path = os.path.join('musicplayerdl-best', f'icon{size}.png')
    
    # Resize the image (maintaining aspect ratio)
    resized_image = source_image.resize((size, size), Image.Resampling.LANCZOS)
    
    # Save the resized image
    try:
        resized_image.save(target_path)
        print(f"Created {target_path} ({size}x{size})")
    except Exception as e:
        print(f"Error saving {target_path}: {e}")

print("Icon resizing complete!") 