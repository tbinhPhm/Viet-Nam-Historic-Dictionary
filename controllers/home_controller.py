from __future__ import annotations

import time
import re
from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore, QtNetwork, QtWidgets
from PySide6.QtGui import QPixmap
import shiboken6

from config import PROJECT_ROOT, avatar_upload_endpoint
from services.avatar_codec import data_url_to_pixmap, pixmap_to_data_url
from services.avatar_upload import upload_avatar_via_endpoint
from services.chatbot_service import ChatbotService
from services.history_data import HistoryData
from ui_loader import adopt_loaded_mainwindow, load_ui_mainwindow
from controllers.user_tools_controller import UserToolsController


@dataclass(frozen=True)
class UiRefs:
    home_butt: QtWidgets.QPushButton
    directory_butt: QtWidgets.QPushButton
    profile_butt: QtWidgets.QPushButton
    settings_butt: QtWidgets.QPushButton
    log_out_butt: QtWidgets.QPushButton | None
    search_button: QtWidgets.QPushButton
    search_button_1: QtWidgets.QPushButton
    search_bar: QtWidgets.QLineEdit
    search_bar_1: QtWidgets.QLineEdit
    search_result: QtWidgets.QTextEdit
    stack: QtWidgets.QStackedWidget


class UserToolsWindow(QtWidgets.QMainWindow):
    def __init__(self, user_store, username: str, user_id: str | None = None, parent=None):
        super().__init__(parent)
        loaded = load_ui_mainwindow(PROJECT_ROOT / "ui" / "user_tools.ui")
        adopt_loaded_mainwindow(self, loaded)
        self._controller = UserToolsController(self, user_store, username, user_id=user_id)

    def open_page_2(self) -> None:
        self._controller.open_page_2()


