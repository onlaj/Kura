import logging
import multiprocessing
import os
from collections import OrderedDict
from queue import Queue, Empty
from threading import Thread, Lock

from PyQt6.QtCore import QObject, pyqtSignal, Qt, QBuffer, QIODevice
from PyQt6.QtGui import QImage, QImageReader

from core.media_utils import grab_video_frame
from core.png_sanitize import png_bytes_for_decode

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
        self.thumbnail = None  # Pre-decoded, pre-scaled QImage (images, gifs, videos)
        self.aspect_ratio = 16 / 9
        self.file_size = None
        self.modified_time = None
        self.exists = False


class PreviewLoadResult:
    """Decoded preview payload built off the UI thread."""

    def __init__(self, request_id, file_path):
        self.request_id = request_id
        self.file_path = file_path
        self.media_type = 'unknown'
        self.image = None
        self.aspect_ratio = 16 / 9
        self.exists = False


def classify_media(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    if ext in GIF_EXTENSIONS:
        return 'gif'
    if ext in VIDEO_EXTENSIONS:
        return 'video'
    return 'unknown'


def preview_max_edge(widget=None) -> int:
    """Longest screen/window edge, used as the preview decode cap."""
    from PyQt6.QtWidgets import QApplication
    if widget is not None:
        window = widget.window()
        if window is not None and window.width() > 0 and window.height() > 0:
            return max(window.width(), window.height())
    screen = QApplication.primaryScreen()
    if screen is not None:
        geo = screen.availableGeometry()
        return max(geo.width(), geo.height())
    return 1920


def _classify(file_path: str) -> str:
    return classify_media(file_path)


def _image_nbytes(image: QImage) -> int:
    if image is None or image.isNull():
        return 0
    nbytes = image.sizeInBytes()
    if nbytes > 0:
        return nbytes
    return max(0, image.width() * image.height() * 4)


class _ThumbnailCache:
    """Process-local LRU of scaled QImages keyed by path + mtime + size."""

    def __init__(self, max_items=256, max_bytes=128 * 1024 * 1024):
        self.max_items = max_items
        self.max_bytes = max_bytes
        self._lock = Lock()
        self._entries = OrderedDict()
        self._bytes = 0

    @staticmethod
    def make_key(path, mtime, size):
        return (path, round(float(mtime), 3), int(size))

    def get(self, key):
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return entry

    def put(self, key, entry, nbytes):
        with self._lock:
            if key in self._entries:
                old = self._entries.pop(key)
                self._bytes -= old.get('nbytes', 0)
            self._entries[key] = {**entry, 'nbytes': nbytes}
            self._bytes += nbytes
            while self._entries and (
                len(self._entries) > self.max_items or self._bytes > self.max_bytes
            ):
                _, evicted = self._entries.popitem(last=False)
                self._bytes -= evicted.get('nbytes', 0)


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

    Decoded thumbs are kept in an in-memory LRU so paging back or a vote
    refresh does not re-decode files that have not changed on disk.
    """
    media_loaded = pyqtSignal(object)  # MediaLoadResult
    all_media_loaded = pyqtSignal(int)  # generation
    progress_updated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.generation = 0
        self._generation_lock = Lock()
        self._cache = _ThumbnailCache()
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
        result.media_type = classify_media(task.file_path)

        try:
            stat = os.stat(task.file_path)
            result.file_size = stat.st_size
            result.modified_time = stat.st_mtime
            result.exists = True
        except OSError:
            return result

        cache_key = _ThumbnailCache.make_key(
            task.file_path, result.modified_time, result.file_size
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            result.media_type = cached['media_type']
            result.thumbnail = cached['thumbnail']
            result.aspect_ratio = cached['aspect_ratio']
            return result

        if result.media_type == 'image':
            self._load_image_thumbnail(result)
        elif result.media_type == 'gif':
            self._load_gif_thumbnail(result)
        elif result.media_type == 'video':
            self._load_video_thumbnail(result)

        if result.thumbnail is not None and not result.thumbnail.isNull():
            self._cache.put(
                cache_key,
                {
                    'media_type': result.media_type,
                    'thumbnail': result.thumbnail,
                    'aspect_ratio': result.aspect_ratio,
                },
                _image_nbytes(result.thumbnail),
            )
        return result

    @staticmethod
    def _image_reader_for(file_path: str):
        """Return (reader, keepalive). keepalive must be held until read() finishes."""
        if os.path.splitext(file_path)[1].lower() == '.png':
            sanitized = png_bytes_for_decode(file_path)
            if sanitized is not None:
                buffer = QBuffer()
                buffer.setData(sanitized)
                buffer.open(QIODevice.OpenModeFlag.ReadOnly)
                reader = QImageReader(buffer)
                reader.setFormat(b'PNG')
                reader.setAutoTransform(True)
                return reader, buffer
        reader = QImageReader(file_path)
        reader.setAutoTransform(True)
        return reader, None

    @staticmethod
    def decode_scaled_image(file_path: str, max_size: int) -> QImage:
        """Decode an image scaled so the longest edge is at most max_size."""
        reader, _keepalive = ThreadedMediaLoader._image_reader_for(file_path)
        size = reader.size()
        if size.isValid() and size.width() > 0 and size.height() > 0:
            if size.width() > max_size or size.height() > max_size:
                reader.setScaledSize(size.scaled(
                    max_size, max_size,
                    Qt.AspectRatioMode.KeepAspectRatio
                ))
        image = reader.read()
        if image.isNull():
            logger.warning(
                f"QImageReader failed for {file_path}: {reader.errorString()}"
            )
            image = ThreadedMediaLoader._load_image_via_pil(file_path, max_size)
        return image

    @staticmethod
    def _load_image_thumbnail(result: MediaLoadResult):
        image = ThreadedMediaLoader.decode_scaled_image(
            result.file_path, THUMBNAIL_MAX_SIZE
        )
        if not image.isNull():
            result.thumbnail = image
            # Compute from the decoded image: EXIF rotation may swap dimensions
            if image.height() > 0:
                result.aspect_ratio = image.width() / image.height()

    @staticmethod
    def _load_image_via_pil(file_path: str, max_size: int = THUMBNAIL_MAX_SIZE) -> QImage:
        """Fallback decode with Pillow for formats QImageReader cannot handle."""
        try:
            from PIL import Image
            from PIL.ImageQt import ImageQt
            with Image.open(file_path) as img:
                img.thumbnail((max_size, max_size))
                # .copy() detaches from the PIL buffer, which is freed on close
                return QImage(ImageQt(img.convert("RGBA"))).copy()
        except Exception as e:
            logger.error(f"PIL fallback failed for {file_path}: {e}")
            return QImage()

    @staticmethod
    def _load_gif_thumbnail(result: MediaLoadResult):
        # QImageReader reads the first frame. The animated QMovie still has to
        # live on the main thread, so the grid only needs this still.
        reader = QImageReader(result.file_path)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and size.width() > 0 and size.height() > 0:
            if size.width() > THUMBNAIL_MAX_SIZE or size.height() > THUMBNAIL_MAX_SIZE:
                reader.setScaledSize(size.scaled(
                    THUMBNAIL_MAX_SIZE, THUMBNAIL_MAX_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio
                ))
        image = reader.read()
        if not image.isNull():
            result.thumbnail = image
            if image.height() > 0:
                result.aspect_ratio = image.width() / image.height()
        elif size.isValid() and size.height() > 0:
            result.aspect_ratio = size.width() / size.height()

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


class PreviewLoader(QObject):
    """
    Decode a single preview image (or video thumb) off the UI thread.

    GIFs are classified only: QMovie must be created on the main thread.
    Videos reuse a provided thumbnail when the caller already has one.
    """
    preview_ready = pyqtSignal(object)  # PreviewLoadResult

    def __init__(self):
        super().__init__()
        self._lock = Lock()
        self._current_id = 0

    def load(self, file_path, max_size, thumbnail=None):
        """Start a preview decode. Returns the request id to match against the signal."""
        with self._lock:
            self._current_id += 1
            request_id = self._current_id
        thread = Thread(
            target=self._worker,
            args=(file_path, max_size, thumbnail, request_id),
            daemon=True,
        )
        thread.start()
        return request_id

    def cancel(self):
        """Invalidate in-flight preview work so its result is dropped."""
        with self._lock:
            self._current_id += 1

    def _worker(self, file_path, max_size, thumbnail, request_id):
        if request_id != self._current_id:
            return
        result = PreviewLoadResult(request_id, file_path)
        result.media_type = classify_media(file_path)
        try:
            os.stat(file_path)
            result.exists = True
        except OSError:
            if request_id == self._current_id:
                self.preview_ready.emit(result)
            return

        if result.media_type == 'image':
            image = ThreadedMediaLoader.decode_scaled_image(file_path, max_size)
            if not image.isNull():
                result.image = image
                if image.height() > 0:
                    result.aspect_ratio = image.width() / image.height()
        elif result.media_type == 'video':
            if thumbnail is not None and not thumbnail.isNull():
                result.image = thumbnail
                if thumbnail.height() > 0:
                    result.aspect_ratio = thumbnail.width() / thumbnail.height()
            else:
                image, aspect_ratio = grab_video_frame(file_path)
                result.image = image
                result.aspect_ratio = aspect_ratio
        # gif: QMovie is created on the main thread

        if request_id == self._current_id:
            self.preview_ready.emit(result)
