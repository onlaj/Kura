# core/image_handler.py

from PIL import Image, ImageSequence
import customtkinter as ctk
from typing import Tuple, Optional, Union
import time
import threading


class ImageHandler:
    def __init__(self, max_size: Tuple[int, int] = (1800, 1600)):
        """
        Initialize the image handler.

        Args:
            max_size: Maximum size (width, height) for displayed images
        """
        self.max_size = max_size
        self.current_size = max_size
        self.animation_threads = {}  # Track animation threads
        self.stop_animations = {}  # Control flags for animations

    def is_animated(self, image_path: str) -> bool:
        """Check if an image file is animated."""
        try:
            with Image.open(image_path) as img:
                return hasattr(img, 'is_animated') and img.is_animated
        except Exception:
            return False

    def set_display_size(self, width: int, height: int):
        """
        Update the current display size.

        Args:
            width: Available width for image
            height: Available height for image
        """
        self.current_size = (width, height)

    def load_image(self, image_path: str, target_size: Optional[Tuple[int, int]] = None,
                   thumbnail_size: Optional[Tuple[int, int]] = None) -> Optional[Union[ctk.CTkImage, tuple]]:
        """
        Enhanced load_image that handles both static and animated images.
        For animated images, returns a tuple (first_frame, frame_count, duration_list).
        """
        try:
            image = Image.open(image_path)

            # Handle animated images
            if hasattr(image, 'is_animated') and image.is_animated:
                frames = []
                durations = []
                max_gif_size = (500, 500)  # Maximum size for animated GIF frames

                # Determine display size
                display_size = target_size if target_size else self.current_size
                if thumbnail_size:
                    display_size = thumbnail_size

                # Process each frame
                for frame in ImageSequence.Iterator(image):
                    # Convert frame to RGB if necessary
                    if frame.mode != 'RGB':
                        frame = frame.convert('RGB')

                    # Resize frame only if it exceeds max_gif_size
                    if frame.width > max_gif_size[0] or frame.height > max_gif_size[1]:
                        width_ratio = max_gif_size[0] / frame.width
                        height_ratio = max_gif_size[1] / frame.height
                        scale_ratio = min(width_ratio, height_ratio)

                        new_size = (int(frame.width * scale_ratio),
                                    int(frame.height * scale_ratio))
                        frame = frame.resize(new_size, Image.Resampling.LANCZOS)

                    frames.append(ctk.CTkImage(light_image=frame, dark_image=frame,
                                               size=frame.size))

                    # Get frame duration in milliseconds
                    duration = frame.info.get('duration', 100)  # Default to 100ms
                    durations.append(duration)

                return (frames, len(frames), durations)

            # Handle static images
            if image.mode != 'RGB':
                image = image.convert('RGB')

            if thumbnail_size:
                width_ratio = thumbnail_size[0] / image.width
                height_ratio = thumbnail_size[1] / image.height
                ratio = min(width_ratio, height_ratio)
                new_size = (int(image.width * ratio), int(image.height * ratio))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            else:
                display_size = target_size if target_size else self.current_size
                if display_size:
                    width_ratio = display_size[0] / image.width
                    height_ratio = display_size[1] / image.height
                    scale_ratio = min(width_ratio, height_ratio)
                    if scale_ratio < 1:
                        new_size = (int(image.width * scale_ratio),
                                    int(image.height * scale_ratio))
                        image = image.resize(new_size, Image.Resampling.LANCZOS)

            return ctk.CTkImage(light_image=image, dark_image=image, size=image.size)

        except Exception as e:
            print(f"Error loading image {image_path}: {e}")
            return None

    def start_animation(self, label: ctk.CTkLabel, frames: list, durations: list):
        """Start animating a sequence of frames in a label with proper cleanup."""
        animation_id = id(label)

        # Stop any existing animation for this label
        self.stop_animation(label)

        # Set up new animation
        self.stop_animations[animation_id] = False

        def animate():
            frame_index = 0
            while not self.stop_animations.get(animation_id, True):
                if frame_index < len(frames):  # Check if frame exists
                    try:
                        label.configure(image=frames[frame_index])
                        duration = durations[frame_index] / 1000.0  # Convert to seconds
                        time.sleep(duration)
                        frame_index = (frame_index + 1) % len(frames)
                    except Exception:
                        # If there's any error, stop the animation
                        break

        # Start animation in a separate thread
        thread = threading.Thread(target=animate, daemon=True)
        self.animation_threads[animation_id] = thread
        thread.start()

    def stop_animation(self, label: ctk.CTkLabel):
        """Stop the animation for a specific label with cleanup."""
        animation_id = id(label)

        # Signal the animation to stop
        self.stop_animations[animation_id] = True

        # Wait for thread to finish
        if animation_id in self.animation_threads:
            thread = self.animation_threads[animation_id]
            thread.join(timeout=0.01)

            # Clean up
            del self.animation_threads[animation_id]
            if animation_id in self.stop_animations:
                del self.stop_animations[animation_id]

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