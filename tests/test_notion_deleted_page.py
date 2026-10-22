"""Notion 側でページが削除（ゴミ箱へ移動）されていた本の扱いの検証テスト (tests/test_notion_deleted_page.py)

実際の Notion には接続しない。

1. 削除されたページへ書き込もうとして失敗したら、エラーにせず、その本とページの連携を外すこと（手元の本は残す）
2. 連携を外した本を、次の同調で Notion に新しいページとして作り直さないこと
3. Notion でページを元に戻すと、次の同調でまた連携すること
4. 連携を外したことを知らせ、詳細画面にも連携を外した状態を表示すること
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

from PySide6.QtWidgets import QApplication

import app_settings
import notion_sync
from core.database import Database
import test_notion_background_sync as base

ARCHIVED = ("Notion がエラーを返しました（400 validation_error）: Can't edit block that is archived. "
            "You must unarchive the block before editing.")


class TrashableNotion(base.FakeNotion):
    """ページをゴミ箱へ移せる偽の Notion（ゴミ箱のページは一覧に出ず、書き込むとエラーになる）"""

    def __init__(self):
        super().__init__()
        self.trashed = {}

    def trash(self, pid):
        self.trashed[pid] = self.pages.pop(pid)

    def restore(self, pid):
        page = self.trashed.pop(pid)
        page["last_edited_time"] = "2027-01-01T00:00:00.000Z"
        self.pages[pid] = page

    def update_page(self, pid, properties=None, cover_upload_id=None):
        if pid in self.trashed:
            self.calls.append(("update-trashed", pid))
            raise notion_sync.NotionError(ARCHIVED)
        return super().update_page(pid, properties, cover_upload_id)


class TestDeletedPage(unittest.TestCase):
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
        self.db_path = os.path.join(self.tmp, "sync.db")
        self.db = Database(self.db_path)
        self.ids = [
            self.db.save_item(f"C:/books/{i}.pdf", title, "クトゥルフ神話TRPG", "2人", "3時間", f"概要{i}", "", None)
            for i, title in enumerate(["共犯者", "影の館"])
        ]
        self.fake = TrashableNotion()
        self._orig = (mod.Settings, notion_sync.NotionClient, mod.app_settings.get_notion_import_limit)
        mod.Settings = base._FakeSettings
        notion_sync.NotionClient = lambda *a, **k: self.fake
        mod.app_settings.get_notion_import_limit = lambda: 0

        self._sync()  # 2 冊とも Notion にページを作って連携した状態にする
        self.page_id = self.db.get_notion_page_id(self.ids[0])
        self.fake.calls.clear()

    def tearDown(self):
        self.mod.Settings, notion_sync.NotionClient, self.mod.app_settings.get_notion_import_limit = self._orig
        app_settings.SETTINGS_FILE, app_settings._settings_instance = self._orig_settings
        self.db.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _sync(self, auto=False):
        worker = self.mod.NotionSyncWorker(self.db)
        worker.defer_conflicts = auto
        result = []
        worker.finished_all.connect(lambda s, f, e: result.append((s, f, e)))
        worker.run()
        self.assertEqual(result[-1][2], "", result[-1][2])
        return worker, result[-1]

    def _trash_and_edit_locally(self):
        self.fake.trash(self.page_id)
        self.db.update_item_meta(self.ids[0], "共犯者", "クトゥルフ神話TRPG", "3人", "3時間")

    def test_01_unlinks_instead_of_failing(self):
        self._trash_and_edit_locally()
        worker, (_s, fail, _e) = self._sync()
        self.assertEqual(fail, 0)
        self.assertEqual(worker.errors, [], "削除されたページへの書き込みを失敗として扱った")
        self.assertEqual(worker.unlinked_titles, ["共犯者"])
        item = self.db.get_item_detail_dict(self.ids[0])
        self.assertIsNotNone(item, "手元の本まで消した")
        self.assertEqual(item["notion_page_id"], "")
        self.assertEqual(self.db.get_notion_deleted_page_id(self.ids[0]), self.page_id)

        # 次の同調では、Notion に作り直さず、エラーも出さない
        self.fake.calls.clear()
        worker, (_s, fail, _e) = self._sync()
        self.assertEqual((fail, worker.errors, worker.unlinked_titles), (0, [], []))
        self.assertNotIn("create", [c[0] for c in self.fake.calls], "Notion で消したページを作り直した")

    def test_02_restored_page_links_again(self):
        self._trash_and_edit_locally()
        self._sync()
        self.fake.restore(self.page_id)
        self._sync()
        self.assertEqual(self.db.get_notion_page_id(self.ids[0]), self.page_id)
        self.assertEqual(self.db.get_notion_deleted_page_id(self.ids[0]), "")

    def test_03_reregister_explicitly(self):
        self._trash_and_edit_locally()
        self._sync()
        # 差分確認画面の「手元のみ」から登録し直したことにする
        self.db.set_notion_link(self.ids[0], "page-new")
        self.assertEqual(self.db.get_notion_deleted_page_id(self.ids[0]), "")

    def test_04_notifies_user(self):
        from gui_qt.main_window import MainWindow

        self._trash_and_edit_locally()
        worker, _ = self._sync()
        win = MainWindow(db_path=os.path.join(self.tmp, "ui.db"))
        try:
            with patch("gui_qt.main_window.QMessageBox.information") as info:
                win._on_notion_sync_finished(worker, False, 1, 0, "")
            self.assertEqual(info.call_count, 1)
            self.assertIn("『共犯者』", info.call_args[0][2])
            self.assertIn("手元の書架からは消していません", info.call_args[0][2])
            self.assertIn("連携を外しました", win.status_bar.sync_label.text())

            # 自動同調ではダイアログを出さず、ステータスバーで知らせる
            with patch("gui_qt.main_window.QMessageBox.information") as info:
                win._on_notion_sync_finished(worker, True, 1, 0, "")
            info.assert_not_called()
            self.assertIn("連携を外しました", win.status_bar.sync_label.text())
        finally:
            win.close()
            win.db.conn.close()

    def test_05_detail_shows_unlinked_state(self):
        from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog

        self._trash_and_edit_locally()
        self._sync()
        dlg = ItemDetailDialog(self.ids[0], self.db)
        dlg.show()
        dlg._toggle_edit_mode()
        QApplication.processEvents()
        self.assertIn("削除されたため", dlg.notion_status_edit_lbl.text())
        self.assertFalse(dlg.notion_sync_btn.isVisible(), "削除されたページと同期するボタンが出ている")
        dlg.close()

    def test_06_detects_deleted_page_errors(self):
        self.assertTrue(notion_sync.is_deleted_page_error(ARCHIVED))
        self.assertTrue(notion_sync.is_deleted_page_error("Can't edit page because it is in trash"))
        self.assertFalse(notion_sync.is_deleted_page_error("Notion がエラーを返しました（401 unauthorized）"))
        self.assertFalse(notion_sync.is_deleted_page_error("Could not find page with ID"))


if __name__ == "__main__":
    unittest.main()
