import json
from datetime import datetime
from PIL import Image, ImageDraw, ImageOps, ExifTags
import logging
from pathlib import Path
import piexif
import os
import time
import shutil
from iptcinfo3 import IPTCInfo
import argparse
import subprocess
import tempfile
import ffmpeg

# ANSI escape codes for text styling
STYLING = {
    "GREEN": "\033[92m",
    "RED": "\033[91m",
    "BLUE": "\033[94m",
    "BOLD": "\033[1m",
    "RESET": "\033[0m",
}

#Setup log styling
class ColorFormatter(logging.Formatter):
    def format(self, record):
        message = super().format(record)
        if record.levelno == logging.INFO and "Finished processing" not in record.msg:
            message = STYLING["GREEN"] + message + STYLING["RESET"]
        elif record.levelno == logging.ERROR:
            message = STYLING["RED"] + message + STYLING["RESET"]
        elif "Finished processing" in record.msg:  # Identify the summary message
            message = STYLING["BLUE"] + STYLING["BOLD"] + message + STYLING["RESET"]
        return message

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
handler = logger.handlers[0]  # Get the default handler installed by basicConfig
handler.setFormatter(ColorFormatter('%(asctime)s - %(levelname)s - %(message)s'))

# Initialize counters
processed_files_count = 0
converted_files_count = 0
combined_files_count = 0
skipped_files_count = 0
video_files_count = 0

# Static IPTC tags
source_app = "BeReal app"
processing_tool = "github/bereal-gdpr-photo-toolkit"

# Define lists to hold the combination data
primary_images = []

# Define paths using pathlib
parser = argparse.ArgumentParser(description='Process BeReal photos and videos.')
parser.add_argument('--path', type=str, help='Path to the BeReal data export folder')
args = parser.parse_args()

json_path = Path(args.path + '/posts.json')
photo_folder = Path(args.path + '/Photos/post/')
bereal_folder = Path(args.path + '/Photos/bereal')
output_folder = Path(args.path + '/Photos/post/__processed')
output_folder_combined = Path(args.path + '/Photos/post/__combined')
output_folder.mkdir(parents=True, exist_ok=True)  # Create the output folder if it doesn't exist

# Print the paths
print(STYLING["BOLD"] + "\nThe following paths are set for the input and output files:" + STYLING["RESET"])
print(f"Photo folder: {photo_folder}")
if os.path.exists(bereal_folder):
    print(f"Older photo folder: {bereal_folder}")
print(f"Output folder for singular images: {output_folder}")
print(f"Output folder for combined images: {output_folder_combined}")
print("")

# Function to count number of input files - updated to handle both .webp and .jpg
def count_files_in_folder(folder_path):
    folder = Path(folder_path)
    webp_count = len(list(folder.glob('*.webp')))
    jpg_count = len(list(folder.glob('*.jpg')))
    mp4_count = len(list(folder.glob('*.mp4')))
    mov_count = len(list(folder.glob('*.mov')))
    return webp_count + jpg_count + mp4_count + mov_count

number_of_files = count_files_in_folder(photo_folder)
print(f"Number of image files in {photo_folder}: {number_of_files}")

if os.path.exists(bereal_folder):
    number_of_files = count_files_in_folder(bereal_folder)
    print(f"Number of (older) image files in {bereal_folder}: {number_of_files}")

# Settings
## Initial choice for accessing advanced settings
print(STYLING["BOLD"] + "\nDo you want to access advanced settings or run with default settings?" + STYLING["RESET"])
print("Default settings are:\n"
"1. Images remain in their original format (WebP remains WebP, JPG remains JPG)\n"
"2. Converted images' filenames do not contain the original filename\n"
"3. Combined images are created on top of processed singular images\n"
"4. Videos are processed and combined with image overlays\n"
"5. High quality settings (Image: 95/100, Video CRF: 18/51)")
advanced_settings = input("\nEnter " + STYLING["BOLD"] + "'yes'" + STYLING["RESET"] + "for advanced settings or press any key to continue with default settings: ").strip().lower()

