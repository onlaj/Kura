import os
import time
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QMovie, QKeyEvent
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QFrame, QSizePolicy)

from core.elo import Rating, ReliabilityCalculator
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
    def __init__(self, get_pair_callback, update_ratings_callback, media_handler,
                 ranking_tab, get_total_media_count, get_total_votes):
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

        self.reliability_label = QLabel()
        self.required_votes_label = QLabel()

        self.get_total_media_count = get_total_media_count
        self.get_total_votes = get_total_votes
        self.total_media = 0
        self.total_votes = 0

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

        #  Reliability info widgets
        reliability_layout = QHBoxLayout()

        self.reliability_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reliability_label.setStyleSheet("color: #AAAAAA;")
        reliability_layout.addWidget(self.reliability_label)

        self.required_votes_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.required_votes_label.setStyleSheet("color: #AAAAAA;")
        reliability_layout.addWidget(self.required_votes_label)

        layout.addLayout(reliability_layout)

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
        # Clear existing media first
        for frame in [self.left_frame, self.right_frame]:
            if frame.media_widget:
                if frame.media_player:
                    frame.media_player.stop()
                    frame.media_player.deleteLater()
                if frame.gif_movie:
                    frame.gif_movie.stop()
                    frame.gif_movie.deleteLater()
                frame.media_widget.deleteLater()
                frame.media_widget = None
                frame.media_player = None
                frame.gif_movie = None

        # Clear file info labels
        self.left_frame.file_info_label.clear()
        self.right_frame.file_info_label.clear()

        if not self.active_album_id:
            self.status_label.setText("No active album selected")
            self.disable_voting()
            self.images_loaded = False
            return

        # Get new pair from database
        media_pair = self.get_pair_callback(self.active_album_id)
        if not media_pair or None in media_pair:
            self.status_label.setText("No media items in this album")
            self.disable_voting()
            self.images_loaded = False
            return

        # Rest of existing loading logic...
        self.current_left, self.current_right = media_pair
        self.images_loaded = True
        self.load_media_to_frame(self.left_frame, self.current_left[1])
        self.load_media_to_frame(self.right_frame, self.current_right[1])
        self.enable_voting()
        self.status_label.clear()
        self.update_reliability_info()

    def set_active_album(self, album_id: int):
        """Set the active album and reload media pair."""
        self.active_album_id = album_id
        self._refresh_counts()
        self.load_new_pair()

    def _refresh_counts(self):
        """Refresh media and vote counts from database"""
        self.total_media = self.get_total_media_count(self.active_album_id)
        self.total_votes = self.get_total_votes(self.active_album_id)
        self.update_reliability_info()

    def update_reliability_info(self):
        """Update reliability information using cached values"""
        if self.total_media == 0:
            current_reliability = 0.0
            target = None
        else:
            current_reliability = ReliabilityCalculator.calculate_reliability(
                self.total_media, self.total_votes
            )
            # Determine next target based on current reliability
            if current_reliability < 90:
                target = 90
            elif current_reliability < 99:
                target = 99
            else:
                target = None

        # Update reliability labels
        reliability_text = f"Current Reliability: {current_reliability:.1f}%"

        if target:
            needed_votes = ReliabilityCalculator.calculate_required_votes(
                self.total_media, target
            )
            remaining = max(0, needed_votes - self.total_votes)
            votes_text = f"Votes to {target}%: {remaining}"
        else:
            if self.total_media == 0:
                votes_text = "Add media to calculate reliability"
            else:
                votes_text = "Maximum Reliability (99%) Reached!"

        self.reliability_label.setText(reliability_text)
        self.required_votes_label.setText(votes_text)

    def refresh_media_count(self):
        """Force refresh media count from database"""
        self.total_media = self.get_total_media_count(self.active_album_id)
        self.total_votes = self.get_total_votes(self.active_album_id)
        self.update_reliability_info()

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

        # Increment local counter
        self.total_votes += vote_count

        # Load new pair
        self.load_new_pair()

        self.update_reliability_info()  # Add this line

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