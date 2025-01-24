from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QListWidget, QListWidgetItem, QInputDialog, QMessageBox, QLabel, QGroupBox, QGridLayout)
from PyQt6.QtCore import pyqtSignal, Qt

from core.elo import ReliabilityCalculator


class AlbumsTab(QWidget):
    album_changed = pyqtSignal(int, str)  # Emits (album_id, album_name)

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.active_album_id = 1  # Default album
        self.setup_ui()
        self.refresh_albums()
        self._select_album_by_id(1)

    def setup_ui(self):
        """Set up the albums interface."""
        layout = QVBoxLayout(self)

        # Create album list
        self.album_list = QListWidget()
        self.album_list.currentItemChanged.connect(self.on_album_selected)
        layout.addWidget(self.album_list)

        # Create stats group first
        self._setup_stats_section()

        # Buttons layout
        button_layout = QHBoxLayout()

        # Create album button
        self.btn_create = QPushButton("Create Album")
        self.btn_create.clicked.connect(self.create_album)
        button_layout.addWidget(self.btn_create)

        # Rename album button
        self.btn_rename = QPushButton("Rename Album")
        self.btn_rename.clicked.connect(self.rename_album)
        button_layout.addWidget(self.btn_rename)

        # Delete album button
        self.btn_delete = QPushButton("Delete Album")
        self.btn_delete.clicked.connect(self.delete_album)
        button_layout.addWidget(self.btn_delete)

        layout.addLayout(button_layout)

    def _setup_stats_section(self):
        """Create statistics display group."""
        self.stats_group = QGroupBox("Album Statistics")
        stats_layout = QGridLayout()

        # Initialize all labels
        self.lbl_total_media = QLabel("Total Media: 0")
        self.lbl_images = QLabel("Images: 0")
        self.lbl_gifs = QLabel("GIFs: 0")
        self.lbl_videos = QLabel("Videos: 0")
        self.lbl_total_size = QLabel("Total Size: 0 MB")
        self.lbl_total_votes = QLabel("Total Votes: 0")
        self.lbl_reliability = QLabel("Reliability: 0%")
        self.lbl_votes_needed = QLabel("Votes to 90%: 0")

        # Add to layout
        stats_layout.addWidget(QLabel("<b>Media Counts:</b>"), 0, 0)
        stats_layout.addWidget(self.lbl_total_media, 1, 0)
        stats_layout.addWidget(self.lbl_images, 2, 0)
        stats_layout.addWidget(self.lbl_gifs, 3, 0)
        stats_layout.addWidget(self.lbl_videos, 4, 0)

        stats_layout.addWidget(QLabel("<b>Storage:</b>"), 0, 1)
        stats_layout.addWidget(self.lbl_total_size, 1, 1)

        stats_layout.addWidget(QLabel("<b>Voting:</b>"), 2, 1)
        stats_layout.addWidget(self.lbl_total_votes, 3, 1)
        stats_layout.addWidget(self.lbl_reliability, 4, 1)
        stats_layout.addWidget(self.lbl_votes_needed, 5, 1)

        self.stats_group.setLayout(stats_layout)
        self.layout().insertWidget(1, self.stats_group)

    def _update_stats_display(self):
        if self.active_album_id is None:
            self.lbl_total_media.setText("Total Media: 0")
            self.lbl_images.setText("Images: 0")
            self.lbl_gifs.setText("GIFs: 0")
            self.lbl_videos.setText("Videos: 0")
            self.lbl_total_size.setText("Total Size: 0 MB")
            self.lbl_total_votes.setText("Total Votes: 0")
            self.lbl_reliability.setText("Reliability: 0%")
            self.lbl_votes_needed.setText("Add albums to view stats")
            return

        """Update statistics for currently selected album."""
        # Get media counts
        media_counts = self.db.get_media_type_counts(self.active_album_id)
        total_media = sum([media_counts['image'], media_counts['gif'], media_counts['video']])

        # Get votes
        total_votes = self.db.get_total_votes(self.active_album_id)

        # Calculate reliability
        reliability = ReliabilityCalculator.calculate_reliability(total_media, total_votes)
        target = 94 if reliability >= 85 else 85
        votes_needed = ReliabilityCalculator.calculate_required_votes(total_media, target) - total_votes

        # Format size
        total_size_mb = media_counts['total_size'] / (1024 * 1024)

        # Update labels
        self.lbl_total_media.setText(f"Total Media: {total_media}")
        self.lbl_images.setText(f"Images: {media_counts['image']}")
        self.lbl_gifs.setText(f"GIFs: {media_counts['gif']}")
        self.lbl_videos.setText(f"Videos: {media_counts['video']}")
        self.lbl_total_size.setText(f"Total Size: {total_size_mb:.2f} MB")
        self.lbl_total_votes.setText(f"Total Votes: {total_votes}")
        self.lbl_reliability.setText(f"Reliability: {reliability:.1f}%")
        self.lbl_votes_needed.setText(f"Votes to {target}%: {max(votes_needed, 0)}")

    def _select_album_by_id(self, album_id: int):
        """Select an album in the list by its ID."""
        for index in range(self.album_list.count()):
            item = self.album_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == album_id:
                self.album_list.setCurrentItem(item)
                break

    def create_album(self):
        """Create a new album and select it after creation."""
        name, ok = QInputDialog.getText(self, "Create Album", "Album name:")
        if ok and name:
            if self.db.create_album(name):
                # Get the ID of the newly created album
                albums = self.db.get_albums()
                new_album = next((a for a in albums if a[1] == name), None)

                if new_album:
                    new_id = new_album[0]
                    self.refresh_albums()

                    # Find and select the new album
                    for index in range(self.album_list.count()):
                        item = self.album_list.item(index)
                        if item.data(Qt.ItemDataRole.UserRole) == new_id:
                            self.album_list.setCurrentItem(item)
                            break
            else:
                QMessageBox.warning(self, "Error", "Album name already exists")

    def rename_album(self):
        """Rename the selected album."""
        current = self.album_list.currentItem()
        if not current:
            return

        album_id = current.data(Qt.ItemDataRole.UserRole)
        if album_id == 1:
            QMessageBox.warning(self, "Error", "Cannot rename Default album")
            return

        name, ok = QInputDialog.getText(self, "Rename Album", "New name:")
        if ok and name:
            if self.db.rename_album(album_id, name):
                self.refresh_albums()
                if album_id == self.active_album_id:
                    self.album_changed.emit(album_id, name)
            else:
                QMessageBox.warning(self, "Error", "Album name already exists")

    def delete_album(self):
        """Delete the selected album."""
        current = self.album_list.currentItem()
        if not current:
            return

        album_id = current.data(Qt.ItemDataRole.UserRole)

        reply = QMessageBox.question(self, "Confirm Delete",
                                   "This will delete all media in the album. Continue?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            if self.db.delete_album(album_id):
                if album_id == self.active_album_id:
                    self.active_album_id = 1
                    self.album_changed.emit(1, "Default")
                self.refresh_albums()
                self._select_album_by_id(1)
            else:
                QMessageBox.warning(self, "Error", "Could not delete album")

    def on_album_selected(self, current, previous):
        """Handle album selection."""
        if current:
            album_id = current.data(Qt.ItemDataRole.UserRole)
            self.active_album_id = album_id
            self.album_changed.emit(album_id, current.text())
            self._update_stats_display()  # Update stats when album changes

    def refresh_albums(self):
        """Refresh the albums list."""
        self.album_list.clear()
        for album_id, album_name in self.db.get_albums():
            item = QListWidgetItem(f"{album_name}")
            item.setData(Qt.ItemDataRole.UserRole, album_id)
            self.album_list.addItem(item)
        self._update_stats_display()  # Refresh stats after changes
