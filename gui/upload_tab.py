from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTextEdit, QFileDialog, QCheckBox, QGroupBox, QFormLayout)

class UploadTab(QWidget):
    def __init__(self, db_callback, media_handler, ranking_tab):
        super().__init__()
        self.db_callback = db_callback
        self.media_handler = media_handler
        self.ranking_tab = ranking_tab  # Store reference to RankingTab
        self.setup_ui()

    def setup_ui(self):
        """Set up the upload interface."""
        self.setAcceptDrops(True)
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

        # Create options group box
        options_group = QGroupBox("Folder Upload Options")
        options_layout = QFormLayout()

        # Recursive search checkbox
        self.recursive_checkbox = QCheckBox("Recursive search")
        self.recursive_checkbox.setChecked(True)
        options_layout.addRow(self.recursive_checkbox)

        # Image checkbox
        self.images_checkbox = QCheckBox("Images")
        self.images_checkbox.setChecked(True)
        options_layout.addRow(self.images_checkbox)

        # GIF checkbox
        self.gifs_checkbox = QCheckBox("GIFs")
        self.gifs_checkbox.setChecked(True)
        options_layout.addRow(self.gifs_checkbox)

        # Video checkbox
        self.videos_checkbox = QCheckBox("Videos")
        self.videos_checkbox.setChecked(True)
        options_layout.addRow(self.videos_checkbox)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Create log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [url.toLocalFile() for url in urls]

        allowed_exts = {'.jpg', '.jpeg', '.png', '.gif', '.mp4', '.avi', '.mov', '.mkv', '.webp', '.webm'}
        all_files = []

        for path in paths:
            file_path = Path(path)
            if file_path.is_file():
                ext = file_path.suffix.lower()
                if ext in allowed_exts:
                    all_files.append(file_path)
                else:
                    self.log_text.append(f"Skipped (unsupported type): {file_path}")
            elif file_path.is_dir():
                extensions = self._get_selected_extensions()
                media_files = self._collect_media_files_from_folder(str(file_path), extensions)
                all_files.extend(media_files)

        self.process_files(all_files)

    # Helper methods extracted from add_folder
    def _get_selected_extensions(self):
        extensions = []
        if self.images_checkbox.isChecked():
            extensions.extend(['.jpg', '.jpeg', '.png', '.webp'])
        if self.gifs_checkbox.isChecked():
            extensions.append('.gif')
        if self.videos_checkbox.isChecked():
            extensions.extend(['.mp4', '.avi', '.mov', '.mkv', '.webm'])
        return extensions

    def _collect_media_files_from_folder(self, folder, extensions):
        media_files = []
        if self.recursive_checkbox.isChecked():
            for ext in extensions:
                media_files.extend(Path(folder).glob(f"**/*{ext}"))
        else:
            for ext in extensions:
                media_files.extend(Path(folder).glob(f"*{ext}"))
        return media_files

    def add_files(self):
        """Handle adding individual files."""
        file_filter = "Media files (*.jpg *.jpeg *.png *.gif *.mp4 *.avi *.mov *.mkv *.webp *.webm)"

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
        media_files = None
        if folder:
            extensions = self._get_selected_extensions()
            media_files = self._collect_media_files_from_folder(folder, extensions)
            self.process_files(media_files)
        if media_files:
            self.process_files(media_files)

    def process_files(self, files):
        """Process the selected files and add them to the database."""
        added = 0
        skipped = 0

        for file in files:
            file_path = str(file)
            media_type = self.media_handler.get_media_type(file_path)
            if self.db_callback(file_path, media_type):
                added += 1
                self.log_text.append(f"Added: {file_path} ({media_type})")
            else:
                skipped += 1
                self.log_text.append(f"Skipped (already exists): {file_path}")

        self.log_text.append(
            f"\nSummary: Added {added} files, Skipped {skipped} files\n"
        )

        # Notify RankingTab that new files have been uploaded
        if added > 0:
            self.ranking_tab.set_new_files_flag()

        # Scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())