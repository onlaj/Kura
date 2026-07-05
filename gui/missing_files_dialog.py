import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QMessageBox, QFileDialog,
                             QProgressDialog, QInputDialog, QApplication)

from core.media_workers import FileSearchWorker

logger = logging.getLogger(__name__)


def _format_size(size) -> str:
    """Format a file size in bytes as a human-readable string."""
    if size is None:
        return "Unknown"
    size = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024


class MissingFilesDialog(QDialog):
    """
    Review dialog for media records whose files are missing on disk.

    Lets the user remove the records from the database, locate moved files,
    or ignore the problem (e.g. when a drive is temporarily disconnected).
    """

    files_changed = pyqtSignal()  # Emitted after records were removed or paths updated

    CHECK_COL = 0
    NAME_COL = 1
    PATH_COL = 2
    SIZE_COL = 3

    def __init__(self, db, missing_files, parent=None):
        """
        Args:
            db: Database instance
            missing_files: List of dicts with keys id, original_path, filename, file_size
            parent: Parent widget
        """
        super().__init__(parent)
        self.db = db
        self.search_worker = None
        self.search_progress = None
        self.search_results = {}
        self.changes_made = False

        self.setWindowTitle("Missing Files")
        self.setMinimumSize(700, 450)
        self._setup_ui()
        self._populate_table(missing_files)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        hint_label = QLabel(
            "The files may have been deleted, moved or renamed, or they may be on a "
            "disconnected external or network drive. Nothing is changed unless you "
            "choose an action below - closing this dialog leaves everything as it is."
        )
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(hint_label)

        # Table of missing files
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["", "Filename", "Original Path", "Size"])
        self.table.horizontalHeader().setSectionResizeMode(self.CHECK_COL, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(self.NAME_COL, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(self.PATH_COL, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(self.SIZE_COL, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        # Selection controls
        select_layout = QHBoxLayout()
        self.btn_select_all = QPushButton("Select All")
        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_select_all.clicked.connect(lambda: self._set_all_checked(True))
        self.btn_deselect_all.clicked.connect(lambda: self._set_all_checked(False))
        select_layout.addWidget(self.btn_select_all)
        select_layout.addWidget(self.btn_deselect_all)
        select_layout.addStretch()
        layout.addLayout(select_layout)

        # Action buttons
        action_layout = QHBoxLayout()
        self.btn_locate = QPushButton("Locate Selected…")
        self.btn_locate.setToolTip(
            "Search a folder of your choice for the selected files "
            "(matched by filename and size) and update their records"
        )
        self.btn_remove = QPushButton("Remove Selected from Database")
        self.btn_remove.setToolTip(
            "Remove the selected records and their votes from the database. "
            "Files on disk are not touched."
        )
        self.btn_close = QPushButton("Ignore for Now")
        self.btn_close.setToolTip("Close without making any changes")
        self.btn_locate.clicked.connect(self._locate_selected)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_close.clicked.connect(self.accept)
        action_layout.addWidget(self.btn_locate)
        action_layout.addWidget(self.btn_remove)
        action_layout.addStretch()
        action_layout.addWidget(self.btn_close)
        layout.addLayout(action_layout)

    def _populate_table(self, missing_files):
        self.table.setRowCount(0)
        for media in missing_files:
            row = self.table.rowCount()
            self.table.insertRow(row)

            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check_item.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row, self.CHECK_COL, check_item)

            name_item = QTableWidgetItem(media['filename'])
            name_item.setData(Qt.ItemDataRole.UserRole, media)
            self.table.setItem(row, self.NAME_COL, name_item)

            self.table.setItem(row, self.PATH_COL, QTableWidgetItem(media['original_path']))
            self.table.setItem(row, self.SIZE_COL, QTableWidgetItem(_format_size(media['file_size'])))

        self._update_info_label()

    def _update_info_label(self):
        count = self.table.rowCount()
        self.info_label.setText(
            f"<b>{count} media file{'s' if count != 1 else ''} could not be found on disk.</b>"
        )

    def _set_all_checked(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.table.rowCount()):
            self.table.item(row, self.CHECK_COL).setCheckState(state)

    def _selected_media(self):
        """Get the media dicts for all checked rows."""
        selected = []
        for row in range(self.table.rowCount()):
            if self.table.item(row, self.CHECK_COL).checkState() == Qt.CheckState.Checked:
                selected.append(self.table.item(row, self.NAME_COL).data(Qt.ItemDataRole.UserRole))
        return selected

    def _remove_resolved_rows(self, resolved_ids):
        """Remove rows whose media ids were resolved, closing the dialog if empty."""
        for row in range(self.table.rowCount() - 1, -1, -1):
            media = self.table.item(row, self.NAME_COL).data(Qt.ItemDataRole.UserRole)
            if media['id'] in resolved_ids:
                self.table.removeRow(row)
        self._update_info_label()
        if self.table.rowCount() == 0:
            self.accept()

    # ------------------------------------------------------------------
    # Remove records
    # ------------------------------------------------------------------

    def _remove_selected(self):
        selected = self._selected_media()
        if not selected:
            QMessageBox.information(self, "Nothing Selected", "Please select at least one file first.")
            return

        count = len(selected)
        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Remove {count} record{'s' if count != 1 else ''} from the database?\n\n"
            "This also removes their voting history and recalculates ratings. "
            "Files on disk are not touched.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        media_ids = [m['id'] for m in selected]
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            deleted = self.db.delete_media_batch(media_ids)
        except Exception as e:
            logger.error(f"Error removing missing media records: {e}")
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Error", f"Failed to remove records: {str(e)}")
            return
        QApplication.restoreOverrideCursor()

        if deleted:
            self.changes_made = True
            self.files_changed.emit()
        # Removing all requested rows is safe even when deleted < len(media_ids):
        # delete_media_batch is a single all-or-nothing transaction that raises on
        # failure (handled above), so any ID it did not delete was already absent
        # from the database - exactly the state "Remove from Database" aims for.
        self._remove_resolved_rows(set(media_ids))

    # ------------------------------------------------------------------
    # Locate moved files
    # ------------------------------------------------------------------

    def _locate_selected(self):
        selected = self._selected_media()
        if not selected:
            QMessageBox.information(self, "Nothing Selected", "Please select at least one file first.")
            return

        search_dir = QFileDialog.getExistingDirectory(self, "Select Folder to Search")
        if not search_dir:
            return

        if self.search_worker and self.search_worker.isRunning():
            self.search_worker.cancel()
            self.search_worker.wait()

        self.btn_locate.setEnabled(False)
        self.btn_remove.setEnabled(False)

        self.search_progress = QProgressDialog(
            "Searching for missing files...", "Cancel", 0, len(selected), self
        )
        self.search_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.search_progress.show()

        self.search_results = {}
        self.search_worker = FileSearchWorker(selected, search_dir)
        self.search_worker.file_found.connect(self._on_file_found)
        self.search_worker.progress.connect(self._on_search_progress)
        self.search_worker.finished.connect(self._on_search_finished)
        self.search_worker.start()

    def _on_file_found(self, media_id, matches):
        self.search_results[media_id] = matches

    def _on_search_progress(self, current, total):
        if self.search_progress:
            self.search_progress.setValue(current)
            if self.search_progress.wasCanceled() and self.search_worker:
                self.search_worker.cancel()

    def _on_search_finished(self):
        if self.search_progress:
            self.search_progress.close()
            self.search_progress = None

        media_by_id = {}
        for row in range(self.table.rowCount()):
            media = self.table.item(row, self.NAME_COL).data(Qt.ItemDataRole.UserRole)
            media_by_id[media['id']] = media

        resolved_ids = set()
        searched = len(self.search_results)

        for media_id, matches in self.search_results.items():
            if not matches:
                continue
            media = media_by_id.get(media_id)
            if not media:
                continue

            if len(matches) == 1:
                new_path = matches[0]
            else:
                item, ok = QInputDialog.getItem(
                    self,
                    "Select File",
                    f"Multiple matches found for {media['filename']}:",
                    matches,
                    0, False
                )
                new_path = item if ok else None

            if new_path and self.db.update_media_path(media_id, new_path):
                resolved_ids.add(media_id)

        self.btn_locate.setEnabled(True)
        self.btn_remove.setEnabled(True)
        self.search_worker = None
        self.search_results = {}

        if resolved_ids:
            self.changes_made = True
            self.files_changed.emit()

        QMessageBox.information(
            self,
            "Search Complete",
            f"Found and updated {len(resolved_ids)} of {searched} selected file"
            f"{'s' if searched != 1 else ''}."
        )
        self._remove_resolved_rows(resolved_ids)

    def closeEvent(self, event):
        """Make sure a running search is stopped when the dialog closes."""
        if self.search_worker and self.search_worker.isRunning():
            self.search_worker.cancel()
            self.search_worker.wait()
        super().closeEvent(event)
