import math
import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QMovie, QIcon
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QScrollArea, QGridLayout, QFrame, QMessageBox,
                             QComboBox, QWidget, QSizePolicy, QCheckBox)

from core.preview_handler import MediaPreview
from gui.voting_tab import AspectRatioWidget


class MediaFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.layout = QVBoxLayout(self)

        # Media container
        self.media_container = QWidget()
        self.media_container.setMinimumSize(200, 200)  # Minimum size for thumbnails
        self.media_container.setSizePolicy(QSizePolicy.Policy.Expanding,
                                           QSizePolicy.Policy.Expanding)
        self.media_layout = QVBoxLayout(self.media_container)
        self.media_layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.media_container)

        # Checkbox in the top-right corner
        self.checkbox = QCheckBox(self)
        self.checkbox.setStyleSheet("""
                    QCheckBox {
                        background-color: rgba(255, 255, 255, 0);
                        border: 0px solid #ccc;
                        border-radius: 3px;
                        padding: 1px;
                    }
                    QCheckBox::indicator {
                        width: 16px;
                        height: 16px;
                    }
                    QCheckBox::indicator:checked {
                        image: url(:/icons/checked.png);  /* Use a custom checkmark image if desired */
                        background-color: #0096FF;  /* Green background for checked state */
                        border: 1px solid #388E3C;
                    }
                    QCheckBox::indicator:unchecked {
                        background-color: #f0f0f0;  /* Light gray background for unchecked state */
                        border: 1px solid #ccc;
                    }
                """)
        self.checkbox.move(self.width() - 30, 10)
        QTimer.singleShot(0, self.checkbox.hide)  # Hide with a slight delay

        # Info label
        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        if not self.checkbox.isChecked():  # Only hide if the checkbox is unchecked
            self.checkbox.hide()
        super().leaveEvent(event)


