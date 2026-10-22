"""エラーの詳細表示（ポップアップ）と error.log への書き出しの検証テスト (tests/test_error_report.py)

1. error.log に日時・作業内容・エラー内容・詳細（どこで起きたか）が書き出されること
2. エラーのポップアップに、ログと同じ内容（作業内容・詳細）が表示されること
3. URL からの取り込みに失敗したとき、URL を含む作業内容でポップアップとログが出ること
4. Notion との同調に失敗したとき、詳細付きで表示されること（自動同調では失敗が続いても 1 回だけ表示し、ログには毎回書く）
5. 本ごとの失敗（ファイルの取り込み・Notion 同調）は、どの本で何が起きたかをまとめて表示すること
6. 想定外のエラー（プログラムの不具合）も、別スレッドで起きたものを含めてポップアップとログに出ること
"""

import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core import error_log
from gui_qt import error_dialog


class _ErrorCapture(unittest.TestCase):
    """ポップアップの代わりに表示内容を受け取り、ログは一時ファイルへ書き出す"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_log = error_log.LOG_PATH
        error_log.LOG_PATH = os.path.join(self.tmp, "error.log")
        self.popups = []
        error_dialog.display_hook = self.popups.append

    def tearDown(self):
        error_dialog.display_hook = None
        error_log.LOG_PATH = self._orig_log
        shutil.rmtree(self.tmp, ignore_errors=True)

    def log_text(self):
        if not os.path.exists(error_log.LOG_PATH):
            return ""
        with open(error_log.LOG_PATH, encoding="utf-8") as f:
            return f.read()

    def assert_entry(self, text, operation_part, message_part):
        self.assertRegex(text, r"発生日時: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
        self.assertRegex(text, r"作業内容: .*" + re.escape(operation_part))
        self.assertRegex(text, r"エラー内容: .*" + re.escape(message_part))


def _raise(exc):
    raise exc


class TestErrorLogAndPopup(_ErrorCapture):
    def test_01_log_has_time_operation_message_and_traceback(self):
        try:
            _raise(ValueError("壊れたデータ"))
        except ValueError as e:
            entry = error_log.log_error("テスト用の作業", "読み込みに失敗しました", exc=e)
        log = self.log_text()
        self.assertIn(entry, log)
        self.assert_entry(log, "テスト用の作業", "読み込みに失敗しました")
        self.assertIn("詳細:", log)
        self.assertIn("Traceback (most recent call last)", log)
        self.assertIn("_raise", log, "どこで起きたかが書かれていない")
        self.assertIn("ValueError: 壊れたデータ", log)

    def test_02_popup_shows_same_details_as_log(self):
        try:
            _raise(OSError("ディスクがいっぱいです"))
        except OSError as e:
            error_dialog.show_error(None, "バックアップを作成する", "バックアップの作成中にエラーが発生しました", exc=e,
                                    title="バックアップ失敗")
        self.assertEqual(len(self.popups), 1)
        popup = self.popups[0]
        self.assertEqual(popup["title"], "バックアップ失敗")
        self.assertEqual(popup["operation"], "バックアップを作成する")
        self.assertIn("ディスクがいっぱいです", popup["message"])
        self.assertIn(popup["entry"], self.log_text(), "ポップアップとログの内容が違う")
        self.assertIn("Traceback", popup["entry"])

        # 実際のポップアップ画面: エラー内容・作業内容・詳細が最初から見えている
        dlg = error_dialog.ErrorDialog(popup["title"], popup["message"], popup["operation"], popup["entry"])
        self.assertEqual(dlg.detail_edit.toPlainText(), popup["entry"])
        texts = " ".join(lbl.text() for lbl in dlg.findChildren(error_dialog.QLabel))
        self.assertIn("ディスクがいっぱいです", texts)
        self.assertIn("作業内容: バックアップを作成する", texts)
        self.assertIn("発生日時:", texts)
        dlg._copy()
        self.assertEqual(QApplication.clipboard().text(), popup["entry"])
        dlg.deleteLater()

    def test_03_url_import_failure(self):
        import app_settings
        from core.database import Database
        from gui_qt.dialogs.add_scenario_url_dialog import AddScenarioUrlDialog

        orig = (app_settings.SETTINGS_FILE, app_settings._settings_instance)
        app_settings.SETTINGS_FILE = os.path.join(self.tmp, "settings.ini")
        app_settings._settings_instance = None
        db = Database(os.path.join(self.tmp, "url.db"))
        try:
            dlg = AddScenarioUrlDialog(db, initial_url="https://booth.pm/ja/items/123")
            dlg.show()
            try:
                _raise(ConnectionError("HTTP 404"))
            except ConnectionError as e:
                dlg._on_fetch_failed(e)
            self.assertEqual(len(self.popups), 1)
            self.assertIn("https://booth.pm/ja/items/123", self.popups[0]["operation"])
            self.assertIn("HTTP 404", self.popups[0]["message"])
            self.assert_entry(self.log_text(), "https://booth.pm/ja/items/123", "シナリオ情報の取得に失敗しました")
            self.assertIn("ConnectionError: HTTP 404", self.log_text())
            dlg.close()
        finally:
            db.conn.close()
            app_settings.SETTINGS_FILE, app_settings._settings_instance = orig


class _FakeWorker:
    def __init__(self, errors=(), error_detail=""):
        self.errors = list(errors)
        self.error_detail = error_detail
        self.unlinked_titles = []
        self.imported_count = self.pushed_count = self.deferred_count = 0


class TestMainWindowErrors(_ErrorCapture):
    def setUp(self):
        super().setUp()
        import app_settings
        from gui_qt.main_window import MainWindow

        self._orig_settings = (app_settings.SETTINGS_FILE, app_settings._settings_instance)
        app_settings.SETTINGS_FILE = os.path.join(self.tmp, "settings.ini")
        app_settings._settings_instance = None
        self.win = MainWindow(db_path=os.path.join(self.tmp, "ui.db"))

    def tearDown(self):
        import app_settings

        self.win.close()
        self.win.db.conn.close()
        app_settings.SETTINGS_FILE, app_settings._settings_instance = self._orig_settings
        super().tearDown()

    def test_04_notion_sync_connection_error(self):
        worker = _FakeWorker(error_detail='Traceback (most recent call last):\n  File "notion_sync.py"\nNotionError: 401')
        self.win._on_notion_sync_finished(worker, False, 0, 0, "Notionへの接続に失敗しました:\nAPI トークンが無効です")
        self.assertEqual(len(self.popups), 1)
        self.assertEqual(self.popups[0]["operation"], "Notion と同調する")
        self.assertIn("API トークンが無効です", self.popups[0]["message"])
        self.assertIn("NotionError: 401", self.popups[0]["entry"])
        self.assert_entry(self.log_text(), "Notion と同調する", "Notionへの接続に失敗しました")

    def test_04b_auto_sync_reports_once_while_failing(self):
        for _ in range(3):
            self.win._on_notion_sync_finished(_FakeWorker(), True, 0, 0, "Notionへの接続に失敗しました:\nタイムアウト")
        self.assertEqual(len(self.popups), 1, "自動同調の失敗のたびにポップアップが出ている")
        self.assertEqual(self.log_text().count("作業内容: Notion と自動同調する"), 3, "ログに毎回書き出していない")

        # 一度うまくいったら、次に失敗したときはまた知らせる
        self.win._on_notion_sync_finished(_FakeWorker(), True, 1, 0, "")
        self.win._on_notion_sync_finished(_FakeWorker(), True, 0, 0, "Notionへの接続に失敗しました:\nタイムアウト")
        self.assertEqual(len(self.popups), 2)

    def test_05_per_book_failures_are_listed(self):
        errors = [
            error_log.build_entry("手元の本を Notion へ送る（『影の館』）", "HTTP 400", "Traceback ...\nNotionError: 400"),
            error_log.build_entry("Notion のページを手元へ取り込む（『星の書』）", "database is locked", "Traceback ..."),
        ]
        self.win._on_notion_sync_finished(_FakeWorker(errors), False, 3, 2, "")
        self.assertEqual(len(self.popups), 1)
        entry = self.popups[0]["entry"]
        self.assertIn("2 冊の同調に失敗しました", self.popups[0]["message"])
        self.assertIn("『影の館』", entry)
        self.assertIn("『星の書』", entry)
        self.assertIn(entry, self.log_text())

    def test_05b_file_import_failures_are_listed(self):
        from gui_qt.dialogs import import_progress_dialog as mod

        bad = os.path.join(self.tmp, "壊れた.pdf")
        with open(bad, "wb") as f:
            f.write(b"not a pdf")
        orig = mod.extract_scenario_data
        mod.extract_scenario_data = lambda extractor, target: _raise(RuntimeError("PDF を読めません"))
        try:
            worker = mod.ImportWorker([bad], None, self.win.db)
            worker.run()
        finally:
            mod.extract_scenario_data = orig
        self.assertEqual(len(worker.errors), 1)
        self.assertIn(bad, worker.errors[0])
        self.assertIn("RuntimeError: PDF を読めません", worker.errors[0])


class TestUnexpectedErrors(_ErrorCapture):
    def setUp(self):
        super().setUp()
        self._orig_hooks = (sys.excepthook, threading.excepthook)
        error_dialog.install_excepthook()

    def tearDown(self):
        sys.excepthook, threading.excepthook = self._orig_hooks
        error_dialog._relay = None
        super().tearDown()

    def test_06_unexpected_error_in_ui_and_worker_thread(self):
        try:
            _raise(KeyError("missing"))
        except KeyError:
            sys.excepthook(*sys.exc_info())
        self.assertEqual(len(self.popups), 1)
        self.assertIn("KeyError", self.popups[0]["message"])
        self.assertIn("test_error_report", self.popups[0]["operation"], "どの処理で起きたかが作業内容に無い")

        # 別スレッドで起きたエラーは、画面スレッドでポップアップにする
        t = threading.Thread(target=_raise, args=(ZeroDivisionError("division by zero"),))
        t.start()
        t.join()
        deadline = time.time() + 3
        while time.time() < deadline and len(self.popups) < 2:
            QApplication.processEvents()
            time.sleep(0.01)
        self.assertEqual(len(self.popups), 2)
        self.assertIn("ZeroDivisionError", self.popups[1]["message"])
        self.assertEqual(self.log_text().count("想定外のエラーが発生しました"), 2)


if __name__ == "__main__":
    unittest.main()
