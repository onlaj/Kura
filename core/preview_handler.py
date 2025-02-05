# core/preview_handler.py
from PyQt6.QtCore import Qt, QEvent, QTimer, QUrl
from PyQt6.QtGui import QKeyEvent, QDesktopServices
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QSizePolicy, QPushButton, QHBoxLayout, QWidget


class MediaPreview(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Set window flags for a proper dialog window
        self.thumbnail_media_player = None
        self.setWindowFlags(Qt.WindowType.Window |
                            Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Media container with semi-transparent background
        self.media_container = QWidget(self)
        self.media_container.setStyleSheet("background-color: rgba(0, 0, 0, 180);")
        self.media_layout = QHBoxLayout(self.media_container)
        self.media_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.media_layout.setContentsMargins(50, 50, 50, 50)
        self.media_layout.setSpacing(0)

        # Navigation buttons
        self.prev_button = QPushButton("←")
        self.prev_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 180);
                color: white;
                border: none;
                padding: 15px;
                font-size: 24px;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 180);
            }
        """)
        self.prev_button.setFixedWidth(50)
        self.prev_button.setSizePolicy(QSizePolicy.Policy.Fixed,
                                       QSizePolicy.Policy.Expanding)
        self.prev_button.hide()

        self.next_button = QPushButton("→")
        self.next_button.setStyleSheet(self.prev_button.styleSheet())
        self.next_button.setFixedWidth(50)
        self.next_button.setSizePolicy(QSizePolicy.Policy.Fixed,
                                       QSizePolicy.Policy.Expanding)
        self.next_button.hide()

        # Content widget
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        # Arrange layout
        self.media_layout.addWidget(self.prev_button)
        self.media_layout.addWidget(self.content_widget, 1)
        self.media_layout.addWidget(self.next_button)

        # Create top and bottom button containers
        self.top_layout = QHBoxLayout()
        self.top_layout.setContentsMargins(50, 20, 50, 0)

        # Create "Open in app" button with distinct style
        self.open_button = QPushButton("Open in default app")
        self.open_button.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(60, 60, 60, 180);
                        color: white;
                        border: none;
                        padding: 10px 20px;
                        font-size: 14px;
                        border-radius: 5px;
                    }
                    QPushButton:hover {
                        background-color: rgba(60, 140, 220, 180);
                    }
                """)
        self.open_button.hide()
        self.open_button.clicked.connect(self.open_in_system_app)

        # Add open button to top layout
        self.top_layout.addWidget(self.open_button)
        self.top_layout.addStretch()

        # Create media container with semi-transparent background
        self.media_container = QWidget(self)
        self.media_container.setStyleSheet("background-color: rgba(0, 0, 0, 180);")
        self.media_layout = QVBoxLayout(self.media_container)
        self.media_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Add top layout to media container
        self.media_layout.addLayout(self.top_layout)

        # Create horizontal layout for navigation and content
        nav_content_layout = QHBoxLayout()
        nav_content_layout.setContentsMargins(50, 0, 50, 50)

        # Add navigation buttons and content to horizontal layout
        nav_content_layout.addWidget(self.prev_button)
        nav_content_layout.addWidget(self.content_widget, 1)
        nav_content_layout.addWidget(self.next_button)

        # Add navigation and content layout to media container
        self.media_layout.addLayout(nav_content_layout)

        # Add media container to main layout
        self.layout.addWidget(self.media_container)

        self.current_media_path = None

        self.layout.addWidget(self.media_container)

        self.current_media = None
        self.video_player = None
        self.gif_movie = None
        self.on_prev = None
        self.on_next = None

        # Connect buttons
        self.prev_button.clicked.connect(self.navigate_prev)
        self.next_button.clicked.connect(self.navigate_next)

        # Enable focus for keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Connect mouse press event
        self.media_container.mousePressEvent = lambda e: self.handle_click(e)

        # Install event filter to track main window resize events
        if self.parent():
            self.parent().window().installEventFilter(self)

        # Timer to track window movement
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_window_position)
        self.timer.start(10)  # Check every 100ms

        # Store the last known position of the main window
        self.last_window_position = None

        self.is_video_preview = False
        self.single_click_timer = QTimer(self)
        self.single_click_timer.setSingleShot(True)
        self.single_click_timer.timeout.connect(self.handle_video_click)
        self.pending_video_click = False

    def show_media(self, media_widget, video_player=None, gif_movie=None, enable_navigation=False,
                   media_path=None, thumbnail_media_player=None):
        """Show media in the preview dialog"""
        # Clear existing media
        if self.current_media:
            if self.video_player:
                self.video_player.stop()
            self.current_media.setParent(None)

        if video_player:
            self.is_video_preview = True
            media_widget.installEventFilter(self)
        else:
            self.is_video_preview = False

        self.current_media = media_widget
        self.video_player = video_player
        self.gif_movie = gif_movie

        # Determine position from thumbnail media player, if available
        self.thumbnail_media_player = thumbnail_media_player
        position = thumbnail_media_player.position() if thumbnail_media_player else 0

        # Store the media path
        self.current_media_path = media_path
        self.open_button.setVisible(media_path is not None)

        # Set size policy to expand in both directions
        media_widget.setSizePolicy(QSizePolicy.Policy.Expanding,
                                   QSizePolicy.Policy.Expanding)

        # Add the media widget to the content layout
        self.content_layout.addWidget(media_widget)

        # Adjust content margins for better spacing
        self.content_layout.setContentsMargins(20, 20, 20, 20)

        # Use a QTimer to delay the video playback
        if video_player:
            QTimer.singleShot(100, lambda: video_player.setPosition(position))
            QTimer.singleShot(150, video_player.play)

        # Set size and position relative to parent
        if self.parent():
            main_window = self.parent().window()
            main_rect = main_window.geometry()
            self.setGeometry(main_rect)

        # Show/hide navigation
        self.prev_button.setVisible(enable_navigation)
        self.next_button.setVisible(enable_navigation)

        self.show()
        self.raise_()
        self.setFocus()

    def handle_click(self, event):
        """Handle click events on the preview"""
        if not self.is_video_preview:
            clicked_widget = self.childAt(event.position().toPoint())
            if clicked_widget not in [self.prev_button, self.next_button]:
                self.close()

    def handle_video_click(self):
        """Handle single click on video preview (play/pause)"""
        if self.pending_video_click and self.video_player:
            if self.video_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.video_player.pause()
            else:
                self.video_player.play()
        self.pending_video_click = False

    def open_in_system_app(self):
        """Open the current media file in the system's default application"""
        if self.current_media_path:
            url = QUrl.fromLocalFile(self.current_media_path)
            QDesktopServices.openUrl(url)

    def set_navigation_callbacks(self, on_prev=None, on_next=None):
        """Set callbacks for navigation"""
        self.on_prev = on_prev
        self.on_next = on_next

        # Update button visibility and enabled state
        self.prev_button.setVisible(on_prev is not None)
        self.next_button.setVisible(on_next is not None)
        self.prev_button.setEnabled(on_prev is not None)
        self.next_button.setEnabled(on_next is not None)

    def navigate_prev(self):
        """Handle navigation to previous media"""
        if self.on_prev:
            self.on_prev()

    def navigate_next(self):
        """Handle navigation to next media"""
        if self.on_next:
            self.on_next()

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard navigation"""
        if event.key() == Qt.Key.Key_Left and self.prev_button.isVisible():
            self.navigate_prev()
        elif event.key() == Qt.Key.Key_Right and self.next_button.isVisible():
            self.navigate_next()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def close(self):
        """Handle closing the preview"""
        if self.video_player:
            # Set time of video player in preview to thumbnail video preview
            if self.thumbnail_media_player:
                self.thumbnail_media_player.setPosition(self.video_player.position())
            if self.video_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                if self.thumbnail_media_player:
                    QTimer.singleShot(100,
                                      lambda: self.thumbnail_media_player.play())
            self.video_player.stop()
        if self.gif_movie:
            self.gif_movie.stop()

        self.single_click_timer.stop()
        self.pending_video_click = False
        super().close()

    def resizeEvent(self, event):
        """Ensure preview takes up full parent widget size"""
        if self.parent():
            # Update the preview window's geometry to match the main window
            main_window = self.parent().window()
            main_rect = main_window.geometry()
            self.setGeometry(main_rect)
        super().resizeEvent(event)

    def showEvent(self, event):
        """Ensure proper sizing when showing the preview"""
        if self.parent():
            # Update the preview window's geometry to match the main window
            main_window = self.parent().window()
            main_rect = main_window.geometry()
            self.setGeometry(main_rect)
        super().showEvent(event)

    def eventFilter(self, obj, event):
        """Handle video preview interactions"""
        if self.is_video_preview:
            if event.type() == QEvent.Type.MouseButtonPress:
                self.pending_video_click = True
                self.single_click_timer.start(250)  # 250ms threshold for double-click
                return True
            elif event.type() == QEvent.Type.MouseButtonDblClick:
                self.single_click_timer.stop()
                self.pending_video_click = False
                self.close()
                return True
        return super().eventFilter(obj, event)

    def check_window_position(self):
        """Check if the main window has moved and update the preview window accordingly"""
        if self.parent():
            main_window = self.parent().window()
            current_position = main_window.geometry().topLeft()

            # If the position has changed, update the preview window
            if self.last_window_position != current_position:
                self.last_window_position = current_position
                main_rect = main_window.geometry()
                self.setGeometry(main_rect)