if advanced_settings != 'yes':
    print("Continuing with default settings.\n")

## Default responses - updated to maintain original format as default
convert_format = 'no'
target_format = 'jpg'
keep_original_filename = 'no'
create_combined_images = 'yes'
process_videos = 'yes'
image_quality = 95  # High quality for images (1-100, higher = better)
video_crf = 18     # High quality for videos (0-51, lower = better)

## Proceed with advanced settings if chosen
if advanced_settings == 'yes':
    # User choice for converting format
    convert_format = None
    while convert_format not in ['yes', 'no']:
        convert_format = input(STYLING["BOLD"] + "\n1. Do you want to convert all images to a single format? (yes/no): " + STYLING["RESET"]).strip().lower()
        if convert_format == 'yes':
            target_format = None
            while target_format not in ['jpg', 'webp']:
                target_format = input(STYLING["BOLD"] + "   Which format do you want to convert to? (jpg/webp): " + STYLING["RESET"]).strip().lower()
        if convert_format == 'no':
            print("Your images will remain in their original format. Metadata will still be added.")
        if convert_format not in ['yes', 'no']:
            logging.error("Invalid input. Please enter 'yes' or 'no'.")

    # User choice for keeping original filename
    print(STYLING["BOLD"] + "\n2. There are two options for how output files can be named" + STYLING["RESET"] + "\n"
    "Option 1: YYYY-MM-DDTHH-MM-SS_primary/secondary_original-filename.ext\n"
    "Option 2: YYYY-MM-DDTHH-MM-SS_primary/secondary.ext\n"
    "This will only influence the naming scheme of singular images.")
    keep_original_filename = None
    while keep_original_filename not in ['yes', 'no']:
        keep_original_filename = input(STYLING["BOLD"] + "Do you want to keep the original filename in the renamed file? (yes/no): " + STYLING["RESET"]).strip().lower()
        if keep_original_filename not in ['yes', 'no']:
            logging.error("Invalid input. Please enter 'yes' or 'no'.")

    # User choice for creating combined images
    create_combined_images = None
    while create_combined_images not in ['yes', 'no']:
        create_combined_images = input(STYLING["BOLD"] + "\n3. Do you want to create combined images like the original BeReal memories? (yes/no): " + STYLING["RESET"]).strip().lower()
        if create_combined_images not in ['yes', 'no']:
            logging.error("Invalid input. Please enter 'yes' or 'no'.")

    # User choice for processing videos
    process_videos = None
    while process_videos not in ['yes', 'no']:
        process_videos = input(STYLING["BOLD"] + "\n4. Do you want to process and combine videos with image overlays? (yes/no): " + STYLING["RESET"]).strip().lower()
        if process_videos not in ['yes', 'no']:
            logging.error("Invalid input. Please enter 'yes' or 'no'.")

    # User choice for quality settings
    print(STYLING["BOLD"] + "\n5. Quality Settings" + STYLING["RESET"])
    print("Current defaults: Image quality=95 (1-100, higher=better), Video CRF=18 (0-51, lower=better)")
    
    quality_choice = input(STYLING["BOLD"] + "Do you want to customize quality settings? (yes/no): " + STYLING["RESET"]).strip().lower()
    if quality_choice == 'yes':
        # Image quality setting
        while True:
            try:
                image_quality_input = input(STYLING["BOLD"] + "Image quality (1-100, recommend 85-98, default 95): " + STYLING["RESET"]).strip()
                if image_quality_input == "":
                    break  # Keep default
                image_quality = int(image_quality_input)
                if 1 <= image_quality <= 100:
                    break
                else:
                    print("Please enter a number between 1 and 100.")
            except ValueError:
                print("Please enter a valid number.")
        
        # Video quality setting  
        while True:
            try:
                video_crf_input = input(STYLING["BOLD"] + "Video CRF (0-51, recommend 15-23, default 18): " + STYLING["RESET"]).strip()
                if video_crf_input == "":
                    break  # Keep default
                video_crf = int(video_crf_input)
                if 0 <= video_crf <= 51:
                    break
                else:
                    print("Please enter a number between 0 and 51.")
            except ValueError:
                print("Please enter a valid number.")
    
    print(f"Using image quality: {image_quality}, video CRF: {video_crf}")

