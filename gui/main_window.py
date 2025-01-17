from PyQt6.QtWidgets import (QMainWindow, QTabWidget, QWidget, QVBoxLayout,
                             QApplication)
from PyQt6.QtCore import Qt


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image ELO Ranker")
        self.resize(1024, 768)

        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Initialize tabs (will be set by Application class)
        self.tab_voting = None
        self.tab_upload = None
        self.tab_ranking = None

    def setup_tabs(self, voting_tab, upload_tab, ranking_tab):
        """Set up the application tabs."""
        self.tab_voting = voting_tab
        self.tab_upload = upload_tab
        self.tab_ranking = ranking_tab

        self.tab_widget.addTab(self.tab_voting, "Voting")
        self.tab_widget.addTab(self.tab_upload, "Upload")
        self.tab_widget.addTab(self.tab_ranking, "Ranking")

        # Connect tab changed signal
        self.tab_widget.currentChanged.connect(self._handle_tab_change)

    def _handle_tab_change(self, index):
        """Handle tab changes."""
        tab_name = self.tab_widget.tabText(index)
        if tab_name == "Voting":
            self.tab_voting.ensure_images_loaded()
        elif tab_name == "Ranking":
            self.tab_ranking.refresh_rankings()