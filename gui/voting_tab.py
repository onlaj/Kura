# gui/voting_tab.py

import customtkinter as ctk
from PIL import Image, ImageTk
import time
from core.elo import Rating
from typing import Optional, Tuple


class VotingTab(ctk.CTkFrame):
    def __init__(self, parent, get_pair_callback, update_ratings_callback, image_handler):
        """
        Initialize the voting tab.

        Args:
            parent: Parent widget
            get_pair_callback: Callback to get image pair for voting
            update_ratings_callback: Callback to update ratings after vote
            image_handler: ImageHandler instance for loading images
        """
        super().__init__(parent)
        self.get_pair_callback = get_pair_callback
        self.update_ratings_callback = update_ratings_callback
        self.image_handler = image_handler

        # Current images data
        self.current_left = None
        self.current_right = None
        self.photo_references = []
        self.images_loaded = False  # Track if images have been loaded

        # Voting cooldown
        self.last_vote_time = 0
        self.vote_cooldown = 1.0  # seconds

        # Configure grid layout
        self.grid_columnconfigure((0, 1), weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.setup_ui()
        self.load_new_pair()


    def setup_ui(self):
        """Setup all UI elements"""
        # Left frame
        self.left_frame = ctk.CTkFrame(self)
        self.left_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.left_frame.grid_rowconfigure(0, weight=1)
        self.left_frame.grid_columnconfigure(0, weight=1)

        # Right frame
        self.right_frame = ctk.CTkFrame(self)
        self.right_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.right_frame.grid_rowconfigure(0, weight=1)
        self.right_frame.grid_columnconfigure(0, weight=1)

        # Image labels
        self.left_image_label = ctk.CTkLabel(self.left_frame, text="")
        self.left_image_label.grid(row=0, column=0, padx=10, pady=10)

        self.right_image_label = ctk.CTkLabel(self.right_frame, text="")
        self.right_image_label.grid(row=0, column=0, padx=10, pady=10)

        # Vote buttons
        self.left_button = ctk.CTkButton(
            self.left_frame,
            text="Vote Left",
            command=lambda: self.handle_vote("left")
        )
        self.left_button.grid(row=1, column=0, padx=10, pady=10)

        self.right_button = ctk.CTkButton(
            self.right_frame,
            text="Vote Right",
            command=lambda: self.handle_vote("right")
        )
        self.right_button.grid(row=1, column=0, padx=10, pady=10)

        # Skip button
        self.skip_button = ctk.CTkButton(
            self,
            text="Skip Pair",
            command=self.load_new_pair
        )
        self.skip_button.grid(row=1, column=0, columnspan=2, padx=10, pady=10)

        # Status label
        self.status_label = ctk.CTkLabel(self, text="")
        self.status_label.grid(row=2, column=0, columnspan=2, padx=10, pady=5)

    def load_new_pair(self):
        """Load a new pair of images for voting"""
        # Clear current images
        self.photo_references.clear()

        # Get new pair from database
        image_pair = self.get_pair_callback()
        if not image_pair or None in image_pair:
            self.show_error("Not enough images in database")
            self.disable_voting()
            self.images_loaded = False  # Reset loaded state if no images available
            return

        self.current_left, self.current_right = image_pair
        self.images_loaded = True  # Mark as loaded

        # Load and display left image
        left_photo = self.image_handler.load_image(self.current_left[1])
        if left_photo:
            self.photo_references.append(left_photo)
            self.left_image_label.configure(image=left_photo)

        # Load and display right image
        right_photo = self.image_handler.load_image(self.current_right[1])
        if right_photo:
            self.photo_references.append(right_photo)
            self.right_image_label.configure(image=right_photo)

        # Enable voting and clear status
        self.enable_voting()
        self.status_label.configure(text="")

    def ensure_images_loaded(self):
        """Load images if they haven't been loaded yet"""
        if not self.images_loaded:
            self.load_new_pair()

    def handle_vote(self, vote: str):
        """
        Handle voting for an image.

        Args:
            vote: Either "left" or "right"
        """
        # Check cooldown
        current_time = time.time()
        if current_time - self.last_vote_time < self.vote_cooldown:
            return

        self.last_vote_time = current_time

        # Determine winner and loser
        if vote == "left":
            winner = self.current_left
            loser = self.current_right
        else:
            winner = self.current_right
            loser = self.current_left

        # Calculate new ratings
        rating = Rating(
            winner[2],  # winner's current rating
            loser[2],  # loser's current rating
            Rating.WIN,
            Rating.LOST
        )
        new_ratings = rating.get_new_ratings()

        # Update database
        self.update_ratings_callback(
            winner[0],  # winner_id
            loser[0],  # loser_id
            new_ratings['a'],  # new winner rating
            new_ratings['b']  # new loser rating
        )

        # Load new pair
        self.load_new_pair()

    def enable_voting(self):
        """Enable voting buttons"""
        self.left_button.configure(state="normal")
        self.right_button.configure(state="normal")
        self.skip_button.configure(state="normal")

    def disable_voting(self):
        """Disable voting buttons"""
        self.left_button.configure(state="disabled")
        self.right_button.configure(state="disabled")
        self.skip_button.configure(state="disabled")

    def show_error(self, message: str):
        """Show error message in status label"""
        self.status_label.configure(text=message)