if convert_format == 'no' and create_combined_images == 'no':
    print("You chose not to convert image formats nor do you want to output combined images.\n"
    "The script will therefore only copy images to a new folder and rename them according to your choice, adding metadata.\n"
    "Script will continue to run in 5 seconds.")
    time.sleep(5)

# Function to convert image format
def convert_image_format(image_path, target_format, quality=95):
    current_format = image_path.suffix.lower()[1:]  # Remove the dot
    
    if current_format == target_format:
        return image_path, False  # No conversion needed
    
    new_path = image_path.with_suffix(f'.{target_format}')
    try:
        with Image.open(image_path) as img:
            if target_format == 'jpg':
                img.convert('RGB').save(new_path, "JPEG", quality=quality)
            else:  # webp
                img.save(new_path, "WEBP", quality=quality)
            logging.info(f"Converted {image_path} to {target_format.upper()} with quality {quality}.")
        return new_path, True
    except Exception as e:
        logging.error(f"Error converting {image_path} to {target_format.upper()}: {e}")
        return None, False

# Helper function to check if file is a supported image format
def is_image_file(file_path):
    """Check if file is a supported image format (not video)"""
    image_extensions = {'.webp', '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.gif'}
    video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}
    
    file_ext = file_path.suffix.lower()
    
    if file_ext in video_extensions:
        return False
    elif file_ext in image_extensions:
        return True
    else:
        # Try to open with PIL to be sure
        try:
            with Image.open(file_path) as img:
                img.verify()  # Verify it's a valid image
            return True
        except Exception:
            return False

# Helper function to check if file is a video format
def is_video_file(file_path):
    """Check if file is a supported video format"""
    video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}
    file_ext = file_path.suffix.lower()
    return file_ext in video_extensions

# Helper function to determine file type
def get_file_type(file_path):
    """Return 'image', 'video', or 'unknown' for the file type"""
    if is_image_file(file_path):
        return 'image'
    elif is_video_file(file_path):
        return 'video'
    else:
        return 'unknown'

# Helper function to convert latitude and longitude to EXIF-friendly format
def _convert_to_degrees(value):
    """Convert decimal latitude / longitude to degrees, minutes, seconds (DMS)"""
    d = int(value)
    m = int((value - d) * 60)
    s = (value - d - m/60) * 3600.00

    # Convert to tuples of (numerator, denominator)
    d = (d, 1)
    m = (m, 1)
    s = (int(s * 100), 100)  # Assuming 2 decimal places for seconds for precision

    return (d, m, s)

# Function to update EXIF data
def update_exif(image_path, datetime_original, location=None, caption=None):
    try:
        exif_dict = piexif.load(image_path.as_posix())

        # Ensure the '0th' and 'Exif' directories are initialized
        if '0th' not in exif_dict:
            exif_dict['0th'] = {}
        if 'Exif' not in exif_dict:
            exif_dict['Exif'] = {}

        # Update datetime original
        exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = datetime_original.strftime("%Y:%m:%d %H:%M:%S")
        datetime_print = datetime_original.strftime("%Y:%m:%d %H:%M:%S")
        logging.info(f"Found datetime: {datetime_print}")
        logging.info(f"Added capture date and time.")

        # Update GPS information if location is provided
        if location and 'latitude' in location and 'longitude' in location:
            logging.info(f"Found location: {location}")
            gps_ifd = {
                piexif.GPSIFD.GPSLatitudeRef: 'N' if location['latitude'] >= 0 else 'S',
                piexif.GPSIFD.GPSLatitude: _convert_to_degrees(abs(location['latitude'])),
                piexif.GPSIFD.GPSLongitudeRef: 'E' if location['longitude'] >= 0 else 'W',
                piexif.GPSIFD.GPSLongitude: _convert_to_degrees(abs(location['longitude'])),
            }
            exif_dict['GPS'] = gps_ifd
            logging.info(f"Added GPS location.")

        # Transfer caption as title in ImageDescription
        if caption:
            logging.info(f"Found caption: {caption}")
            exif_dict['0th'][piexif.ImageIFD.ImageDescription] = caption.encode('utf-8')
            logging.info(f"Updated title with caption.")


        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, image_path.as_posix())
        logging.info(f"Updated EXIF data for {image_path}.")

        # For debugging: Load and log the updated EXIF data
        #updated_exif_dict = piexif.load(image_path.as_posix())
        #logging.info(f"Updated EXIF data for {image_path}: {updated_exif_dict}")

    except Exception as e:
        logging.error(f"Failed to update EXIF data for {image_path}: {e}")

