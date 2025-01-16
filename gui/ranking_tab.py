# gui/ranking_tab.py

import customtkinter as ctk
from PIL import Image
import os
from typing import List, Tuple
import math


class RankingTab(ctk.CTkFrame):
    def __init__(self, parent, get_rankings_callback, image_handler, delete_callback):
        super().__init__(parent)
        self.get_rankings_callback = get_rankings_callback
        self.image_handler = image_handler
        self.delete_callback = delete_callback
        self.thumbnail_height = 200  # Fixed thumbnail height
        self.photo_references = []
        self.current_page = 1
        self.per_page = 12
        self.total_images = 0
        self.columns = 3
        self.current_images = []  # Store current page's images
        self.preview_mode = False

        # Configure grid layout
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Bind keyboard events
        self.bind("<Left>", lambda e: self.navigate_preview("prev"))
        self.bind("<Right>", lambda e: self.navigate_preview("next"))

        # Create widgets
        self.setup_ui()

    def setup_ui(self):
        """Setup all UI elements"""
        # Create top control frame
        self.control_frame = ctk.CTkFrame(self)
        self.control_frame.grid(row=0, column=0, padx=20, pady=10, sticky="ew")
        self.control_frame.grid_columnconfigure(2, weight=1)

        # Refresh button
        self.btn_refresh = ctk.CTkButton(
            self.control_frame,
            text="Refresh Rankings",
            command=self.refresh_rankings
        )
        self.btn_refresh.grid(row=0, column=0, padx=10, pady=10)

        # Column selector
        self.column_label = ctk.CTkLabel(self.control_frame, text="Columns:")
        self.column_label.grid(row=0, column=1, padx=(20, 5), pady=10)

        self.column_selector = ctk.CTkOptionMenu(
            self.control_frame,
            values=["2", "3", "4", "5"],
            command=self.change_columns,
            width=70
        )
        self.column_selector.set(str(self.columns))
        self.column_selector.grid(row=0, column=2, padx=5, pady=10)

        # Page info label
        self.page_label = ctk.CTkLabel(
            self.control_frame,
            text="Page 1"
        )
        self.page_label.grid(row=0, column=3, padx=10, pady=10)

        # Navigation buttons
        self.btn_prev = ctk.CTkButton(
            self.control_frame,
            text="Previous",
            command=self.prev_page,
            state="disabled"
        )
        self.btn_prev.grid(row=0, column=4, padx=5, pady=10)

        self.btn_next = ctk.CTkButton(
            self.control_frame,
            text="Next",
            command=self.next_page,
            state="disabled"
        )
        self.btn_next.grid(row=0, column=5, padx=5, pady=10)

        # Create scrollable frame for rankings
        self.scrollable_frame = ctk.CTkScrollableFrame(self)
        self.scrollable_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")

        # Initial refresh
        self.refresh_rankings()

    def show_preview(self, image_index: int):
        """Show a full-size preview of the image with navigation arrows."""
        if self.preview_mode:
            # Stop any existing preview animation
            if hasattr(self, 'preview_label'):
                self.image_handler.stop_animation(self.preview_label)
            return

        self.preview_mode = True
        self.current_preview_index = image_index

        # Create preview overlay
        self.preview_frame = ctk.CTkFrame(self, fg_color="black")
        self.preview_frame.grid(row=0, column=0, rowspan=3, columnspan=2, sticky="nsew")
        self.preview_frame.grid_columnconfigure(1, weight=1)
        self.preview_frame.grid_rowconfigure(0, weight=1)

        # Left arrow button
        self.btn_prev_image = ctk.CTkButton(
            self.preview_frame,
            text="←",
            command=lambda: self.navigate_preview("prev"),
            width=40,
            state="normal" if self.can_navigate_prev() else "disabled"
        )
        self.btn_prev_image.grid(row=0, column=0, padx=10, pady=10)

        # Preview image
        self.preview_label = ctk.CTkLabel(self.preview_frame, text="")
        self.preview_label.grid(row=0, column=1, padx=10, pady=10)

        # Load and display preview
        result = self.image_handler.load_image(self.current_images[image_index][1])
        if isinstance(result, tuple):  # Animated image
            frames, frame_count, durations = result
            self.photo_references.extend(frames)
            self.preview_label.configure(image=frames[0])
            self.image_handler.start_animation(self.preview_label, frames, durations)
        else:  # Static image
            self.photo_references.append(result)
            self.preview_label.configure(image=result)

        # Right arrow button
        self.btn_next_image = ctk.CTkButton(
            self.preview_frame,
            text="→",
            command=lambda: self.navigate_preview("next"),
            width=40,
            state="normal" if self.can_navigate_next() else "disabled"
        )
        self.btn_next_image.grid(row=0, column=2, padx=10, pady=10)

        # Click anywhere to exit
        self.preview_label.bind("<Button-1>", self.exit_preview)

    def navigate_preview(self, direction: str):
        """Navigate through images in preview mode."""
        if not self.preview_mode:
            return

        new_index = self.current_preview_index
        if direction == "next" and self.can_navigate_next():
            new_index += 1
            if new_index >= len(self.current_images):
                self.next_page()
                new_index = 0
        elif direction == "prev" and self.can_navigate_prev():
            new_index -= 1
            if new_index < 0:
                self.prev_page()
                new_index = len(self.current_images) - 1

        if new_index != self.current_preview_index:
            self.exit_preview()
            self.show_preview(new_index)

    def can_navigate_next(self):
        """Check if can navigate to next image."""
        return (self.current_preview_index < len(self.current_images) - 1 or
                self.current_page * self.per_page < self.total_images)

    def can_navigate_prev(self):
        """Check if can navigate to previous image."""
        return self.current_preview_index > 0 or self.current_page > 1

    def exit_preview(self, event=None):
        """Exit preview mode and clean up animations."""
        if not self.preview_mode:
            return

        # Stop preview animation
        if hasattr(self, 'preview_label'):
            self.image_handler.stop_animation(self.preview_label)

        self.preview_mode = False
        if self.preview_frame:
            self.preview_frame.destroy()
            self.preview_frame = None

    def create_image_frame(self, parent: ctk.CTkFrame, rank: int,
                           id: int, path: str, rating: float, votes: int,
                           index: int) -> ctk.CTkFrame:
        """Create a frame for displaying an image with its info"""
        frame = ctk.CTkFrame(parent)
        frame.grid_columnconfigure(0, weight=1)

        # Image container
        image_frame = ctk.CTkFrame(frame)
        image_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        # Calculate thumbnail dimensions
        image = Image.open(path)
        aspect_ratio = image.width / image.height
        scaled_width = int(self.thumbnail_height * aspect_ratio)

        # Create and store the image label
        image_label = ctk.CTkLabel(image_frame, text="")
        image_label.grid(row=0, column=0, padx=5, pady=5)

        # Load and display thumbnail
        result = self.image_handler.load_image(
            path,
            thumbnail_size=(scaled_width, self.thumbnail_height)
        )

        if isinstance(result, tuple):  # Animated image
            frames, frame_count, durations = result
            self.photo_references.extend(frames)
            image_label.configure(image=frames[0])
            self.image_handler.start_animation(image_label, frames, durations)
        elif result:  # Static image
            self.photo_references.append(result)
            image_label.configure(image=result)

        image_label.bind("<Button-1>", lambda e: self.show_preview(index))

        # Store reference to label and animation status
        frame.image_label = image_label  # Store reference for cleanup

        # Info frame
        info_frame = ctk.CTkFrame(frame)
        info_frame.grid(row=1, column=0, padx=5, pady=5, sticky="ew")

        # Rank number and filename
        ctk.CTkLabel(info_frame, text=f"#{rank} - {os.path.basename(path)}").grid(
            row=0, column=0, padx=5, pady=2, sticky="w"
        )

        # Rating and votes
        ctk.CTkLabel(info_frame, text=f"Rating: {rating:.1f} | Votes: {votes}").grid(
            row=1, column=0, padx=5, pady=2, sticky="w"
        )

        # Delete button
        delete_button = ctk.CTkButton(
            info_frame,
            text="Delete",
            command=lambda: self.confirm_delete(id, path),
            fg_color="red",
            hover_color="darkred",
            width=80
        )
        delete_button.grid(row=2, column=0, padx=5, pady=5)

        return frame

    def change_columns(self, value):
        """Handle column count change"""
        self.columns = int(value)
        self.refresh_rankings()

    def refresh_rankings(self):
        """Refresh the rankings display with animation cleanup"""
        # Stop all current animations
        for widget in self.scrollable_frame.winfo_children():
            if hasattr(widget, 'image_label'):
                self.image_handler.stop_animation(widget.image_label)

        # Clear current rankings and photo references
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.photo_references.clear()
        self.current_images = []

        # Reconfigure grid columns
        for i in range(self.columns):
            self.scrollable_frame.grid_columnconfigure(i, weight=1)

        # Get current page of rankings
        rankings, self.total_images = self.get_rankings_callback(self.current_page, self.per_page)
        self.current_images = rankings
        total_pages = math.ceil(self.total_images / self.per_page)

        # Update page info
        self.page_label.configure(
            text=f"Page {self.current_page} of {total_pages} (Total: {self.total_images})"
        )

        # Update navigation buttons
        self.btn_prev.configure(state="normal" if self.current_page > 1 else "disabled")
        self.btn_next.configure(state="normal" if self.current_page < total_pages else "disabled")

        # Calculate starting rank for current page
        start_rank = (self.current_page - 1) * self.per_page + 1

        # Display rankings in grid
        for i, (id, path, rating, votes) in enumerate(rankings):
            frame = self.create_image_frame(
                self.scrollable_frame,
                start_rank + i,
                id,
                path,
                rating,
                votes,
                i  # Pass index for preview navigation
            )
            row = i // self.columns
            col = i % self.columns
            frame.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

    def confirm_delete(self, image_id: int, image_path: str):
        """Show delete confirmation dialog"""
        dialog = ctk.CTkInputDialog(
            text=f"Type 'DELETE' to confirm removing:\n{os.path.basename(image_path)}",
            title="Confirm Delete"
        )
        result = dialog.get_input()

        if result == "DELETE":
            try:
                self.delete_callback(image_id)
                self.refresh_rankings()
            except Exception as e:
                self.show_error(f"Error deleting image: {str(e)}")

    def show_error(self, message: str):
        """Show error dialog"""
        dialog = ctk.CTkInputDialog(
            text=message,
            title="Error"
        )
        dialog.get_input()

    def next_page(self):
        """Go to next page"""
        total_pages = math.ceil(self.total_images / self.per_page)
        if self.current_page < total_pages:
            self.current_page += 1
            self.refresh_rankings()

    def prev_page(self):
        """Go to previous page"""
        if self.current_page > 1:
            self.current_page -= 1
            self.refresh_rankings()