import os
import sqlite3

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTableWidget, QTableWidgetItem, QInputDialog,
                             QMessageBox, QLabel, QGroupBox, QGridLayout, QHeaderView, QComboBox, QFileDialog,
                             QDialog, QLineEdit, QDialogButtonBox)
from PyQt6.QtCore import pyqtSignal, Qt, QSortFilterProxyModel, QSize
import math

from core.reliability_calculator import ReliabilityCalculator
from core.media_workers import AlbumExportWorker, AlbumImportWorker
from db.database import get_database_path


class AlbumsTab(QWidget):
    album_changed = pyqtSignal(int, str)  # Emits (album_id, album_name)
    check_missing_requested = pyqtSignal()  # User asked to check for missing files

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.active_album_id = 1
        self.current_page = 1
        self.per_page = 10
        self.sort_by = "created_at"
        self.sort_order = "ASC"
        self.total_albums = 0
        self.export_worker = None
        self.import_worker = None
        self.setup_ui()
        self._select_album_by_id(1)
        self.refresh_albums()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Album Table
        self.album_table = QTableWidget()
        self.album_table.setColumnCount(4)
        self.album_table.setHorizontalHeaderLabels(["Name", "Media Count", "Rating Method", "Created At"])
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
        self.btn_check_missing = QPushButton("Check for Missing Files…")

        button_layout_top.addWidget(self.btn_create)
        button_layout_top.addWidget(self.btn_rename)
        button_layout_top.addWidget(self.btn_delete)
        button_layout_bottom.addWidget(self.btn_check_missing)
        self.btn_check_missing.setToolTip(
            "Check all albums for media whose files no longer exist on disk, "
            "then choose whether to remove their records, locate the moved files, or ignore them"
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
        self.btn_check_missing.clicked.connect(self.check_missing_requested.emit)
        self.album_table.selectionModel().selectionChanged.connect(self.on_selection_changed)
        self.items_per_page.currentTextChanged.connect(self.change_items_per_page)
        self.first_page_btn.clicked.connect(self.go_to_first_page)
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn.clicked.connect(self.next_page)
        self.last_page_btn.clicked.connect(self.go_to_last_page)

        self._setup_stats_section()

    def on_header_clicked(self, logical_index):
        columns = ["name", "total_media", "rating_system", "created_at"]
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
            album_id, name, media_count, created, rating_system = album

            # Format rating system name
            system_name = "Glicko2" if rating_system == "glicko2" else "Elo"

            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, album_id)
            self.album_table.setItem(row, 0, name_item)
            self.album_table.setItem(row, 1, QTableWidgetItem(str(media_count)))
            self.album_table.setItem(row, 2, QTableWidgetItem(system_name))
            self.album_table.setItem(row, 3, QTableWidgetItem(created))

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
        """Create a new album with rating system selection and description"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Album")
        layout = QVBoxLayout(dialog)

        # Name input
        name_edit = QLineEdit()
        layout.addWidget(QLabel("Album name:"))
        layout.addWidget(name_edit)

        # Rating system selection
        layout.addWidget(QLabel("Ranking System:"))
        system_combo = QComboBox()
        system_combo.addItem("Glicko2 (Recommended)", "glicko2")
        system_combo.addItem("Elo (Classic)", "elo")
        layout.addWidget(system_combo)

        # System description label
        desc_label = QLabel()
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; font-size: 11px; margin-top: 5px;")
        layout.addWidget(desc_label)

        # Update description when selection changes
        def update_description(index):
            if system_combo.currentData() == "glicko2":
                desc_label.setText("Glicko2: Advanced system that considers rating certainty and "
                                   "volatility. Better for large collections and infrequent voters.")
            else:
                desc_label.setText("Elo: Simple pairwise comparison system. Classic method used in "
                                   "chess rankings. Good for small collections.")

        system_combo.currentIndexChanged.connect(update_description)
        update_description(0)  # Initial update

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_edit.text()
            rating_system = system_combo.currentData()
            if name:
                new_id = self.db.create_album(name, rating_system)  # Modified database method should return ID
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
        """Delete the selected album. If it's the default album, create a new one."""
        selected = self.album_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        album_id = self.album_table.item(row, 0).data(Qt.ItemDataRole.UserRole)

        # Confirm deletion
        reply = QMessageBox.question(
            self, "Confirm Delete",
            "This action is irreversible. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            was_default = album_id == 1

            # Delete the album
            if self.db.delete_album(album_id):
                # If we were on the deleted album, switch to the new default
                if album_id == self.active_album_id:
                    self._select_album_by_id(1)

                self.refresh_albums()
            else:
                QMessageBox.warning(self, "Error", "Failed to delete album")


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

        # Cancel any existing worker
        if self.export_worker and self.export_worker.isRunning():
            self.export_worker.wait()

        # Disable button during operation
        self.btn_export.setEnabled(False)

        # Create and start worker
        self.export_worker = AlbumExportWorker(get_database_path(), album_id, file_path)
        self.export_worker.progress.connect(lambda msg: None)  # Could show status if needed
        self.export_worker.finished.connect(self._on_export_finished)
        self.export_worker.start()

    def _on_export_finished(self, success, message):
        """Handle completion of album export."""
        # Re-enable button
        self.btn_export.setEnabled(True)

        # Show result
        if success:
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.critical(self, "Error", message)

        # Clean up
        self.export_worker = None

    def import_album(self):
        # Get import file
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Album", "", "Database Files (*.db)"
        )
        if not file_path:
            return

        # Check album name conflict (this is quick, can stay in main thread)
        try:
            backup_conn = sqlite3.connect(file_path)
            backup_cursor = backup_conn.cursor()
            backup_cursor.execute("SELECT name FROM albums")
            backup_name = backup_cursor.fetchone()[0]
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Error", f"Failed to read backup file: {str(e)}")
            return
        finally:
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

        # Cancel any existing worker
        if self.import_worker and self.import_worker.isRunning():
            self.import_worker.wait()

        # Disable button during operation
        self.btn_import.setEnabled(False)

        # Create and start worker
        self.import_worker = AlbumImportWorker(get_database_path(), file_path, new_name)
        self.import_worker.progress.connect(lambda msg: None)  # Could show status if needed
        self.import_worker.finished.connect(self._on_import_finished)
        self.import_worker.start()

    def _on_import_finished(self, success, message):
        """Handle completion of album import."""
        # Re-enable button
        self.btn_import.setEnabled(True)

        # Show result and refresh
        if success:
            self.refresh_albums()
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.warning(self, "Error", message)

        # Clean up
        self.import_worker = None