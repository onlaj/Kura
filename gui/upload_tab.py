from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTextEdit, QFileDialog)
from PyQt6.QtCore import Qt
import os
from pathlib import Path


class UploadTab(QWidget):
    def __init__(self, db_callback):
        """Initialize the upload tab."""
        super().__init__()
        self.db_callback = db_callback
        self.setup_ui()

    def setup_ui(self):
        """Set up the upload interface."""
        layout = QVBoxLayout(self)

        # Create button layout
        button_layout = QHBoxLayout()

        # Add files button
        self.btn_add_files = QPushButton("Add Files")
        self.btn_add_files.clicked.connect(self.add_files)
        button_layout.addWidget(self.btn_add_files)

        # Add folder button
        self.btn_add_folder = QPushButton("Add Folder")
        self.btn_add_folder.clicked.connect(self.add_folder)
        button_layout.addWidget(self.btn_add_folder)

        layout.addLayout(button_layout)

        # Create log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

    def add_files(self):
        """Handle adding individual files."""
        file_filter = "Media files (*.jpg *.jpeg *.png *.gif *.mp4 *.avi *.mov *.mkv *.webp)"

        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Select media files",
            "",
            file_filter
        )

        self.process_files(filenames)

    def add_folder(self):
        """Handle adding a folder of media files."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select folder containing media files"
        )

        if folder:
            extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp',
                          '.mp4', '.avi', '.mov', '.mkv', '.webp')
            media_files = []

            for ext in extensions:
                media_files.extend(Path(folder).glob(f"**/*{ext}"))

            self.process_files(media_files)

    def process_files(self, files):
        """Process the selected files and add them to the database."""
        added = 0
        skipped = 0

        for file in files:
            file_path = str(file)
            if self.db_callback(file_path):
                added += 1
                self.log_text.append(f"Added: {file_path}")
            else:
                skipped += 1
                self.log_text.append(f"Skipped (already exists): {file_path}")

        self.log_text.append(
            f"\nSummary: Added {added} files, Skipped {skipped} files\n"
        )

        # Scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())