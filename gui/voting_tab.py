import time

from PyQt6.QtCore import Qt, QTimer, QObject
from PyQt6.QtGui import QMovie, QKeyEvent
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QFrame, QSizePolicy)

from core.elo import Rating, ReliabilityCalculator
from core.media_utils import set_file_info, handle_video_single_click, handle_video_events
from core.preview_handler import MediaPreview
from core.media_utils import AspectRatioWidget


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

        self.default_style = self.styleSheet()

    def set_file_info(self, file_path):
        set_file_info(file_path, self.file_info_label)

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

    def flash_winner(self):
        """Create a subtle flash effect for winning media"""
        self.setStyleSheet("QFrame { background-color: rgba(255, 255, 255, 30); }")
        QTimer.singleShot(150, self.reset_style)

    def reset_style(self):
        """Reset frame style after flash"""
        self.setStyleSheet(self.default_style)


class PreloadPair(QObject):
    def __init__(self, media_handler):
        super().__init__()
        self.media_handler = media_handler
        self.left_data = None  # (id, path, rating)
        self.right_data = None
        self.left_media = None  # Loaded media widget
        self.right_media = None
        self.is_loaded = False

    def load_pair(self, left_data, right_data):
        """Load media pair in memory with error handling"""
        try:
            self.left_data = left_data
            self.right_data = right_data
            if left_data and right_data:
                self.left_media = self.media_handler.load_media(left_data[1]) or None
                self.right_media = self.media_handler.load_media(right_data[1]) or None
                self.is_loaded = bool(self.left_media and self.right_media)
            else:
                self.is_loaded = False
        except Exception as e:
            print(f"Failed to preload media: {str(e)}")
            self.is_loaded = False

    def cleanup(self):
        """Clean up loaded media"""
        for media in [self.left_media, self.right_media]:
            if isinstance(media, tuple):
                if media[1].__class__.__name__ == 'QMediaPlayer':
                    media[1].stop()
                elif media[1].__class__.__name__ == 'QMovie':
                    media[1].stop()
                media[0].deleteLater()
            elif media:
                media.deleteLater()
        self.left_media = None
        self.right_media = None
        self.is_loaded = False


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

        self.single_click_timer = QTimer(self)
        self.single_click_timer.setSingleShot(True)
        self.single_click_timer.timeout.connect(lambda: handle_video_single_click(self.pending_video_click))
        self.pending_video_click = []  # Stores (media_player, media_path)

        self.current_pair = PreloadPair(media_handler)
        self.next_pair = PreloadPair(media_handler)
        self.preload_timer = QTimer(self)
        self.preload_timer.setSingleShot(True)
        self.preload_timer.timeout.connect(self._finish_preload)

        # Add delayed preload timer
        self.delayed_preload_timer = QTimer(self)
        self.delayed_preload_timer.setSingleShot(True)
        self.delayed_preload_timer.timeout.connect(self._start_preload)

        self.history_tab = None

        self.setup_ui()

    def setup_ui(self):
        """Set up the voting interface."""
        layout = QVBoxLayout(self)

        # Create horizontal layout for media frames
        media_layout = QHBoxLayout()
        media_layout.setContentsMargins(0, 0, 0, 0)
        media_layout.setSpacing(10)  # Add some spacing between media frames

        # Status label
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 16px;")
        layout.addWidget(self.status_label)

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



        # Enable focus for keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()  # Ensure the widget has focus when the tab is opened

    def set_history_tab(self, history_tab):
        """Set reference to history tab"""
        self.history_tab = history_tab

    def eventFilter(self, obj, event):
        """Handle video widget events using shared utility."""
        handled = handle_video_events(
            event, obj,
            self.single_click_timer,
            self.pending_video_click,
            self.show_preview
        )
        if handled:
            return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard voting using arrow keys."""
        if event.key() == Qt.Key.Key_Left:
            self.handle_vote("left", 1)  # Regular vote for left image
        elif event.key() == Qt.Key.Key_Right:
            self.handle_vote("right", 1)  # Regular vote for right image

    def load_new_pair(self):
        """Load initial pairs"""
        if not self.active_album_id:
            self.status_label.setText("No active album selected")
            self.disable_voting()
            return

        # Get first pair
        media_pair = self.get_pair_callback(self.active_album_id)
        if not media_pair or None in media_pair:
            self._clear_frames()
            self.status_label.setText("No media items in this album")
            self.disable_voting()
            self.left_frame.button_container.hide()
            self.right_frame.button_container.hide()
            self.skip_button.hide()
            return

        self.status_label.setText("")

        self.left_frame.button_container.show()
        self.right_frame.button_container.show()
        self.skip_button.show()

        # Load current pair
        self.current_pair.load_pair(*media_pair)
        self._display_current_pair()

        # Schedule preload with a delay
        self.delayed_preload_timer.start(100)

    def _start_preload(self):
        """Start preloading next pair in the background"""
        media_pair = self.get_pair_callback(self.active_album_id)
        if media_pair and None not in media_pair:
            # Use a new timer to enable voting once preload is complete
            QTimer.singleShot(0, lambda: self._do_preload(media_pair))

    def _do_preload(self, media_pair):
        """Actually perform the preload"""
        self.next_pair.load_pair(*media_pair)
        self.enable_voting()

    def _display_current_pair(self):
        """Display current pair in frames"""
        if not self.current_pair.is_loaded:
            return

        # Clear existing media
        self._clear_frames()

        def setup_frame(frame, media, path):
            """Helper function to set up a single frame with its media"""
            if not media:
                frame.file_info_label.setText(f"Failed to load: {path}")
                frame.media_widget = None
                return

            if isinstance(media, tuple):
                frame.media_widget = media[0]

                if isinstance(media[1], QMovie):  # GIF
                    frame.gif_movie = media[1]
                    frame.layout.insertWidget(0, media[0])
                    media[0].mousePressEvent = lambda e, p=path: self.show_preview(p)
                else:  # Video
                    frame.media_player = media[1]
                    frame.layout.insertWidget(0, media[0])

                    # Set video-specific properties
                    frame.media_widget.setProperty('is_video', True)
                    frame.media_widget.setProperty('media_player', frame.media_player)
                    frame.media_widget.setProperty('media_path', path)
                    frame.media_widget.installEventFilter(self)
            else:
                frame.media_widget = media

            if frame.media_widget:
                frame.layout.insertWidget(0, frame.media_widget)
                frame.media_widget.mousePressEvent = lambda e, p=path: self.show_preview(p)
            else:
                frame.file_info_label.setText(f"Failed to load: {path}")

            frame.set_file_info(path)

        # Set up left frame
        left_path = self.current_pair.left_data[1] if self.current_pair.left_data else ""
        setup_frame(self.left_frame, self.current_pair.left_media, left_path)

        # Set up right frame
        right_path = self.current_pair.right_data[1] if self.current_pair.right_data else ""
        setup_frame(self.right_frame, self.current_pair.right_media, right_path)

        self.images_loaded = True

    def _clear_frames(self):
        """Clear media from frames"""
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
            if current_reliability < 85:
                target = 85
            elif current_reliability < 94:
                target = 94
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
                votes_text = "Maximum Reliability (94%) Reached!"

        self.reliability_label.setText(reliability_text)
        self.required_votes_label.setText(votes_text)

    def refresh_media_count(self):
        """Force refresh media count from database"""
        self.total_media = self.get_total_media_count(self.active_album_id)
        self.total_votes = self.get_total_votes(self.active_album_id)
        self.update_reliability_info()

    def show_preview(self, media_path, media_player=None):
        """Show media preview overlay"""
        media = self.media_handler.load_media(media_path)
        self.media_handler.pause_all_videos()
        if isinstance(media, AspectRatioWidget):
            self.preview.show_media(media, media_path=media_path)
        elif isinstance(media, tuple) and media[0].__class__.__name__ == 'AspectRatioWidget':
            if isinstance(media[1], QMovie):  # GIF
                self.preview.show_media(media[0], gif_movie=media[1], media_path=media_path)
            else:  # Video
                self.preview.show_media(media[0], video_player=media[1], media_path=media_path,
                                        thumbnail_media_player=media_player)

    def handle_vote(self, vote, vote_count):
        """Handle voting for a media item."""
        if not self.current_pair.is_loaded:
            return

        current_time = time.time()
        if current_time - self.last_vote_time < self.vote_cooldown:
            return

        self.last_vote_time = current_time
        self.left_frame.set_cooldown_style(True)
        self.right_frame.set_cooldown_style(True)

        # Flash the winning frame
        if vote == "left":
            winner = self.current_pair.left_data
            loser = self.current_pair.right_data
            self.left_frame.flash_winner()
        else:
            winner = self.current_pair.right_data
            loser = self.current_pair.left_data
            self.right_frame.flash_winner()

        n = self.total_media
        v = self.total_votes
        current_reliability = ReliabilityCalculator.calculate_reliability(n, v)
        k_factor = 32 if current_reliability < 85 else 16

        rating = Rating(winner[2], loser[2], Rating.WIN, Rating.LOST, k_factor)
        new_ratings = rating.get_new_ratings()

        # Update database
        for _ in range(vote_count):
            self.update_ratings_callback(
                winner[0], loser[0],
                new_ratings['a'], new_ratings['b'],
                self.active_album_id
            )

        self.ranking_tab.set_new_votes_flag()
        self.total_votes += vote_count

        # Delay the pair replacement
        QTimer.singleShot(150, self._replace_current_pair)

        # Start cooldown timer
        self.cooldown_timer.start(int(self.vote_cooldown * 1000))
        self.update_reliability_info()

        if self.history_tab:
            self.history_tab.set_needs_refresh()

    def _replace_current_pair(self):
        """Replace current pair with preloaded pair"""
        if self.next_pair.is_loaded:
            self.current_pair.cleanup()
            self.current_pair, self.next_pair = self.next_pair, self.current_pair
            self._display_current_pair()

            # Schedule preload with a slight delay
            self.delayed_preload_timer.start(100)
        else:
            # If next pair isn't loaded, load new pair
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

    def _finish_preload(self):
        """Called when preload is complete"""
        if self.next_pair.is_loaded:
            self.enable_voting()
