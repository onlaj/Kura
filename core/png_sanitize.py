"""Rewrite PNG chunk order so Qt/libpng can decode files with bad metadata.

libpng requires IHDR as the first chunk. Files that put tEXt (or other ancillary
chunks) before IHDR fail with "tEXt: missing IHDR" and can abort the process.
This module strips text/time/exif chunks and rebuilds a spec-legal layout
without re-encoding pixels.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Empty IEND with valid CRC (AE 42 60 82).
IEND_CHUNK = bytes.fromhex("0000000049454e44ae426082")
# PNG max chunk payload is 2^31 - 1.
_MAX_CHUNK_LENGTH = 0x7FFFFFFF
_MIN_CHUNK_SIZE = 12  # length + type + crc

# Dropped even when they appear after IHDR: malformed payloads still trip libpng.
_DROP_TYPES = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"}


def _signature_offset(data: bytes) -> int:
    if data.startswith(PNG_SIGNATURE):
        return 0
    return data.find(PNG_SIGNATURE)


def _is_chunk_type(ctype: bytes) -> bool:
    return len(ctype) == 4 and all(65 <= b <= 90 or 97 <= b <= 122 for b in ctype)


def parse_png_chunks(data: bytes, offset: int = 0) -> list[tuple[bytes, bytes]]:
    """Parse PNG chunks starting at offset. Stop on truncated or invalid data."""
    chunks: list[tuple[bytes, bytes]] = []
    n = len(data)
    pos = offset
    while pos + _MIN_CHUNK_SIZE <= n:
        length = int.from_bytes(data[pos : pos + 4], "big")
        if length > _MAX_CHUNK_LENGTH:
            break
        ctype = data[pos + 4 : pos + 8]
        if not _is_chunk_type(ctype):
            break
        end = pos + _MIN_CHUNK_SIZE + length
        if end > n:
            break
        chunks.append((ctype, data[pos:end]))
        pos = end
        if ctype == b"IEND":
            break
    return chunks


def rebuild_png(chunks: list[tuple[bytes, bytes]]) -> bytes | None:
    """Build signature + IHDR + other kept chunks + IDATs + IEND.

    Returns None if there is no IHDR or no IDAT (not a usable image).
    """
    ihdr: bytes | None = None
    idats: list[bytes] = []
    others: list[bytes] = []
    iend: bytes | None = None

    for ctype, raw in chunks:
        if ctype == b"IHDR":
            if ihdr is None:
                ihdr = raw
        elif ctype == b"IDAT":
            idats.append(raw)
        elif ctype == b"IEND":
            iend = raw
        elif ctype in _DROP_TYPES:
            continue
        else:
            others.append(raw)

    if ihdr is None or not idats:
        return None

    return b"".join([PNG_SIGNATURE, ihdr, *others, *idats, iend or IEND_CHUNK])


def sanitize_png(data: bytes) -> bytes:
    """Return PNG bytes with IHDR first and text/time/exif chunks removed.

    Non-PNG input is returned unchanged. If chunks cannot be rebuilt into a
    usable image, the bytes from the PNG signature onward are returned.
    """
    idx = _signature_offset(data)
    if idx < 0:
        return data
    png = data[idx:]
    chunks = parse_png_chunks(png, len(PNG_SIGNATURE))
    rebuilt = rebuild_png(chunks)
    return rebuilt if rebuilt is not None else png


def _headers_need_sanitize(handle) -> bool | None:
    """Scan chunk headers without copying pixel data.

    Returns True if the file must be rewritten, False if the original path is
    safe for libpng, and None if this is not a PNG (or the signature is not
    at offset 0).
    """
    sig = handle.read(len(PNG_SIGNATURE))
    if sig != PNG_SIGNATURE:
        handle.seek(0)
        return None

    first = True
    while True:
        header = handle.read(8)
        if len(header) < 8:
            return False
        length = int.from_bytes(header[:4], "big")
        ctype = header[4:8]
        if not _is_chunk_type(ctype) or length > _MAX_CHUNK_LENGTH:
            return False
        if first:
            if ctype != b"IHDR":
                return True
            first = False
        elif ctype in _DROP_TYPES:
            return True
        handle.seek(length + 4, os.SEEK_CUR)
        if ctype == b"IEND":
            return False


def png_bytes_for_decode(path: str) -> bytes | None:
    """Read a PNG and return sanitized bytes when Qt should not see the file.

    Returns None when the caller can pass the original path to QImageReader
    (not a PNG, unreadable, or already a safe chunk layout). Well-formed PNGs
    only have their chunk headers scanned; the pixel data is not copied.
    """
    try:
        with open(path, "rb") as handle:
            needs = _headers_need_sanitize(handle)
            if needs is False:
                return None
            if needs is True:
                handle.seek(0)
            data = handle.read()
    except OSError:
        return None

    idx = _signature_offset(data)
    if idx < 0:
        return None

    png = data[idx:]
    chunks = parse_png_chunks(png, len(PNG_SIGNATURE))
    rebuilt = rebuild_png(chunks)
    if rebuilt is None:
        return None

    logger.debug("Sanitized PNG metadata for %s", os.path.basename(path))
    return rebuilt
