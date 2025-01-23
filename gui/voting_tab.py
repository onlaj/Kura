import os
import time
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QMovie, QKeyEvent
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QFrame, QSizePolicy)

from core.elo import Rating
from core.preview_handler import MediaPreview


class MediaFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Media display widget (will be set later)
        self.media_widget = None
        self.media_player = None
        self.gif_movie = None  # Added for GIF support

        # File info label
        self.file_info_label = QLabel()
        self.file_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_info_label.setStyleSheet("font-size: 10px; color: white;")
        self.layout.addWidget(self.file_info_label)

        # Vote button container
        self.button_container = QWidget()
        self.button_layout = QHBoxLayout(self.button_container)
        self.button_layout.setContentsMargins(0, 0, 0, 0)
        self.button_layout.setSpacing(5)  # Add some spacing between buttons

        # Regular Vote button
        self.vote_button = QPushButton("Vote")
        self.vote_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Disable focus
        self.button_layout.addWidget(self.vote_button)

        # Double Vote button
        self.double_vote_button = QPushButton("Double Vote")
        self.double_vote_button.setFixedWidth(80)  # Smaller width
        self.double_vote_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Disable focus
        self.button_layout.addWidget(self.double_vote_button)

        self.layout.addWidget(self.button_container)

        # Set size policy for the frame
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(400, 400)  # Set a minimum size for the media container

    def set_file_info(self, file_path):
        """Set the file information (name, size, modification date) in the label."""
        if not os.path.exists(file_path):
            self.file_info_label.setText("File not found: " + file_path)
            return

        # Get file name
        file_name = os.path.basename(file_path)

        # Get file size in KB/MB
        file_size = os.path.getsize(file_path)
        if file_size < 1024:
            file_size_str = f"{file_size} B"
        elif file_size < 1024 * 1024:
            file_size_str = f"{file_size / 1024:.1f} KB"
        else:
            file_size_str = f"{file_size / (1024 * 1024):.1f} MB"

        # Get modification date
        mod_time = os.path.getmtime(file_path)
        mod_date = datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M:%S")

        # Set the label text
        self.file_info_label.setText(f"{file_name} \n {file_size_str} | {mod_date}")

    def set_cooldown_style(self, on_cooldown):
        """Set the button style when on cooldown."""
        if on_cooldown:
            self.vote_button.setStyleSheet("background-color: grey; color: white;")
            self.vote_button.setText("Cooldown...")
            self.double_vote_button.setStyleSheet("background-color: grey; color: white;")
            self.double_vote_button.setText("Cooldown...")
        else:
            self.vote_button.setStyleSheet("")
            self.vote_button.setText("Vote")
            self.double_vote_button.setStyleSheet("")
            self.double_vote_button.setText("Double Vote")


