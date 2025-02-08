# core/media_utils.py
import os
from datetime import datetime
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy


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
            offset = ((width - new_width) // 2) - 20
            self.layout().setContentsMargins(offset, 0, offset, 0)
        else:
            new_height = int(width / target_aspect)
            offset = ((height - new_height) // 2) - 20
            self.layout().setContentsMargins(0, offset, 0, offset)

        super().resizeEvent(event)

def set_file_info(file_path, info_label, elide=False, max_width=150):
    """Set file information in the given label, optionally eliding the file name."""
    if not os.path.exists(file_path):
        info_label.setText(f"File not found: {file_path}")
        return

    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    # Format file size
    if file_size < 1024:
        file_size_str = f"{file_size} B"
    elif file_size < 1024 * 1024:
        file_size_str = f"{file_size / 1024:.1f} KB"
    else:
        file_size_str = f"{file_size / (1024 * 1024):.1f} MB"

    # Format modification date
    mod_time = os.path.getmtime(file_path)
    mod_date = datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M:%S")

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