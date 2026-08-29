import logging
import os

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QMessageBox, QApplication)

from core.file_delete import delete_file

logger = logging.getLogger(__name__)


def failed_file_entry(media_id, file_path, error):
    """Build the dict expected by FailedDeleteDialog."""
    return {
        'id': media_id,
        'path': file_path or '',
        'filename': os.path.basename(file_path) if file_path else '',
        'error': error or 'Unknown error',
    }


class FailedDeleteDialog(QDialog):
    """
    Review dialog for media files that could not be removed from disk.

    The database records are still present. The user can retry the disk delete,
    drop the records while keeping the files, open the containing folder, or ignore.
    """

    files_changed = pyqtSignal()  # Emitted after records were removed or files deleted

    CHECK_COL = 0
    NAME_COL = 1
    PATH_COL = 2
    ERROR_COL = 3

    def __init__(self, db, failed_files, parent=None, release_callback=None):
        """
        Args:
            db: Database instance
            failed_files: List of dicts with keys id, path, filename, error
            parent: Parent widget
            release_callback: Optional callable(path) that releases in-app file handles
        """
        super().__init__(parent)
        self.db = db
        self.release_callback = release_callback
        self.changes_made = False

        self.setWindowTitle("Files Could Not Be Deleted")
        self.setMinimumSize(700, 450)
        self._setup_ui()
        self._populate_table(failed_files)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        hint_label = QLabel(
            "The files are still on disk and their records are still in the database. "
            "Another program may be using them, or they may be locked. Nothing is changed "
            "unless you choose an action below - closing this dialog leaves everything as it is."
        )
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(hint_label)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["", "Filename", "Path", "Error"])
        self.table.horizontalHeader().setSectionResizeMode(self.CHECK_COL, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(self.NAME_COL, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(self.PATH_COL, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(self.ERROR_COL, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        select_layout = QHBoxLayout()
        self.btn_select_all = QPushButton("Select All")
        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_select_all.clicked.connect(lambda: self._set_all_checked(True))
        self.btn_deselect_all.clicked.connect(lambda: self._set_all_checked(False))
        select_layout.addWidget(self.btn_select_all)
        select_layout.addWidget(self.btn_deselect_all)
        select_layout.addStretch()
        layout.addLayout(select_layout)

        action_layout = QHBoxLayout()
        self.btn_retry = QPushButton("Retry Delete Selected")
        self.btn_retry.setToolTip(
            "Release any handles this app still holds, then try to delete the selected files again"
        )
        self.btn_show_folder = QPushButton("Show in Folder")
        self.btn_show_folder.setToolTip(
            "Open the folder containing the selected files so you can close whatever else is using them"
        )
        self.btn_remove = QPushButton("Remove Selected from Database")
        self.btn_remove.setToolTip(
            "Remove the selected records and their votes from the database. "
            "Files on disk are not touched."
        )
        self.btn_close = QPushButton("Ignore for Now")
        self.btn_close.setToolTip("Close without making any changes")
        self.btn_retry.clicked.connect(self._retry_selected)
        self.btn_show_folder.clicked.connect(self._show_in_folder)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_close.clicked.connect(self.accept)
        action_layout.addWidget(self.btn_retry)
        action_layout.addWidget(self.btn_show_folder)
        action_layout.addWidget(self.btn_remove)
        action_layout.addStretch()
        action_layout.addWidget(self.btn_close)
        layout.addLayout(action_layout)

    def _populate_table(self, failed_files):
        self.table.setRowCount(0)
        for media in failed_files:
            self._append_row(media)
        self._update_info_label()

    def _append_row(self, media):
        row = self.table.rowCount()
        self.table.insertRow(row)

        check_item = QTableWidgetItem()
        check_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        check_item.setCheckState(Qt.CheckState.Checked)
        self.table.setItem(row, self.CHECK_COL, check_item)

        name_item = QTableWidgetItem(media['filename'])
        name_item.setData(Qt.ItemDataRole.UserRole, media)
        self.table.setItem(row, self.NAME_COL, name_item)

        self.table.setItem(row, self.PATH_COL, QTableWidgetItem(media['path']))
        self.table.setItem(row, self.ERROR_COL, QTableWidgetItem(media['error']))

    def _update_info_label(self):
        count = self.table.rowCount()
        self.info_label.setText(
            f"<b>{count} file{'s' if count != 1 else ''} could not be deleted from disk.</b>"
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

    def _update_error_for_id(self, media_id, error):
        for row in range(self.table.rowCount()):
            media = self.table.item(row, self.NAME_COL).data(Qt.ItemDataRole.UserRole)
            if media['id'] == media_id:
                media['error'] = error
                self.table.item(row, self.NAME_COL).setData(Qt.ItemDataRole.UserRole, media)
                self.table.setItem(row, self.ERROR_COL, QTableWidgetItem(error))
                break

    def _retry_selected(self):
        selected = self._selected_media()
        if not selected:
            QMessageBox.information(self, "Nothing Selected", "Please select at least one file first.")
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        resolved_ids = set()
        disk_deleted_ids = []
        try:
            for media in selected:
                path = media['path']
                if self.release_callback:
                    try:
                        self.release_callback(path)
                    except Exception as e:
                        logger.warning(f"Error releasing media resources for {path}: {e}")

                ok, error = delete_file(path, pump_events=True)
                if not ok:
                    self._update_error_for_id(media['id'], error or "File still exists after delete")
                    continue
                disk_deleted_ids.append(media['id'])

            if disk_deleted_ids:
                try:
                    self.db.delete_media_batch(disk_deleted_ids)
                    resolved_ids = set(disk_deleted_ids)
                except Exception as e:
                    logger.error(f"Error removing media records after disk delete: {e}")
                    for media_id in disk_deleted_ids:
                        self._update_error_for_id(
                            media_id,
                            f"File deleted, but the database record could not be removed: {e}"
                        )
        finally:
            QApplication.restoreOverrideCursor()

        if resolved_ids:
            self.changes_made = True
            self.files_changed.emit()
            self._remove_resolved_rows(resolved_ids)

        still_failed = len(selected) - len(resolved_ids)
        if still_failed and self.table.rowCount() > 0:
            QMessageBox.warning(
                self,
                "Retry Incomplete",
                f"Deleted {len(resolved_ids)} of {len(selected)} selected file"
                f"{'s' if len(selected) != 1 else ''}. "
                f"{still_failed} could not be removed. Close any program that has them open and try again."
            )

    def _show_in_folder(self):
        selected = self._selected_media()
        if not selected:
            QMessageBox.information(self, "Nothing Selected", "Please select at least one file first.")
            return

        opened = set()
        missing_folders = []
        for media in selected:
            folder = os.path.dirname(media['path'])
            if not folder or folder in opened:
                continue
            if os.path.isdir(folder):
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
                opened.add(folder)
            else:
                missing_folders.append(folder or media['path'])

        if not opened and missing_folders:
            QMessageBox.warning(
                self,
                "Folder Not Found",
                "Could not open the folder for the selected file(s)."
            )

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
            logger.error(f"Error removing media records after failed disk delete: {e}")
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Error", f"Failed to remove records: {str(e)}")
            return
        QApplication.restoreOverrideCursor()

        if deleted:
            self.changes_made = True
            self.files_changed.emit()
        self._remove_resolved_rows(set(media_ids))
