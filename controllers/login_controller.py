from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class LoginController(QtCore.QObject):
    open_home_requested = QtCore.Signal(str, str)  # username, user_id

    def __init__(self, window: QtWidgets.QMainWindow, user_store, parent=None):
        super().__init__(parent)
        self.window = window
        self.user_store = user_store

        self.stacked = self._get(QtWidgets.QStackedWidget, "stackedWidget")
        self.btn_login1 = self._get(QtWidgets.QPushButton, "pushButton_login1")
        self.btn_signup1 = self._get(QtWidgets.QPushButton, "pushButton_signUp1")
        self.btn_signup2 = self._get(QtWidgets.QPushButton, "pushButton_signUp2")
        self.btn_login2 = self._get(QtWidgets.QPushButton, "pushButton_login2")

        self.login_username = self._get(QtWidgets.QLineEdit, "lineEdit_login_username")
        self.login_password = self._get(QtWidgets.QLineEdit, "lineEdit_login_password")
        self.signup_username = self._get(QtWidgets.QLineEdit, "lineEdit_signUp_username")
        self.signup_email = self._get(QtWidgets.QLineEdit, "lineEdit_signUp_email")
        self.signup_password = self._get(QtWidgets.QLineEdit, "lineEdit_signUp_password")
        self.signup_confirm = self._get(QtWidgets.QLineEdit, "lineEdit_signUp_confirmedPassword")

        self.btn_signup1.clicked.connect(self._to_signup)
        self.btn_login2.clicked.connect(self._to_login)
        self.btn_login1.clicked.connect(self._login)
        self.btn_signup2.clicked.connect(self._signup)

        self.stacked.setCurrentIndex(0)

    def _get(self, cls, name: str):
        obj = self.window.findChild(cls, name)
        if obj is None:
            raise RuntimeError(f"Không tìm thấy object '{name}' trong login-signUp.ui")
        return obj

    @QtCore.Slot()
    def _to_signup(self) -> None:
        self.stacked.setCurrentIndex(1)

    @QtCore.Slot()
    def _to_login(self) -> None:
        self.stacked.setCurrentIndex(0)

    @QtCore.Slot()
    def _login(self) -> None:
        username = self.login_username.text().strip()
        password = self.login_password.text()

        if hasattr(self.user_store, "login"):
            user_id, _ = self.user_store.login(username, password)
            if user_id:
                self.open_home_requested.emit(username, str(user_id))
                return
        elif self.user_store.verify(username, password):
            user = self.user_store.get_user(username) or {}
            user_id = str(user.get("ID", "")).strip()
            self.open_home_requested.emit(username, user_id)
            return

        QtWidgets.QMessageBox.warning(self.window, "Login", "Sai username hoặc mật khẩu.")

    @QtCore.Slot()
    def _signup(self) -> None:
        username = self.signup_username.text().strip()
        email = self.signup_email.text().strip()
        password = self.signup_password.text()
        confirm = self.signup_confirm.text()

        if not username or not password or not email:
            QtWidgets.QMessageBox.warning(self.window, "Sign up", "Vui lòng nhập username, email và mật khẩu.")
            return
        if "@" not in email or "." not in email:
            QtWidgets.QMessageBox.warning(self.window, "Sign up", "Email không hợp lệ (chưa cần verify, chỉ kiểm tra cơ bản).")
            return
        if password != confirm:
            QtWidgets.QMessageBox.warning(self.window, "Sign up", "Mật khẩu xác nhận không khớp.")
            return

        try:
            self.user_store.add_user(username, password, email)
            created = self.user_store.get_user(username) if hasattr(self.user_store, "get_user") else None
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self.window, "Sign up", str(exc))
            return

        created_id = str((created or {}).get("ID", "")).strip()
        msg = "Tạo tài khoản thành công."
        if created_id:
            msg = f"{msg}\nID: {created_id}"
        QtWidgets.QMessageBox.information(self.window, "Sign up", msg)
        self.login_username.setText(username)
        self.login_password.setText("")
        self.stacked.setCurrentIndex(0)

