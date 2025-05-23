from functools import lru_cache
import cv2
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QPixmap, QImage, QPainter, QBrush, QColor, QPainterPath
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QSlider, QStyle, QSizePolicy, QLabel)

from core.media_utils import AspectRatioWidget
import logging
from utils.config import DEFAULT_VOLUME
#from core.media_handler import ScalableLabel


logger = logging.getLogger(__name__)

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


class ClickInterceptWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

    def mousePressEvent(self, event):
        # Intercept clicks and do nothing
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setBrush(QBrush(QColor(0, 0, 0, 120)))  # Reduced opacity
        painter.setPen(Qt.PenStyle.NoPen)  # No border
        painter.drawRect(self.rect())  # Fill the widget's entire area


class VideoPlayer(QWidget):
    default_volume = DEFAULT_VOLUME

    @staticmethod
    @lru_cache(maxsize=200)
    def _get_video_thumbnail(file_path: str) -> QPixmap:
        """Cached thumbnail generation with fallback handling"""
        try:
            cap = cv2.VideoCapture(file_path)
            if not cap.isOpened():
                logger.warning(f"Error: Could not open video {file_path}")
                return QPixmap()

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames == 0:
                logger.warning(f"Error: Video {file_path} has no frames")
                cap.release()
                return QPixmap()

            middle_frame = total_frames // 2
            cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame)
            ret, frame = cap.read()
            cap.release()

            if not ret:
                logger.warning(f"Error reading frame from {file_path}")
                return QPixmap()

            # Convert to QPixmap
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            return QPixmap.fromImage(q_img)

        except Exception as e:
            logger.error(f"Error generating thumbnail for {file_path}: {str(e)}")
            return QPixmap()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._is_looping = False

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create aspect ratio container for video
        video_container = QWidget()
        video_container.setLayout(QVBoxLayout())
        video_container.layout().setContentsMargins(0, 0, 0, 0)
        video_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Video widget with click handling
        self.video_widget = QVideoWidget()
        self.video_widget.hide()  # Hide video widget initially
        video_container.layout().addWidget(self.video_widget)

        # Thumbnail label with click handling
        from core.media_handler import ScalableLabel
        self.thumbnail_label = ScalableLabel()
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        video_container.layout().addWidget(self.thumbnail_label)

        # Add aspect ratio wrapper
        layout.addWidget(video_container)

        # Media player setup
        self.media_player = QMediaPlayer()
        self.media_player.setVideoOutput(self.video_widget)

        # Add audio output
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)

        # Create controls widget with background
        controls_widget = ClickInterceptWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(5, 5, 5, 5)

        # Play/Pause button
        self.play_button = QPushButton()
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Disable focus
        self.play_button.clicked.connect(self.play_pause)
        self.play_button.setStyleSheet("""
                    QPushButton {
                        background: #444;
                        border: none;
                        padding: 5px;
                    }
                    QPushButton:hover {
                        background: rgba(255, 255, 255, 0.8);
                        border-radius: 4px;
                    }
                """)
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
        self.volume_slider.setValue(DEFAULT_VOLUME)
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
        self.media_player.mediaStatusChanged.connect(self.handle_media_status_changed)

        # Set initial volume
        self.set_volume(DEFAULT_VOLUME)

    def setLooping(self, loop: bool):
        """Enable or disable video looping."""
        self._is_looping = loop

    def handle_media_status_changed(self, status):
        """Handle media status changes, e.g., for looping."""
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self._is_looping:
            self.media_player.setPosition(0)
            self.media_player.play()

    def set_source(self, path):
        """Set the video source."""
        url = QUrl.fromLocalFile(path)
        logger.info(f"Setting video source: {url.toString()}")
        self.media_player.setSource(url)
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))

        # Extract and display thumbnail
        self.extract_and_display_thumbnail(path)

        # Connect the playback state signal to handle thumbnail visibility
        self.media_player.playbackStateChanged.connect(self.hide_thumbnail_on_play)

    def extract_and_display_thumbnail(self, path):
        """Display cached thumbnail with play button overlay"""
        pixmap = self._get_video_thumbnail(path)

        def add_play_button_overlay(base_pixmap):
            """Helper to add play button overlay to any pixmap"""
            composite = QPixmap(base_pixmap.size())
            composite.fill(Qt.GlobalColor.transparent)
            painter = QPainter(composite)
            painter.drawPixmap(0, 0, base_pixmap)

            # Calculate sizes and positions
            button_size = min(base_pixmap.width(), base_pixmap.height()) // 4
            x_center = base_pixmap.width() // 2
            y_center = base_pixmap.height() // 2

            # Draw semi-transparent circle
            painter.setBrush(QColor(255, 255, 255, 90))  # 70% opacity white
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(x_center - button_size // 2, y_center - button_size // 2, button_size, button_size)

            # Draw play triangle
            triangle_size = button_size // 2
            path = QPainterPath()
            path.moveTo(x_center - triangle_size // 3, y_center - triangle_size // 2)
            path.lineTo(x_center - triangle_size // 3, y_center + triangle_size // 2)
            path.lineTo(x_center + triangle_size // 2, y_center)
            path.closeSubpath()
            painter.setBrush(QColor(0, 0, 0, 100))  # 80% opacity black
            painter.drawPath(path)
            painter.end()
            return composite

        if pixmap.isNull():
            # Create error thumbnail with overlay
            error_pixmap = QPixmap(400, 300)
            error_pixmap.fill(Qt.GlobalColor.darkGray)
            final_pixmap = add_play_button_overlay(error_pixmap)
        else:
            # Add overlay to valid thumbnail
            final_pixmap = add_play_button_overlay(pixmap)

        # Configure label
        self.thumbnail_label.setMinimumSize(1, 1)
        self.thumbnail_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        self.thumbnail_label.setPixmap(final_pixmap)
        #
        self.thumbnail_label.mousePressEvent = self.on_thumbnail_clicked

    def on_thumbnail_clicked(self, event):
        """Handle thumbnail clicks to start playback"""
        if self.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.play_pause()


    def hide_thumbnail_on_play(self, state):
        """Hide the thumbnail and show the video widget when the video starts playing."""
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.thumbnail_label.hide()
            self.video_widget.show()  # Show video widget when playing


    def play_pause(self):
        """Toggle play/pause state."""
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.set_volume(DEFAULT_VOLUME)
            self.volume_slider.setValue(DEFAULT_VOLUME)
            self.media_player.play()

    def update_play_button(self, state):
        """Update play button icon based on playback state."""
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        else:
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))

    def position_changed(self, position):
        """Update slider position and current time label."""
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
            self.media_player.play()

        self.position_slider.setValue(position)
        self.current_time_label.setText(self.format_time(position))

    def duration_changed(self, duration):
        """Update slider range and total time label when video duration changes."""
        self.position_slider.setRange(0, duration)
        self.total_time_label.setText(self.format_time(duration))

    def set_position(self, position):
        """Set video position from slider."""
        self.media_player.play()
        self.media_player.setPosition(position)

    def set_volume(self, volume):
        """Set audio volume and update global default."""
        self.audio_output.setVolume(volume / 100.0)
        global DEFAULT_VOLUME
        DEFAULT_VOLUME = volume

    def stop(self):
        """Stop video playback."""
        self.media_player.stop()

    def pause(self) -> None:
        """Attempt to pause the media playback, silently ignore any failures."""
        try:
            if self.media_player and self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.media_player.pause()
        except RuntimeError:
            # Handle case where underlying C++ object is deleted
            pass
        except Exception as e:
            logger.debug(f"Pause error: {str(e)}")


    @staticmethod
    def format_time(milliseconds):
        """Convert milliseconds to a formatted time string (MM:SS)."""
        seconds = milliseconds // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02}:{seconds:02}"