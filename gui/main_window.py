from PyQt6.QtWidgets import (QMainWindow, QTabWidget, QWidget, QVBoxLayout, QLabel)
from PyQt6.QtCore import Qt


class MainWindow(QMainWindow):
    def __init__(self, media_handler):
        super().__init__()
        self.setWindowTitle("Kura")
        self.resize(1280, 800)

        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Initialize tabs (will be set by Application class)
        self.tab_albums = None
        self.tab_voting = None
        self.tab_load = None
        self.tab_ranking = None

        self.media_handler = media_handler

    def setup_tabs(self, albums_tab, voting_tab, load_tab, ranking_tab, history_tab):
        """Set up the application tabs."""
        self.tab_albums = albums_tab
        self.tab_voting = voting_tab
        self.tab_load = load_tab
        self.tab_ranking = ranking_tab
        self.tab_history = history_tab

        # Connect album change signal
        self.tab_albums.album_changed.connect(self.on_album_changed)

        self.tab_widget.addTab(self.tab_albums, "Albums")
        self.tab_widget.addTab(self.tab_voting, "Voting")
        self.tab_widget.addTab(self.tab_load, "Load")
        self.tab_widget.addTab(self.tab_ranking, "Ranking")
        self.tab_widget.addTab(self.tab_history, "Votes history")

        # Connect tab changed signal
        self.tab_widget.currentChanged.connect(self._handle_tab_change)

    def on_album_changed(self, album_id: int, album_name: str):
        if album_id <= 1:
            self.setWindowTitle("Kura")
        else:
            self.setWindowTitle(f"Kura • {album_name}")

    def _handle_tab_change(self, index):
        """Handle tab changes."""
        tab_name = self.tab_widget.tabText(index)
        if tab_name == "Voting":
            self.tab_voting.ensure_images_loaded()
        elif tab_name == "Ranking":
            self.tab_ranking.refresh_rankings(force_refresh=False)
        elif tab_name == "Votes history":
            self.tab_history.refresh_if_needed()

        self.media_handler.pause_all_videos()