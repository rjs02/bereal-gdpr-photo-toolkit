import os
import pathlib
import argparse
from math import sqrt
from PIL import Image


def create_mosaic(realmoji_path, mosaic_length, element_dim=100):
    image_files = [f for f in os.listdir(realmoji_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
    num_needed = mosaic_length * mosaic_length
    image_files = image_files[:num_needed]
    
    # Create a new image for the mosaic
    mosaic_size = mosaic_length * element_dim
    mosaic_img = Image.new('RGB', (mosaic_size, mosaic_size))
    
    # Process each image and place it in the mosaic
    for i, image_file in enumerate(image_files):
        row = i // mosaic_length
        col = i % mosaic_length
        
        # Load and resize image
        img_path = os.path.join(realmoji_path, image_file)
        img = Image.open(img_path)
        img_resized = img.resize((element_dim, element_dim))
        
        x = col * element_dim
        y = row * element_dim
        mosaic_img.paste(img_resized, (x, y))
    
    return mosaic_img


def create_mosaic_from_template(template_path, realmoji_path, mosaic_length, element_dim=100):
    # Load and process the template image
    template = Image.open(template_path).convert('L')  # Convert to grayscale
    template_width, template_height = template.size
    
    # Get pixel brightness values and create ranking
    pixels = []
    for y in range(template_height):
        for x in range(template_width):
            brightness = template.getpixel((x, y))
            pixels.append((brightness, x, y))
    
    # Sort pixels by brightness (darkest first)
    pixels.sort(key=lambda p: p[0])
    
    # Get list of image files
    image_files = [f for f in os.listdir(realmoji_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
    
    # Calculate average brightness for each image
    image_brightness = []
    for image_file in image_files:
        img_path = os.path.join(realmoji_path, image_file)
        
        # Calculate average brightness
        # img = Image.open(img_path).convert('L')  # Convert to grayscale for brightness calculation
        # pixels_list = list(img.getdata())
        # brightness = sum(pixels_list) / len(pixels_list)

        # Perceived brightness (0.2126*R + 0.7152*G + 0.0722*B); slow af
        # img = Image.open(img_path)
        # pixels_list = list(img.getdata())
        # total_brightness = 0
        # for pixel in pixels_list:
        #     r, g, b = pixel
        #     total_brightness += 0.2126 * r + 0.7152 * g + 0.0722 * b
        # brightness = total_brightness / len(pixels_list)
        # image_brightness.append((brightness, image_file))
    
    # Sort images by brightness (darkest first)
    image_brightness.sort(key=lambda x: x[0])
    
    # Create output mosaic
    mosaic_width = template_width * element_dim
    mosaic_height = template_height * element_dim
    mosaic_img = Image.new('RGB', (mosaic_width, mosaic_height))
    
    # Map template pixels to images
    num_images = len(image_brightness)
    for i, (brightness, x, y) in enumerate(pixels):
        # Map pixel position to image index (distribute evenly across brightness range)
        image_index = min(i * num_images // len(pixels), num_images - 1)
        _, image_file = image_brightness[image_index]
        
        # Load and resize the selected image
        img_path = os.path.join(realmoji_path, image_file)
        img = Image.open(img_path)
        img_resized = img.resize((element_dim, element_dim))
        
        # Calculate position in mosaic
        mosaic_x = x * element_dim
        mosaic_y = y * element_dim
        
        # Paste the image
        mosaic_img.paste(img_resized, (mosaic_x, mosaic_y))
    
    return mosaic_img


def main():
    # --path
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=str)
    parser.add_argument("--template", type=str, help="Path to grayscale template image")
    parser.add_argument("--num_images", type=int)
    parser.add_argument("--element_dim", type=int, default=100)
    args = parser.parse_args()

    realmoji_path = args.path

    # num_images
    if args.num_images is None:
        num_images = len(os.listdir(realmoji_path))
    else:
        num_images = args.num_images
    print(f"Will create a mosaic of {num_images} images")

    # create a mosaic
    if args.template:
        print(f"Using template: {args.template}")
        mosaic = create_mosaic_from_template(args.template, realmoji_path, None, element_dim=args.element_dim)
        output_path = "realmoji_template_mosaic.webp"
    else:
        mosaic_length = int(sqrt(num_images))
        print(f"Mosaic sidelength: {mosaic_length}")
        mosaic = create_mosaic(realmoji_path, mosaic_length, element_dim=args.element_dim)
        output_path = "realmoji_mosaic.webp"
    
    # save mosaic
    mosaic.save(output_path, "WEBP", quality=95)
    print(f"Mosaic saved to {output_path}")


if __name__ == "__main__":
    main()