from PyQt6.QtWidgets import (QMainWindow, QTabWidget, QWidget, QVBoxLayout)


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
        self.tab_history = None
        self.tab_change_callback = None

        self.media_handler = media_handler

    def setup_tabs(self, albums_tab, voting_tab, load_tab, ranking_tab, history_tab):
        """Set up the application tabs."""
        self.tab_albums = albums_tab
        self.tab_voting = voting_tab
        self.tab_load = load_tab
        self.tab_ranking = ranking_tab
        self.tab_history = history_tab

        self.tab_widget.addTab(self.tab_albums, "Albums")
        self.tab_widget.addTab(self.tab_voting, "Voting")
        self.tab_widget.addTab(self.tab_load, "Load")
        self.tab_widget.addTab(self.tab_ranking, "Ranking")
        self.tab_widget.addTab(self.tab_history, "Votes history")

        # Connect tab changed signal
        self.tab_widget.currentChanged.connect(self._handle_tab_change)

    def current_tab_name(self) -> str:
        index = self.tab_widget.currentIndex()
        if index < 0:
            return ""
        return self.tab_widget.tabText(index)

    def on_album_changed(self, album_id: int, album_name: str):
        if album_id <= 1:
            self.setWindowTitle("Kura")
        else:
            self.setWindowTitle(f"Kura • {album_name}")

    def _handle_tab_change(self, _index):
        """Handle tab changes."""
        if self.tab_change_callback:
            self.tab_change_callback()
        self.media_handler.pause_all_videos()