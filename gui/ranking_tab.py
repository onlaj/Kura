# gui/ranking_tab.py

import customtkinter as ctk
from PIL import Image, ImageTk
import os
from typing import List, Tuple


class RankingTab(ctk.CTkFrame):
    def __init__(self, parent, get_rankings_callback, image_handler):
        """
        Initialize the ranking tab.

        Args:
            parent: Parent widget
            get_rankings_callback: Callback to get current rankings from database
            image_handler: ImageHandler instance for loading and resizing images
        """
        super().__init__(parent)
        self.get_rankings_callback = get_rankings_callback
        self.image_handler = image_handler
        self.thumbnail_size = (150, 150)  # Size for thumbnails
        self.photo_references = []  # Keep references to prevent garbage collection

        # Configure grid layout
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Create widgets
        self.setup_ui()

    def setup_ui(self):
        """Setup all UI elements"""
        # Create refresh button
        self.btn_refresh = ctk.CTkButton(
            self,
            text="Refresh Rankings",
            command=self.refresh_rankings
        )
        self.btn_refresh.grid(row=0, column=0, padx=20, pady=20, sticky="ew")

        # Create scrollable frame for rankings
        self.scrollable_frame = ctk.CTkScrollableFrame(self)
        self.scrollable_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.scrollable_frame.grid_columnconfigure(1, weight=1)

        # Initial refresh
        self.refresh_rankings()

    def refresh_rankings(self):
        """Refresh the rankings display"""
        # Clear current rankings and photo references
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.photo_references.clear()

        # Get current rankings
        rankings = self.get_rankings_callback()

        # Display rankings
        for i, (id, path, rating, votes) in enumerate(rankings, 1):
            frame = ctk.CTkFrame(self.scrollable_frame)
            frame.grid(row=i, column=0, padx=10, pady=5, sticky="ew")
            frame.grid_columnconfigure(2, weight=1)

            # Rank number
            rank_label = ctk.CTkLabel(frame, text=f"#{i}")
            rank_label.grid(row=0, column=0, padx=10, pady=5)

            # Load and display thumbnail
            photo = self.image_handler.load_image(path, thumbnail_size=self.thumbnail_size)
            if photo:
                self.photo_references.append(photo)  # Keep reference
                image_label = ctk.CTkLabel(frame, image=photo, text="")
                image_label.grid(row=0, column=1, padx=10, pady=5)

            # Image info frame
            info_frame = ctk.CTkFrame(frame)
            info_frame.grid(row=0, column=2, padx=10, pady=5, sticky="ew")
            info_frame.grid_columnconfigure(0, weight=1)

            # File name
            filename_label = ctk.CTkLabel(
                info_frame,
                text=os.path.basename(path),
                anchor="w"
            )
            filename_label.grid(row=0, column=0, padx=5, pady=2, sticky="w")

            # Rating and votes
            stats_label = ctk.CTkLabel(
                info_frame,
                text=f"Rating: {rating:.1f} | Votes: {votes}",
                anchor="w"
            )
            stats_label.grid(row=1, column=0, padx=5, pady=2, sticky="w")