"""エラーの詳細表示ポップアップ (gui_qt/error_dialog.py)

エラーが起きたら、内容・作業内容・発生日時・詳細（どこで起きたか）をポップアップで表示し、
同じ内容を error.log に書き出す。想定外のエラー（プログラムの不具合）もここで受け止める。
"""

import os
import sys
import threading
from datetime import datetime

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from core import error_log

from .theme import Theme

# テストなど画面の無い環境では、ポップアップを開かずにここへ渡す（引数: 表示するはずだった内容の辞書）
display_hook = None
_open_dialogs = []  # 表示中のポップアップ（想定外のエラーが続いたときに何枚も重ねて出さないため）


class ErrorDialog(QDialog):
    """エラー内容と詳細を表示するポップアップ"""

    def __init__(self, title, message, operation, entry, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(560, 380)
        self.resize(680, 460)
        self.entry = entry

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)

        head = QLabel(f"⚠ {message}")
        head.setWordWrap(True)
        head.setTextInteractionFlags(Qt.TextSelectableByMouse)
        head.setStyleSheet("color: #ff8a80; font-size: 13px; font-weight: bold;")
        layout.addWidget(head)

        info = QLabel(f"作業内容: {operation}\n発生日時: {datetime.now():%Y-%m-%d %H:%M:%S}")
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info.setStyleSheet(f"color: {Theme.TEXT_WHITE}; font-size: 12px;")
        layout.addWidget(info)

        detail_lbl = QLabel("詳細（この内容は error.log にも書き出しました）:")
        detail_lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(detail_lbl)

        self.detail_edit = QPlainTextEdit(entry)
        self.detail_edit.setReadOnly(True)
        self.detail_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.detail_edit.setFont(QFont("Consolas", 9))
        self.detail_edit.setStyleSheet(
            f"QPlainTextEdit {{ background-color: #120e0b; color: #dcd0bd; border: 1px solid {Theme.BRASS_BASE}; }}"
        )
        layout.addWidget(self.detail_edit, 1)

        path_lbl = QLabel(error_log.LOG_PATH)
        path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 10px;")
        layout.addWidget(path_lbl)

        buttons = QHBoxLayout()
        copy_btn = QPushButton("詳細をコピー")
        copy_btn.clicked.connect(self._copy)
        buttons.addWidget(copy_btn)
        log_btn = QPushButton("ログを開く")
        log_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(error_log.LOG_PATH)))
        log_btn.setEnabled(os.path.exists(error_log.LOG_PATH))
        buttons.addWidget(log_btn)
        buttons.addStretch()
        close_btn = QPushButton("閉じる")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    def _copy(self):
        QGuiApplication.clipboard().setText(self.entry)


def _headless():
    app = QApplication.instance()
    return app is None or QGuiApplication.platformName() in ("offscreen", "minimal")


def show_error(parent, operation, message, exc=None, detail="", title="エラー"):
    """エラーを error.log に書き出し、詳細をポップアップで表示する（画面スレッドから呼ぶこと）。

    operation: エラーが起きたときに行っていた作業（例: 「URL からシナリオを取り込む」）
    message:   利用者向けのエラーの説明
    exc:       例外（あれば、どこで起きたかを詳細に含める）
    detail:    例外の代わりに詳細として載せる文章（別スレッドで組み立てた内容など）
    """
    detail = detail or error_log.exception_detail(exc)
    if exc is not None and str(exc) and str(exc) not in message:
        message = f"{message}\n{exc}" if message else str(exc)
    entry = error_log.build_entry(operation, message, detail)
    error_log.write_entry(entry)
    _display(title, message, operation, entry, parent)
    return entry


def _display(title, message, operation, entry, parent=None, unexpected=False):
    if display_hook is not None:
        display_hook({"title": title, "message": message, "operation": operation, "entry": entry})
        return
    if _headless():
        return
    if unexpected and _open_dialogs:
        return  # 想定外のエラーが続けて起きても、ポップアップは 1 枚だけにする（ログには全て残す）
    dlg = ErrorDialog(title, message, operation, entry, parent if _alive(parent) else None)
    _open_dialogs.append(dlg)
    try:
        dlg.exec()
    finally:
        _open_dialogs.remove(dlg)
        dlg.deleteLater()


def _alive(widget):
    if widget is None:
        return False
    try:
        from shiboken6 import isValid
        return isValid(widget)
    except Exception:
        return False


# ----------------------------------------------------------------------------
# 想定外のエラー（プログラムの不具合）の受け止め
# ----------------------------------------------------------------------------
class _MainThreadRelay(QObject):
    """別スレッドで起きた想定外のエラーを、画面スレッドで表示するための中継"""

    unexpected = Signal(str, str, str)  # message, operation, entry

    def __init__(self):
        super().__init__()
        self.unexpected.connect(self._show, Qt.QueuedConnection)

    def _show(self, message, operation, entry):
        _display("想定外のエラー", message, operation, entry, QApplication.activeWindow(), unexpected=True)


_relay = None


def _operation_from_traceback(tb):
    """想定外のエラーが起きた場所（このアプリの中で一番奥の関数）から作業内容を推し量る"""
    where = None
    while tb is not None:
        code = tb.tb_frame.f_code
        if os.path.abspath(code.co_filename).startswith(error_log.ROOT_DIR):
            module = os.path.splitext(os.path.relpath(code.co_filename, error_log.ROOT_DIR))[0].replace(os.sep, ".")
            where = f"{module}.{getattr(code, 'co_qualname', code.co_name)}"
        tb = tb.tb_next
    return f"画面操作中の処理（{where}）" if where else "画面操作中の処理"


def report_unexpected(exc_type, exc, tb, operation=None):
    """想定外のエラーをログに書き、画面にも表示する（どのスレッドから呼んでもよい）"""
    import traceback

    operation = operation or _operation_from_traceback(tb)
    message = f"想定外のエラーが発生しました: {exc_type.__name__}: {exc}"
    detail = "".join(traceback.format_exception(exc_type, exc, tb)).rstrip()
    entry = error_log.build_entry(operation, message, detail)
    error_log.write_entry(entry)
    if _relay is not None and threading.current_thread() is not threading.main_thread():
        try:
            _relay.unexpected.emit(message, operation, entry)
        except RuntimeError:
            pass
        return
    _display("想定外のエラー", message, operation, entry, QApplication.activeWindow(), unexpected=True)


def install_excepthook():
    """想定外のエラーを受け止めて、ポップアップ表示とログへの書き出しをするようにする（QApplication 作成後に呼ぶ）"""
    global _relay
    _relay = _MainThreadRelay()  # 画面スレッドで作るので、中継先の表示も画面スレッドで行われる

    def _hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        try:
            report_unexpected(exc_type, exc, tb)
        except Exception:
            sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook
    threading.excepthook = lambda args: _hook(args.exc_type, args.exc_value, args.exc_traceback)
