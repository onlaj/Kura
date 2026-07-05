import logging
import multiprocessing
import os
from queue import Queue, Empty
from threading import Thread, Lock

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtGui import QImage, QImageReader

from core.media_utils import grab_video_frame

logger = logging.getLogger(__name__)

# Maximum edge length for grid thumbnails. Decoding straight to this size is
# much faster than decoding full resolution and scaling afterwards.
THUMBNAIL_MAX_SIZE = 640

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
GIF_EXTENSIONS = {'.gif'}
VIDEO_EXTENSIONS = {'.mp4', '.m4v', '.wmv', '.avi', '.mov', '.mkv', '.webm'}


class MediaLoadTask:
    def __init__(self, media_id, file_path, index):
        self.media_id = media_id
        self.file_path = file_path
        self.index = index


class MediaLoadResult:
    """Everything the main thread needs to build a grid widget without disk I/O."""

    def __init__(self, media_id, file_path, index, generation):
        self.media_id = media_id
        self.file_path = file_path
        self.index = index
        self.generation = generation
        self.media_type = 'unknown'  # 'image', 'gif', 'video' or 'unknown'
        self.thumbnail = None  # Pre-decoded, pre-scaled QImage (images and videos)
        self.aspect_ratio = 16 / 9
        self.file_size = None
        self.modified_time = None
        self.exists = False


def _classify(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    if ext in GIF_EXTENSIONS:
        return 'gif'
    if ext in VIDEO_EXTENSIONS:
        return 'video'
    return 'unknown'


class ThreadedMediaLoader(QObject):
    """
    Loads media thumbnails for a page of results entirely in background threads.

    Worker threads decode images (QImageReader with scaled decode) and grab
    video frames (OpenCV) off the main thread, then emit ready-to-use
    MediaLoadResult objects via queued signals. QImage is safe to create in
    worker threads (QPixmap is not); the main thread only converts the final
    QImage to a QPixmap and builds widgets.

    Each call to load_media_batch() starts a new generation and invalidates the
    previous one: stale workers stop emitting and exit on their own.
    """
    media_loaded = pyqtSignal(object)  # MediaLoadResult
    all_media_loaded = pyqtSignal(int)  # generation
    progress_updated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.generation = 0
        self._generation_lock = Lock()
        # Cap the decoder pool: more threads saturate the CPU and starve the
        # GUI thread of the GIL, which is exactly the freeze we want to avoid.
        # Four decoders keep a page loading fast while the UI stays fluid.
        self.thread_count = max(1, min(4, multiprocessing.cpu_count() - 1))

    def load_media_batch(self, media_list):
        """Start loading a batch of media files, cancelling any previous batch."""
        with self._generation_lock:
            self.generation += 1
            generation = self.generation

        total = len(media_list)
        if total == 0:
            self.all_media_loaded.emit(generation)
            return

        task_queue = Queue()
        for index, (media_id, file_path, _, _) in enumerate(media_list):
            task_queue.put(MediaLoadTask(media_id, file_path, index))

        counter = {'done': 0}
        counter_lock = Lock()

        for _ in range(min(self.thread_count, total)):
            thread = Thread(
                target=self._worker_thread,
                args=(task_queue, generation, total, counter, counter_lock),
                daemon=True
            )
            thread.start()

    def stop(self):
        """Cancel the current batch; in-flight workers stop emitting and exit."""
        with self._generation_lock:
            self.generation += 1

    def _worker_thread(self, task_queue, generation, total, counter, counter_lock):
        while generation == self.generation:
            try:
                task = task_queue.get_nowait()
            except Empty:
                return

            try:
                result = self._load_result(task, generation)
            except Exception as e:
                logger.error(f"Error loading media {task.file_path}: {e}")
                result = MediaLoadResult(task.media_id, task.file_path, task.index, generation)

            if generation == self.generation:
                self.media_loaded.emit(result)
                self.progress_updated.emit()

            with counter_lock:
                counter['done'] += 1
                finished = counter['done'] == total
            if finished and generation == self.generation:
                self.all_media_loaded.emit(generation)

    def _load_result(self, task, generation) -> MediaLoadResult:
        """Decode a single media file into a MediaLoadResult (runs in worker thread)."""
        result = MediaLoadResult(task.media_id, task.file_path, task.index, generation)
        result.media_type = _classify(task.file_path)

        try:
            stat = os.stat(task.file_path)
            result.file_size = stat.st_size
            result.modified_time = stat.st_mtime
            result.exists = True
        except OSError:
            return result

        if result.media_type == 'image':
            self._load_image_thumbnail(result)
        elif result.media_type == 'gif':
            self._load_gif_info(result)
        elif result.media_type == 'video':
            self._load_video_thumbnail(result)
        return result

    @staticmethod
    def _load_image_thumbnail(result: MediaLoadResult):
        reader = QImageReader(result.file_path)
        reader.setAutoTransform(True)  # Respect EXIF orientation
        size = reader.size()
        if size.isValid() and size.width() > 0 and size.height() > 0:
            if size.width() > THUMBNAIL_MAX_SIZE or size.height() > THUMBNAIL_MAX_SIZE:
                reader.setScaledSize(size.scaled(
                    THUMBNAIL_MAX_SIZE, THUMBNAIL_MAX_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio
                ))
        image = reader.read()
        if image.isNull():
            logger.warning(
                f"QImageReader failed for {result.file_path}: {reader.errorString()}"
            )
            image = ThreadedMediaLoader._load_image_via_pil(result.file_path)
        if not image.isNull():
            result.thumbnail = image
            # Compute from the decoded image: EXIF rotation may swap dimensions
            if image.height() > 0:
                result.aspect_ratio = image.width() / image.height()

    @staticmethod
    def _load_image_via_pil(file_path: str) -> QImage:
        """Fallback decode with Pillow for formats QImageReader cannot handle."""
        try:
            from PIL import Image
            from PIL.ImageQt import ImageQt
            with Image.open(file_path) as img:
                img.thumbnail((THUMBNAIL_MAX_SIZE, THUMBNAIL_MAX_SIZE))
                # .copy() detaches from the PIL buffer, which is freed on close
                return QImage(ImageQt(img.convert("RGBA"))).copy()
        except Exception as e:
            logger.error(f"PIL fallback failed for {file_path}: {e}")
            return QImage()

    @staticmethod
    def _load_gif_info(result: MediaLoadResult):
        # The animated QMovie must live on the main thread; only probe the
        # first frame here for the aspect ratio.
        reader = QImageReader(result.file_path)
        size = reader.size()
        if size.isValid() and size.width() > 0 and size.height() > 0:
            result.aspect_ratio = size.width() / size.height()
        else:
            image = reader.read()
            if not image.isNull():
                result.thumbnail = image
                if image.height() > 0:
                    result.aspect_ratio = image.width() / image.height()

    @staticmethod
    def _load_video_thumbnail(result: MediaLoadResult):
        image, aspect_ratio = grab_video_frame(result.file_path)
        result.aspect_ratio = aspect_ratio
        if not image.isNull():
            if image.width() > THUMBNAIL_MAX_SIZE or image.height() > THUMBNAIL_MAX_SIZE:
                image = image.scaled(
                    THUMBNAIL_MAX_SIZE, THUMBNAIL_MAX_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            result.thumbnail = image
