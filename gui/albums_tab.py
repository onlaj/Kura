import os
import sqlite3

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTableWidget, QTableWidgetItem, QInputDialog,
                             QMessageBox, QLabel, QGroupBox, QGridLayout, QHeaderView, QComboBox, QFileDialog,
                             QProgressDialog)
from PyQt6.QtCore import pyqtSignal, Qt, QSortFilterProxyModel, QSize
import math

from core.elo import ReliabilityCalculator


class AlbumsTab(QWidget):
    album_changed = pyqtSignal(int, str)  # Emits (album_id, album_name)

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.active_album_id = 1
        self.current_page = 1
        self.per_page = 10
        self.sort_by = "created_at"
        self.sort_order = "ASC"
        self.total_albums = 0
        self.setup_ui()
        self._select_album_by_id(1)
        self.refresh_albums()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Album Table
        self.album_table = QTableWidget()
        self.album_table.setColumnCount(3)
        self.album_table.setHorizontalHeaderLabels(["Name", "Media Count", "Created At"])
        self.album_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.album_table.horizontalHeader().setSortIndicatorShown(True)
        self.album_table.horizontalHeader().sectionClicked.connect(self.on_header_clicked)
        self.album_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.album_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.album_table)

        # Pagination Controls
        control_layout = QHBoxLayout()
        self.first_page_btn = QPushButton("<<")
        self.prev_btn = QPushButton("Previous")
        self.next_btn = QPushButton("Next")
        self.last_page_btn = QPushButton(">>")
        self.page_label = QLabel("Page 1")
        self.items_per_page = QComboBox()
        self.items_per_page.addItems(["10", "25", "50", "100"])
        self.items_per_page.setCurrentText("10")

        control_layout.addWidget(self.first_page_btn)
        control_layout.addWidget(self.prev_btn)
        control_layout.addWidget(self.next_btn)
        control_layout.addWidget(self.last_page_btn)
        control_layout.addWidget(QLabel("Items per page:"))
        control_layout.addWidget(self.items_per_page)
        control_layout.addWidget(self.page_label)
        control_layout.addStretch()

        # Buttons
        button_layout_top = QHBoxLayout()
        button_layout_bottom = QHBoxLayout()
        self.btn_create = QPushButton("Create Album")
        self.btn_rename = QPushButton("Rename Album")
        self.btn_delete = QPushButton("Delete Album")
        self.btn_export = QPushButton("Export Album")
        self.btn_import = QPushButton("Import Album")
        self.btn_relocate = QPushButton("Relocate Missing Files")

        button_layout_top.addWidget(self.btn_create)
        button_layout_top.addWidget(self.btn_rename)
        button_layout_top.addWidget(self.btn_delete)
        button_layout_bottom.addWidget(self.btn_relocate)
        self.btn_relocate.setToolTip(
            "Locate missing media files by searching for matching filenames and file sizes in a directory of your choice"
        )
        button_layout_bottom.addWidget(self.btn_export)
        button_layout_bottom.addWidget(self.btn_import)



        layout.addLayout(control_layout)
        layout.addLayout(button_layout_top)
        layout.addLayout(button_layout_bottom)

        # Signals
        self.btn_create.clicked.connect(self.create_album)
        self.btn_rename.clicked.connect(self.rename_album)
        self.btn_delete.clicked.connect(self.delete_album)
        self.btn_export.clicked.connect(self.export_album)
        self.btn_import.clicked.connect(self.import_album)
        self.btn_relocate.clicked.connect(self.relocate_missing_files)
        self.album_table.selectionModel().selectionChanged.connect(self.on_selection_changed)
        self.items_per_page.currentTextChanged.connect(self.change_items_per_page)
        self.first_page_btn.clicked.connect(self.go_to_first_page)
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn.clicked.connect(self.next_page)
        self.last_page_btn.clicked.connect(self.go_to_last_page)

        self._setup_stats_section()

    def on_header_clicked(self, logical_index):
        columns = ["name", "total_media", "created_at"]
        if logical_index >= len(columns):
            return
        new_sort = columns[logical_index]
        if new_sort == self.sort_by:
            self.sort_order = "DESC" if self.sort_order == "ASC" else "ASC"
        else:
            self.sort_by = new_sort
            self.sort_order = "ASC"
        self.refresh_albums()

    def refresh_albums(self):
        albums, total = self.db.get_albums_page(
            self.current_page, self.per_page, self.sort_by, self.sort_order
        )
        self.total_albums = total
        self.album_table.setRowCount(0)

        for album in albums:
            row = self.album_table.rowCount()
            self.album_table.insertRow(row)
            album_id, name, media_count, created = album
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, album_id)
            self.album_table.setItem(row, 0, name_item)
            self.album_table.setItem(row, 1, QTableWidgetItem(str(media_count)))
            self.album_table.setItem(row, 2, QTableWidgetItem(created))

        total_pages = math.ceil(total / self.per_page) if self.per_page else 1
        self.page_label.setText(f"Page {self.current_page} of {total_pages} (Total: {total})")
        self.first_page_btn.setEnabled(self.current_page > 1)
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < total_pages)
        self.last_page_btn.setEnabled(self.current_page < total_pages)
        self._update_stats_display()
        self._select_album_by_id(self.active_album_id)

    def on_selection_changed(self):
        selected = self.album_table.selectedItems()
        if selected:
            row = selected[0].row()
            album_id = self.album_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            album_name = self.album_table.item(row, 0).text()
            self.active_album_id = album_id
            self.album_changed.emit(album_id, album_name)
            self._update_stats_display()

    def change_items_per_page(self, text):
        self.per_page = int(text)
        self.current_page = 1
        self.refresh_albums()

    def go_to_first_page(self):
        self.current_page = 1
        self.refresh_albums()

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.refresh_albums()

    def next_page(self):
        total_pages = math.ceil(self.total_albums / self.per_page)
        if self.current_page < total_pages:
            self.current_page += 1
            self.refresh_albums()

    def go_to_last_page(self):
        self.current_page = math.ceil(self.total_albums / self.per_page)
        self.refresh_albums()

    def _select_album_by_id(self, album_id: int):
        """Select an album in the table by its ID."""
        for row in range(self.album_table.rowCount()):
            item = self.album_table.item(row, 0)  # Name column contains the ID in UserRole
            if item.data(Qt.ItemDataRole.UserRole) == album_id:
                self.album_table.setCurrentCell(row, 0)
                self.album_table.scrollToItem(item)  # Ensure visibility
                break

    def create_album(self):
        """Create a new album and select it after creation."""
        name, ok = QInputDialog.getText(self, "Create Album", "Album name:")
        if ok and name:
            # Create album and get its ID
            new_id = self.db.create_album(name)  # Modified database method should return ID
            if new_id:
                # Refresh with sorting by creation date descending
                self.sort_by = "created_at"
                self.sort_order = "DESC"
                self.current_page = 1
                self.refresh_albums()
                self._select_album_by_id(new_id)
            else:
                QMessageBox.warning(self, "Error", "Album name already exists")

    def rename_album(self):
        selected = self.album_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        album_id = self.album_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        old_name = self.album_table.item(row, 0).text()
        if album_id == 1:
            QMessageBox.warning(self, "Error", "Cannot rename Default album")
            return

        name, ok = QInputDialog.getText(self, "Rename Album", "New name:", text=old_name)
        if ok and name:
            if self.db.rename_album(album_id, name):
                self.refresh_albums()
                if album_id == self.active_album_id:
                    self.album_changed.emit(album_id, name)
            else:
                QMessageBox.warning(self, "Error", "Album name already exists")

    def delete_album(self):
        """Delete the selected album and switch to default."""
        selected = self.album_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        album_id = self.album_table.item(row, 0).data(Qt.ItemDataRole.UserRole)

        if album_id == 1:
            QMessageBox.warning(self, "Error", "Cannot delete Default album")
            return

        # Confirm deletion
        reply = QMessageBox.question(
            self, "Confirm Delete",
            "This will delete all media in the album. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self.db.delete_album(album_id):
                # Switch to default album
                self._select_album_by_id(1)
                self.refresh_albums()


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


    def relocate_missing_files(self):
        """Handle the file relocation process."""
        missing = self.db.find_missing_media()
        if not missing:
            QMessageBox.information(self, "Info", "No missing files found")
            return

        # Get search directory
        search_dir = QFileDialog.getExistingDirectory(
            self, "Select Search Directory"
        )
        if not search_dir:
            return

        # Search for matches
        total_fixed = 0
        progress = QProgressDialog(
            "Relocating files...",
            "Cancel",
            0,
            len(missing),
            self
        )
        progress.setWindowModality(Qt.WindowModality.WindowModal)

        for i, media in enumerate(missing):
            progress.setValue(i)
            if progress.wasCanceled():
                break

            matches = []
            target_name = media['filename']
            target_size = media['file_size']

            # Recursive search
            for root, _, files in os.walk(search_dir):
                for file in files:
                    if file == target_name:
                        full_path = os.path.join(root, file)
                        try:
                            if os.path.getsize(full_path) == target_size:
                                matches.append(full_path)
                        except OSError:
                            continue

            # Handle matches
            if matches:
                if len(matches) == 1:
                    new_path = matches[0]
                else:
                    # Let user choose from multiple matches
                    item, ok = QInputDialog.getItem(
                        self,
                        "Select File",
                        f"Multiple matches found for {target_name}:",
                        matches,
                        0, False
                    )
                    new_path = item if ok else None

                if new_path and self.db.update_media_path(media['id'], new_path):
                    total_fixed += 1

        progress.close()
        QMessageBox.information(
            self,
            "Process Complete",
            f"Updated paths for {total_fixed}/{len(missing)} missing files"
        )
        self.album_changed.emit(self.active_album_id, "")  # Refresh UI

    def export_album(self):
        selected = self.album_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Error", "Please select an album to export.")
            return

        row = selected[0].row()
        album_id = self.album_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        album_name = self.album_table.item(row, 0).text()

        # Get export path
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Album", f"{album_name}.db", "Database Files (*.db)"
        )
        if not file_path:
            return

        # Perform export
        try:
            from core.album_io import export_album
            export_album(self.db, album_id, file_path)
            QMessageBox.information(self, "Success", "Album exported successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export failed: {str(e)}")

    def import_album(self):
        # Get import file
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Album", "", "Database Files (*.db)"
        )
        if not file_path:
            return

        # Check album name conflict
        backup_conn = sqlite3.connect(file_path)
        backup_cursor = backup_conn.cursor()
        backup_cursor.execute("SELECT name FROM albums")
        backup_name = backup_cursor.fetchone()[0]
        backup_conn.close()

        new_name = backup_name
        existing = self.db.cursor.execute(
            "SELECT id FROM albums WHERE name = ?",
            (backup_name,)
        ).fetchone()
        if existing:
            new_name, ok = QInputDialog.getText(
                self, "Rename Album",
                "This album already exists. Enter a new name:",
                text=f"{backup_name} (Imported)"
            )
            if not ok or not new_name:
                return

        # Perform import
        from core.album_io import import_album
        success, message = import_album(self.db, file_path, new_name)
        if success:
            self.refresh_albums()
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.warning(self, "Error", message)