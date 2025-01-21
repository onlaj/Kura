import os
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QPixmap, QMovie
from PyQt6.QtWidgets import QLabel, QSizePolicy

from core.video_player import VideoPlayer
from gui.voting_tab import AspectRatioWidget

import logging

logger = logging.getLogger(__name__)

class ScalableLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1, 1)
        # Change to Expanding in both directions
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        # Remove maximum height restriction
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._original_pixmap = None
        self._original_size = None
        self._aspect_ratio = None

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
            available_size = self.size()
            # Calculate the scaled size while maintaining aspect ratio
            scaled_size = self._original_pixmap.size()
            scaled_size.scale(
                available_size.width(),
                available_size.height(),
                Qt.AspectRatioMode.KeepAspectRatio
            )

            scaled_pixmap = self._original_pixmap.scaled(
                scaled_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            super().setPixmap(scaled_pixmap)

    def get_aspect_ratio(self):
        return self._aspect_ratio if self._aspect_ratio else 16 / 9

    def minimumSizeHint(self):
        return QSize(100, 100)  # Set a reasonable minimum size

class ScalableMovie(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1, 1)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding  # Change to Expanding
        )
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
            # Calculate the scaled size while maintaining aspect ratio
            scaled_size = self._original_size
            scaled_size.scale(
                available_size.width(),
                available_size.height(),
                Qt.AspectRatioMode.KeepAspectRatio
            )
            self._movie.setScaledSize(scaled_size)

    def get_aspect_ratio(self):
        return self._aspect_ratio

    def minimumSizeHint(self):
        return QSize(100, 100)  # Set a reasonable minimum size

class MediaHandler:
    VALID_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    VALID_VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv'}

    def __init__(self):
        """Initialize the media handler."""
        self.active_video_players = []

    def is_valid_media(self, file_path: str) -> bool:
        """Check if the file is a valid media file."""
        path = Path(file_path)
        return (path.suffix.lower() in self.VALID_IMAGE_EXTENSIONS or
                path.suffix.lower() in self.VALID_VIDEO_EXTENSIONS)

    def get_media_type(self, file_path: str) -> str:
        """Determine the type of media (image, gif, video)."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.webp']:
            return 'image'
        elif ext == '.gif':
            return 'gif'
        elif ext in ['.mp4', '.avi', '.mov', '.mkv']:
            return 'video'
        else:
            return 'unknown'

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
        elif ext in ['.jpg', '.jpeg', '.png', '.webp']:
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
        logger.info(f"Creating video widget for: {video_path}")
        video_player = VideoPlayer()
        self.active_video_players.append(video_player)
        try:
            video_player.set_source(video_path)
            logger.info(f"Successfully created video player for: {video_path}")
            # Run video_player.stop() after short delay
            #QTimer.singleShot(1, lambda: self.stop_all_videos())
            return video_player, video_player.media_player
        except Exception as e:
            logger.warning(f"Error creating video player: {e}")
            raise

    def pause_all_videos(self):
        logger.info("Stopping all active video players.")
        """Stop all active video players."""
        for player in self.active_video_players:
            player.pause()

    def stop_all_videos(self):
        logger.info("Stopping all active video players.")
        """Stop all active video players."""
        for player in self.active_video_players:
            player.stop()

    def cleanup_player(self, player):
        """Remove player from tracking."""
        if player in self.active_video_players:
            self.active_video_players.remove(player)