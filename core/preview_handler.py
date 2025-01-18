# core/preview_handler.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QMovie, QKeyEvent
from PyQt6.QtMultimediaWidgets import QVideoWidget


class MediaPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
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
        self.media_layout.setSpacing(0)  # Reduce spacing

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
        self.prev_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.prev_button.hide()  # Hide by default

        self.next_button = QPushButton("→")
        self.next_button.setStyleSheet(self.prev_button.styleSheet())
        self.next_button.setFixedWidth(50)
        self.next_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.next_button.hide()  # Hide by default

        # Add content area with proper aspect ratio for videos
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)  # Reduce spacing

        # Arrange layout
        self.media_layout.addWidget(self.prev_button)
        self.media_layout.addWidget(self.content_widget, 1)
        self.media_layout.addWidget(self.next_button)

        self.layout.addWidget(self.media_container)

        self.current_media = None
        self.video_player = None
        self.gif_movie = None

        # Navigation callbacks
        self.on_prev = None
        self.on_next = None

        # Connect buttons
        self.prev_button.clicked.connect(self.navigate_prev)
        self.next_button.clicked.connect(self.navigate_next)

        # Enable focus for keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Connect mouse press event for the media container
        self.media_container.mousePressEvent = lambda e: self.handle_click(e)

    def is_video_control(self, widget):
        """Check if the widget is a video control element"""
        if widget is None:
            return False
            
        # Get the widget's parent chain
        widget_chain = []
        current = widget
        while current is not None:
            widget_chain.append(current)
            current = current.parent()
            
        # Check if any widget in the chain has a specific video control class name
        video_control_classes = {'QVideoWidget', 'QSlider', 'QPushButton', 'QToolButton'}
        for w in widget_chain:
            class_name = w.__class__.__name__
            if class_name in video_control_classes and 'control' in w.objectName().lower():
                return True
        return False

    def handle_click(self, event):
        """Handle click events on the preview"""
        clicked_widget = self.childAt(event.position().toPoint())
        
        # Only prevent closing if clicking specifically on video controls
        if self.is_video_control(clicked_widget):
            return
            
        self.close()

    def show_media(self, media_widget, video_player=None, gif_movie=None, enable_navigation=False):
        """Show media in the preview overlay"""
        # Clear any existing media
        if self.current_media:
            if self.video_player:
                self.video_player.stop()
            self.current_media.setParent(None)

        # Store and show new media
        self.current_media = media_widget
        self.video_player = video_player
        self.gif_movie = gif_movie

        # Ensure the media widget expands properly
        media_widget.setSizePolicy(QSizePolicy.Policy.Expanding,
                                   QSizePolicy.Policy.Expanding)

        # Add new media to layout
        self.content_layout.addWidget(media_widget)

        # Start media playback if needed
        if video_player:
            video_player.play()

        # Ensure the preview covers the entire parent widget
        if self.parent():
            self.setGeometry(self.parent().rect())

        # Show/hide navigation buttons based on enable_navigation parameter
        self.prev_button.setVisible(enable_navigation)
        self.next_button.setVisible(enable_navigation)

        # Show the preview and set focus for keyboard events
        self.show()
        self.raise_()
        self.setFocus()

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
            self.video_player.stop()
        if self.gif_movie:
            self.gif_movie.stop()
        super().close()

    def resizeEvent(self, event):
        """Ensure preview takes up full parent widget size"""
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().resizeEvent(event)

    def showEvent(self, event):
        """Ensure proper sizing when showing the preview"""
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().showEvent(event)