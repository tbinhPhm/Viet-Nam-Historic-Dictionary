from __future__ import annotations

import base64

from PySide6 import QtCore
from PySide6.QtGui import QPixmap


def pixmap_to_data_url(pixmap: QPixmap) -> str:
    target = pixmap.scaled(
        QtCore.QSize(128, 128),
        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        QtCore.Qt.TransformationMode.SmoothTransformation,
    )
    image = target.toImage()
    ba = QtCore.QByteArray()
    buf = QtCore.QBuffer(ba)
    buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    ok = image.save(buf, b"JPG", quality=75)
    buf.close()
    if not ok:
        raise ValueError("Không thể encode ảnh.")
    b64 = base64.b64encode(bytes(ba)).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def data_url_to_pixmap(data_url: str) -> QPixmap | None:
    s = (data_url or "").strip()
    if not s.startswith("data:image/"):
        return None
    try:
        _header, b64 = s.split(",", 1)
        raw = base64.b64decode(b64.encode("ascii"), validate=False)
        pixmap = QPixmap()
        if not pixmap.loadFromData(raw):
            return None
        return pixmap
    except Exception:
        return None

