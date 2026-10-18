from __future__ import annotations

import os
import sys
import PySide6
from PySide6 import QtWidgets

from config import UI_DIR, USER_DB_PATH, auto_sync_user_json_to_firebase, use_firebase
from controllers.home_controller import HomeController
from controllers.login_controller import LoginController
from services.auto_sync import LocalUserJsonAutoSync
from stores.firestore_user_store import FirestoreUserStore, sync_user_json_to_firebase
from stores.local_user_store import UserStore
from ui_loader import adopt_loaded_mainwindow, load_ui_mainwindow


def _mirror_password_to_firebase(username: str, new_password: str) -> None:
    if not use_firebase():
        return
    try:
        FirestoreUserStore().update_password(username, new_password)
    except Exception:
        return


class AppMainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self._home_controller: HomeController | None = None
        self._login_controller: LoginController | None = None
        self._current_user: str | None = None
        self._current_user_id: str | None = None

        self._user_store = self._create_user_store()
        self._auto_sync: LocalUserJsonAutoSync | None = None
        if use_firebase() and auto_sync_user_json_to_firebase():
            self._auto_sync = LocalUserJsonAutoSync(USER_DB_PATH, sync_user_json_to_firebase, parent=self)
            self._auto_sync.start()

        self.show_login()

    def _create_user_store(self):
        if use_firebase():
            try:
                return FirestoreUserStore()
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Firebase", f"Không dùng được Firebase, fallback user.json.\n{exc}")
        return UserStore(USER_DB_PATH, mirror_password_func=_mirror_password_to_firebase)

    def show_login(self) -> None:
        self._home_controller = None
        self._current_user = None
        self._current_user_id = None

        loaded = load_ui_mainwindow(UI_DIR / "login-signUp.ui")
        adopt_loaded_mainwindow(self, loaded)

        stacked = self.findChild(QtWidgets.QStackedWidget, "stackedWidget")
        if stacked is not None:
            stacked.setCurrentIndex(0)

        try:
            self._login_controller = LoginController(self, self._user_store)
            self._login_controller.open_home_requested.connect(self.show_home)
        except Exception as exc:
            self._login_controller = None
            QtWidgets.QMessageBox.warning(self, "Login", f"Lỗi khởi tạo màn Login/Sign up:\n{exc}")

    def show_home(self, username: str = "", user_id: str = "") -> None:
        self._login_controller = None
        self._current_user = (username or "").strip() or None
        self._current_user_id = (user_id or "").strip() or None

        loaded = load_ui_mainwindow(UI_DIR / "home.ui")
        adopt_loaded_mainwindow(self, loaded)

        self._home_controller = HomeController(
            self,
            user_store=self._user_store,
            current_user=self._current_user,
            current_user_id=self._current_user_id,
        )


def main() -> int:
    # để icon path ../img trong .ui chạy đúng theo CWD
    if UI_DIR.exists():
        os.chdir(UI_DIR)
    app = QtWidgets.QApplication(sys.argv)
    window = AppMainWindow()
    window.show()
    return app.exec()
