from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QProgressBar


class LoadingOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Set up the overlay appearance
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 0, 0, 180);
            }
            QLabel {
                color: white;
                font-size: 16px;
            }
        """)

        # Create layout
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Add loading text
        self.label = QLabel("Loading media...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        # Add progress bar
        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(0)  # Indeterminate progress
        self.progress.setMinimumWidth(300)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: 2px solid grey;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                width: 20px;
            }
        """)
        layout.addWidget(self.progress)

        # Hide by default
        self.hide()

        self.total_items = 0
        self.loaded_items = 0

    def showEvent(self, event):
        """Position the overlay to cover the parent widget."""
        if self.parent():
            self.setGeometry(self.parent().rect())
            # Ensure overlay is on top
            self.raise_()
            self.activateWindow()
        super().showEvent(event)

    def set_message(self, message):
        """Update the loading message."""
        self.label.setText(message)
        # Ensure visibility
        if not self.isVisible():
            self.show()

    def set_total_items(self, total):
        """Set the total number of items to load."""
        self.total_items = total
        self.loaded_items = 0
        self.progress.setMaximum(total)
        self.progress.setValue(0)

    def increment_progress(self):
        """Increment the progress counter by one."""
        self.loaded_items += 1
        self.progress.setValue(self.loaded_items)
        self.label.setText(f"Loading media... ({self.loaded_items}/{self.total_items})")