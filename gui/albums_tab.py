from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                            QListWidget, QListWidgetItem, QInputDialog, QMessageBox, QLabel)
from PyQt6.QtCore import pyqtSignal, Qt


class AlbumsTab(QWidget):
    album_changed = pyqtSignal(int, str)  # Emits (album_id, album_name)

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.active_album_id = 1  # Default album
        self.setup_ui()
        self.refresh_albums()

    def setup_ui(self):
        """Set up the albums interface."""
        layout = QVBoxLayout(self)

        # Create album list
        self.album_list = QListWidget()
        self.album_list.currentItemChanged.connect(self.on_album_selected)
        layout.addWidget(self.album_list)

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

    def refresh_albums(self):
        """Refresh the albums list."""
        self.album_list.clear()
        for album_id, album_name in self.db.get_albums():
            item = QListWidgetItem(f"{album_name}")
            item.setData(Qt.ItemDataRole.UserRole, album_id)
            self.album_list.addItem(item)

    def create_album(self):
        """Create a new album."""
        name, ok = QInputDialog.getText(self, "Create Album", "Album name:")
        if ok and name:
            if self.db.create_album(name):
                self.refresh_albums()
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
        if album_id == 1:
            QMessageBox.warning(self, "Error", "Cannot delete Default album")
            return

        reply = QMessageBox.question(self, "Confirm Delete",
                                   "This will delete all media in the album. Continue?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            if self.db.delete_album(album_id):
                if album_id == self.active_album_id:
                    self.active_album_id = 1
                    self.album_changed.emit(1, "Default")
                self.refresh_albums()
            else:
                QMessageBox.warning(self, "Error", "Could not delete album")

    def on_album_selected(self, current, previous):
        """Handle album selection."""
        if current:
            album_id = current.data(Qt.ItemDataRole.UserRole)
            self.active_album_id = album_id
            self.album_changed.emit(album_id, current.text())
