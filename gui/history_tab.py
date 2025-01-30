# gui/history_tab.py
import logging
import os
from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QMovie
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QHeaderView, QLineEdit,
                             QComboBox, QPushButton, QLabel, QAbstractItemView, QMessageBox, QCheckBox)
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
        self.per_page = 10
        self.search_query = None
        self._is_programmatic_change = False

        self.selected_votes = set()
        self.current_vote_ids = []  # Track vote IDs on current page
        self._needs_refresh = False  # Flag for tracking refresh need

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Controls
        control_layout = QHBoxLayout()

        # Add selection controls
        control_layout.addWidget(QLabel("Selection:"))

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all_on_page)
        control_layout.addWidget(self.select_all_btn)

        self.unselect_all_btn = QPushButton("Unselect All")
        self.unselect_all_btn.clicked.connect(self.unselect_all)
        self.unselect_all_btn.hide()  # Start hidden
        control_layout.addWidget(self.unselect_all_btn)

        self.delete_selected_btn = QPushButton("Delete Selected")
        self.delete_selected_btn.clicked.connect(self.delete_selected_votes)
        control_layout.addWidget(self.delete_selected_btn)

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search files...")
        self.search_input.textChanged.connect(self.on_search_changed)
        control_layout.addWidget(self.search_input)

        # Add spacer before pagination controls
        control_layout.addStretch()


        control_layout.addWidget(QLabel("Items per page:"))
        self.items_per_page = QComboBox()
        self.items_per_page.addItems(["10", "20", "50", "100"])
        self.items_per_page.setCurrentText("10")
        self.items_per_page.currentTextChanged.connect(self.change_items_per_page)
        control_layout.addWidget(self.items_per_page)

        control_layout.addWidget(QLabel("Page:"))
        self.page_input = QLineEdit()
        self.page_input.setFixedWidth(50)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.page_input.textChanged.connect(self.on_page_input_changed)
        control_layout.addWidget(self.page_input)

        self.go_button = QPushButton("Go")
        self.go_button.setFixedWidth(40)
        self.go_button.clicked.connect(self.go_to_page)
        self.go_button.hide()
        control_layout.addWidget(self.go_button)

        # Existing pagination buttons
        self.first_page_btn = QPushButton("<<")
        self.first_page_btn.clicked.connect(self.go_to_first_page)
        self.prev_btn = QPushButton("Previous")
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.next_page)
        self.last_page_btn = QPushButton(">>")
        self.last_page_btn.clicked.connect(self.go_to_last_page)
        self.page_label = QLabel()

        # Add widgets to layout
        control_layout.addWidget(self.first_page_btn)
        control_layout.addWidget(self.prev_btn)
        control_layout.addWidget(self.next_btn)
        control_layout.addWidget(self.last_page_btn)
        control_layout.addWidget(self.page_label)

        layout.addLayout(control_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["", "Date", "Winner", "Loser"])
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().sectionClicked.connect(self.on_header_clicked)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.cellDoubleClicked.connect(self.show_history_preview)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.table)

        self.load_data()

    def set_needs_refresh(self):
        """Mark that the history needs to be refreshed"""
        self._needs_refresh = True

    def refresh_if_needed(self):
        """Refresh the data only if needed"""
        if self._needs_refresh:
            self.load_data()
            self._needs_refresh = False


    def load_data(self):
        self.table.setRowCount(0)
        self.current_vote_ids = []
        history, total = self.db.get_vote_history_page(
            self.active_album_id,
            self.current_page,
            self.per_page,
            self.sort_by,
            self.sort_order,
            self.search_query
        )

        for row_idx, row in enumerate(history):
            self.table.insertRow(row_idx)
            vote_id = row[0]
            self.current_vote_ids.append(vote_id)

            # Checkbox column
            checkbox = QCheckBox()
            checkbox.setChecked(vote_id in self.selected_votes)
            checkbox.stateChanged.connect(lambda state, vid=vote_id: self.update_selected_votes(state, vid))
            self.table.setCellWidget(row_idx, 0, checkbox)

            # Date column
            self.table.setItem(row_idx, 1, QTableWidgetItem(str(row[1])))

            # Winner column
            winner_item = self.create_media_item(row[2])  # Adjusted index for winner path
            self.table.setItem(row_idx, 2, winner_item)

            # Loser column
            loser_item = self.create_media_item(row[3])  # Adjusted index for loser path
            self.table.setItem(row_idx, 3, loser_item)

        # Update pagination
        total_pages = max(1, (total + self.per_page - 1) // self.per_page)
        self.page_label.setText(f"Page {self.current_page} of {total_pages}")
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < total_pages)
        self.first_page_btn.setEnabled(self.current_page > 1)
        self.last_page_btn.setEnabled(self.current_page < total_pages)

        self._is_programmatic_change = True
        self.page_input.setText(str(self.current_page))
        self._is_programmatic_change = False
        self.update_selected_buttons()

    def create_media_item(self, path):
        item = QTableWidgetItem(os.path.basename(path))
        item.setData(Qt.ItemDataRole.UserRole, path)
        return item

    def show_history_preview(self, row, col):
        if col not in [2, 3]:  # Only preview for winner/loser columns
            return

        path = self.table.item(row, col).data(Qt.ItemDataRole.UserRole)
        media = self.media_handler.load_media(path)
        self.media_handler.pause_all_videos()

        # Store references to the media player
        media_player = None
        widget = None

        if isinstance(media, tuple):
            widget, player = media
            if hasattr(player, 'play'):  # Video player
                media_player = player
            elif isinstance(player, QMovie):  # GIF
                media_player = player

        # Install event filter for video controls
        if widget and media_player:
            widget.installEventFilter(self)
            widget.setProperty('media_player', media_player)
            widget.setProperty('media_path', path)

        self.preview.show_media(widget if widget else media,
                                media_path=path,
                                video_player=media_player)

    def eventFilter(self, obj, event):
        """Handle video widget events in preview"""
        if event.type() == QEvent.Type.MouseButtonPress:
            media_player = obj.property('media_player')
            preview = self.preview

            if event.button() == Qt.MouseButton.LeftButton:
                # Single click - toggle play/pause
                if event.type() == QEvent.Type.MouseButtonPress:
                    if media_player:
                        if media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                            media_player.pause()
                        else:
                            media_player.play()
                        return True

            # Double click - stop and close
            elif event.type() == QEvent.Type.MouseButtonDblClick:
                if media_player:
                    media_player.stop()
                self.preview.close()
                return True

        return super().eventFilter(obj, event)

    def update_selected_votes(self, state, vote_id):
        if state == Qt.CheckState.Checked.value:
            self.selected_votes.add(vote_id)
        else:
            self.selected_votes.discard(vote_id)

        # Update buttons visibility
        self.unselect_all_btn.setVisible(len(self.selected_votes) > 0)
        self.delete_selected_btn.setVisible(len(self.selected_votes) > 0)

    def unselect_all(self):
        """Deselect all votes across all pages"""
        self.selected_votes.clear()
        self.update_checkboxes()

        # Update buttons visibility
        self.unselect_all_btn.hide()
        self.delete_selected_btn.hide()

    def select_all_on_page(self):
        for vote_id in self.current_vote_ids:
            self.selected_votes.add(vote_id)
        self.update_checkboxes()
        self.update_selected_buttons()

    def update_selected_buttons(self):
        """Update visibility of selection-related buttons"""
        has_selections = len(self.selected_votes) > 0
        self.unselect_all_btn.setVisible(has_selections)
        self.delete_selected_btn.setVisible(has_selections)

    def update_checkboxes(self):
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 0)
            if checkbox:  # Add null check
                vote_id = self.current_vote_ids[row]
                checkbox.setChecked(vote_id in self.selected_votes)

    def delete_selected_votes(self):
        if not self.selected_votes:
            return

        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete {len(self.selected_votes)} votes? This will recalculate all ratings.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Start transaction
                self.db.conn.execute("BEGIN")

                # Delete selected votes
                self.db.cursor.executemany(
                    "DELETE FROM votes WHERE id = ?",
                    [(vid,) for vid in self.selected_votes]
                )

                # Recalculate ratings once
                self.db._recalculate_ratings()

                self.db.conn.commit()

                # Clear selection and refresh
                self.selected_votes.clear()
                self.load_data()
                # Refresh ranking tab if needed
                if hasattr(self.parent(), 'ranking_tab'):
                    self.parent().ranking_tab.refresh_rankings()

            except Exception as e:
                self.db.conn.rollback()
                QMessageBox.critical(self, "Error", f"Failed to delete votes: {str(e)}")

    def change_items_per_page(self, value):
        """Handle changes to items per page selection"""
        self.per_page = int(value)
        self.current_page = 1  # Reset to first page when changing page size
        self.load_data()

    def on_page_input_changed(self):
        """Handle page input changes"""
        if not self._is_programmatic_change and self.page_input.text().strip():
            self.go_button.show()
        else:
            self.go_button.hide()

    def go_to_page(self):
        """Navigate to specified page"""
        try:
            page_number = int(self.page_input.text())
            total_pages = self.get_total_pages()

            if 1 <= page_number <= total_pages:
                self.current_page = page_number
                self.load_data()
                self.go_button.hide()
            else:
                QMessageBox.warning(self, "Invalid Page",
                                    f"Please enter a page number between 1 and {total_pages}.")
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid page number.")

    def on_sort_changed(self, text):
        sort_map = {
            "Date": "timestamp",
            "Winner": "winner",
            "Loser": "loser"
        }
        self.sort_by = sort_map.get(text, "timestamp")
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
            1: "timestamp",
            2: "winner",
            3: "loser"
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
        _, total = self.db.get_vote_history_page(
            self.active_album_id,
            1,  # Any page number since we just need total count
            self.per_page,  # Use the current per_page value
            self.sort_by,
            self.sort_order,
            self.search_query
        )
        return max(1, (total + self.per_page - 1) // self.per_page)