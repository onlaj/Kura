# gui/main_window.py

import customtkinter as ctk


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Configure window
        self.title("Image ELO Ranker")
        self.geometry("1024x768")

        # Configure grid layout (1x1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Create tabview with command
        self.tabview = ctk.CTkTabview(self, command=self._on_tab_change)
        self.tabview.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")

        # Create tabs
        self.tab_voting = self.tabview.add("Voting")
        self.tab_upload = self.tabview.add("Upload")
        self.tab_ranking = self.tabview.add("Ranking")

        # Store tab change callback
        self.tab_change_callback = None

        # Configure grid layout for each tab
        for tab in [self.tab_voting, self.tab_upload, self.tab_ranking]:
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)

    def set_tab_change_callback(self, callback):
        """Set callback for tab changes"""
        self.tab_change_callback = callback

    def _on_tab_change(self):
        """Handle tab changes"""
        if self.tab_change_callback:
            current_tab = self.tabview.get()
            self.tab_change_callback(current_tab)

    def start(self):
        """Start the application main loop"""
        self.mainloop()