# Function to update IPTC information
def update_iptc(image_path, caption):
    try:
        # Check if the file is a JPEG - IPTC works best with JPEG files
        file_path = Path(image_path)
        if file_path.suffix.lower() not in ['.jpg', '.jpeg']:
            logging.info(f"Skipping IPTC metadata for {file_path.suffix} file (IPTC works best with JPEG files)")
            return
            
        # Load the IPTC data from the image
        info = IPTCInfo(image_path, force=True)  # Use force=True to create IPTC data if it doesn't exist

        # Check for errors (known issue with iptcinfo3 creating _markers attribute error)
        if not hasattr(info, '_markers'):
            info._markers = []
        
        # Check for _fob attribute issue
        if not hasattr(info, '_fob'):
            logging.warning(f"IPTC library error with file {image_path}, skipping IPTC metadata")
            return

        # Update the "Caption-Abstract" field
        if caption:
            info['caption/abstract'] = caption
            logging.info(f"Caption added to image.")

        # Add static IPTC tags and keywords
        info['source'] = source_app
        info['originating program'] = processing_tool

        # Save the changes back to the image
        info.save_as(image_path)
        logging.info(f"Updated IPTC Caption-Abstract for {image_path}")
    except Exception as e:
        logging.warning(f"Skipping IPTC metadata for {image_path}: {e}")


# Function to handle deduplication
def get_unique_filename(path):
    if not path.exists():
        return path
    else:
        prefix = path.stem
        suffix = path.suffix
        counter = 1
        while path.exists():
            path = path.with_name(f"{prefix}_{counter}{suffix}")
            counter += 1
        return path

def combine_images_with_resizing(primary_path, secondary_path):
    # Parameters for rounded corners, outline and position
    corner_radius = 60
    outline_size = 7
    position = (55, 55)

    # Load primary and secondary images
    primary_image = Image.open(primary_path)
    secondary_image = Image.open(secondary_path)

    # Resize the secondary image using LANCZOS resampling for better quality
    scaling_factor = 1/3.33333333
    width, height = secondary_image.size
    new_width = int(width * scaling_factor)
    new_height = int(height * scaling_factor)
    resized_secondary_image = secondary_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Ensure secondary image has an alpha channel for transparency
    if resized_secondary_image.mode != 'RGBA':
        resized_secondary_image = resized_secondary_image.convert('RGBA')

    # Create mask for rounded corners
    mask = Image.new('L', (new_width, new_height), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, new_width, new_height), corner_radius, fill=255)

    # Apply the rounded corners mask to the secondary image
    resized_secondary_image.putalpha(mask)

    # Create a new blank image with the size of the primary image
    combined_image = Image.new("RGB", primary_image.size)
    combined_image.paste(primary_image, (0, 0))

    # Draw the black outline with rounded corners directly on the combined image
    outline_layer = Image.new('RGBA', combined_image.size, (0, 0, 0, 0))  # Transparent layer for drawing the outline
    draw = ImageDraw.Draw(outline_layer)
    outline_box = [position[0] - outline_size, position[1] - outline_size, position[0] + new_width + outline_size, position[1] + new_height + outline_size]
    draw.rounded_rectangle(outline_box, corner_radius + outline_size, fill=(0, 0, 0, 255))

    # Merge the outline layer with the combined image
    combined_image.paste(outline_layer, (0, 0), outline_layer)

    # Paste the secondary image onto the combined image using its alpha channel as the mask
    combined_image.paste(resized_secondary_image, position, resized_secondary_image)

    return combined_image