class RankingTab(QWidget):
    def __init__(self, get_rankings_callback, media_handler, delete_callback, db):
        super().__init__()
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

        self.setup_ui()

        self.current_preview_index = -1

    def setup_ui(self):
        """Setup the UI elements"""
        layout = QVBoxLayout(self)

        # Control panel
        control_panel = QHBoxLayout()

        # Refresh button
        self.refresh_button = QPushButton("Refresh Rankings")
        self.refresh_button.clicked.connect(self.refresh_rankings)
        control_panel.addWidget(self.refresh_button)

        # Column selector
        control_panel.addWidget(QLabel("Columns:"))
        self.column_selector = QComboBox()
        self.column_selector.addItems(["2", "3", "4", "5"])
        self.column_selector.setCurrentText(str(self.columns))
        self.column_selector.currentTextChanged.connect(self.change_columns)
        control_panel.addWidget(self.column_selector)

        # Page info
        self.page_label = QLabel("Page 1")
        control_panel.addWidget(self.page_label)

        # Navigation buttons
        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self.prev_page)
        self.prev_button.setEnabled(False)
        control_panel.addWidget(self.prev_button)

        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.next_page)
        self.next_button.setEnabled(False)
        control_panel.addWidget(self.next_button)

        # Trash bin button
        self.trash_button = QPushButton()
        self.trash_button.setIcon(QIcon.fromTheme("edit-delete"))
        self.trash_button.setToolTip("Delete selected items")
        self.trash_button.clicked.connect(self.delete_selected_items)
        self.trash_button.hide()
        control_panel.addWidget(self.trash_button)

        # Uncheck button
        self.uncheck_button = QPushButton("Uncheck All")
        self.uncheck_button.clicked.connect(self.uncheck_all)
        self.uncheck_button.hide()
        control_panel.addWidget(self.uncheck_button)

        control_panel.addStretch()
        layout.addLayout(control_panel)

        # Scroll area for images
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        # Container for grid
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(10)  # Add some space between items
        self.grid_layout.setColumnStretch(0, 1)  # Ensure columns are equal width
        scroll_area.setWidget(self.grid_container)

    def create_image_frame(self, rank, id, path, rating, votes, index):
        frame = MediaFrame()

        # Load media
        media = self.media_handler.load_media(path)

        if isinstance(media, AspectRatioWidget):
            frame.media_layout.addWidget(media)
            media.mousePressEvent = lambda e, p=path: self.show_preview(p)
        elif isinstance(media, tuple) and media[0].__class__.__name__ == 'AspectRatioWidget':
            if isinstance(media[1], QMovie):  # GIF
                frame.media_layout.addWidget(media[0])
                frame.gif_movie = media[1]
                media[0].mousePressEvent = lambda e, p=path: self.show_preview(p)
            else:  # Video
                frame.media_layout.addWidget(media[0])
                frame.video_player = media[1]
                media[1].play()
                media[0].mousePressEvent = lambda e, p=path: self.show_preview(p)

        # Set information
        frame.info_label.setText(f"#{rank} - {os.path.basename(path)}")
        frame.rating_label.setText(f"Rating: {rating:.1f} | Votes: {votes}")

        # Configure delete button
        frame.delete_button.clicked.connect(lambda: self.confirm_delete(id, path))

        # Configure checkbox
        frame.checkbox.setChecked(id in self.checked_items)
        frame.checkbox.stateChanged.connect(lambda state, id=id: self.toggle_checkbox(state, id))
        frame.checkbox.show()

        return frame

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

    def uncheck_all(self):
        """Uncheck all checkboxes."""
        self.checked_items.clear()
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if hasattr(widget, 'checkbox'):
                    widget.checkbox.setChecked(False)
        self.update_buttons_visibility()

    def delete_selected_items(self):
        """Delete selected items."""
        if not self.checked_items:
            return

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText(f"Are you sure you want to delete {len(self.checked_items)} item(s)?")
        msg.setWindowTitle("Confirm Delete")

        # Add a checkbox for permanent file deletion
        delete_file_checkbox = QCheckBox("Also permanently delete files", msg)
        delete_file_checkbox.setChecked(False)  # Unchecked by default
        msg.setCheckBox(delete_file_checkbox)

        # Add standard buttons
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.Cancel
        )

        # Show the dialog and wait for user input
        result = msg.exec()

        if result == QMessageBox.StandardButton.Yes:
            try:
                delete_files = delete_file_checkbox.isChecked()
                for media_id in list(self.checked_items):
                    # Delete the media from the database and get the file path
                    file_path = self.delete_callback(media_id, recalculate=False)  # Disable recalculation
                    if delete_files and file_path and os.path.exists(file_path):
                        try:
                            os.remove(file_path)  # Delete the file from the system
                            print(f"File deleted from disk: {file_path}")
                        except Exception as e:
                            print(f"Error deleting file {file_path}: {e}")

                # Recalculate ratings once after all deletions are complete
                self.db._recalculate_ratings()  # Call recalculation directly

                self.checked_items.clear()  # Clear the set of checked items
                self.refresh_rankings()  # Refresh the rankings display
            except Exception as e:
                self.show_error(f"Error deleting items: {str(e)}")

    def show_preview(self, media_path):
        """Show media preview overlay with navigation"""
        # Find index of current media
        self.current_preview_index = -1
        for i, (_, path, _, _) in enumerate(self.current_images):
            if path == media_path:
                self.current_preview_index = i
                break

        media = self.media_handler.load_media(media_path)

        if isinstance(media, AspectRatioWidget):
            self.preview.show_media(media, enable_navigation=True, media_path=media_path)
        elif isinstance(media, tuple) and media[0].__class__.__name__ == 'AspectRatioWidget':
            if isinstance(media[1], QMovie):  # GIF
                self.preview.show_media(media[0], gif_movie=media[1], enable_navigation=True, media_path=media_path)
            else:  # Video
                self.preview.show_media(media[0], video_player=media[1], enable_navigation=True, media_path=media_path)

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
        """Show previous media in preview"""
        if self.current_preview_index > 0:
            # Show previous media on current page
            self.current_preview_index -= 1
            _, path, _, _ = self.current_images[self.current_preview_index]
            self.show_preview(path)
        elif self.current_page > 1:
            # Load previous page and show last media
            self.current_page -= 1
            self.refresh_rankings()
            if self.current_images:
                self.current_preview_index = len(self.current_images) - 1
                _, path, _, _ = self.current_images[self.current_preview_index]
                self.show_preview(path)

    def show_next_preview(self):
        """Show next media in preview"""
        if self.current_preview_index < len(self.current_images) - 1:
            # Show next media on current page
            self.current_preview_index += 1
            _, path, _, _ = self.current_images[self.current_preview_index]
            self.show_preview(path)
        else:
            # Check if we can load next page
            total_pages = math.ceil(self.total_images / self.per_page)
            if self.current_page < total_pages:
                self.current_page += 1
                self.refresh_rankings()
                if self.current_images:
                    self.current_preview_index = 0
                    _, path, _, _ = self.current_images[0]
                    self.show_preview(path)

    def change_columns(self, value):
        """Handle column count change"""
        self.columns = int(value)
        self.refresh_rankings()

    def refresh_rankings(self):
        """Refresh the rankings display."""
        # Stop any playing media
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if hasattr(widget, 'video_player') and widget.video_player:
                    widget.video_player.stop()

        # Clear current grid
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Get current page
        rankings, self.total_images = self.get_rankings_callback(
            self.current_page,
            self.per_page
        )
        self.current_images = rankings

        # Update pagination
        total_pages = math.ceil(self.total_images / self.per_page)
        self.page_label.setText(
            f"Page {self.current_page} of {total_pages} (Total: {self.total_images})"
        )

        # Update navigation buttons
        self.prev_button.setEnabled(self.current_page > 1)
        self.next_button.setEnabled(self.current_page < total_pages)

        # Calculate starting rank
        start_rank = (self.current_page - 1) * self.per_page + 1

        # Display rankings
        for i, (id, path, rating, votes) in enumerate(rankings):
            frame = self.create_image_frame(
                start_rank + i,
                id,
                path,
                rating,
                votes,
                i
            )
            row = i // self.columns
            col = i % self.columns
            self.grid_layout.addWidget(frame, row, col)

        # Adjust grid layout properties for better presentation
        self.grid_layout.setHorizontalSpacing(10)
        self.grid_layout.setVerticalSpacing(10)

        # Ensure columns are equal width
        for col in range(self.columns):
            self.grid_layout.setColumnStretch(col, 1)

    def confirm_delete(self, image_id, image_path):
        """Show delete confirmation dialog with a checkbox to delete the file permanently."""
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText(f"Are you sure you want to delete:\n{os.path.basename(image_path)}?")
        msg.setWindowTitle("Confirm Delete")

        # Add a checkbox for permanent file deletion
        delete_file_checkbox = QCheckBox("Also permanently delete files", msg)
        delete_file_checkbox.setChecked(False)  # Unchecked by default
        msg.setCheckBox(delete_file_checkbox)

        # Add standard buttons
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No
        )

        # Show the dialog and wait for user input
        result = msg.exec()

        if result == QMessageBox.StandardButton.Yes:
            try:
                # Delete the entry from the database
                self.delete_callback(image_id)

                # If the checkbox is checked, delete the file from the hard drive
                if delete_file_checkbox.isChecked():
                    if os.path.exists(image_path):
                        os.remove(image_path)
                        print(f"File deleted from disk: {image_path}")
                    else:
                        print(f"File not found: {image_path}")

                # Refresh the rankings
                self.refresh_rankings()
            except Exception as e:
                self.show_error(f"Error deleting image: {str(e)}")

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