class HomeController(QtCore.QObject):
    HOME_PAGE_INDEX = 0
    DIRECTORY_PAGE_INDEX = 1
    PROFILE_PAGE_INDEX = 2
    USER_SEARCH_PAGE_INDEX = 3
    USER_INSPECT_PAGE_INDEX = 4
    HISTORY_HEADERS = ("Th\u1eddi gian", "T\u1eeb kh\u00f3a", "S\u1ed1 l\u01b0\u1ee3ng k\u1ebft qu\u1ea3")

    def __init__(self, window: QtWidgets.QMainWindow, user_store=None, current_user: str | None = None, current_user_id: str | None = None, parent=None):
        super().__init__(parent)
        self.window = window
        self.user_store = user_store
        self.current_user = (current_user or "").strip() or None
        self.current_user_id = (current_user_id or "").strip() or None

        self.db = HistoryData()
        self.ui = self._wire_ui(window)
        self._connect_signals()
        self._user_tools_window: UserToolsWindow | None = None

        self._avatar_pixmap_original: QPixmap | None = None
        self._avatar_label = self.window.findChild(QtWidgets.QLabel, "avatar")
        if self._avatar_label is not None:
            self._avatar_label.installEventFilter(self)
        self._inspect_avatar_pixmap_original: QPixmap | None = None
        self._inspect_avatar_label = self.window.findChild(QtWidgets.QLabel, "avatar_inspect")
        if self._inspect_avatar_label is not None:
            self._inspect_avatar_label.installEventFilter(self)
        self._avatar_net = QtNetwork.QNetworkAccessManager(self)
        self._user_search_results: list[dict] = []
        self._user_search_list: QtWidgets.QListWidget | None = None
        self._chatbot_service = ChatbotService()

        self._apply_runtime_text()
        self._wire_user_search_ui()
        self._wire_user_inspect_ui()
        self._wire_chatbot_ui()
        self._apply_user()
        self._apply_avatar_from_store()
        self._render_search_history()

    def _get(self, cls, name: str):
        obj = self.window.findChild(cls, name)
        if obj is None:
            raise RuntimeError(f"Không tìm thấy object '{name}' trong home.ui")
        return obj

    def _wire_ui(self, window: QtWidgets.QMainWindow) -> UiRefs:
        return UiRefs(
            home_butt=self._get(QtWidgets.QPushButton, "home_butt"),
            directory_butt=self._get(QtWidgets.QPushButton, "directory_butt"),
            profile_butt=self._get(QtWidgets.QPushButton, "profile_butt"),
            settings_butt=self._get(QtWidgets.QPushButton, "settings_butt"),
            log_out_butt=self.window.findChild(QtWidgets.QPushButton, "log-out_butt"),
            search_button=self._get(QtWidgets.QPushButton, "search_button"),
            search_button_1=self._get(QtWidgets.QPushButton, "search_button_1"),
            search_bar=self._get(QtWidgets.QLineEdit, "search_bar"),
            search_bar_1=self._get(QtWidgets.QLineEdit, "search_bar_1"),
            search_result=self._get(QtWidgets.QTextEdit, "search_result"),
            stack=self._get(QtWidgets.QStackedWidget, "stack"),
        )

    def _connect_signals(self) -> None:
        self.ui.home_butt.clicked.connect(self._go_home)
        self.ui.directory_butt.clicked.connect(self._go_directory)
        self.ui.profile_butt.clicked.connect(self._go_profile)
        self.ui.settings_butt.clicked.connect(self._go_settings)
        if self.ui.log_out_butt is not None:
            self.ui.log_out_butt.clicked.connect(self._logout)

        settings_logout_butt = self.window.findChild(QtWidgets.QPushButton, "log_out_butt_settings")
        if settings_logout_butt is not None:
            settings_logout_butt.clicked.connect(self._logout)

        change_password = self.window.findChild(QtWidgets.QPushButton, "change_password")
        if change_password is not None:
            change_password.clicked.connect(self._open_user_tools_page_2)
        forgot_password = self.window.findChild(QtWidgets.QPushButton, "forgot_password")
        if forgot_password is not None:
            forgot_password.clicked.connect(self._open_user_tools_page_2)

        change_avatar = self.window.findChild(QtWidgets.QPushButton, "change_avatar")
        if change_avatar is not None:
            change_avatar.clicked.connect(self._upload_avatar)

        actions_layout = self.window.findChild(QtWidgets.QHBoxLayout, "horizontalLayout_6")
        if actions_layout is not None:
            find_user_button = QtWidgets.QPushButton("T\u00ecm ng\u01b0\u1eddi d\u00f9ng", self.window)
            find_user_button.setObjectName("find_user_button")
            find_user_button.setMinimumSize(150, 50)
            if change_avatar is not None:
                find_user_button.setStyleSheet(change_avatar.styleSheet())
            find_user_button.clicked.connect(self._go_user_search)
            actions_layout.addWidget(find_user_button)

        self.ui.search_button.clicked.connect(self._search_from_page_2)
        self.ui.search_button_1.clicked.connect(self._search_from_page_3)
        self.ui.search_bar.returnPressed.connect(self._search_from_page_2)
        self.ui.search_bar_1.returnPressed.connect(self._search_from_page_3)

        self.ui.search_bar.setPlaceholderText("VD: 938 hoặc Văn Lang...")
        self.ui.search_bar_1.setPlaceholderText("VD: 938 hoặc Văn Lang...")
        self.ui.stack.setCurrentIndex(self.HOME_PAGE_INDEX)

    def _apply_runtime_text(self) -> None:
        labels = {
            "search_history_qlabel": "L\u1ecbch s\u1eed tra c\u1ee9u:",
            "search_history_qlabel_inspect": "L\u1ecbch s\u1eed tra c\u1ee9u:",
            "search_user_label": "Nh\u1eadp t\u00ean ng\u01b0\u1eddi d\u00f9ng mu\u1ed1n t\u00ecm ki\u1ebfm:",
        }
        for name, text in labels.items():
            label = self.window.findChild(QtWidgets.QLabel, name)
            if label is not None:
                label.setText(text)

    def _wire_user_search_ui(self) -> None:
        search_bar = self.window.findChild(QtWidgets.QLineEdit, "search_bar_user")
        search_button = self.window.findChild(QtWidgets.QPushButton, "search_button_user")
        result_box = self.window.findChild(QtWidgets.QTextEdit, "search_user_result")
        add_friend = self.window.findChild(QtWidgets.QPushButton, "addFriend_user")

        if add_friend is not None:
            add_friend.hide()
        if search_bar is not None:
            search_bar.setPlaceholderText("Nhập username hoặc ID...")
            search_bar.returnPressed.connect(self._search_users)
        if search_button is not None:
            search_button.clicked.connect(self._search_users)
        if result_box is None:
            return

        parent = result_box.parentWidget()
        parent_layout = self.window.findChild(QtWidgets.QVBoxLayout, "verticalLayout_8")
        self._user_search_list = QtWidgets.QListWidget(parent)
        self._user_search_list.setObjectName("search_user_result_list")
        self._user_search_list.setStyleSheet(result_box.styleSheet())
        self._user_search_list.setSizePolicy(result_box.sizePolicy())
        self._user_search_list.setMinimumSize(result_box.minimumSize())
        self._user_search_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self._user_search_list.itemActivated.connect(self._open_selected_user_result)
        self._user_search_list.itemClicked.connect(self._open_selected_user_result)

        if parent_layout is not None:
            idx = parent_layout.indexOf(result_box)
            if idx >= 0:
                parent_layout.insertWidget(idx, self._user_search_list)
                result_box.hide()
                self._set_user_search_message("Nhập tên hoặc ID để tìm người dùng.")

    def _find_layout_containing_widget(self, layout, widget):
        if layout is None:
            return None
        for idx in range(layout.count()):
            item = layout.itemAt(idx)
            if item.widget() is widget:
                return layout
            child_layout = item.layout()
            found = self._find_layout_containing_widget(child_layout, widget)
            if found is not None:
                return found
        return None

    def _wire_user_inspect_ui(self) -> None:
        actions_layout = self.window.findChild(QtWidgets.QHBoxLayout, "horizontalLayout_10")
        if actions_layout is None:
            return

        back_button = QtWidgets.QPushButton("< Back", self.window)
        back_button.setObjectName("back_user_inspect")
        back_button.setMinimumSize(120, 42)
        source_button = self.window.findChild(QtWidgets.QPushButton, "addFriend_user")
        if source_button is not None:
            back_button.setStyleSheet(source_button.styleSheet())
        back_button.clicked.connect(self._go_user_search)
        actions_layout.addWidget(back_button)
        actions_layout.addStretch(1)

    def _wire_chatbot_ui(self) -> None:
        chatbot_button = self.window.findChild(QtWidgets.QPushButton, "chatbot_butt")
        ask_line = self.window.findChild(QtWidgets.QLineEdit, "ask_line")
        ask_button = self.window.findChild(QtWidgets.QPushButton, "ask_butt")
        answer_table = self.window.findChild(QtWidgets.QTableWidget, "answer_table")

        if chatbot_button is not None:
            chatbot_button.clicked.connect(self._go_chatbot)
        if ask_button is not None:
            ask_button.clicked.connect(self._ask_chatbot)
        if ask_line is not None:
            ask_line.returnPressed.connect(self._ask_chatbot)
            ask_line.setPlaceholderText("Nh\u1eadp c\u00e2u h\u1ecfi l\u1ecbch s\u1eed...")
        if answer_table is not None:
            answer_table.setColumnCount(2)
            answer_table.setHorizontalHeaderLabels(["Vai tr\u00f2", "N\u1ed9i dung"])
            answer_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            answer_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            answer_table.verticalHeader().setVisible(False)
            header = answer_table.horizontalHeader()
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.Fixed)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
            answer_table.setColumnWidth(0, 110)

    def _apply_user(self) -> None:
        if self.current_user:
            label = self.window.findChild(QtWidgets.QLabel, "username")
            if label is None:
                label = self.window.findChild(QtWidgets.QLabel, "label_6")
            if label is not None:
                label.setText(self.current_user)

        if self.current_user_id:
            label_id = self.window.findChild(QtWidgets.QLabel, "user_id")
            if label_id is None:
                label_id = self.window.findChild(QtWidgets.QLabel, "label_7")
            if label_id is not None:
                label_id.setText(f"ID: {self.current_user_id}")

    def _run_search(self, query: str) -> None:
        query = (query or "").strip()
        if not query:
            self.ui.search_result.setPlainText("Vui lòng nhập năm hoặc từ khóa để tra cứu.")
            return

        start = time.perf_counter()
        try:
            results = self.db.search(query)
            self.ui.search_result.setPlainText(self.db.format_events(results))
            elapsed = time.perf_counter() - start
            print(f"[SEARCH] query={query!r} results={len(results)} time={elapsed * 1000:.2f}ms")
            if self.user_store is not None and self.current_user:
                if self.current_user_id and hasattr(self.user_store, "append_search_history_by_id"):
                    self.user_store.append_search_history_by_id(self.current_user_id, query, len(results))
                else:
                    self.user_store.append_search_history(self.current_user, query, len(results))
                self._render_search_history()
        except Exception as exc:
            elapsed = time.perf_counter() - start
            print(f"[SEARCH-ERROR] query={query!r} time={elapsed * 1000:.2f}ms error={exc!r}")
            self.ui.search_result.setPlainText(f"Lỗi khi tra cứu: {exc}")

    @QtCore.Slot()
    def _search_from_page_2(self) -> None:
        query = self.ui.search_bar.text()
        self.ui.search_bar_1.setText(query)
        self._run_search(query)
        self.ui.stack.setCurrentIndex(self.DIRECTORY_PAGE_INDEX)

    @QtCore.Slot()
    def _search_from_page_3(self) -> None:
        query = self.ui.search_bar_1.text()
        self._run_search(query)

    @QtCore.Slot()
    def _go_home(self) -> None:
        self.ui.stack.setCurrentIndex(self.HOME_PAGE_INDEX)

    @QtCore.Slot()
    def _go_directory(self) -> None:
        self.ui.stack.setCurrentIndex(self.DIRECTORY_PAGE_INDEX)

    @QtCore.Slot()
    def _go_profile(self) -> None:
        self.ui.stack.setCurrentIndex(self.PROFILE_PAGE_INDEX)
        self._render_search_history()

    @QtCore.Slot()
    def _go_settings(self) -> None:
        settings_page = self.window.findChild(QtWidgets.QWidget, "settings")
        if settings_page is None:
            settings_page = self.window.findChild(QtWidgets.QWidget, "settingsPage")
        if settings_page is None:
            return
        idx = self.ui.stack.indexOf(settings_page)
        if idx >= 0:
            self.ui.stack.setCurrentIndex(idx)

    @QtCore.Slot()
    def _go_user_search(self) -> None:
        self.ui.stack.setCurrentIndex(self.USER_SEARCH_PAGE_INDEX)

    @QtCore.Slot()
    def _go_chatbot(self) -> None:
        page = self.window.findChild(QtWidgets.QWidget, "talk_with_chatbot")
        if page is not None:
            idx = self.ui.stack.indexOf(page)
            if idx >= 0:
                self.ui.stack.setCurrentIndex(idx)

    @QtCore.Slot()
    def _ask_chatbot(self) -> None:
        ask_line = self.window.findChild(QtWidgets.QLineEdit, "ask_line")
        answer_table = self.window.findChild(QtWidgets.QTableWidget, "answer_table")
        if ask_line is None or answer_table is None:
            return

        question = ask_line.text().strip()
        if not question:
            return
        ask_line.clear()

        self._append_chatbot_row("Bạn", question)
        answer_row = self._append_chatbot_row("AI", "Đang trả lời...")
        QtWidgets.QApplication.processEvents()

        try:
            context = self._build_chatbot_context(question)
            answer = self._chatbot_service.answer(question, context)
        except Exception as exc:
            answer = f"Lỗi khi gọi AI: {exc}"
        self._set_chatbot_answer(answer_row, answer)

    def _build_chatbot_context(self, question: str) -> str:
        try:
            results = self._search_history_for_chatbot(question)
            if not results:
                return ""
            return self.db.format_events(results[:8])
        except Exception:
            return ""

    def _search_history_for_chatbot(self, question: str) -> list[dict]:
        question = (question or "").strip()
        if not question:
            return []

        found: list[dict] = []
        seen: set[int] = set()

        def add_results(items: list[dict]) -> None:
            for item in items:
                marker = id(item)
                if marker in seen:
                    continue
                seen.add(marker)
                found.append(item)

        for raw_year in re.findall(r"-?\d{1,4}", question):
            try:
                year = int(raw_year)
            except ValueError:
                continue
            add_results(self.db.search_by_year(year))

        add_results(self.db.search(question))
        if found:
            return found

        stopwords = {
            "nam", "n\u0103m", "xay", "x\u1ea3y", "ra", "su", "s\u1ef1", "kien", "ki\u1ec7n",
            "lich", "l\u1ecbch", "gi", "g\u00ec", "la", "l\u00e0", "ve", "v\u1ec1", "cho", "toi",
            "t\u00f4i", "biet", "bi\u1ebft", "hay", "h\u00e3y", "noi", "n\u00f3i", "giai", "gi\u1ea3i",
            "thich", "th\u00edch", "tom", "t\u00f3m", "tat", "t\u1eaft",
        }
        words = re.findall(r"[\w\u00c0-\u1ef9]+", question.lower())
        keywords = [word for word in words if len(word) >= 3 and word not in stopwords and not word.isdigit()]
        for keyword in keywords[:8]:
            add_results(self.db.search_by_keyword(keyword))
            if len(found) >= 8:
                break
        return found

    def _append_chatbot_row(self, role: str, content: str) -> int:
        table = self.window.findChild(QtWidgets.QTableWidget, "answer_table")
        if table is None:
            return -1
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QtWidgets.QTableWidgetItem(role))
        table.setItem(row, 1, QtWidgets.QTableWidgetItem(content))
        table.resizeRowsToContents()
        table.scrollToBottom()
        return row

    def _set_chatbot_answer(self, row: int, answer: str) -> None:
        table = self.window.findChild(QtWidgets.QTableWidget, "answer_table")
        if table is None or row < 0:
            return
        table.setItem(row, 1, QtWidgets.QTableWidgetItem(answer))
        table.resizeRowsToContents()
        table.scrollToBottom()

    @QtCore.Slot()
    def _logout(self) -> None:
        if hasattr(self.window, "show_login"):
            self.window.show_login()
        else:
            QtWidgets.QApplication.quit()

    @QtCore.Slot()
    def _open_user_tools_page_2(self) -> None:
        if not self.current_user:
            QtWidgets.QMessageBox.warning(self.window, "User tools", "Bạn cần đăng nhập trước.")
            return
        if self.user_store is None:
            QtWidgets.QMessageBox.warning(self.window, "User tools", "Thiếu UserStore.")
            return
        self._user_tools_window = UserToolsWindow(self.user_store, self.current_user, user_id=self.current_user_id, parent=self.window)
        self._user_tools_window.open_page_2()
        self._user_tools_window.show()

    def _render_search_history(self) -> None:
        table = self.window.findChild(QtWidgets.QTableWidget, "search_history_table")
        if table is None:
            return
        if self.user_store is None or not self.current_user:
            table.setRowCount(0)
            table.setColumnCount(3)
            table.setHorizontalHeaderLabels(list(self.HISTORY_HEADERS))
            return

        if self.current_user_id and hasattr(self.user_store, "get_search_history_by_id"):
            history = self.user_store.get_search_history_by_id(self.current_user_id)
        else:
            history = self.user_store.get_search_history(self.current_user)

        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(list(self.HISTORY_HEADERS))
        table.setRowCount(len(history))
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        table.verticalHeader().setVisible(False)

        for row, item in enumerate(reversed(history)):
            ts = str(item.get("ts", "") or "")
            q = str(item.get("query", "") or "")
            res = str(item.get("results", "") or "")
            table.setItem(row, 0, QtWidgets.QTableWidgetItem(ts))
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(q))
            table.setItem(row, 2, QtWidgets.QTableWidgetItem(res))

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        table.setColumnWidth(0, 180)
        table.setColumnWidth(2, 330)

    def _render_history_table(self, table: QtWidgets.QTableWidget | None, history: list[dict]) -> None:
        if table is None:
            return
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(list(self.HISTORY_HEADERS))
        table.setRowCount(len(history))
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        table.verticalHeader().setVisible(False)

        for row, item in enumerate(reversed(history)):
            table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(item.get("ts", "") or "")))
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(item.get("query", "") or "")))
            table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(item.get("results", "") or "")))

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        table.setColumnWidth(0, 180)
        table.setColumnWidth(2, 330)

    @QtCore.Slot()
    def _search_users(self) -> None:
        search_bar = self.window.findChild(QtWidgets.QLineEdit, "search_bar_user")
        query = search_bar.text().strip() if search_bar is not None else ""
        if not query:
            self._user_search_results = []
            self._set_user_search_message("Nhập tên hoặc ID để tìm người dùng.")
            return
        if self.user_store is None or not hasattr(self.user_store, "search_public_users"):
            self._user_search_results = []
            self._set_user_search_message("Không có UserStore để tìm người dùng.")
            return

        try:
            self._user_search_results = self.user_store.search_public_users(query)
        except Exception as exc:
            self._user_search_results = []
            self._set_user_search_message(f"Lỗi khi tìm người dùng: {exc}")
            return

        if not self._user_search_results:
            self._set_user_search_message("Không tìm thấy người dùng phù hợp.")
            return

        if self._user_search_list is None:
            return
        self._user_search_list.clear()
        for user in self._user_search_results:
            username = str(user.get("username", "") or "")
            user_id = str(user.get("ID", "") or "")
            item = QtWidgets.QListWidgetItem(f"{username}    ID: {user_id}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, user_id)
            self._user_search_list.addItem(item)

    def _set_user_search_message(self, message: str) -> None:
        if self._user_search_list is None:
            return
        self._user_search_list.clear()
        item = QtWidgets.QListWidgetItem(message)
        item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
        self._user_search_list.addItem(item)

    @QtCore.Slot(QtWidgets.QListWidgetItem)
    def _open_selected_user_result(self, item: QtWidgets.QListWidgetItem) -> None:
        user_id = str(item.data(QtCore.Qt.ItemDataRole.UserRole) or "").strip()
        if not user_id:
            return
        self._open_user_inspect(user_id)

    def _open_user_inspect(self, user_id: str) -> None:
        if self.user_store is None:
            return
        user = None
        if hasattr(self.user_store, "get_public_user_by_id"):
            user = self.user_store.get_public_user_by_id(user_id)
        if not user:
            QtWidgets.QMessageBox.warning(self.window, "User", "Không tìm thấy người dùng.")
            return

        username = str(user.get("username", "") or "")
        uid = str(user.get("ID", "") or user_id)
        avatar_url = str(user.get("avatar_url", "") or "")

        label_username = self.window.findChild(QtWidgets.QLabel, "username_inspect")
        label_user_id = self.window.findChild(QtWidgets.QLabel, "user_id_inspect")
        if label_username is not None:
            label_username.setText(username)
        if label_user_id is not None:
            label_user_id.setText(f"ID: {uid}")

        self._apply_avatar_to_label(self._inspect_avatar_label, avatar_url, inspect=True)

        history = []
        if hasattr(self.user_store, "get_search_history_by_id"):
            history = self.user_store.get_search_history_by_id(uid)
        elif hasattr(self.user_store, "get_search_history"):
            history = self.user_store.get_search_history(username)
        self._render_history_table(self.window.findChild(QtWidgets.QTableWidget, "search_history_table_inspect"), history)
        self.ui.stack.setCurrentIndex(self.USER_INSPECT_PAGE_INDEX)

    @QtCore.Slot()
    def _upload_avatar(self) -> None:
        label = self._avatar_label or self.window.findChild(QtWidgets.QLabel, "avatar")
        if label is None:
            QtWidgets.QMessageBox.warning(self.window, "Avatar", "Không tìm thấy label 'avatar' trong home.ui")
            return

        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.window,
            "Chọn ảnh đại diện",
            str(PROJECT_ROOT),
            "Images (*.png *.jpg *.jpeg *.bmp *.gif)",
        )
        if not file_path:
            return

        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            QtWidgets.QMessageBox.warning(self.window, "Avatar", "Không thể đọc file ảnh.")
            return

        self._avatar_label = label
        self._avatar_pixmap_original = pixmap
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        label.setScaledContents(False)
        self._rescale_avatar()

        if self.user_store is None or not self.current_user:
            return

        endpoint = avatar_upload_endpoint()
        if endpoint:
            try:
                url = upload_avatar_via_endpoint(self.current_user_id or "", self.current_user, file_path)
                try:
                    if self.current_user_id and hasattr(self.user_store, "update_avatar_url_by_id"):
                        self.user_store.update_avatar_url_by_id(self.current_user_id, url)
                    else:
                        self.user_store.update_avatar_url(self.current_user, url)
                except Exception:
                    pass
                return
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self.window, "Avatar", f"Lỗi upload qua web: {exc}")

        if self.current_user_id and hasattr(self.user_store, "upload_avatar_and_get_url_by_id"):
            try:
                self.user_store.upload_avatar_and_get_url_by_id(self.current_user_id, file_path)
                return
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self.window, "Avatar", f"Lỗi upload avatar: {exc}")
                return

        # fallback local
        try:
            data_url = pixmap_to_data_url(pixmap)
            if hasattr(self.user_store, "update_avatar_url"):
                self.user_store.update_avatar_url(self.current_user, data_url)
        except Exception:
            pass

    def _rescale_avatar(self) -> None:
        if self._avatar_label is None or self._avatar_pixmap_original is None:
            return
        target = self._avatar_label.size()
        if target.width() <= 1 or target.height() <= 1:
            target = self._avatar_label.minimumSize()
        if target.width() <= 1 or target.height() <= 1:
            target = QtCore.QSize(150, 150)

        scaled = self._avatar_pixmap_original.scaled(
            target,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self._avatar_label.setPixmap(scaled)

    def _apply_avatar_from_store(self) -> None:
        if self.user_store is None or not self.current_user:
            return
        if self._avatar_label is None:
            return
        user = self.user_store.get_user(self.current_user) if hasattr(self.user_store, "get_user") else None
        user = user or {}
        self._apply_avatar_to_label(self._avatar_label, str(user.get("avatar_url", "") or ""), inspect=False)

    def _apply_avatar_to_label(self, label: QtWidgets.QLabel | None, path: str, inspect: bool = False) -> None:
        if label is None:
            return
        path = (path or "").strip()
        if not self._has_custom_avatar(path):
            path = str(self._default_avatar_path())

        if path.startswith("data:image/"):
            pixmap = data_url_to_pixmap(path)
            if pixmap is None or pixmap.isNull():
                return
            self._set_avatar_pixmap(label, pixmap, inspect=inspect)
            return

        if path.startswith("http://") or path.startswith("https://"):
            self._load_avatar_from_url_for_label(label, path, inspect=inspect)
            return

        if not Path(path).exists():
            default_path = self._default_avatar_path()
            if Path(path) != default_path and default_path.exists():
                self._apply_avatar_to_label(label, str(default_path), inspect=inspect)
                return
            label.clear()
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        self._set_avatar_pixmap(label, pixmap, inspect=inspect)

    def _has_custom_avatar(self, avatar_url: str) -> bool:
        value = (avatar_url or "").strip()
        if not value:
            return False
        try:
            return Path(value) != self._default_avatar_path()
        except Exception:
            return True

    def _default_avatar_path(self) -> Path:
        return PROJECT_ROOT / "img" / "t\u1ea3i xu\u1ed1ng (3).png"

    def _is_alive(self, obj) -> bool:
        return obj is not None and shiboken6.isValid(obj)

    def _set_avatar_pixmap(self, label: QtWidgets.QLabel, pixmap: QPixmap, inspect: bool = False) -> None:
        if not self._is_alive(label):
            return
        if inspect:
            self._inspect_avatar_pixmap_original = pixmap
        else:
            self._avatar_pixmap_original = pixmap
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        label.setScaledContents(False)
        self._rescale_avatar_label(label, pixmap)

    def _rescale_avatar_label(self, label: QtWidgets.QLabel, pixmap: QPixmap) -> None:
        if not self._is_alive(label):
            return
        target = label.size()
        if target.width() <= 1 or target.height() <= 1:
            target = label.minimumSize()
        if target.width() <= 1 or target.height() <= 1:
            target = QtCore.QSize(150, 150)
        label.setPixmap(
            pixmap.scaled(
                target,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _load_avatar_from_url_for_label(self, label: QtWidgets.QLabel, url: str, inspect: bool = False) -> None:
        req = QtNetwork.QNetworkRequest(QtCore.QUrl(url))
        reply = self._avatar_net.get(req)

        def _done():
            try:
                if not self._is_alive(label):
                    return
                if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError:
                    return
                data = bytes(reply.readAll())
                pixmap = QPixmap()
                if not pixmap.loadFromData(data):
                    return
                self._set_avatar_pixmap(label, pixmap, inspect=inspect)
            finally:
                reply.deleteLater()

        reply.finished.connect(_done)

    def _load_avatar_from_url(self, url: str) -> None:
        if not self._is_alive(self._avatar_label):
            return
        req = QtNetwork.QNetworkRequest(QtCore.QUrl(url))
        reply = self._avatar_net.get(req)

        def _done():
            try:
                if not self._is_alive(self._avatar_label):
                    return
                if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError:
                    return
                data = bytes(reply.readAll())
                pixmap = QPixmap()
                if not pixmap.loadFromData(data):
                    return
                self._avatar_pixmap_original = pixmap
                self._avatar_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self._avatar_label.setScaledContents(False)
                self._rescale_avatar()
            finally:
                reply.deleteLater()

        reply.finished.connect(_done)

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self._avatar_label and event.type() == QtCore.QEvent.Type.Resize:
            self._rescale_avatar()
        if watched is self._inspect_avatar_label and event.type() == QtCore.QEvent.Type.Resize:
            if self._inspect_avatar_pixmap_original is not None and self._inspect_avatar_label is not None:
                self._rescale_avatar_label(self._inspect_avatar_label, self._inspect_avatar_pixmap_original)
        return super().eventFilter(watched, event)
