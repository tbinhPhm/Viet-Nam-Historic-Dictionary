from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class UserToolsController(QtCore.QObject):
    def __init__(self, window: QtWidgets.QMainWindow, user_store, username: str, user_id: str | None = None, parent=None):
        super().__init__(parent)
        self.window = window
        self.user_store = user_store
        self.username = (username or "").strip()
        self.user_id = (user_id or "").strip() or None

        self.stack = self._get(QtWidgets.QStackedWidget, "stackedWidget")
        self.page_2 = self._get(QtWidgets.QWidget, "page_2")

        self.le_username = self._get(QtWidgets.QLineEdit, "ut_username")
        self.le_email = self._get(QtWidgets.QLineEdit, "ut_email")
        self.le_old = self._get(QtWidgets.QLineEdit, "ut_old_password")
        self.le_new = self._get(QtWidgets.QLineEdit, "ut_new_password")
        self.le_confirm = self._get(QtWidgets.QLineEdit, "ut_confirm_password")
        self.btn_save = self._get(QtWidgets.QPushButton, "ut_save_password")
        self.btn_close = self._get(QtWidgets.QPushButton, "ut_close")
        self.status = self._get(QtWidgets.QLabel, "ut_status")

        self.le_username.setText(self.username)
        self.le_username.setReadOnly(True)
        self._load_email()

        self.btn_save.clicked.connect(self._save_password)
        self.btn_close.clicked.connect(self.window.close)

    def _get(self, cls, name: str):
        obj = self.window.findChild(cls, name)
        if obj is None:
            raise RuntimeError(f"Không tìm thấy object '{name}' trong user_tools.ui")
        return obj

    def _load_email(self) -> None:
        user = self.user_store.get_user(self.username) if hasattr(self.user_store, "get_user") else None
        user = user or {}
        self.le_email.setText(str(user.get("email", "") or ""))

    def open_page_2(self) -> None:
        idx = self.stack.indexOf(self.page_2)
        if idx >= 0:
            self.stack.setCurrentIndex(idx)

    @QtCore.Slot()
    def _save_password(self) -> None:
        old_pw = self.le_old.text()
        new_pw = self.le_new.text()
        confirm = self.le_confirm.text()
        email_input = self.le_email.text().strip()

        if not new_pw:
            self.status.setText("Vui lòng nhập mật khẩu mới.")
            return
        if new_pw != confirm:
            self.status.setText("Mật khẩu xác nhận không khớp.")
            return

        if old_pw:
            if not self.user_store.verify(self.username, old_pw):
                self.status.setText("Mật khẩu hiện tại không đúng.")
                return
        else:
            user = self.user_store.get_user(self.username) if hasattr(self.user_store, "get_user") else None
            user = user or {}
            stored_email = str(user.get("email", "") or "").strip()
            if not stored_email:
                self.status.setText("Tài khoản này chưa có email để dùng chức năng quên mật khẩu.")
                return
            if not email_input or email_input != stored_email:
                self.status.setText("Email không khớp với tài khoản.")
                return

        try:
            if self.user_id and hasattr(self.user_store, "update_password_by_id"):
                self.user_store.update_password_by_id(self.user_id, new_pw)
            else:
                self.user_store.update_password(self.username, new_pw)
        except Exception as exc:
            self.status.setText(f"Lỗi: {exc}")
            return

        self.le_old.setText("")
        self.le_new.setText("")
        self.le_confirm.setText("")
        self.status.setText("Đổi mật khẩu thành công.")

