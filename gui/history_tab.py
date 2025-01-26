# gui/history_tab.py
import logging
import os
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QHeaderView, QLineEdit,
                             QComboBox, QPushButton, QLabel, QAbstractItemView)
from core.preview_handler import MediaPreview
from core.media_handler import MediaHandler

logger = logging.getLogger(__name__)


class HistoryTab(QWidget):
    def __init__(self, db, media_handler):
        super().__init__()
        self.db = db
        self.media_handler = media_handler
        self.preview = MediaPreview(self)
        self.current_page = 1
        self.per_page = 20
        self.active_album_id = 1
        self.sort_by = "timestamp"
        self.sort_order = "DESC"
        self.search_query = None

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Controls
        control_layout = QHBoxLayout()

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search files...")
        self.search_input.textChanged.connect(self.on_search_changed)
        control_layout.addWidget(self.search_input)

        # Pagination controls
        self.first_page_btn = QPushButton("<<")
        self.first_page_btn.clicked.connect(self.go_to_first_page)
        self.prev_btn = QPushButton("Previous")
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.next_page)
        self.last_page_btn = QPushButton(">>")
        self.last_page_btn.clicked.connect(self.go_to_last_page)
        self.page_label = QLabel()

        control_layout.addWidget(self.first_page_btn)
        control_layout.addWidget(self.prev_btn)
        control_layout.addWidget(self.next_btn)
        control_layout.addWidget(self.last_page_btn)
        control_layout.addWidget(self.page_label)

        layout.addLayout(control_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Date", "Winner", "Loser"])
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().sectionClicked.connect(self.on_header_clicked)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.cellDoubleClicked.connect(self.show_history_preview)

        layout.addWidget(self.table)

        self.load_data()


    def load_data(self):
        self.table.setRowCount(0)
        history, total = self.db.get_vote_history_page(
            self.active_album_id,
            self.current_page,
            self.per_page,
            self.sort_by,
            self.sort_order,
            self.search_query
        )

        for row in history:
            idx = self.table.rowCount()
            self.table.insertRow(idx)

            # Date
            self.table.setItem(idx, 0, QTableWidgetItem(str(row[1])))

            # Winner
            winner_item = self.create_media_item(row[2])
            self.table.setItem(idx, 1, winner_item)

            # Loser
            loser_item = self.create_media_item(row[3])
            self.table.setItem(idx, 2, loser_item)

        # Update pagination
        total_pages = max(1, (total + self.per_page - 1) // self.per_page)
        self.page_label.setText(f"Page {self.current_page} of {total_pages}")
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < total_pages)
        self.first_page_btn.setEnabled(self.current_page > 1)
        self.last_page_btn.setEnabled(self.current_page < total_pages)

    def create_media_item(self, path):
        item = QTableWidgetItem(os.path.basename(path))
        item.setData(Qt.ItemDataRole.UserRole, path)
        return item

    def show_history_preview(self, row, col):
        if col not in [1, 2]:  # Only preview for winner/loser columns
            return

        path = self.table.item(row, col).data(Qt.ItemDataRole.UserRole)
        media = self.media_handler.load_media(path)
        self.media_handler.pause_all_videos()

        if isinstance(media, tuple):
            widget, player = media
            self.preview.show_media(widget, media_path=path)
        else:
            self.preview.show_media(media, media_path=path)

    def on_sort_changed(self, text):
        sort_map = {
            "Date": "timestamp",
            "Winner": "winner",
            "Loser": "loser"
        }
        self.sort_by = sort_map.get(text, "timestamp")
        self.load_data()

    def on_order_changed(self, text):
        self.sort_order = "DESC" if text == "Descending" else "ASC"
        self.load_data()

    def on_search_changed(self, text):
        self.search_query = text if text.strip() else None
        self.current_page = 1
        self.load_data()

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_data()

    def next_page(self):
        self.current_page += 1
        self.load_data()

    def set_active_album(self, album_id: int):
        self.active_album_id = album_id
        self.load_data()

    def on_header_clicked(self, logical_index):
        sort_mapping = {
            0: "timestamp",
            1: "winner",
            2: "loser"
        }
        new_sort_by = sort_mapping.get(logical_index, "timestamp")

        if self.sort_by == new_sort_by:
            self.sort_order = "DESC" if self.sort_order == "ASC" else "ASC"
        else:
            self.sort_by = new_sort_by
            self.sort_order = "DESC"

        self.table.horizontalHeader().setSortIndicator(
            logical_index,
            Qt.SortOrder.DescendingOrder if self.sort_order == "DESC" else Qt.SortOrder.AscendingOrder
        )
        self.load_data()

    # New navigation methods
    def go_to_first_page(self):
        self.current_page = 1
        self.load_data()

    def go_to_last_page(self):
        self.current_page = self.get_total_pages()
        self.load_data()

    def get_total_pages(self):
        self.table.horizontalHeader().setSortIndicatorShown(True)
        _, total = self.db.get_vote_history_page(
            self.active_album_id,
            self.current_page,
            self.per_page,
            self.sort_by,
            self.sort_order,
            self.search_query
        )
        return max(1, (total + self.per_page - 1) // self.per_page)