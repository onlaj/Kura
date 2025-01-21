import os
from queue import Queue
from threading import Thread, Lock
import multiprocessing

from PyQt6.QtCore import QObject, pyqtSignal

import logging

logger = logging.getLogger(__name__)

class MediaLoadTask:
    def __init__(self, media_id, file_path, index):
        self.media_id = media_id
        self.file_path = file_path
        self.index = index

class ThreadedMediaLoader(QObject):
    media_loaded = pyqtSignal(int, str, int)  # media_id, file_path, index
    all_media_loaded = pyqtSignal()
    progress_updated = pyqtSignal()  # Add new signal for progress updates

    def __init__(self, media_handler):
        super().__init__()
        self.media_handler = media_handler
        self.task_queue = Queue()
        self.result_lock = Lock()
        self.active = False
        self.thread_count = multiprocessing.cpu_count()
        self.threads = []

    def load_media_batch(self, media_list):
        """Start loading a batch of media files."""
        self.active = True
        self.threads.clear()
        
        # Clear existing queue
        while not self.task_queue.empty():
            self.task_queue.get()

        # Add all tasks to queue
        for index, (media_id, file_path, _, _) in enumerate(media_list):
            self.task_queue.put(MediaLoadTask(media_id, file_path, index))

        # Start worker threads
        for _ in range(self.thread_count):
            thread = Thread(target=self._worker_thread, daemon=True)
            self.threads.append(thread)
            thread.start()

        # Start monitor thread
        monitor_thread = Thread(target=self._monitor_completion, daemon=True)
        monitor_thread.start()

    def stop(self):
        """Stop all loading operations."""
        self.active = False
        # Clear queue
        while not self.task_queue.empty():
            self.task_queue.get()

    def _worker_thread(self):
        """Worker thread function."""
        while self.active:
            try:
                # Get task with timeout to allow checking active flag
                task = self.task_queue.get(timeout=0.5)
            except:
                continue

            try:
                # Instead of loading the widget here, just emit the path
                # The actual widget creation will happen in the main thread
                self.media_loaded.emit(task.media_id, task.file_path, task.index)
                self.progress_updated.emit()  # Emit progress signal
            except Exception as e:
                logger.error(f"Error loading media {task.file_path}: {e}")

            self.task_queue.task_done()

    def _monitor_completion(self):
        """Monitor thread to check when all tasks are complete."""
        self.task_queue.join()  # Wait for all tasks to complete
        if self.active:
            self.all_media_loaded.emit()  # Emit signal when all media is actually loaded