# Function to create styled overlay image for video processing
def create_styled_overlay_image(secondary_image_path, video_width, output_path=None):
    """Create a styled overlay image with rounded corners and black outline, scaled to video width"""
    if output_path is None:
        output_path = tempfile.mktemp(suffix='.png')
    
    # Calculate overlay size based on video width (28% of video width)
    overlay_width_ratio = 0.28
    target_overlay_width = int(video_width * overlay_width_ratio)
    
    # Load and process the secondary image
    secondary_image = Image.open(secondary_image_path)
    original_width, original_height = secondary_image.size
    
    # Calculate target height maintaining aspect ratio
    aspect_ratio = original_height / original_width
    target_overlay_height = int(target_overlay_width * aspect_ratio)
    
    # Resize the secondary image to target dimensions
    resized_secondary_image = secondary_image.resize((target_overlay_width, target_overlay_height), Image.Resampling.LANCZOS)
    
    # Parameters for rounded corners and outline (scale with overlay size)
    corner_radius = max(30, int(target_overlay_width * 0.04))  # 4% of width, minimum 30px
    outline_size = max(4, int(target_overlay_width * 0.01))    # 1% of width, minimum 4px
    
    # Create a transparent base image with padding for the outline
    padding = outline_size * 2
    canvas_width = target_overlay_width + padding
    canvas_height = target_overlay_height + padding
    canvas = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
    
    # Draw the black outline
    draw = ImageDraw.Draw(canvas)
    outline_box = [0, 0, canvas_width, canvas_height]
    draw.rounded_rectangle(outline_box, corner_radius + outline_size, fill=(0, 0, 0, 255))
    
    # Create mask for rounded corners on the content
    if resized_secondary_image.mode != 'RGBA':
        resized_secondary_image = resized_secondary_image.convert('RGBA')
    
    mask = Image.new('L', (target_overlay_width, target_overlay_height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, target_overlay_width, target_overlay_height), corner_radius, fill=255)
    
    # Apply the rounded corners mask
    resized_secondary_image.putalpha(mask)
    
    # Paste the content onto the canvas with the outline
    content_position = (outline_size, outline_size)
    canvas.paste(resized_secondary_image, content_position, resized_secondary_image)
    
    # Save the styled overlay
    canvas.save(output_path, 'PNG')
    return output_path

# Function to combine video with image overlay using FFmpeg
def combine_video_with_image(primary_video_path, secondary_image_path, output_path, crf=18):
    """Combine video with image overlay using FFmpeg"""
    try:
        # Get video dimensions using ffprobe
        probe_cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            str(primary_video_path)
        ]
        
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        import json
        probe_data = json.loads(probe_result.stdout)
        
        # Find video stream and get dimensions
        video_width = None
        video_height = None
        for stream in probe_data['streams']:
            if stream['codec_type'] == 'video':
                video_width = stream['width']
                video_height = stream['height']
                break
        
        if video_width is None:
            raise Exception("Could not determine video dimensions")
        
        logging.info(f"Video dimensions: {video_width}x{video_height}")
        
        # Create styled overlay image with adaptive sizing
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_overlay:
            overlay_path = create_styled_overlay_image(secondary_image_path, video_width, temp_overlay.name)
        
        # Use subprocess to call FFmpeg directly for better error handling
        cmd = [
            'ffmpeg',
            '-i', str(primary_video_path),  # Input video
            '-i', overlay_path,             # Input overlay image
            '-filter_complex', '[1:v]scale=iw:ih[overlay];[0:v][overlay]overlay=55:55',
            '-c:a', 'copy',                 # Copy audio without re-encoding
            '-c:v', 'libx264',              # Use H.264 for compatibility
            '-crf', str(crf),               # Configurable quality setting
            '-preset', 'medium',            # Balance between speed and compression
            '-y',                           # Overwrite output file
            str(output_path)
        ]
        
        # Run the ffmpeg command
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # Clean up temporary overlay file
        os.unlink(overlay_path)
        
        logging.info(f"Successfully created combined video: {output_path} with CRF {crf}")
        return True
        
    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg command failed: {e}")
        logging.error(f"FFmpeg stderr: {e.stderr}")
        # Clean up temporary files on error
        try:
            if 'overlay_path' in locals():
                os.unlink(overlay_path)
        except:
            pass
        return False
        
    except Exception as e:
        logging.error(f"Error combining video with image overlay: {e}")
        # Clean up temporary files on error
        try:
            if 'overlay_path' in locals():
                os.unlink(overlay_path)
        except:
            pass
        return False

