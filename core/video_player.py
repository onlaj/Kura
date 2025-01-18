from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                            QSlider, QStyle, QSizePolicy)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from gui.voting_tab import AspectRatioWidget

class VideoPlayer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                          QSizePolicy.Policy.Expanding)

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)  # Reduce spacing between video and controls

        # Create aspect ratio container for video
        video_container = QWidget()
        video_container.setLayout(QVBoxLayout())
        video_container.layout().setContentsMargins(0, 0, 0, 0)
        video_container.setSizePolicy(QSizePolicy.Policy.Expanding,
                                    QSizePolicy.Policy.Expanding)

        # Video widget
        self.video_widget = QVideoWidget()
        video_container.layout().addWidget(self.video_widget)

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
        controls_layout.setContentsMargins(5, 5, 5, 5)  # Add some padding

        # Play/Pause button
        self.play_button = QPushButton()
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_button.clicked.connect(self.play_pause)
        controls_layout.addWidget(self.play_button)

        # Position slider
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self.set_position)
        controls_layout.addWidget(self.position_slider)

        # Volume slider
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setMaximumWidth(100)
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
        """Update slider position."""
        self.position_slider.setValue(position)

    def duration_changed(self, duration):
        """Update slider range when video duration changes."""
        self.position_slider.setRange(0, duration)

    def set_position(self, position):
        """Set video position from slider."""
        self.media_player.setPosition(position)

    def set_volume(self, volume):
        """Set audio volume."""
        self.audio_output.setVolume(volume / 100.0)

    def stop(self):
        """Stop video playback."""
        self.media_player.stop()
