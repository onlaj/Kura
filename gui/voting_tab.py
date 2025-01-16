# gui/voting_tab.py

import customtkinter as ctk
from PIL import Image, ImageTk
import time
from core.elo import Rating
from typing import Optional, Tuple


class VotingTab(ctk.CTkFrame):
    def __init__(self, parent, get_pair_callback, update_ratings_callback, image_handler):
        super().__init__(parent)
        self.parent = parent
        self.get_pair_callback = get_pair_callback
        self.update_ratings_callback = update_ratings_callback
        self.image_handler = image_handler

        self.current_left = None
        self.current_right = None
        self.photo_references = []
        self.images_loaded = False

        self.last_vote_time = 0
        self.vote_cooldown = 1.0  # seconds

        # Configure grid weights for proper scaling
        self.grid_columnconfigure((0, 1), weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.preview_mode = False
        self.preview_label = None

        self.setup_ui()

        # Bind resize event
        self.bind("<Configure>", self.on_resize)

        self.bind("<Map>", self.on_map_event)

    def on_map_event(self, event=None):
        """
        This method is called when the widget is actually displayed on the screen.
        We use this to ensure the UI is fully rendered before loading images.
        """
        # Unbind the event to prevent multiple calls
        self.unbind("<Map>")

        # Force the UI to process all pending events
        self.update_idletasks()

        # Now load the images
        self.load_new_pair()


    def setup_ui(self):
        # Create containers for images with proper scaling
        self.left_frame = ctk.CTkFrame(self)
        self.left_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.left_frame.grid_rowconfigure(0, weight=1)
        self.left_frame.grid_columnconfigure(0, weight=1)

        self.right_frame = ctk.CTkFrame(self)
        self.right_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.right_frame.grid_rowconfigure(0, weight=1)
        self.right_frame.grid_columnconfigure(0, weight=1)

        # Image labels with proper scaling
        self.left_image_label = ctk.CTkLabel(self.left_frame, text="")
        self.left_image_label.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.left_image_label.bind("<Button-1>", lambda e: self.show_preview(self.current_left[1]))

        self.right_image_label = ctk.CTkLabel(self.right_frame, text="")
        self.right_image_label.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.right_image_label.bind("<Button-1>", lambda e: self.show_preview(self.current_right[1]))

        # Voting buttons
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

        self.skip_button = ctk.CTkButton(
            self,
            text="Skip Pair",
            command=self.load_new_pair
        )
        self.skip_button.grid(row=1, column=0, columnspan=2, padx=10, pady=10)

        self.status_label = ctk.CTkLabel(self, text="")
        self.status_label.grid(row=2, column=0, columnspan=2, padx=10, pady=5)

    def show_preview(self, image_path: str):
        """Show a full-size preview of the image, handling animations."""
        if self.preview_mode:
            return

        self.preview_mode = True

        # Create preview frame
        self.preview_frame = ctk.CTkFrame(self, fg_color="black")
        self.preview_frame.grid(row=0, column=0, rowspan=3, columnspan=2, sticky="nsew")
        self.preview_frame.grid_columnconfigure(0, weight=1)
        self.preview_frame.grid_rowconfigure(0, weight=1)

        # Load and display the preview image
        result = self.image_handler.load_image(image_path)
        self.preview_label = ctk.CTkLabel(self.preview_frame, text="")
        self.preview_label.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        if isinstance(result, tuple):  # Animated image
            frames, frame_count, durations = result
            self.photo_references.extend(frames)
            self.preview_label.configure(image=frames[0])
            self.image_handler.start_animation(self.preview_label, frames, durations)
        else:  # Static image
            self.photo_references.append(result)
            self.preview_label.configure(image=result)

        # Add click event to exit preview
        self.preview_label.bind("<Button-1>", self.exit_preview)

    def exit_preview(self, event=None):
        """Exit preview mode and stop any animations."""
        if not self.preview_mode:
            return

        if self.preview_label:
            self.image_handler.stop_animation(self.preview_label)

        self.preview_mode = False
        if self.preview_frame:
            self.preview_frame.destroy()
            self.preview_frame = None

    def on_resize(self, event):
        """Handle window resize events"""
        if not hasattr(self, 'last_resize_time'):
            self.last_resize_time = 0

        current_time = time.time()

        # Throttle resize events (process only every 0.1 seconds)
        if current_time - self.last_resize_time > 0.1:
            self.last_resize_time = current_time

            # Calculate available space for each image
            # Account for padding and middle gap
            available_width = (event.width - 60) // 2  # 60 pixels for padding and gap
            available_height = event.height - 100  # 100 pixels for buttons and padding

            # Update image handler with new size
            self.image_handler.set_display_size(available_width, available_height)

            # Reload current images if they exist
            if self.current_left and self.current_right:
                self.reload_current_images()

    def reload_current_images(self):
        """Reload and resize current images, handling animations with proper cleanup"""
        # Stop any existing animations and clear labels
        if hasattr(self, 'left_image_label'):
            self.image_handler.stop_animation(self.left_image_label)
            self.left_image_label.configure(image=None)

        if hasattr(self, 'right_image_label'):
            self.image_handler.stop_animation(self.right_image_label)
            self.right_image_label.configure(image=None)

        # Clear all photo references
        self.photo_references.clear()

        # Load left image
        if self.current_left:
            result = self.image_handler.load_image(self.current_left[1])
            if isinstance(result, tuple):  # Animated image
                frames, frame_count, durations = result
                self.photo_references.extend(frames)
                if frames:  # Check if we have any frames
                    self.left_image_label.configure(image=frames[0])
                    self.image_handler.start_animation(self.left_image_label, frames, durations)
            elif result:  # Static image
                self.photo_references.append(result)
                self.left_image_label.configure(image=result)

        # Load right image
        if self.current_right:
            result = self.image_handler.load_image(self.current_right[1])
            if isinstance(result, tuple):  # Animated image
                frames, frame_count, durations = result
                self.photo_references.extend(frames)
                if frames:  # Check if we have any frames
                    self.right_image_label.configure(image=frames[0])
                    self.image_handler.start_animation(self.right_image_label, frames, durations)
            elif result:  # Static image
                self.photo_references.append(result)
                self.right_image_label.configure(image=result)

    def load_new_pair(self):
        """Load a new pair of images for voting with proper cleanup"""
        # Stop any existing animations
        if hasattr(self, 'left_image_label'):
            self.image_handler.stop_animation(self.left_image_label)
            self.left_image_label.configure(image=None)  # Clear the image

        if hasattr(self, 'right_image_label'):
            self.image_handler.stop_animation(self.right_image_label)
            self.right_image_label.configure(image=None)  # Clear the image

        # Clear all photo references
        self.photo_references.clear()

        # Get new pair from database
        image_pair = self.get_pair_callback()
        if not image_pair or None in image_pair:
            self.show_error("Not enough images in database")
            self.disable_voting()
            self.images_loaded = False
            return

        # Store new pair
        self.current_left, self.current_right = image_pair
        self.images_loaded = True

        # Load and display new images
        self.reload_current_images()

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

        # Stop any existing animations
        if hasattr(self, 'left_image_label'):
            self.image_handler.stop_animation(self.left_image_label)
            self.left_image_label.configure(image=None)  # Clear the image

        if hasattr(self, 'right_image_label'):
            self.image_handler.stop_animation(self.right_image_label)
            self.right_image_label.configure(image=None)  # Clear the image

        # Clear all photo references
        self.photo_references.clear()

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