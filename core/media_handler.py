from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QImage, QMovie
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget, QVBoxLayout
import os
from PIL import Image
from pathlib import Path

from gui.voting_tab import AspectRatioWidget
from core.video_player import VideoPlayer


class ScalableLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                          QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._original_pixmap = None
        self._original_size = None

    def setPixmap(self, pixmap):
        self._original_pixmap = pixmap
        if not self._original_size:
            self._original_size = pixmap.size()
            if self._original_size.width() > 0 and self._original_size.height() > 0:
                self._aspect_ratio = self._original_size.width() / self._original_size.height()
            else:
                self._aspect_ratio = 1
        self._update_scaled_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self):
        if self._original_pixmap:
            scaled_pixmap = self._original_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            super().setPixmap(scaled_pixmap)

    def get_aspect_ratio(self):
        return self._aspect_ratio if hasattr(self, '_aspect_ratio') else 16/9

class ScalableMovie(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                          QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._movie = None
        self._original_size = None
        self._aspect_ratio = 16/9

    def setMovie(self, movie):
        self._movie = movie
        self._original_size = movie.currentImage().size()
        if self._original_size.width() > 0 and self._original_size.height() > 0:
            self._aspect_ratio = self._original_size.width() / self._original_size.height()
        super().setMovie(movie)
        self._update_scaled_movie()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled_movie()

    def _update_scaled_movie(self):
        if self._movie and self._original_size:
            available_size = self.size()
            scaled_size = self._original_size.scaled(
                available_size,
                Qt.AspectRatioMode.KeepAspectRatio
            )
            self._movie.setScaledSize(scaled_size)

    def get_aspect_ratio(self):
        return self._aspect_ratio

class MediaHandler:
    VALID_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif'}
    VALID_VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv'}

    def __init__(self):
        """Initialize the media handler."""
        pass

    def is_valid_media(self, file_path: str) -> bool:
        """Check if the file is a valid media file."""
        path = Path(file_path)
        return (path.suffix.lower() in self.VALID_IMAGE_EXTENSIONS or
                path.suffix.lower() in self.VALID_VIDEO_EXTENSIONS)

    def load_media(self, file_path: str, target_size=None):
        """Load media file and return appropriate widget."""
        ext = os.path.splitext(file_path)[1].lower()

        # Get aspect ratio from image
        try:
            with Image.open(file_path) as img:
                aspect_ratio = img.width / img.height
        except:
            aspect_ratio = 16/9  # Default aspect ratio

        # Handle different media types
        if ext == '.gif':
            widget, movie = self._load_gif(file_path)
        elif ext in ['.jpg', '.jpeg', '.png']:
            widget = self._load_image(file_path)
        elif ext in ['.mp4', '.avi', '.mov', '.mkv']:
            widget, player = self._create_video_widget(file_path)
        else:
            return None

        # Wrap in aspect ratio maintainer
        if widget:
            wrapped_widget = AspectRatioWidget(widget, aspect_ratio)
            if ext == '.gif':
                return wrapped_widget, movie
            elif ext in ['.mp4', '.avi', '.mov', '.mkv']:
                return wrapped_widget, player
            return wrapped_widget
        return None

    def _load_gif(self, gif_path: str):
        """Load animated GIF and return ScalableMovie with QMovie."""
        movie = QMovie(gif_path)
        if movie.isValid():
            label = ScalableMovie()
            label.setMovie(movie)
            movie.start()
            return label, movie
        else:
            return self._load_image(gif_path), None

    def _load_image(self, image_path: str):
        """Load image and return QPixmap in ScalableLabel."""
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            label = ScalableLabel()
            label.setPixmap(pixmap)
            return label
        return None

    def _create_video_widget(self, video_path: str):
        """Create and return video widget."""
        print(f"Creating video widget for: {video_path}")
        video_player = VideoPlayer()
        try:
            video_player.set_source(video_path)
            print(f"Successfully created video player for: {video_path}")
            return video_player, video_player.media_player
        except Exception as e:
            print(f"Error creating video player: {e}")
            raise