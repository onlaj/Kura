from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QFrame, QSizePolicy, QDialog)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QMovie
from PyQt6.QtMultimediaWidgets import QVideoWidget
from core.elo import Rating
import time

from core.preview_handler import MediaPreview


class MediaFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)

        self.layout = QVBoxLayout(self)

        # Media display widget (will be set later)
        self.media_widget = None
        self.media_player = None
        self.gif_movie = None  # Added for GIF support

        # Vote button
        self.vote_button = QPushButton("Vote")
        self.layout.addWidget(self.vote_button)

        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)


class AspectRatioWidget(QWidget):
    def __init__(self, widget, aspect_ratio=16 / 9, parent=None):
        super().__init__(parent)
        self.aspect_ratio = aspect_ratio
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(widget)

        # The contained widget should expand in both directions
        widget.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Expanding)

        # This widget should expand in both directions
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

    def resizeEvent(self, event):
        width = self.width()
        height = self.height()

        target_aspect = self.aspect_ratio
        current_aspect = width / height if height != 0 else 1

        if current_aspect > target_aspect:
            # Too wide - constrain width
            new_width = int(height * target_aspect)
            offset = (width - new_width) // 2
            self.layout().setContentsMargins(offset, 0, offset, 0)
        else:
            # Too tall - constrain height
            new_height = int(width / target_aspect)
            offset = (height - new_height) // 2
            self.layout().setContentsMargins(0, offset, 0, offset)

        super().resizeEvent(event)

class VotingTab(QWidget):
    def __init__(self, get_pair_callback, update_ratings_callback, media_handler):
        super().__init__()
        self.get_pair_callback = get_pair_callback
        self.update_ratings_callback = update_ratings_callback
        self.media_handler = media_handler
        self.preview = MediaPreview(self)

        self.current_left = None
        self.current_right = None
        self.images_loaded = False
        self.last_vote_time = 0
        self.vote_cooldown = 1.0

        self.setup_ui()

    def setup_ui(self):
        """Set up the voting interface."""
        layout = QVBoxLayout(self)

        # Create horizontal layout for media frames
        media_layout = QHBoxLayout()

        # Left media frame
        self.left_frame = MediaFrame()
        self.left_frame.vote_button.clicked.connect(
            lambda: self.handle_vote("left"))
        media_layout.addWidget(self.left_frame)

        # Right media frame
        self.right_frame = MediaFrame()
        self.right_frame.vote_button.clicked.connect(
            lambda: self.handle_vote("right"))
        media_layout.addWidget(self.right_frame)

        layout.addLayout(media_layout)

        # Skip button
        self.skip_button = QPushButton("Skip Pair")
        self.skip_button.clicked.connect(self.load_new_pair)
        layout.addWidget(self.skip_button)

        # Status label
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

    def load_media_to_frame(self, frame, media_path):
        if frame.media_widget:
            if frame.media_player:
                frame.media_player.stop()
            frame.media_widget.deleteLater()
            frame.media_widget = None
            frame.media_player = None

        media = self.media_handler.load_media(media_path)

        if isinstance(media, AspectRatioWidget):
            frame.media_widget = media
            frame.layout.insertWidget(0, media)
            # Add click handler
            media.mousePressEvent = lambda e, p=media_path: self.show_preview(p)
        elif isinstance(media, tuple) and media[0].__class__.__name__ == 'AspectRatioWidget':
            if isinstance(media[1], QMovie):  # GIF
                frame.media_widget = media[0]
                frame.gif_movie = media[1]
                frame.layout.insertWidget(0, media[0])
                media[0].mousePressEvent = lambda e, p=media_path: self.show_preview(p)
            else:  # Video
                frame.media_widget = media[0]
                frame.media_player = media[1]
                frame.layout.insertWidget(0, media[0])
                media[1].play()
                media[0].mousePressEvent = lambda e, p=media_path: self.show_preview(p)

    def load_new_pair(self):
        """Load a new pair of media items for voting."""
        # Stop any playing media
        for frame in [self.left_frame, self.right_frame]:
            if frame.media_player:
                frame.media_player.stop()
            if frame.gif_movie:
                frame.gif_movie.stop()

        # Get new pair from database
        media_pair = self.get_pair_callback()
        if not media_pair or None in media_pair:
            self.status_label.setText("Not enough media items in database")
            self.disable_voting()
            self.images_loaded = False
            return

        # Store new pair
        self.current_left, self.current_right = media_pair
        self.images_loaded = True

        # Load media into frames
        self.load_media_to_frame(self.left_frame, self.current_left[1])
        self.load_media_to_frame(self.right_frame, self.current_right[1])

        # Enable voting and clear status
        self.enable_voting()
        self.status_label.clear()

    def show_preview(self, media_path):
        """Show media preview overlay"""
        media = self.media_handler.load_media(media_path)

        if isinstance(media, AspectRatioWidget):
            self.preview.show_media(media, media_path=media_path)
        elif isinstance(media, tuple) and media[0].__class__.__name__ == 'AspectRatioWidget':
            if isinstance(media[1], QMovie):  # GIF
                self.preview.show_media(media[0], gif_movie=media[1], media_path=media_path)
            else:  # Video
                self.preview.show_media(media[0], video_player=media[1], media_path=media_path)

    def handle_vote(self, vote):
        """Handle voting for a media item."""
        # Check cooldown
        current_time = time.time()
        if current_time - self.last_vote_time < self.vote_cooldown:
            return

        self.last_vote_time = current_time

        # Determine winner and loser
        if vote == "left":
            winner = self.current_left
            loser = self.current_right
        else:
            winner = self.current_right
            loser = self.current_left

        # Calculate new ratings
        rating = Rating(
            winner[2],  # winner's current rating
            loser[2],  # loser's current rating
            Rating.WIN,
            Rating.LOST
        )
        new_ratings = rating.get_new_ratings()

        # Update database
        self.update_ratings_callback(
            winner[0],  # winner_id
            loser[0],  # loser_id
            new_ratings['a'],  # new winner rating
            new_ratings['b']  # new loser rating
        )

        # Load new pair
        self.load_new_pair()

    def ensure_images_loaded(self):
        """Load images if they haven't been loaded yet."""
        if not self.images_loaded:
            self.load_new_pair()

    def enable_voting(self):
        """Enable voting buttons."""
        self.left_frame.vote_button.setEnabled(True)
        self.right_frame.vote_button.setEnabled(True)
        self.skip_button.setEnabled(True)

    def disable_voting(self):
        """Disable voting buttons."""
        self.left_frame.vote_button.setEnabled(False)
        self.right_frame.vote_button.setEnabled(False)
        self.skip_button.setEnabled(False)