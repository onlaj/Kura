import cv2
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QSlider, QStyle, QSizePolicy, QLabel)

from gui.voting_tab import AspectRatioWidget


class ClickableSlider(QSlider):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)

    def mousePressEvent(self, event):
        """Handle mouse press events to move the slider to the clicked position."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Calculate the new position based on the click
            value = self.minimum() + ((self.maximum() - self.minimum()) * event.position().x()) / self.width()
            self.setValue(int(value))
            event.accept()
            # Emit the sliderMoved signal manually
            self.sliderMoved.emit(int(value))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move events to update the slider while dragging."""
        if event.buttons() & Qt.MouseButton.LeftButton:
            # Calculate the new position based on the mouse position
            value = self.minimum() + ((self.maximum() - self.minimum()) * event.position().x()) / self.width()
            self.setValue(int(value))
            event.accept()
            # Emit the sliderMoved signal manually
            self.sliderMoved.emit(int(value))
        super().mouseMoveEvent(event)

class VideoPlayer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create aspect ratio container for video
        video_container = QWidget()
        video_container.setLayout(QVBoxLayout())
        video_container.layout().setContentsMargins(0, 0, 0, 0)
        video_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Video widget
        self.video_widget = QVideoWidget()
        self.video_widget.hide()  # Hide video widget initially
        video_container.layout().addWidget(self.video_widget)

        # Thumbnail label
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        video_container.layout().addWidget(self.thumbnail_label)

        # Add aspect ratio wrapper
        aspect_widget = AspectRatioWidget(video_container, 16/9)
        layout.addWidget(aspect_widget)

        # Media player setup
        self.media_player = QMediaPlayer()
        self.media_player.setVideoOutput(self.video_widget)

        # Add audio output
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)

        # Create controls widget with background
        controls_widget = QWidget()
        controls_widget.setStyleSheet("background-color: rgba(30, 30, 30, 180);")
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(5, 5, 5, 5)

        # Play/Pause button
        self.play_button = QPushButton()
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Disable focus
        self.play_button.clicked.connect(self.play_pause)
        controls_layout.addWidget(self.play_button)

        # Current time label
        self.current_time_label = QLabel("00:00")
        self.current_time_label.setStyleSheet("color: white; font-size: 12px;")
        controls_layout.addWidget(self.current_time_label)

        # Position slider (using the new ClickableSlider)
        self.position_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self.set_position)
        self.position_slider.setMinimumHeight(20)
        self.position_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Disable focus
        self.position_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #444;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #fff;
                width: 16px;
                height: 16px;
                margin: -4px 0;
                border-radius: 8px;
            }
        """)
        controls_layout.addWidget(self.position_slider)

        # Total time label
        self.total_time_label = QLabel("00:00")
        self.total_time_label.setStyleSheet("color: white; font-size: 12px;")
        controls_layout.addWidget(self.total_time_label)

        # Volume slider (using the new ClickableSlider)
        self.volume_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setMaximumWidth(100)
        self.volume_slider.setMinimumHeight(20)
        self.volume_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Disable focus
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #444;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #fff;
                width: 16px;
                height: 16px;
                margin: -4px 0;
                border-radius: 8px;
            }
        """)
        self.volume_slider.valueChanged.connect(self.set_volume)
        controls_layout.addWidget(self.volume_slider)

        layout.addWidget(controls_widget)

        # Connect signals
        self.media_player.playbackStateChanged.connect(self.update_play_button)
        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.durationChanged.connect(self.duration_changed)

        # Set initial volume
        self.set_volume(70)

    def set_source(self, path):
        """Set the video source."""
        url = QUrl.fromLocalFile(path)
        print(f"Setting video source: {url.toString()}")
        self.media_player.setSource(url)
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))

        # Extract and display thumbnail
        self.extract_and_display_thumbnail(path)

    def extract_and_display_thumbnail(self, path):
        """Extract a thumbnail from the middle of the video and display it."""
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            print(f"Error: Could not open video {path}")
            return

        # Get total number of frames
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames == 0:
            print(f"Error: Video {path} has no frames")
            return

        # Set the frame position to the middle of the video
        middle_frame = total_frames // 2
        cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame)
        ret, frame = cap.read()
        if not ret:
            print(f"Error: Could not read frame {middle_frame} from video {path}")
            return

        # Convert the frame to QImage
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        bytes_per_line = ch * w
        q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

        # Convert QImage to QPixmap and set it to the thumbnail label
        pixmap = QPixmap.fromImage(q_img)
        self.thumbnail_label.setPixmap(pixmap.scaled(self.video_widget.size(), Qt.AspectRatioMode.KeepAspectRatio))

        # Hide the thumbnail when the video starts playing
        self.media_player.playbackStateChanged.connect(self.hide_thumbnail_on_play)

        cap.release()

    def hide_thumbnail_on_play(self, state):
        """Hide the thumbnail and show the video widget when the video starts playing."""
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.thumbnail_label.hide()
            self.video_widget.show()  # Show video widget when playing
        else:
            self.thumbnail_label.show()
            self.video_widget.hide()  # Hide video widget when paused/stopped

    def play_pause(self):
        """Toggle play/pause state."""
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def update_play_button(self, state):
        """Update play button icon based on playback state."""
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        else:
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))

    def position_changed(self, position):
        """Update slider position and current time label."""
        self.position_slider.setValue(position)
        self.current_time_label.setText(self.format_time(position))

    def duration_changed(self, duration):
        """Update slider range and total time label when video duration changes."""
        self.position_slider.setRange(0, duration)
        self.total_time_label.setText(self.format_time(duration))

    def set_position(self, position):
        """Set video position from slider."""
        self.media_player.setPosition(position)

    def set_volume(self, volume):
        """Set audio volume."""
        self.audio_output.setVolume(volume / 100.0)

    def stop(self):
        """Stop video playback."""
        self.media_player.stop()

    def format_time(self, milliseconds):
        """Convert milliseconds to a formatted time string (MM:SS)."""
        seconds = milliseconds // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02}:{seconds:02}"