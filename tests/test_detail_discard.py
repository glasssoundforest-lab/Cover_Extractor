"""詳細編集画面の「シナリオ破棄」ボタンの検証テスト (tests/test_detail_discard.py)

実際の Notion には接続しない。

1. 破棄ボタンは編集画面だけに出ること
2. キャンセルでは何も消えないこと
3. 破棄すると本とセッション履歴が消え、画面が閉じて item_deleted が飛ぶこと
4. Notion 由来の本を手元だけ破棄すると、次の同調で取り込み直されないこと
5. 「Notion のページもゴミ箱へ」では Notion のページを捨ててから消し、失敗したら本を残すこと
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

import app_settings
import notion_sync
from core.database import Database
import test_notion_background_sync as base
from test_notion_deleted_page import TrashableNotion


def _click(text_part):
    """QMessageBox.exec の代わりに、指定の文言のボタンを押したことにする"""

    def fake_exec(box):
        for b in box.buttons():
            if text_part in b.text():
                box._clicked = b
                return 0
        raise AssertionError(f"ボタンが無い: {text_part} / {[b.text() for b in box.buttons()]}")

    return patch.object(QMessageBox, "exec", fake_exec), patch.object(
        QMessageBox, "clickedButton", lambda box: box._clicked)


class TestDiscard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        from gui_qt.dialogs import notion_sync_dialog as mod

        self.mod = mod
        self.tmp = tempfile.mkdtemp()
        self._orig_settings = (app_settings.SETTINGS_FILE, app_settings._settings_instance)
        app_settings.SETTINGS_FILE = os.path.join(self.tmp, "settings.ini")
        app_settings._settings_instance = None
        self.db = Database(os.path.join(self.tmp, "d.db"))
        self.ids = [
            self.db.save_item(f"C:/books/{i}.pdf", title, "クトゥルフ神話TRPG", "2人", "3時間", f"概要{i}", "", None)
            for i, title in enumerate(["共犯者", "影の館"])
        ]
        self.fake = TrashableNotion()
        self._orig = (mod.Settings, notion_sync.NotionClient, mod.app_settings.get_notion_import_limit)
        mod.Settings = base._FakeSettings
        notion_sync.NotionClient = lambda *a, **k: self.fake
        mod.app_settings.get_notion_import_limit = lambda: 0

    def tearDown(self):
        self.mod.Settings, notion_sync.NotionClient, self.mod.app_settings.get_notion_import_limit = self._orig
        app_settings.SETTINGS_FILE, app_settings._settings_instance = self._orig_settings
        self.db.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _sync(self):
        worker = self.mod.NotionSyncWorker(self.db)
        result = []
        worker.finished_all.connect(lambda s, f, e: result.append(e))
        worker.run()
        self.assertEqual(result[-1], "", result[-1])

    def _open(self, item_id, edit=True):
        from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog

        dlg = ItemDetailDialog(item_id, self.db, item_ids=self.ids)
        dlg.show()
        if edit:
            dlg._toggle_edit_mode()
        QApplication.processEvents()
        self.deleted = []
        dlg.item_deleted.connect(self.deleted.append)
        return dlg

    def _wait(self, cond):
        import time

        end = time.time() + 5
        while not cond() and time.time() < end:
            QApplication.processEvents()
            time.sleep(0.01)

    def test_01_button_only_in_edit_mode(self):
        dlg = self._open(self.ids[0], edit=False)
        self.assertFalse(dlg.discard_btn.isVisible())
        dlg._toggle_edit_mode()
        self.assertTrue(dlg.discard_btn.isVisible())
        dlg._toggle_edit_mode()
        self.assertFalse(dlg.discard_btn.isVisible())
        dlg.close()

    def test_02_cancel_keeps_everything(self):
        dlg = self._open(self.ids[0])
        e, c = _click("キャンセル")
        with e, c:
            dlg._on_discard_clicked()
        self.assertIsNotNone(self.db.get_item(self.ids[0]))
        self.assertEqual(self.deleted, [])
        self.assertTrue(dlg.isVisible())
        dlg.close()

    def test_03_discard_removes_book_and_play_logs(self):
        self.db.add_play_log(self.ids[0], session_date="2026-01-01", role="PL", memo="メモ")
        dlg = self._open(self.ids[0])
        e, c = _click("破棄する")
        with e, c:
            dlg._on_discard_clicked()
        self.assertIsNone(self.db.get_item(self.ids[0]))
        self.assertEqual(self.db.get_play_logs(self.ids[0]), [])
        self.assertEqual(self.deleted, [self.ids[0]])
        self.assertFalse(dlg.isVisible())
        self.assertIsNotNone(self.db.get_item(self.ids[1]), "別の本まで消した")

    def test_04_local_discard_not_reimported(self):
        self._sync()
        pid = self.db.get_notion_page_id(self.ids[0])
        self.assertTrue(pid)
        dlg = self._open(self.ids[0])
        e, c = _click("手元だけ破棄")
        with e, c:
            dlg._on_discard_clicked()
        self.assertIsNone(self.db.get_item(self.ids[0]))
        self.assertIn(pid, self.db.get_ignored_notion_pages())
        self.assertIn(pid, self.fake.pages, "手元だけ破棄したのに Notion のページが消えた")
        self._sync()
        titles = [it[2] for it in self.db.get_items()]
        self.assertNotIn("共犯者", titles, "破棄した本を取り込み直した")

    def test_05_trash_notion_page_too(self):
        self._sync()
        pid = self.db.get_notion_page_id(self.ids[0])
        dlg = self._open(self.ids[0])
        e, c = _click("ゴミ箱")
        with e, c, patch.object(self.mod, "open_notion_connection",
                                lambda: (_TrashClient(self.fake), None, None, None)):
            dlg._on_discard_clicked()
            self._wait(lambda: bool(self.deleted))
        self.assertEqual(self.deleted, [self.ids[0]])
        self.assertIsNone(self.db.get_item(self.ids[0]))
        self.assertIn(pid, self.fake.trashed)
        self.assertNotIn(pid, self.db.get_ignored_notion_pages())

    def test_06_trash_failure_keeps_book(self):
        self._sync()
        dlg = self._open(self.ids[0])

        def boom():
            raise notion_sync.NotionError("通信に失敗しました")

        e, c = _click("ゴミ箱")
        with e, c, patch.object(self.mod, "open_notion_connection", boom), \
                patch("gui_qt.dialogs.item_detail_dialog.show_error") as err:
            dlg._on_discard_clicked()
            self._wait(lambda: err.called)
        self.assertTrue(err.called)
        self.assertIsNotNone(self.db.get_item(self.ids[0]), "Notion の削除に失敗したのに本を消した")
        self.assertEqual(self.deleted, [])
        self.assertTrue(dlg.discard_btn.isEnabled())
        dlg.close()

    def test_07_local_book_has_no_notion_choice(self):
        dlg = self._open(self.ids[1])
        seen = []

        def fake_exec(box):
            seen.extend(b.text() for b in box.buttons())
            box._clicked = [b for b in box.buttons() if "キャンセル" in b.text()][0]

        with patch.object(QMessageBox, "exec", fake_exec), patch.object(
                QMessageBox, "clickedButton", lambda box: box._clicked):
            dlg._on_discard_clicked()
        self.assertFalse(any("Notion" in t for t in seen), seen)
        dlg.close()


class _TrashClient:
    def __init__(self, fake):
        self.fake = fake

    def trash_page(self, page_id):
        self.fake.trash(page_id)


if __name__ == "__main__":
    unittest.main()