# Function to add metadata to video files (basic implementation)
def update_video_metadata(video_path, datetime_original, location=None, caption=None):
    """Add metadata to video file using FFmpeg"""
    try:
        # For now, we'll use a simple approach with FFmpeg metadata
        # Note: Video metadata is more limited than image EXIF
        temp_output = tempfile.mktemp(suffix=video_path.suffix)
        
        metadata_args = {}
        if caption:
            metadata_args['title'] = caption
            metadata_args['description'] = caption
        
        metadata_args['creation_time'] = datetime_original.strftime("%Y-%m-%dT%H:%M:%S.000000Z")
        metadata_args['artist'] = source_app
        metadata_args['comment'] = f"Processed by {processing_tool}"
        
        # Create FFmpeg command with metadata
        input_stream = ffmpeg.input(str(video_path))
        out = ffmpeg.output(
            input_stream,
            temp_output,
            acodec='copy',
            vcodec='copy',
            **{f'metadata:{k}': v for k, v in metadata_args.items()}
        )
        
        # Run with error handling
        ffmpeg.run(out, overwrite_output=True, quiet=True, capture_stdout=True, capture_stderr=True)
        
        # Replace original with updated file
        shutil.move(temp_output, video_path)
        logging.info(f"Updated video metadata for {video_path}")
        
    except ffmpeg.Error as e:
        logging.warning(f"FFmpeg error updating metadata for {video_path}, continuing without metadata: {e}")
        # Clean up temporary file on error
        try:
            if os.path.exists(temp_output):
                os.unlink(temp_output)
        except:
            pass
    except Exception as e:
        logging.warning(f"Failed to update video metadata for {video_path}, continuing without metadata: {e}")
        # Clean up temporary file on error
        try:
            if 'temp_output' in locals() and os.path.exists(temp_output):
                os.unlink(temp_output)
        except:
            pass

# Function to clean up backup files left behind by iptcinfo3
def remove_backup_files(directory):
    # List all files in the given directory
    for filename in os.listdir(directory):
        # Check if the filename ends with '~'
        if filename.endswith('~'):
            # Construct the full path to the file
            file_path = os.path.join(directory, filename)
            try:
                # Remove the file
                os.remove(file_path)
                print(f"Removed backup file: {file_path}")
            except Exception as e:
                print(f"Failed to remove backup file {file_path}: {e}")

# Load the JSON file
try:
    with open(json_path, encoding="utf8") as f:
        data = json.load(f)
except FileNotFoundError:
    logging.error("JSON file not found. Please check the path.")
    exit()

