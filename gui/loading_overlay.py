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

    def showEvent(self, event):
        """Position the overlay to cover the parent widget."""
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().showEvent(event)

    def set_message(self, message):
        """Update the loading message."""
        self.label.setText(message)