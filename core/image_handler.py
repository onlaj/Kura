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
        self.current_size = max_size  # Track current display size

    def set_display_size(self, width: int, height: int):
        """
        Update the current display size.

        Args:
            width: Available width for image
            height: Available height for image
        """
        self.current_size = (width, height)

    def load_image(self, image_path: str, target_size: Optional[Tuple[int, int]] = None,
                   thumbnail_size: Optional[Tuple[int, int]] = None) -> Optional[ImageTk.PhotoImage]:
        """
        Load and process an image file for display.

        Args:
            image_path: Path to the image file
            target_size: Optional specific size to fit image within (width, height)
                        If None, uses current_size
            thumbnail_size: Optional size for thumbnail (width, height)
                          If provided, creates a thumbnail instead of regular resize

        Returns:
            PhotoImage object ready for display, or None if loading fails
        """
        try:
            # Open and convert image
            image = Image.open(image_path)

            # Convert to RGB if necessary (handles PNG transparency)
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Handle thumbnail creation
            if thumbnail_size:
                # Calculate thumbnail size while maintaining aspect ratio
                width_ratio = thumbnail_size[0] / image.width
                height_ratio = thumbnail_size[1] / image.height
                ratio = min(width_ratio, height_ratio)
                new_size = (int(image.width * ratio), int(image.height * ratio))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            else:
                # Use provided target size or current display size
                display_size = target_size if target_size else self.current_size

                if display_size:
                    # Calculate scaling ratios
                    width_ratio = display_size[0] / image.width
                    height_ratio = display_size[1] / image.height

                    # Use the smaller ratio to ensure image fits within bounds
                    scale_ratio = min(width_ratio, height_ratio)

                    # Only resize if image is too large
                    if scale_ratio < 1:
                        new_width = int(image.width * scale_ratio)
                        new_height = int(image.height * scale_ratio)
                        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

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