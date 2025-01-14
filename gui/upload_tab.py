# gui/upload_tab.py

import os
import customtkinter as ctk
from tkinter import filedialog
from pathlib import Path
from typing import Callable


class UploadTab(ctk.CTkFrame):
    def __init__(self, parent, db_callback: Callable):
        """
        Initialize the upload tab.

        Args:
            parent: Parent widget
            db_callback: Callback function to add images to database
        """
        super().__init__(parent)
        self.db_callback = db_callback

        # Configure grid layout
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Create widgets
        self.setup_ui()

    def setup_ui(self):
        """Setup all UI elements"""
        # Create buttons frame
        self.button_frame = ctk.CTkFrame(self)
        self.button_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")

        # Add file button
        self.btn_add_files = ctk.CTkButton(
            self.button_frame,
            text="Add Files",
            command=self.add_files
        )
        self.btn_add_files.grid(row=0, column=0, padx=10, pady=10)

        # Add folder button
        self.btn_add_folder = ctk.CTkButton(
            self.button_frame,
            text="Add Folder",
            command=self.add_folder
        )
        self.btn_add_folder.grid(row=0, column=1, padx=10, pady=10)

        # Create textbox for logging
        self.log_text = ctk.CTkTextbox(self)
        self.log_text.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")

    def add_files(self):
        """Handle adding individual files"""
        filetypes = (
            ('Image files', '*.jpg *.jpeg *.png *.gif *.bmp'),
            ('All files', '*.*')
        )

        filenames = filedialog.askopenfilenames(
            title='Select images',
            filetypes=filetypes
        )

        self.process_files(filenames)

    def add_folder(self):
        """Handle adding a folder of images"""
        folder = filedialog.askdirectory(
            title='Select folder containing images'
        )

        if folder:
            image_files = []
            for ext in ('*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp'):
                image_files.extend(Path(folder).glob(f"**/{ext}"))

            self.process_files(image_files)

    def process_files(self, files):
        """
        Process the selected files and add them to the database.

        Args:
            files: List of file paths to process
        """
        added = 0
        skipped = 0

        for file in files:
            file_path = str(file)
            if self.db_callback(file_path):
                added += 1
                self.log_text.insert('end', f"Added: {file_path}\n")
            else:
                skipped += 1
                self.log_text.insert('end', f"Skipped (already exists): {file_path}\n")

        self.log_text.insert('end', f"\nSummary: Added {added} files, Skipped {skipped} files\n")
        self.log_text.see('end')