# Process files
for entry in data:
    try:
        # Extract filenames from the posts.json structure
        # posts.json uses: primary, secondary, optional btsMedia
        front_filename = Path(entry['primary']['path']).name
        back_filename = Path(entry['secondary']['path']).name
        
        # Check if there's a behind-the-scenes video
        bts_filename = None
        has_bts = 'btsMedia' in entry and entry['btsMedia'] is not None
        if has_bts:
            bts_filename = Path(entry['btsMedia']['path']).name

        front_path = photo_folder / front_filename
        back_path = photo_folder / back_filename
        bts_path = None
        if has_bts:
            bts_path = photo_folder / bts_filename

        # If files not found in main folder, try the older folder
        if not os.path.exists(front_path):
            front_path = bereal_folder / front_filename
            back_path = bereal_folder / back_filename
            if has_bts:
                bts_path = bereal_folder / bts_filename

        # Determine file types
        front_type = get_file_type(front_path)
        back_type = get_file_type(back_path)
        bts_type = None
        if has_bts and bts_path:
            bts_type = get_file_type(bts_path)

        # Skip if files don't exist or front/back are unknown types
        if front_type == 'unknown' or back_type == 'unknown':
            logging.info(f"Skipping unknown file types: {front_filename}, {back_filename}")
            skipped_files_count += 1
            continue

        # Skip bts videos if user chose not to process them or if bts file type is unknown
        if has_bts and process_videos == 'no':
            logging.info(f"Skipping behind-the-scenes video (user choice): {bts_filename}")
            has_bts = False  # Process as regular image combination
        elif has_bts and bts_type == 'unknown':
            logging.info(f"Skipping unknown BTS file type: {bts_filename}")
            has_bts = False

        # Log what we found
        if has_bts:
            logging.info(f"Found BeReal with BTS video: front={front_filename} ({front_type}), back={back_filename} ({back_type}), bts={bts_filename} ({bts_type})")
            video_files_count += 1
        else:
            logging.info(f"Found BeReal: front={front_filename} ({front_type}), back={back_filename} ({back_type})")

        taken_at = datetime.strptime(entry['takenAt'], "%Y-%m-%dT%H:%M:%S.%fZ")
        location = entry.get('location')  # This will be None if 'location' is not present
        caption = entry.get('caption')  # This will be None if 'caption' is not present

        # Process individual files
        processed_front_path = None
        processed_back_path = None
        processed_bts_path = None

        # Process front and back images
        for path, role, file_type in [(front_path, 'front', front_type), (back_path, 'back', back_type)]:
            logging.info(f"Processing {file_type}: {path}")
            
            if file_type == 'image':
                # Check if format conversion is enabled by the user
                if convert_format == 'yes':
                    # Convert image format if necessary
                    converted_path, converted = convert_image_format(path, target_format, image_quality)
                    if converted_path is None:
                        skipped_files_count += 1
                        continue  # Skip this file if conversion failed
                    if converted:
                        converted_files_count += 1
                    path = converted_path  # Update path for further processing

                # Get original file extension
                file_extension = path.suffix.lower()

                # Adjust filename based on user's choice
                time_str = taken_at.strftime("%Y-%m-%dT%H-%M-%S")
                original_filename_without_extension = Path(path).stem

                # Determine the actual file extension based on conversion
                actual_extension = file_extension
                if convert_format == 'yes':
                    actual_extension = f'.{target_format}'

                if keep_original_filename == 'yes':
                    new_filename = f"{time_str}_{role}_{original_filename_without_extension}{actual_extension}"
                else:
                    new_filename = f"{time_str}_{role}{actual_extension}"

                new_path = output_folder / new_filename
                new_path = get_unique_filename(new_path)

                if convert_format == 'yes' and converted:
                    converted_path.rename(new_path)
                    update_exif(new_path, taken_at, location, caption)
                    logging.info(f"EXIF data added to converted image.")
                    image_path_str = str(new_path)
                    update_iptc(image_path_str, caption)
                else:
                    shutil.copy2(path, new_path)
                    update_exif(new_path, taken_at, location, caption)
                    logging.info(f"EXIF data added to copied image.")
                    image_path_str = str(new_path)
                    update_iptc(image_path_str, caption)

            # Store processed paths for combination
            if role == 'front':
                processed_front_path = new_path
            elif role == 'back':
                processed_back_path = new_path

            logging.info(f"Successfully processed {role} {file_type}.")
            processed_files_count += 1

        # Process BTS video if present
        if has_bts and bts_path:
            logging.info(f"Processing BTS video: {bts_path}")
            
            time_str = taken_at.strftime("%Y-%m-%dT%H-%M-%S")
            original_filename_without_extension = Path(bts_path).stem
            file_extension = bts_path.suffix.lower()

            if keep_original_filename == 'yes':
                new_filename = f"{time_str}_bts_{original_filename_without_extension}{file_extension}"
            else:
                new_filename = f"{time_str}_bts{file_extension}"

            new_path = output_folder / new_filename
            new_path = get_unique_filename(new_path)

            # Copy video file
            shutil.copy2(bts_path, new_path)
            
            # Add metadata to video
            update_video_metadata(new_path, taken_at, location, caption)
            logging.info(f"BTS video metadata added.")
            
            processed_bts_path = new_path
            processed_files_count += 1
            logging.info(f"Successfully processed BTS video.")

        # Store data for combination
        combination_data = {
            'front_path': processed_front_path,
            'back_path': processed_back_path,
            'bts_path': processed_bts_path,
            'taken_at': taken_at,
            'location': location,
            'caption': caption,
            'has_bts': has_bts
        }
        
        # Store in primary_images list for combination processing
        primary_images.append(combination_data)

        print("")
    except Exception as e:
        logging.error(f"Error processing entry {entry}: {e}")
        skipped_files_count += 1

