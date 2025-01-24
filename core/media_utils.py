# core/media_utils.py
import os
from datetime import datetime
from PyQt6.QtCore import Qt


def set_file_info(file_path, info_label, elide=False, max_width=150):
    """Set file information in the given label, optionally eliding the file name."""
    if not os.path.exists(file_path):
        info_label.setText(f"File not found: {file_path}")
        return

    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    # Format file size
    if file_size < 1024:
        file_size_str = f"{file_size} B"
    elif file_size < 1024 * 1024:
        file_size_str = f"{file_size / 1024:.1f} KB"
    else:
        file_size_str = f"{file_size / (1024 * 1024):.1f} MB"

    # Format modification date
    mod_time = os.path.getmtime(file_path)
    mod_date = datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M:%S")

    # Elide file name if required
    if elide:
        elided_name = elide_text(file_name, max_width, info_label)
        info_label.setText(f"{elided_name}\n{file_size_str} | {mod_date}")
        info_label.setToolTip(f"{file_name}\nSize: {file_size_str}\nModified: {mod_date}")
    else:
        info_label.setText(f"{file_name}\n{file_size_str} | {mod_date}")


def elide_text(text, max_width, label):
    """Elide text to fit within the specified width using the label's font metrics."""
    metrics = label.fontMetrics()
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, max_width)