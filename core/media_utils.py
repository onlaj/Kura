# core/media_utils.py
import logging
import os
from datetime import datetime

import cv2
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QPainterPath
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy

logger = logging.getLogger(__name__)


def grab_video_frame(file_path):
    """
    Grab the middle frame of a video with OpenCV.

    Safe to call from any thread (uses QImage, not QPixmap).

    Returns:
        (QImage, float): the frame (null QImage on failure) and the video's
        aspect ratio (falls back to 16/9 when it cannot be determined).
    """
    aspect_ratio = 16 / 9
    try:
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            logger.warning(f"Could not open video {file_path}")
            return QImage(), aspect_ratio

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if width > 0 and height > 0:
            aspect_ratio = width / height

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            logger.warning(f"Video {file_path} has no frames")
            cap.release()
            return QImage(), aspect_ratio

        cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            logger.warning(f"Error reading frame from {file_path}")
            return QImage(), aspect_ratio

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        if h > 0:
            aspect_ratio = w / h
        # .copy() detaches from the numpy buffer, which is freed on return
        image = QImage(frame_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
        return image, aspect_ratio

    except Exception as e:
        logger.error(f"Error grabbing video frame from {file_path}: {str(e)}")
        return QImage(), aspect_ratio


def add_play_button_overlay(base_pixmap: QPixmap) -> QPixmap:
    """Return a copy of the pixmap with a semi-transparent play button drawn on top."""
    composite = QPixmap(base_pixmap.size())
    composite.fill(Qt.GlobalColor.transparent)
    painter = QPainter(composite)
    painter.drawPixmap(0, 0, base_pixmap)

    button_size = min(base_pixmap.width(), base_pixmap.height()) // 4
    x_center = base_pixmap.width() // 2
    y_center = base_pixmap.height() // 2

    # Semi-transparent circle
    painter.setBrush(QColor(255, 255, 255, 90))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(x_center - button_size // 2, y_center - button_size // 2, button_size, button_size)

    # Play triangle
    triangle_size = button_size // 2
    path = QPainterPath()
    path.moveTo(x_center - triangle_size // 3, y_center - triangle_size // 2)
    path.lineTo(x_center - triangle_size // 3, y_center + triangle_size // 2)
    path.lineTo(x_center + triangle_size // 2, y_center)
    path.closeSubpath()
    painter.setBrush(QColor(0, 0, 0, 100))
    painter.drawPath(path)
    painter.end()
    return composite


def handle_video_events(event, obj, single_click_timer, pending_video_click, show_preview_callback):
    """Handle video-related mouse events (to be called from eventFilter)."""
    if event.type() == QEvent.Type.MouseButtonPress:
        if obj.property('is_video'):
            pending_video_click[:] = [
                obj.property('media_player'),
                obj.property('media_path')
            ]
            single_click_timer.start(250)
            return True
    elif event.type() == QEvent.Type.MouseButtonDblClick:
        if obj.property('is_video'):
            single_click_timer.stop()
            media_player = obj.property('media_player')
            media_path = obj.property('media_path')
            show_preview_callback(media_path, media_player)
            pending_video_click.clear()
            return True
    return False

def handle_video_single_click(pending_video_click):
    """Handle video play/pause logic (to be called from single-click timer)."""
    if pending_video_click:
        media_player, _ = pending_video_click
        if media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            media_player.pause()
        else:
            media_player.play()
        pending_video_click.clear()

class AspectRatioWidget(QWidget):
    def __init__(self, widget, aspect_ratio=16/9, parent=None):
        super().__init__(parent)
        self.aspect_ratio = aspect_ratio
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(widget)

        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def resizeEvent(self, event):
        width = self.width()
        height = self.height()
        target_aspect = self.aspect_ratio
        current_aspect = width / height if height != 0 else 1
        if current_aspect > target_aspect:
            new_width = int(height * target_aspect)
            offset = (width - new_width) // 2
            self.layout().setContentsMargins(offset, 0, offset, 0)
        else:
            new_height = int(width / target_aspect)
            offset = (height - new_height) // 2
            self.layout().setContentsMargins(0, offset -18, 0, offset - 18)

        super().resizeEvent(event)

def set_file_info(file_path, info_label, elide=False, max_width=150,
                  file_size=None, modified_time=None):
    """
    Set file information in the given label, optionally eliding the file name.

    When file_size and modified_time are provided (e.g. pre-fetched by a
    background loader), the file system is not touched at all.
    """
    if file_size is None or modified_time is None:
        if not os.path.exists(file_path):
            info_label.setText(f"File not found: {file_path}")
            return
        file_size = os.path.getsize(file_path)
        modified_time = os.path.getmtime(file_path)

    file_name = os.path.basename(file_path)

    # Format file size
    if file_size < 1024:
        file_size_str = f"{file_size} B"
    elif file_size < 1024 * 1024:
        file_size_str = f"{file_size / 1024:.1f} KB"
    else:
        file_size_str = f"{file_size / (1024 * 1024):.1f} MB"

    # Format modification date
    mod_date = datetime.fromtimestamp(modified_time).strftime("%Y-%m-%d %H:%M:%S")

    # Elide file name if required
    if elide:
        elided_name = elide_text(file_name, max_width, info_label)
        info_label.setText(f"{elided_name}\n{file_size_str} | {mod_date}")
        info_label.setToolTip(f"{file_name}\nSize: {file_size_str}\nModified: {mod_date}")
    else:
        info_label.setText(f"{file_name}\n{file_size_str} | {mod_date}")


def elide_text(text, max_width, label):
    """Elide text to fit within the specified width using the label's font metrics."""
    metrics = label.fontMetrics()
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, max_width)