class AspectRatioWidget(QWidget):
    def __init__(self, widget, aspect_ratio=16 / 9, parent=None):
        super().__init__(parent)
        self.aspect_ratio = aspect_ratio
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(widget)

        # The contained widget should expand in both directions
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # This widget should expand in both directions
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

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
    def __init__(self, get_pair_callback, update_ratings_callback, media_handler, ranking_tab):
        super().__init__()
        self.get_pair_callback = get_pair_callback
        self.update_ratings_callback = update_ratings_callback
        self.media_handler = media_handler
        self.ranking_tab = ranking_tab  # Store reference to RankingTab
        self.preview = MediaPreview(self)

        self.current_left = None
        self.current_right = None
        self.images_loaded = False
        self.last_vote_time = 0
        self.vote_cooldown = 1.0
        self.cooldown_timer = QTimer(self)
        self.cooldown_timer.timeout.connect(self.end_cooldown)
        self.active_album_id = 1  # Default album

        self.setup_ui()


    def setup_ui(self):
        """Set up the voting interface."""
        layout = QVBoxLayout(self)

        # Create horizontal layout for media frames
        media_layout = QHBoxLayout()
        media_layout.setContentsMargins(0, 0, 0, 0)
        media_layout.setSpacing(10)  # Add some spacing between media frames

        # Left media frame
        self.left_frame = MediaFrame()
        self.left_frame.vote_button.clicked.connect(
            lambda: self.handle_vote("left", 1))
        self.left_frame.double_vote_button.clicked.connect(
            lambda: self.handle_vote("left", 2))
        media_layout.addWidget(self.left_frame, 1)  # Equal stretch for both frames

        # Right media frame
        self.right_frame = MediaFrame()
        self.right_frame.vote_button.clicked.connect(
            lambda: self.handle_vote("right", 1))
        self.right_frame.double_vote_button.clicked.connect(
            lambda: self.handle_vote("right", 2))
        media_layout.addWidget(self.right_frame, 1)  # Equal stretch for both frames

        layout.addLayout(media_layout)

        # Skip button
        self.skip_button = QPushButton("Skip Pair")
        self.skip_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Disable focus
        self.skip_button.clicked.connect(self.load_new_pair)
        layout.addWidget(self.skip_button)

        # Status label
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Enable focus for keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()  # Ensure the widget has focus when the tab is opened

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard voting using arrow keys."""
        if event.key() == Qt.Key.Key_Left:
            self.handle_vote("left", 1)  # Regular vote for left image
        elif event.key() == Qt.Key.Key_Right:
            self.handle_vote("right", 1)  # Regular vote for right image

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
                media[0].mousePressEvent = lambda e, f=frame.media_player, p=media_path: self.show_preview(p, f)

        # Ensure the media widget expands to fill the frame
        if frame.media_widget:
            frame.media_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Set file information in the label
        frame.set_file_info(media_path)

    def load_new_pair(self):
        """Load a new pair of media items for voting."""
        # Stop any playing media
        for frame in [self.left_frame, self.right_frame]:
            if frame.media_player:
                frame.media_player.stop()
            if frame.gif_movie:
                frame.gif_movie.stop()

        # Get new pair from database using active album
        media_pair = self.get_pair_callback(self.active_album_id)  # Pass album_id
        if not media_pair or None in media_pair:
            self.status_label.setText("Not enough media items in this album")
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

    def set_active_album(self, album_id: int):
        """Set the active album and reload media pair."""
        self.active_album_id = album_id
        self.load_new_pair()

    def show_preview(self, media_path, media_player = None):
        """Show media preview overlay"""
        media = self.media_handler.load_media(media_path)
        self.media_handler.pause_all_videos()
        if isinstance(media, AspectRatioWidget):
            self.preview.show_media(media, media_path=media_path)
        elif isinstance(media, tuple) and media[0].__class__.__name__ == 'AspectRatioWidget':
            if isinstance(media[1], QMovie):  # GIF
                self.preview.show_media(media[0], gif_movie=media[1], media_path=media_path)
            else:  # Video
                self.preview.show_media(media[0], video_player=media[1], media_path=media_path, thumbnail_media_player=media_player)

    def handle_vote(self, vote, vote_count):
        """Handle voting for a media item."""
        # Check cooldown
        current_time = time.time()
        if current_time - self.last_vote_time < self.vote_cooldown:
            return

        self.last_vote_time = current_time

        # Apply cooldown styling
        self.left_frame.set_cooldown_style(True)
        self.right_frame.set_cooldown_style(True)

        # Start cooldown timer
        self.cooldown_timer.start(int(self.vote_cooldown * 1000))

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
        for _ in range(vote_count):
            self.update_ratings_callback(
                winner[0],  # winner_id
                loser[0],  # loser_id
                new_ratings['a'],  # new winner rating
                new_ratings['b'],  # new loser rating
                self.active_album_id  # new album_id parameter
            )

        # Notify RankingTab that there are new votes
        self.ranking_tab.set_new_votes_flag()

        # Load new pair
        self.load_new_pair()

    def end_cooldown(self):
        """End the cooldown period and revert button styles."""
        self.left_frame.set_cooldown_style(False)
        self.right_frame.set_cooldown_style(False)
        self.cooldown_timer.stop()

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