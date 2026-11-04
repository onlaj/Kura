"""
Size hints of grid media widgets must not depend on the widget's current size.

If they do, QScrollArea re-enters resize -> hint -> resize without settling and
the process dies with a native stack overflow, which Python cannot report.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QMovie, QPixmap
from PyQt6.QtWidgets import QApplication

from core.media_handler import ScalableLabel, ScalableMovie
from core.media_utils import AspectRatioWidget

SIZES = [(200, 200), (640, 200), (300, 300), (1000, 280), (211, 297), (523, 241)]


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


def _pixmap(width, height):
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("red"))
    return pixmap


def _hints_at_each_size(widget, app):
    widget.show()
    hints = set()
    for width, height in SIZES:
        widget.resize(width, height)
        app.processEvents()
        hint, minimum = widget.sizeHint(), widget.minimumSizeHint()
        hints.add((hint.width(), hint.height(), minimum.width(), minimum.height()))
    widget.close()
    return hints


@pytest.mark.parametrize("pixmap_size", [(640, 360), (360, 640), (120, 90)])
def test_scalable_label_hint_is_independent_of_size(app, pixmap_size):
    label = ScalableLabel()
    label.setPixmap(_pixmap(*pixmap_size))
    assert len(_hints_at_each_size(label, app)) == 1
    assert label.sizeHint() == QSize(*pixmap_size)


@pytest.mark.parametrize("pixmap_size", [(640, 360), (360, 640), (120, 90)])
def test_aspect_ratio_widget_hint_ignores_resize_margins(app, pixmap_size):
    label = ScalableLabel()
    label.setPixmap(_pixmap(*pixmap_size))
    wrapped = AspectRatioWidget(label, pixmap_size[0] / pixmap_size[1])
    assert len(_hints_at_each_size(wrapped, app)) == 1
    # Qt raises the content hint to the label's minimumSizeHint
    assert wrapped.sizeHint() == label.sizeHint().expandedTo(label.minimumSizeHint())


def test_scalable_movie_keeps_original_size_when_scaled(app, tmp_path):
    gif_path = tmp_path / "frame.gif"
    Image.new("RGB", (320, 180), "red").save(gif_path)  # Qt cannot write GIFs
    movie = QMovie(str(gif_path))
    movie.jumpToFrame(0)
    label = ScalableMovie()
    label.setMovie(movie)
    assert len(_hints_at_each_size(label, app)) == 1
    assert label.sizeHint() == QSize(320, 180)
