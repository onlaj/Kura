from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QImage, QMovie
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QLabel
import os
from PIL import Image


class MediaHandler:
    def __init__(self, max_size=(1800, 1600)):
        """Initialize the media handler."""
        self.max_size = max_size
        self.current_size = max_size

    def set_display_size(self, width: int, height: int):
        """Update the current display size."""
        self.current_size = (width, height)

    def is_valid_media(self, file_path: str) -> bool:
        """Check if file is a valid image or video."""
        ext = os.path.splitext(file_path)[1].lower()

        # Check images
        if ext in ['.jpg', '.jpeg', '.png', '.gif']:
            try:
                with Image.open(file_path) as img:
                    img.verify()
                return True
            except Exception:
                return False

        # Check videos
        elif ext in ['.mp4', '.avi', '.mov', '.mkv']:
            try:
                player = QMediaPlayer()
                player.setSource(file_path)
                return player.hasVideo()
            except Exception:
                return False

        return False

    def load_media(self, file_path: str, target_size=None):
        """Load media file and return appropriate widget or pixmap."""
        ext = os.path.splitext(file_path)[1].lower()

        # Handle GIF separately
        if ext == '.gif':
            return self._load_gif(file_path, target_size)
        # Handle other images
        elif ext in ['.jpg', '.jpeg', '.png']:
            return self._load_image(file_path, target_size)
        # Handle videos
        elif ext in ['.mp4', '.avi', '.mov', '.mkv']:
            return self._create_video_widget(file_path)

        return None

    def _load_gif(self, gif_path: str, target_size=None):
        """Load animated GIF and return QLabel with QMovie."""
        display_size = target_size if target_size else self.current_size

        # Create movie object
        movie = QMovie(gif_path)
        if movie.isValid():
            # Scale if needed
            current_size = movie.currentImage().size()
            if (current_size.width() > display_size[0] or
                    current_size.height() > display_size[1]):
                movie.setScaledSize(QSize(
                    display_size[0],
                    int(display_size[0] * current_size.height() / current_size.width())
                ))

            # Create label and set movie
            label = QLabel()
            label.setMovie(movie)
            movie.start()

            return (label, movie)  # Return both label and movie to manage lifecycle
        else:
            # Fallback to static image if GIF loading fails
            return self._load_image(gif_path, target_size)

    def _load_image(self, image_path: str, target_size=None):
        """Load image and return QPixmap."""
        display_size = target_size if target_size else self.current_size

        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            # Scale if needed
            if (pixmap.width() > display_size[0] or
                    pixmap.height() > display_size[1]):
                pixmap = pixmap.scaled(
                    display_size[0], display_size[1],
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
        return pixmap

    def _create_video_widget(self, video_path: str):
        """Create and return video widget."""
        player = QMediaPlayer()
        audio_output = QAudioOutput()
        player.setAudioOutput(audio_output)

        video_widget = QVideoWidget()
        player.setVideoOutput(video_widget)
        player.setSource(video_path)

        return video_widget, player