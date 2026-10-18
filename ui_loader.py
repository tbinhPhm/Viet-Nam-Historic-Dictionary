from __future__ import annotations

from pathlib import Path

from PySide6 import QtWidgets
from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader


def load_ui_mainwindow(ui_path: Path) -> QtWidgets.QMainWindow:
    loader = QUiLoader()
    file = QFile(str(ui_path))
    if not file.open(QFile.ReadOnly):
        raise FileNotFoundError(f"Không mở được file UI: {ui_path}")
    try:
        window = loader.load(file)
    finally:
        file.close()
    if window is None:
        raise RuntimeError(f"Load UI thất bại: {ui_path}")
    if not isinstance(window, QtWidgets.QMainWindow):
        raise TypeError(f"UI không phải QMainWindow (nhận {type(window)})")
    return window


def adopt_loaded_mainwindow(target: QtWidgets.QMainWindow, loaded: QtWidgets.QMainWindow) -> None:
    old = target.takeCentralWidget()
    if old is not None:
        old.deleteLater()

    target.setObjectName(loaded.objectName())
    target.setWindowTitle(loaded.windowTitle())
    target.setMinimumSize(loaded.minimumSize())
    target.setMaximumSize(loaded.maximumSize())
    target.resize(loaded.size())
    target.setStyleSheet(loaded.styleSheet())

    central = loaded.takeCentralWidget()
    if central is None:
        raise RuntimeError("UI không có centralWidget()")
    target.setCentralWidget(central)

