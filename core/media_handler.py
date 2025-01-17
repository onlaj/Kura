from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QImage, QMovie
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QLabel, QSizePolicy
import os
from PIL import Image

class ScalableLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                          QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._original_pixmap = None

    def setPixmap(self, pixmap):
        self._original_pixmap = pixmap
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

class ScalableMovie(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                          QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._movie = None
        self._original_size = None

    def setMovie(self, movie):
        self._movie = movie
        self._original_size = movie.currentImage().size()
        super().setMovie(movie)
        self._update_scaled_movie()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled_movie()

    def _update_scaled_movie(self):
        if self._movie and self._original_size:
            # Calculate scaled size maintaining aspect ratio
            available_size = self.size()
            scaled_size = self._original_size.scaled(
                available_size,
                Qt.AspectRatioMode.KeepAspectRatio
            )
            self._movie.setScaledSize(scaled_size)

class MediaHandler:
    def __init__(self):
        """Initialize the media handler."""
        pass

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
        """Load media file and return appropriate widget."""
        ext = os.path.splitext(file_path)[1].lower()

        # Handle GIF separately
        if ext == '.gif':
            return self._load_gif(file_path)
        # Handle other images
        elif ext in ['.jpg', '.jpeg', '.png']:
            return self._load_image(file_path)
        # Handle videos
        elif ext in ['.mp4', '.avi', '.mov', '.mkv']:
            return self._create_video_widget(file_path)

        return None

    def _load_gif(self, gif_path: str):
        """Load animated GIF and return ScalableMovie with QMovie."""
        movie = QMovie(gif_path)
        if movie.isValid():
            label = ScalableMovie()
            label.setMovie(movie)
            movie.start()
            return (label, movie)
        else:
            return self._load_image(gif_path)

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
        player = QMediaPlayer()
        audio_output = QAudioOutput()
        player.setAudioOutput(audio_output)

        video_widget = QVideoWidget()
        video_widget.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Expanding)
        player.setVideoOutput(video_widget)
        player.setSource(video_path)

        return video_widget, player