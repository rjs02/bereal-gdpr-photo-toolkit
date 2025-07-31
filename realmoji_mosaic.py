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


def main():
    # --path
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=str)
    parser.add_argument("--num_images", type=int)
    parser.add_argument("--element_dim", type=int, default=100)
    args = parser.parse_args()

    realmoji_path = args.path
    realmoji_path = "/home/robin/CLOUD-ROBIN/Archiv/BeReal/Export_2025-07-27/Photos/realmoji"

    # num_images
    if args.num_images is None:
        num_images = len(os.listdir(realmoji_path))
    else:
        num_images = args.num_images
    print(f"Will create a mosaic of {num_images} images")

    mosaic_length = int(sqrt(num_images))
    print(f"Mosaic sidelength: {mosaic_length}")

    # create a mosaic
    mosaic = create_mosaic(realmoji_path, mosaic_length, element_dim=args.element_dim)
    
    # save mosaic
    output_path = "realmoji_mosaic.webp"
    mosaic.save(output_path, "WEBP", quality=95)
    print(f"Mosaic saved to {output_path}")


if __name__ == "__main__":
    main()