# Create combined images/videos if user chose 'yes'
if create_combined_images == 'yes':
    #Create output folder if it doesn't exist
    output_folder_combined.mkdir(parents=True, exist_ok=True)

    for i, bereal_data in enumerate(primary_images):
        # Extract data for this BeReal
        front_path = bereal_data['front_path']
        back_path = bereal_data['back_path']
        bts_path = bereal_data['bts_path']
        taken_at = bereal_data['taken_at']
        location = bereal_data['location']
        caption = bereal_data['caption']
        has_bts = bereal_data['has_bts']

        timestamp = front_path.stem.split('_')[0]

        # Always create front + back combination
        logging.info(f"Creating front + back combination for {timestamp}")
        output_format = 'jpg'
        combined_filename = f"{timestamp}_combined.{output_format}"
        combined_image = combine_images_with_resizing(front_path, back_path)

        combined_image_path = output_folder_combined / combined_filename
        combined_image.save(combined_image_path, 'JPEG', quality=image_quality)
        combined_files_count += 1

        logging.info(f"Combined image saved: {combined_image_path} with quality {image_quality}")

        # Add metadata to combined image
        update_exif(combined_image_path, taken_at, location, caption)
        logging.info(f"Metadata added to combined image.")

        image_path_str = str(combined_image_path)
        update_iptc(image_path_str, caption)

        # If BTS video exists, create front + BTS video combination
        if has_bts and bts_path:
            logging.info(f"Creating BTS video + front overlay combination for {timestamp}")
            output_format = 'mp4'
            bts_combined_filename = f"{timestamp}_bts_combined.{output_format}"
            bts_combined_video_path = output_folder_combined / bts_combined_filename

            # BTS video (back camera) as background, front camera image (selfie) as overlay
            # success = combine_video_with_image(bts_path, front_path, bts_combined_video_path, video_crf)
            success = combine_video_with_image(bts_path, back_path, bts_combined_video_path, video_crf)
            if success:
                combined_files_count += 1
                logging.info(f"Combined BTS video saved: {bts_combined_video_path}")
                
                # Add metadata to combined video
                update_video_metadata(bts_combined_video_path, taken_at, location, caption)
                logging.info(f"Metadata added to combined BTS video.")
            else:
                logging.error(f"Failed to create combined BTS video for {timestamp}")

        print("")

# Clean up backup files
print(STYLING['BOLD'] + "Removing backup files left behind by iptcinfo3" + STYLING["RESET"])
remove_backup_files(output_folder)
if create_combined_images == 'yes': remove_backup_files(output_folder_combined)
print("")

# Summary
logging.info(f"Finished processing.\nNumber of input-files: {number_of_files}\nTotal files processed: {processed_files_count}\nFiles converted: {converted_files_count}\nVideo files processed: {video_files_count}\nFiles skipped: {skipped_files_count}\nFiles combined: {combined_files_count}")
