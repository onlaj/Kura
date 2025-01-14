# core/image_handler.py

from PIL import Image, ImageTk
from pathlib import Path
from typing import Tuple, Optional


class ImageHandler:
    def __init__(self, max_size: Tuple[int, int] = (800, 600)):
        """
        Initialize the image handler.

        Args:
            max_size: Maximum size (width, height) for displayed images
        """
        self.max_size = max_size

    def load_image(self, image_path: str, thumbnail_size: Optional[Tuple[int, int]] = None) -> Optional[
        ImageTk.PhotoImage]:
        """
        Load and process an image file for display.

        Args:
            image_path: Path to the image file
            thumbnail_size: Optional size for thumbnail (width, height)

        Returns:
            PhotoImage object ready for display, or None if loading fails
        """
        try:
            # Open and convert image
            image = Image.open(image_path)

            # Convert to RGB if necessary (handles PNG transparency)
            if image.mode != 'RGB':
                image = image.convert('RGB')

            if thumbnail_size:
                # Calculate thumbnail size while maintaining aspect ratio
                width_ratio = thumbnail_size[0] / image.width
                height_ratio = thumbnail_size[1] / image.height
                ratio = min(width_ratio, height_ratio)
                new_size = (int(image.width * ratio), int(image.height * ratio))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            else:
                # Calculate new size while maintaining aspect ratio
                width_ratio = self.max_size[0] / image.width
                height_ratio = self.max_size[1] / image.height
                ratio = min(width_ratio, height_ratio)

                if ratio < 1:
                    new_size = (int(image.width * ratio), int(image.height * ratio))
                    image = image.resize(new_size, Image.Resampling.LANCZOS)

            # Convert to PhotoImage for display
            return ImageTk.PhotoImage(image)

        except Exception as e:
            print(f"Error loading image {image_path}: {e}")
            return None

    @staticmethod
    def is_valid_image(file_path: str) -> bool:
        """
        Check if a file is a valid image.

        Args:
            file_path: Path to the file to check

        Returns:
            Boolean indicating if the file is a valid image
        """
        try:
            with Image.open(file_path) as img:
                img.verify()
            return True
        except Exception:
            return False