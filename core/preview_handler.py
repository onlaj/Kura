# core/preview_handler.py

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QMovie
from PyQt6.QtMultimediaWidgets import QVideoWidget


class MediaPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Set up the overlay widget to cover the entire window
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Create media container that fills the entire space
        self.media_container = QWidget(self)
        # self.media_container.setStyleSheet("""
        #     QWidget {
        #         background-color: rgba(0, 0, 0, 200);
        #     }
        # """)
        self.media_layout = QVBoxLayout(self.media_container)
        self.media_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Add spacing around the media content
        self.media_layout.setContentsMargins(50, 50, 50, 50)
        self.layout.addWidget(self.media_container)

        self.current_media = None
        self.video_player = None
        self.gif_movie = None

        # Connect click event to close
        self.media_container.mousePressEvent = lambda e: self.close()

    def show_media(self, media_widget, video_player=None, gif_movie=None):
        """Show media in the preview overlay"""
        # Clear any existing media
        if self.current_media:
            if self.video_player:
                self.video_player.stop()
            self.current_media.setParent(None)

        # Store and show new media
        self.current_media = media_widget
        self.video_player = video_player
        self.gif_movie = gif_movie

        # Ensure the media widget expands properly
        media_widget.setSizePolicy(QSizePolicy.Policy.Expanding,
                                   QSizePolicy.Policy.Expanding)

        # Add new media to layout
        self.media_layout.addWidget(media_widget)

        # Start media playback if needed
        if video_player:
            video_player.play()

        # Ensure the preview covers the entire parent widget
        if self.parent():
            self.setGeometry(self.parent().rect())

        # Show the preview
        self.show()
        self.raise_()

    def close(self):
        """Handle closing the preview"""
        if self.video_player:
            self.video_player.stop()
        if self.gif_movie:
            self.gif_movie.stop()
        super().close()

    def resizeEvent(self, event):
        """Ensure preview takes up full parent widget size"""
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().resizeEvent(event)

    def showEvent(self, event):
        """Ensure proper sizing when showing the preview"""
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().showEvent(event)