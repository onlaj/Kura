"""Pure helpers for picking a mid-content video thumbnail timestamp."""

# Never seek to the opening frame: many videos start with a fade. Cap how far
# into a long file we go so a 20-minute clip is not decoded to the midpoint.
VIDEO_THUMB_SEEK_CAP_MS = 8000


def video_thumb_seek_ms(duration_ms: float) -> float:
    """Timestamp for a mid-content thumbnail. Never 0 when duration is known."""
    if duration_ms <= 0:
        return float(VIDEO_THUMB_SEEK_CAP_MS)
    halfway = duration_ms / 2.0
    target = min(halfway, float(VIDEO_THUMB_SEEK_CAP_MS))
    return target if target > 0 else halfway
