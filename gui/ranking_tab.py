from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QScrollArea, QGridLayout, QFrame, QMessageBox,
                             QComboBox, QWidget)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap
import os
import math


class ImageFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.layout = QVBoxLayout(self)

        # Image label
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.image_label)

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


class RankingTab(QWidget):
    def __init__(self, get_rankings_callback, media_handler, delete_callback):
        super().__init__()
        self.get_rankings_callback = get_rankings_callback
        self.media_handler = media_handler
        self.delete_callback = delete_callback
        self.thumbnail_height = 200
        self.current_page = 1
        self.per_page = 12
        self.columns = 3
        self.total_images = 0
        self.current_images = []
        self.preview_window = None

        self.setup_ui()

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

        control_panel.addStretch()
        layout.addLayout(control_panel)

        # Scroll area for images
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        # Container for grid
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        scroll_area.setWidget(self.grid_container)

        # Initial refresh
        self.refresh_rankings()

    def create_image_frame(self, rank, id, path, rating, votes, index):
        """Create a frame for an image with its information"""
        frame = ImageFrame()

        # Load and display media
        media = self.media_handler.load_media(path, (self.thumbnail_height * 2, self.thumbnail_height))

        if isinstance(media, tuple):  # Video
            video_widget, player = media
            frame.layout.insertWidget(0, video_widget)
            frame.video_player = player
            player.start()
        else:  # Image
            frame.image_label.setPixmap(media)

        # Set information
        frame.info_label.setText(f"#{rank} - {os.path.basename(path)}")
        frame.rating_label.setText(f"Rating: {rating:.1f} | Votes: {votes}")

        # Configure delete button
        frame.delete_button.clicked.connect(lambda: self.confirm_delete(id, path))

        # Add preview capability
        frame.image_label.mousePressEvent = lambda e: self.show_preview(path)

        return frame

    def show_preview(self, media_path):
        """Show full-size preview of media"""
        from gui.voting_tab import MediaPreviewDialog
        dialog = MediaPreviewDialog(media_path, self.media_handler, self)
        dialog.exec()

    def change_columns(self, value):
        """Handle column count change"""
        self.columns = int(value)
        self.refresh_rankings()

    def refresh_rankings(self):
        """Refresh the rankings display"""
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

    def confirm_delete(self, image_id, image_path):
        """Show delete confirmation dialog"""
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText(f"Are you sure you want to delete:\n{os.path.basename(image_path)}?")
        msg.setWindowTitle("Confirm Delete")
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No
        )

        if msg.exec() == QMessageBox.StandardButton.Yes:
            try:
                self.delete_callback(image_id)
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