import logging
import math
import os

from PyQt6.QtCore import Qt, QTimer, QUrl, QObject, pyqtSignal, QThread
from PyQt6.QtGui import QMovie, QIcon, QKeyEvent
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QScrollArea, QGridLayout, QFrame, QMessageBox,
                             QComboBox, QWidget, QSizePolicy, QCheckBox, QLineEdit)

from core.media_loader import ThreadedMediaLoader
from core.media_utils import AspectRatioWidget
from core.media_utils import set_file_info, handle_video_single_click, handle_video_events
from core.preview_handler import MediaPreview
from gui.loading_overlay import LoadingOverlay

logger = logging.getLogger(__name__)


class MediaLoader(QObject):
    """Helper class to handle media loading operations in the main thread."""
    load_started = pyqtSignal()
    load_finished = pyqtSignal(list, int)

    def __init__(self, get_rankings_callback):
        super().__init__()
        self.get_rankings_callback = get_rankings_callback

    def load_media(self, page, per_page):
        """Load media items (runs in main thread)."""
        try:
            rankings, total = self.get_rankings_callback(page, per_page)
            self.load_finished.emit(rankings, total)
        except Exception as e:
            logger.info(f"Error loading media: {e}")
            self.load_finished.emit([], 0)


class LoadingThread(QThread):
    """Thread to coordinate loading process."""
    request_load = pyqtSignal(int, int)  # Signal to request loading (page, per_page)

    def __init__(self, page, per_page):
        super().__init__()
        self.page = page
        self.per_page = per_page

    def run(self):
        """Emit signal to request loading in main thread."""
        self.request_load.emit(self.page, self.per_page)


class MediaFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.layout = QVBoxLayout(self)

        # Media container with fixed maximum height
        self.media_container = QWidget()
        self.media_container.setMinimumSize(200, 200)  # Minimum size for thumbnails
        self.media_container.setMaximumHeight(300)  # Add maximum height constraint
        self.media_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )

        self.media_layout = QVBoxLayout(self.media_container)
        self.media_layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.media_container)

        # Checkbox in the top-right corner
        self.checkbox = QCheckBox(self)
        self.checkbox.setStyleSheet("""
            QCheckBox {
                background-color: rgba(255, 255, 255, 150);
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 5px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:checked {
                image: url(:/icons/checked.png);  /* Use a custom checkmark image if desired */
                background-color: #4CAF50;  /* Green background for checked state */
                border: 1px solid #388E3C;
            }
            QCheckBox::indicator:unchecked {
                background-color: #f0f0f0;  /* Light gray background for unchecked state */
                border: 1px solid #ccc;
            }
        """)
        self.checkbox.move(self.width() - 30, 10)
        self.checkbox.hide()  # Hide the checkbox by default

        # Info label (for file name)
        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.info_label.setWordWrap(True)  # Enable word wrapping
        self.info_label.setStyleSheet("font-size: 10px;")  # Optional: Adjust font size
        self.layout.addWidget(self.info_label)

        # Rating label
        self.rating_label = QLabel()
        self.rating_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.rating_label)

        # Delete button
        self.delete_button = QPushButton("Delete")
        self.delete_button.setStyleSheet("background-color: #ff0000; color: white;")
        self.layout.addWidget(self.delete_button)

        # Set size policy for the frame
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

    def set_file_info(self, file_path):
        set_file_info(file_path, self.info_label, elide=True, max_width=150)

    def elide_text(self, text, max_width=150):
        """Elide text to fit within a specified width."""
        metrics = self.info_label.fontMetrics()
        elided_text = metrics.elidedText(text, Qt.TextElideMode.ElideRight, max_width)
        return elided_text

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position the checkbox in the top-right corner
        self.checkbox.move(self.width() - 30, 10)

    def enterEvent(self, event):
        """Show the checkbox when the mouse enters the frame."""
        self.checkbox.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Hide the checkbox when the mouse leaves the frame, unless it is checked."""
        if not self.checkbox.isChecked():
            self.checkbox.hide()
        super().leaveEvent(event)

    def cleanup(self):
        """Release any resources (e.g., video players) used by this frame."""
        if hasattr(self, 'video_player') and self.video_player:
            self.video_player.stop()
            self.video_player.setSource(QUrl())  # Clear the source
        if hasattr(self, 'gif_movie') and self.gif_movie:
            self.gif_movie.stop()
            self.gif_movie.setFileName("")  # Clear the file name


# noinspection PyUnresolvedReferences
class RankingTab(QWidget):
    def __init__(self, get_rankings_callback, media_handler, delete_callback, db):
        super().__init__()
        self.is_refreshing = False
        self.get_rankings_callback = get_rankings_callback
        self.media_handler = media_handler
        self.delete_callback = delete_callback
        self.db = db  # Store the db object
        self.preview = MediaPreview(self)

        self.current_page = 1
        self.per_page = 12
        self.columns = 3
        self.total_images = 0
        self.current_images = []
        self.checked_items = set()  # Track checked items

        # Add a flag to track if there are new votes
        self.new_votes_since_last_refresh = True

        # Add loading overlay
        self.loading_overlay = LoadingOverlay(self)

        # Set up media loader
        self.media_loader = MediaLoader(get_rankings_callback)
        self.media_loader.load_started.connect(self._on_load_started)
        self.media_loader.load_finished.connect(self._handle_loaded_media)

        # Initialize thread variable
        self.loading_thread = None

        self.pending_preview_action = None  # 'prev' or 'next'
        self.pending_preview_page = None

        self.current_preview_index = -1

        self.current_filter = "all"  # Default filter

        self.sort_by = "rating"  # Default sort column
        self.sort_order = "DESC"  # Default sort order

        self.search_query = None

        self.active_album_id = 1  # Default album

        # Cache for total media count
        self.total_media_count = self.db.get_total_media_count(self.active_album_id)

        # Add a flag to track new files
        self.new_files_since_last_refresh = False

        self._is_programmatic_change = False

        self.setup_ui()

        # Add threaded media loader
        self.threaded_loader = ThreadedMediaLoader(media_handler)
        self.threaded_loader.media_loaded.connect(self._handle_loaded_media_item)
        self.threaded_loader.all_media_loaded.connect(self._on_all_media_loaded)

        # Add single-click timer for video handling
        self.single_click_timer = QTimer(self)
        self.single_click_timer.setSingleShot(True)
        self.single_click_timer.timeout.connect(lambda: handle_video_single_click(self.pending_video_click))
        self.pending_video_click = []  # Stores (media_player, media_path)

        self.deletion_errors = []

    def setup_ui(self):
        """Setup the UI elements"""
        layout = QVBoxLayout(self)

        # Control panel
        control_panel = QHBoxLayout()
        control_panel_2 = QHBoxLayout()

        # Search input
        control_panel.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search files...")
        self.search_input.textChanged.connect(self.on_search_changed)
        control_panel.addWidget(self.search_input)

        # Column selector
        control_panel.addWidget(QLabel("Columns:"))
        self.column_selector = QComboBox()
        self.column_selector.addItems(["2", "3", "4", "5"])
        self.column_selector.setCurrentText(str(self.columns))
        self.column_selector.currentTextChanged.connect(self.change_columns)
        control_panel.addWidget(self.column_selector)

        # Items per page selector
        control_panel.addWidget(QLabel("On page:"))
        self.items_per_page_selector = QComboBox()
        self.items_per_page_selector.addItems(["12", "24", "48", "96", "500", "ALL"])
        self.items_per_page_selector.setCurrentText(str(self.per_page))
        self.items_per_page_selector.currentTextChanged.connect(self.change_items_per_page)
        control_panel.addWidget(self.items_per_page_selector)

        # Media type filter
        control_panel.addWidget(QLabel("Filter:"))
        self.filter_selector = QComboBox()
        self.filter_selector.addItems(["All", "Image", "Gif", "Video"])
        self.filter_selector.currentTextChanged.connect(self.change_filter)
        control_panel.addWidget(self.filter_selector)

        control_panel.addWidget(QLabel("Sort by:"))
        self.sort_selector = QComboBox()
        self.sort_selector.addItems(["Rating", "Votes", "File Name", "File Size", "Time Added", "File Modified"])
        self.sort_selector.currentTextChanged.connect(self.change_sort)
        control_panel.addWidget(self.sort_selector)

        # Order by selector
        control_panel.addWidget(QLabel("Order:"))
        self.order_selector = QComboBox()
        self.order_selector.addItems(["Descending", "Ascending"])
        self.order_selector.currentTextChanged.connect(self.change_order)
        control_panel.addWidget(self.order_selector)

        # Page navigation input
        control_panel.addWidget(QLabel("Page:"))
        self.page_input = QLineEdit()
        self.page_input.setFixedWidth(50)  # Set a fixed width for the input field
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignRight)  # Align text to the right
        self.page_input.textChanged.connect(self.on_page_input_changed)  # Connect to the textChanged signal
        control_panel.addWidget(self.page_input)

        # "Go" button (initially hidden)
        self.go_button = QPushButton("Go")
        self.go_button.setFixedWidth(40)  # Set a fixed width for the button
        self.go_button.clicked.connect(self.go_to_page)  # Connect to the go_to_page method
        self.go_button.hide()  # Hide the button initially
        control_panel.addWidget(self.go_button)

        # Page info label
        self.page_label = QLabel("Page 1")
        control_panel.addWidget(self.page_label)

        # First page button (<<)
        self.first_page_button = QPushButton("<<")
        self.first_page_button.clicked.connect(self.go_to_first_page)
        self.first_page_button.setEnabled(False)
        control_panel_2.addWidget(self.first_page_button)

        # Previous button
        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self.prev_page)
        self.prev_button.setEnabled(False)
        control_panel_2.addWidget(self.prev_button)

        # Next button
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.next_page)
        self.next_button.setEnabled(False)
        control_panel_2.addWidget(self.next_button)

        # Last page button (>>)
        self.last_page_button = QPushButton(">>")
        self.last_page_button.clicked.connect(self.go_to_last_page)
        self.last_page_button.setEnabled(False)
        control_panel_2.addWidget(self.last_page_button)

        # Trash bin button
        self.trash_button = QPushButton()
        self.trash_button.setIcon(QIcon.fromTheme("edit-delete"))
        self.trash_button.setToolTip("Delete selected items")
        self.trash_button.clicked.connect(self.delete_selected_items)
        self.trash_button.hide()
        control_panel_2.addWidget(self.trash_button)

        # Uncheck button
        self.uncheck_button = QPushButton("Uncheck All")
        self.uncheck_button.clicked.connect(self.uncheck_all)
        self.uncheck_button.hide()
        control_panel_2.addWidget(self.uncheck_button)

        # Select All button (always visible)
        self.select_all_button = QPushButton("Select All")
        self.select_all_button.setToolTip(
            "Select all items on current page"
        )
        self.select_all_button.clicked.connect(self.select_all)
        control_panel_2.addWidget(self.select_all_button)

        control_panel.addStretch()
        layout.addLayout(control_panel)
        layout.addLayout(control_panel_2)

        # Scroll area for images
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        # Container for grid
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setColumnStretch(0, 1)
        scroll_area.setWidget(self.grid_container)

    def set_new_files_flag(self):
        """Set the flag indicating that new files have been loaded."""
        self.new_files_since_last_refresh = True

    def change_filter(self, value):
        """Handle filter change."""
        self.current_filter = value.lower()
        self.current_page = 1  # Reset to the first page
        self.refresh_rankings()

    def change_sort(self, value):
        """Handle sort column change"""
        sort_map = {
            "Rating": "rating",
            "Votes": "votes",
            "File Name": "file_name",
            "File Size": "file_size",
            "Time Added": "created_at",
            "File Modified": "modified_at"
        }
        self.sort_by = sort_map[value]
        self.current_page = 1  # Reset to first page
        self.refresh_rankings()

    def change_order(self, value):
        """Handle sort order change"""
        self.sort_order = "DESC" if value == "Descending" else "ASC"
        self.current_page = 1  # Reset to first page
        self.refresh_rankings()

    def close_preview(self):
        """Handle preview closing"""
        if self.preview.isVisible():
            self.preview.close()

    def keyPressEvent(self, event: QKeyEvent):
        """Handle ESC key to close preview"""
        if event.key() == Qt.Key.Key_Escape:
            self.close_preview()
        else:
            super().keyPressEvent(event)

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

    def create_image_frame(self, rank, id, path, rating, votes, index, pre_loaded_widget=None):
        frame = MediaFrame()

        # Load the media in the frame
        media = self.media_handler.load_media(path)

        if isinstance(media, AspectRatioWidget):
            frame.media_layout.addWidget(media)
            media.mousePressEvent = lambda e, p=path: self.show_preview(p)
        elif isinstance(media, tuple):
            widget, player = media
            frame.media_layout.addWidget(widget)
            if isinstance(player, QMovie):  # GIF
                frame.gif_movie = player
                widget.mousePressEvent = lambda e, p=path: self.show_preview(p)
            else:  # Video
                frame.video_player = player
                widget.setProperty('is_video', True)
                widget.setProperty('media_player', frame.video_player)
                widget.setProperty('media_path', path)
                widget.installEventFilter(self)

        # Set file info
        file_name = os.path.basename(path)
        frame.set_file_info(path)

        # Set rating and votes
        frame.rating_label.setText(f"Rating: {rating:.1f} | Votes: {votes}")

        # Configure delete button
        frame.delete_button.clicked.connect(lambda: self.confirm_delete(id, path))

        # Configure checkbox
        frame.checkbox.setChecked(id in self.checked_items)
        frame.checkbox.stateChanged.connect(lambda state, id=id: self.toggle_checkbox(state, id))

        # Use a QTimer to delay the visibility check
        QTimer.singleShot(0, lambda: self.update_checkbox_visibility(frame, id))

        return frame

    def update_checkbox_visibility(self, frame, id):
        """Update the visibility of the checkbox based on its state."""
        if id in self.checked_items:
            frame.checkbox.show()
        else:
            frame.checkbox.hide()

    def toggle_checkbox(self, state, id):
        """Handle checkbox state changes."""
        if state == Qt.CheckState.Checked.value:
            self.checked_items.add(id)
        else:
            self.checked_items.discard(id)
        self.update_buttons_visibility()

    def update_buttons_visibility(self):
        """Show/hide trash and uncheck buttons based on checked items."""
        if self.checked_items:
            self.trash_button.show()
            self.uncheck_button.show()
        else:
            self.trash_button.hide()
            self.uncheck_button.hide()

    def select_all(self):
        """Select all media items on the current page."""
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and item.widget():
                frame = item.widget()
                if hasattr(frame, 'checkbox'):
                    frame.checkbox.setChecked(True)  # Check the checkbox
                    frame.checkbox.show()
                    media_id = self.current_images[i][0]  # Get the media ID from current_images
                    self.checked_items.add(media_id)  # Add to the checked_items set

        # Show the trash and uncheck buttons
        self.update_buttons_visibility()

    def uncheck_all(self):
        """Uncheck all checkboxes."""
        self.checked_items.clear()
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if hasattr(widget, 'checkbox'):
                    widget.checkbox.setChecked(False)
                    widget.checkbox.hide()
        self.update_buttons_visibility()


    def show_preview(self, media_path, media_player=None):
        """Show media preview overlay with navigation"""
        # Find index of current media
        self.current_preview_index = -1
        for i, (_, path, _, _) in enumerate(self.current_images):
            if path == media_path:
                self.current_preview_index = i
                break

        media = self.media_handler.load_media(media_path)
        self.media_handler.pause_all_videos()

        if isinstance(media, AspectRatioWidget):
            self.preview.show_media(media, enable_navigation=True, media_path=media_path)
        elif isinstance(media, tuple) and media[0].__class__.__name__ == 'AspectRatioWidget':
            if isinstance(media[1], QMovie):  # GIF
                self.preview.show_media(media[0], gif_movie=media[1], enable_navigation=True, media_path=media_path)
            else:  # Video
                self.preview.show_media(
                    media[0],
                    video_player=media[1],
                    enable_navigation=True,
                    media_path=media_path,
                    thumbnail_media_player=media_player
                )
                # Add event filter to video preview
                media[0].installEventFilter(self.preview)

        # Set up navigation callbacks
        self.preview.set_navigation_callbacks(
            on_prev=self.show_previous_preview if self.can_show_previous() else None,
            on_next=self.show_next_preview if self.can_show_next() else None
        )

    def can_show_previous(self):
        """Check if we can show previous media"""
        if self.current_preview_index > 0:
            return True
        return self.current_page > 1

    def can_show_next(self):
        """Check if we can show next media"""
        if self.current_preview_index < len(self.current_images) - 1:
            return True
        total_pages = math.ceil(self.total_images / self.per_page)
        return self.current_page < total_pages

    def show_previous_preview(self):
        if self.current_preview_index > 0:
            self.current_preview_index -= 1
            _, path, _, _ = self.current_images[self.current_preview_index]
            self.show_preview(path)
        elif self.current_page > 1:
            # Store preview action and defer loading
            self.pending_preview_action = 'prev'
            self.pending_preview_page = self.current_page - 1
            self.current_page = self.pending_preview_page
            self.refresh_rankings()

    def show_next_preview(self):
        if self.current_preview_index < len(self.current_images) - 1:
            self.current_preview_index += 1
            _, path, _, _ = self.current_images[self.current_preview_index]
            self.show_preview(path)
        else:
            # Store preview action and defer loading
            self.pending_preview_action = 'next'
            self.pending_preview_page = self.current_page + 1
            self.current_page = self.pending_preview_page
            self.refresh_rankings()

    def on_search_changed(self, text):
        self.search_query = text.strip() or None
        self.current_page = 1
        self.refresh_rankings()

    def change_columns(self, value):
        """Handle column count change"""
        self.columns = int(value)

        # Clear existing stretch factors
        for col in range(self.grid_layout.columnCount()):
            self.grid_layout.setColumnStretch(col, 0)

        # Set new stretch factors
        for col in range(self.columns):
            self.grid_layout.setColumnStretch(col, 1)

        # Force full layout recalculation
        self.grid_container.updateGeometry()
        self.grid_layout.update()
        self.update()

        self.refresh_rankings()

    def change_items_per_page(self, value):
        """Handle changes to the 'On page' dropdown."""
        if value == "ALL":
            self.per_page = 5000  # Set a large number to show all items
        else:
            self.per_page = int(value)  # Set the number of items per page

        # Reset to the first page
        self.current_page = 1

        # Refresh the rankings
        self.refresh_rankings()

    def refresh_rankings(self, force_refresh=True):
        if self.is_refreshing:
            return  # Prevent concurrent refreshes
        """Refresh the rankings display."""
        if not hasattr(self, 'pending_preview_page') or self.current_page != self.pending_preview_page:
            self.pending_preview_action = None
            self.pending_preview_page = None

        if not force_refresh and not self.new_votes_since_last_refresh and not self.new_files_since_last_refresh:
            return  # Skip refresh if no new votes or files and no forced refresh

        # Show loading overlay immediately
        self.loading_overlay.set_message("Loading media data...")
        self.loading_overlay.show()

        self.is_refreshing = True

        # Create a loading thread
        self.loading_thread = LoadingThread(self.current_page, self.per_page)
        self.loading_thread.request_load.connect(self._request_rankings_load)
        self.loading_thread.start()

    def _request_rankings_load(self, page, per_page):
        """Request rankings load in the main thread."""
        try:
            # Pass sorting parameters to get_rankings
            rankings, total_filtered = self.get_rankings_callback(
                page,
                per_page,
                self.current_filter,
                self.active_album_id,
                self.sort_by,
                self.sort_order,
                self.search_query
            )
            self._handle_loaded_media(rankings, total_filtered)
        except Exception as e:
            logger.error(f"Error loading rankings: {e}")
            self.loading_overlay.hide()
            self.is_refreshing = False

    def _on_load_started(self):
        """Handle load start event."""
        self.loading_overlay.set_message("Loading media items...")

    def _show_empty_state(self, message):
        """Display a message when there's no data."""
        self.grid_layout.addWidget(QLabel(message), 0, 0, alignment=Qt.AlignmentFlag.AlignCenter)
        self.loading_overlay.hide()

    def _handle_loaded_media(self, rankings, total_filtered):
        if self.active_album_id is None:
            self._show_empty_state("No active album selected")
            return
        """Handle the loaded media data."""
        # Clear existing grid first
        for i in reversed(range(self.grid_layout.count())):
            item = self.grid_layout.takeAt(0)
            if item and item.widget():
                if hasattr(item.widget(), 'cleanup'):
                    item.widget().cleanup()
                item.widget().deleteLater()

        self.current_images = rankings
        self.total_images = total_filtered

        # Update pagination info
        total_pages = math.ceil(self.total_images / self.per_page) if self.per_page != self.total_images else 1
        self.page_label.setText(
            f"Page {self.current_page} of {total_pages} (Total: {self.total_media_count}, Filtered: {self.total_images})"
        )

        # Update page input field
        self._is_programmatic_change = True
        self.page_input.setText(str(self.current_page))
        self._is_programmatic_change = False

        # Update navigation buttons
        self.first_page_button.setEnabled(self.current_page > 1)
        self.prev_button.setEnabled(self.current_page > 1)
        self.next_button.setEnabled(self.current_page < total_pages)
        self.last_page_button.setEnabled(self.current_page < total_pages)

        # Update loading overlay and progress
        self.loading_overlay.set_message("Loading media files...")
        self.loading_overlay.set_total_items(len(rankings))  # Set total items to load

        # Start threaded loading of media
        self.threaded_loader = ThreadedMediaLoader(self.media_handler)
        self.threaded_loader.media_loaded.connect(self._handle_loaded_media_item)
        self.threaded_loader.all_media_loaded.connect(self._on_all_media_loaded)
        self.threaded_loader.progress_updated.connect(
            self.loading_overlay.increment_progress)  # Connect progress signal
        self.threaded_loader.load_media_batch(rankings)

    def _handle_loaded_media_item(self, media_id, file_path, index):
        """Handle individual loaded media item."""
        try:
            if index < len(self.current_images):
                id, path, rating, votes = self.current_images[index]
                frame = self.create_image_frame(
                    index + 1,  # rank
                    id,
                    path,
                    rating,
                    votes,
                    index
                )

                row = index // self.columns
                col = index % self.columns
                self.grid_layout.addWidget(frame, row, col)
        except Exception as e:
            logger.error(f"Error handling loaded media item: {e}")

    def _on_all_media_loaded(self):
        """Handle completion of all media loading."""
        # Existing grid layout adjustments
        self.grid_layout.setHorizontalSpacing(10)
        self.grid_layout.setVerticalSpacing(10)

        # Set column and row stretches
        for col in range(self.columns):
            self.grid_layout.setColumnStretch(col, 1)

        total_rows = math.ceil(len(self.current_images) / self.columns)
        for row in range(total_rows):
            self.grid_layout.setRowStretch(row, 1)

        # Reset flags and hide loading overlay
        self.new_votes_since_last_refresh = False
        self.loading_overlay.hide()
        self.is_refreshing = False

        # Handle pending preview navigation after load
        if self.pending_preview_action:
            try:
                if self.pending_preview_action == 'next':
                    self.current_preview_index = 0
                    _, path, _, _ = self.current_images[0]
                    self.show_preview(path)
                elif self.pending_preview_action == 'prev':
                    self.current_preview_index = len(self.current_images) - 1
                    _, path, _, _ = self.current_images[-1]
                    self.show_preview(path)

                # Force focus back to preview
                self.preview.raise_()
                self.preview.activateWindow()
                self.preview.setFocus()  # <-- Add this line
            except (IndexError, TypeError) as e:
                logger.error(f"Preview navigation error: {e}")
            finally:
                self.pending_preview_action = None
                self.pending_preview_page = None

    def invalidate_total_media_count_cache(self):
        """Invalidate the total media count cache."""
        self.total_media_count = self.db.get_total_media_count(self.active_album_id)

    def resizeEvent(self, event):
        """Handle resize events to keep overlay properly positioned."""
        super().resizeEvent(event)
        if self.loading_overlay:
            self.loading_overlay.setGeometry(self.rect())

    def set_new_votes_flag(self):
        """Set the flag indicating that there are new votes."""
        self.new_votes_since_last_refresh = True

    def _cleanup_media_resources(self, file_path: str):
        """Release all resources associated with a media file."""
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if hasattr(widget, 'cleanup'):
                    widget.cleanup()

                # Close preview if it's showing this file
                if self.preview.isVisible() and hasattr(self.preview, 'current_media_path'):
                    if self.preview.current_media_path == file_path:
                        self.preview.close()

    def _delete_file(self, file_path: str) -> bool:
        """
        Attempt to delete a file from disk.
        Returns True if successful, False otherwise.
        """
        try:
            if os.path.exists(file_path):
                self._cleanup_media_resources(file_path)
                os.remove(file_path)
                logger.info(f"File deleted from disk: {file_path}")
                return True
            else:
                logger.warning(f"File not found: {file_path}")
                return False
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
            self.deletion_errors.append((file_path, str(e)))
            return False

    def _show_deletion_errors(self):
        """Show error dialog for failed deletions."""
        if self.deletion_errors:
            error_msg = "Failed to delete the following files:\n\n"
            for file_path, error in self.deletion_errors:
                error_msg += f"• {os.path.basename(file_path)}: {error}\n"

            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Deletion Errors")
            msg.setText(error_msg)
            msg.exec()
            self.deletion_errors.clear()

    def _handle_media_deletion(self, media_id: int, file_path: str, delete_file: bool, recalculate: bool = True):
        """
        Handle the deletion of a media item.
        Returns True if the database deletion was successful.
        """
        try:
            # Delete from database
            self.delete_callback(media_id, recalculate=recalculate)

            # Delete file if requested
            if delete_file:
                self._delete_file(file_path)

            return True
        except Exception as e:
            logger.error(f"Error deleting media {media_id}: {e}")
            self.deletion_errors.append((file_path, str(e)))
            return False

    def confirm_delete(self, media_id: int, file_path: str):
        """Show delete confirmation dialog for a single item."""
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText(f"Are you sure you want to delete:\n{os.path.basename(file_path)}?")
        msg.setWindowTitle("Confirm Delete")

        delete_file_checkbox = QCheckBox("Also permanently delete file from disk", msg)
        delete_file_checkbox.setChecked(False)
        msg.setCheckBox(delete_file_checkbox)

        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No
        )

        if msg.exec() == QMessageBox.StandardButton.Yes:
            self._handle_media_deletion(media_id, file_path, delete_file_checkbox.isChecked())
            self._show_deletion_errors()
            self.refresh_rankings()

    def delete_selected_items(self):
        """Delete multiple selected items."""
        if not self.checked_items:
            return

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText(f"Are you sure you want to delete {len(self.checked_items)} item(s)?")
        msg.setWindowTitle("Confirm Delete")

        delete_file_checkbox = QCheckBox("Also permanently delete files from disk", msg)
        delete_file_checkbox.setChecked(False)
        msg.setCheckBox(delete_file_checkbox)

        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.Cancel
        )

        if msg.exec() == QMessageBox.StandardButton.Yes:
            delete_files = delete_file_checkbox.isChecked()
            success_count = 0

            try:
                for media_id in list(self.checked_items):
                    # Get file path from database before deletion
                    file_path = self.db.get_media_path(media_id)
                    if self._handle_media_deletion(media_id, file_path, delete_files, recalculate=False):
                        success_count += 1
                        self.checked_items.discard(media_id)

                # Recalculate ratings once after all deletions
                self.db._recalculate_ratings()

                # Show any errors that occurred
                self._show_deletion_errors()

                # Show success message
                if success_count > 0:
                    QMessageBox.information(
                        self,
                        "Deletion Complete",
                        f"Successfully deleted {success_count} item(s)."
                    )

                # Refresh the display
                self.uncheck_all()
                self.refresh_rankings()

            except Exception as e:
                logger.error(f"Error in batch deletion: {e}")
                QMessageBox.critical(
                    self,
                    "Error",
                    f"An error occurred during deletion: {str(e)}"
                )

    def show_error(self, message):
        """Show error dialog"""
        QMessageBox.critical(self, "Error", message)

    def next_page(self):
        """Go to next page"""
        total_pages = math.ceil(self.total_images / self.per_page)
        if self.current_page < total_pages:
            self.current_page += 1
            self.refresh_rankings()

    def prev_page(self):
        """Go to previous page"""
        if self.current_page > 1:
            self.current_page -= 1
            self.refresh_rankings()

    def go_to_first_page(self):
        """Navigate to the first page."""
        if self.current_page != 1:  # Only navigate if not already on the first page
            self.current_page = 1
            self.refresh_rankings()

    def go_to_last_page(self):
        """Navigate to the last page."""
        total_pages = math.ceil(self.total_images / self.per_page)
        if self.current_page != total_pages:  # Only navigate if not already on the last page
            self.current_page = total_pages
            self.refresh_rankings()

    def on_page_input_changed(self):
        """Show the 'Go' button when the user edits the page input field."""
        if not self._is_programmatic_change and self.page_input.text().strip():
            self.go_button.show()
        else:
            self.go_button.hide()

    def go_to_page(self):
        """Navigate to the page specified in the page input field."""
        try:
            page_number = int(self.page_input.text())
            total_pages = math.ceil(self.total_images / self.per_page)

            if 1 <= page_number <= total_pages:
                self.current_page = page_number
                self.refresh_rankings()
                self.go_button.hide()  # Hide the "Go" button after navigation
            else:
                QMessageBox.warning(self, "Invalid Page", f"Please enter a page number between 1 and {total_pages}.")
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid page number.")
        finally:
            self._is_programmatic_change = False  # Reset the flag

    def set_active_album(self, album_id: int):
        """Set the active album and refresh rankings."""
        self.active_album_id = album_id
        self.refresh_rankings(force_refresh=True)
