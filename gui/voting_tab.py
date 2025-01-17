from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QFrame, QSizePolicy, QDialog)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QMovie
from PyQt6.QtMultimediaWidgets import QVideoWidget
from core.elo import Rating
import time


class MediaPreviewDialog(QDialog):
    def __init__(self, media_path, media_handler, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preview")
        self.setModal(True)

        # Set up layout
        layout = QVBoxLayout(self)

        # Load media
        media = media_handler.load_media(media_path, (800, 600))

        if isinstance(media, QPixmap):
            # Static image preview
            label = QLabel()
            label.setPixmap(media)
            layout.addWidget(label)
        elif isinstance(media, tuple) and isinstance(media[0], QLabel):
            # Animated GIF preview
            layout.addWidget(media[0])
            self.gif_movie = media[1]  # Keep reference to prevent garbage collection
        else:
            # Video preview
            video_widget, player = media
            layout.addWidget(video_widget)
            player.play()

        # Add close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self.resize(850, 650)


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

        # Preview button
        self.preview_button = QPushButton("Preview")
        self.layout.addWidget(self.preview_button)

        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)


class VotingTab(QWidget):
    def __init__(self, get_pair_callback, update_ratings_callback, media_handler):
        super().__init__()
        self.get_pair_callback = get_pair_callback
        self.update_ratings_callback = update_ratings_callback
        self.media_handler = media_handler

        self.current_left = None
        self.current_right = None
        self.images_loaded = False
        self.last_vote_time = 0
        self.vote_cooldown = 1.0  # seconds

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
        self.left_frame.preview_button.clicked.connect(
            lambda: self.show_preview(self.current_left[1]))
        media_layout.addWidget(self.left_frame)

        # Right media frame
        self.right_frame = MediaFrame()
        self.right_frame.vote_button.clicked.connect(
            lambda: self.handle_vote("right"))
        self.right_frame.preview_button.clicked.connect(
            lambda: self.show_preview(self.current_right[1]))
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
        """Load media into a frame."""
        # Clear existing media
        if frame.media_widget:
            if frame.media_player:
                frame.media_player.stop()
            if frame.gif_movie:
                frame.gif_movie.stop()
            frame.media_widget.deleteLater()
            frame.media_widget = None
            frame.media_player = None
            frame.gif_movie = None

        # Load new media
        media = self.media_handler.load_media(media_path)

        if isinstance(media, QPixmap):
            # Static image
            label = QLabel()
            label.setPixmap(media)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            frame.media_widget = label
            frame.layout.insertWidget(0, label)
        elif isinstance(media, tuple) and isinstance(media[0], QLabel):
            # Animated GIF
            frame.media_widget = media[0]
            frame.gif_movie = media[1]
            frame.layout.insertWidget(0, media[0])
        else:
            # Video
            video_widget, player = media
            frame.media_widget = video_widget
            frame.media_player = player
            frame.layout.insertWidget(0, video_widget)
            player.play()

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
        """Show full-size preview of the media item."""
        dialog = MediaPreviewDialog(media_path, self.media_handler, self)
        dialog.exec()

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