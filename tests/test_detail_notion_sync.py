"""詳細編集画面の「Notionと同期」ボタンの検証テスト (tests/test_detail_notion_sync.py)

実際の Notion には接続しない（ページの取得は偽の関数に差し替える）。

1. Notion から取り込んだシナリオを編集しているときだけ、保存・取消の上に「Notionと同期」が出ること
2. 押すと Notion の内容を取得し、比較画面で選んだ項目を入力欄に反映すること（保存で確定する）
   タグは Notion のタグにそろえ、通過記録はセッション履歴に取り込むこと
3. 手元と Notion が同じなら比較画面を出さずに知らせること
4. 取得に失敗したら、詳細をポップアップで表示してログに書き出すこと
5. Notion の設定が無いときは、分かりやすい理由で接続を断ること
"""

import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

import app_settings
from core import error_log
from core.database import Database
from gui_qt import error_dialog
from gui_qt.dialogs import notion_sync_dialog
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog


def _fetched(**overrides):
    values = {
        "title": "影の館",
        "author": "黒木",
        "system_name": "クトゥルフ神話TRPG",
        "players_text": "2人",
        "duration_text": "3時間",
        "overview": "Notion で書き直した概要",
        "synopsis": "あらすじ",
        "tags": ["CoC", "通過済み"],
        "source_url": "https://booth.pm/ja/items/1",
        "play_log": {"session_date": "2024-05-03", "gm": "Aさん", "character_name": "御手洗"},
    }
    values.update(overrides)
    return {"page": {"id": "page-1"}, "values": values, "image_bytes": None}


class TestDetailNotionSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (app_settings.SETTINGS_FILE, app_settings._settings_instance, error_log.LOG_PATH)
        app_settings.SETTINGS_FILE = os.path.join(self.tmp, "settings.ini")
        app_settings._settings_instance = None
        error_log.LOG_PATH = os.path.join(self.tmp, "error.log")
        self.popups = []
        error_dialog.display_hook = self.popups.append

        self.db = Database(os.path.join(self.tmp, "detail.db"))
        self.notion_id = self.db.save_item("notion://page-1", "影の館", "クトゥルフ神話TRPG", "2人", "3時間",
                                           "手元の概要", "あらすじ", None)
        self.db.set_notion_link(self.notion_id, "page-1")
        self.local_id = self.db.save_item("C:/books/local.pdf", "手元だけの本", "", "", "", "", "", None)

    def tearDown(self):
        error_dialog.display_hook = None
        app_settings.SETTINGS_FILE, app_settings._settings_instance, error_log.LOG_PATH = self._orig
        self.db.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _open(self, item_id):
        dlg = ItemDetailDialog(item_id, self.db)
        dlg.show()
        QApplication.processEvents()
        return dlg

    def _click_and_wait(self, dlg):
        dlg.notion_sync_btn.click()
        deadline = time.time() + 5
        while time.time() < deadline and dlg._notion_fetch_task is not None:
            QApplication.processEvents()
            time.sleep(0.01)
        self.assertIsNone(dlg._notion_fetch_task, "取得が終わらない")

    def test_01_button_only_for_notion_items_in_edit_mode(self):
        dlg = self._open(self.notion_id)
        self.assertFalse(dlg.notion_sync_btn.isVisible(), "閲覧中に出ている")
        dlg._toggle_edit_mode()
        self.assertTrue(dlg.notion_sync_btn.isVisible())
        # 「保存」「取消」の上の段に、同じ幅で置かれている
        top = lambda w: w.mapTo(dlg, w.rect().topLeft())
        self.assertLess(top(dlg.notion_sync_btn).y() + dlg.notion_sync_btn.height(), top(dlg.save_btn).y() + 1)
        self.assertEqual(top(dlg.notion_sync_btn).x(), top(dlg.save_btn).x())
        self.assertEqual(top(dlg.notion_sync_btn).x() + dlg.notion_sync_btn.width(),
                         top(dlg.cancel_btn).x() + dlg.cancel_btn.width())
        dlg._on_cancel()
        self.assertFalse(dlg.notion_sync_btn.isVisible())
        dlg.close()

        dlg = self._open(self.local_id)
        dlg._toggle_edit_mode()
        self.assertFalse(dlg.notion_sync_btn.isVisible(), "Notion と関係ない本に出ている")
        dlg.close()

    def test_02_fetch_compare_and_apply(self):
        dlg = self._open(self.notion_id)
        dlg._toggle_edit_mode()
        compared = {}

        def fake_exec(diff_dlg):
            compared["current"] = dict(diff_dlg.current_data)
            compared["notion"] = dict(diff_dlg.web_data)
            compared["source"] = diff_dlg.source_name
            return QDialog.Accepted

        with patch.object(notion_sync_dialog, "fetch_notion_page", lambda pid: _fetched()) as _, \
             patch("gui_qt.dialogs.web_info_diff_dialog.WebInfoComparisonDialog.exec", fake_exec), \
             patch("gui_qt.dialogs.web_info_diff_dialog.WebInfoComparisonDialog.get_selected_fields",
                   return_value={"author", "overview", "tags"}), \
             patch("gui_qt.dialogs.item_detail_dialog.QMessageBox.information") as info:
            self._click_and_wait(dlg)

        self.assertEqual(compared["source"], "Notion")
        self.assertEqual(compared["current"]["overview"], "手元の概要")
        self.assertEqual(compared["notion"]["overview"], "Notion で書き直した概要")
        # 選んだ項目だけ入力欄に反映（まだ保存していない）
        self.assertEqual(dlg.overview_edit.toPlainText(), "Notion で書き直した概要")
        self.assertEqual(dlg.edit_inputs["author"].text(), "黒木")
        self.assertEqual(self.db.get_item(self.notion_id)[6], "手元の概要", "保存前に確定している")
        self.assertEqual(dlg.url_edit.text(), "https://booth.pm/ja/items/1", "空欄の情報元 URL を補っていない")
        # タグと通過記録はその場で取り込む
        self.assertEqual({t[1] for t in self.db.get_item_tags(self.notion_id)}, {"CoC", "通過済み"})
        logs = self.db.get_play_logs(self.notion_id)
        self.assertEqual([(l["gm"], l["character_name"]) for l in logs], [("Aさん", "御手洗")])
        self.assertIn("保存", info.call_args[0][2])

        with patch("gui_qt.dialogs.item_detail_dialog.QMessageBox.information"):
            dlg._on_save()
        self.assertEqual(self.db.get_item(self.notion_id)[6], "Notion で書き直した概要")
        self.assertEqual(self.popups, [])
        dlg.close()

    def test_03_same_content_skips_comparison(self):
        dlg = self._open(self.notion_id)
        dlg._toggle_edit_mode()
        same = _fetched(overview="手元の概要", author="", tags=None, source_url="", play_log=None)
        same["values"].pop("tags")
        with patch.object(notion_sync_dialog, "fetch_notion_page", lambda pid: same), \
             patch("gui_qt.dialogs.web_info_diff_dialog.WebInfoComparisonDialog.exec") as cmp_exec, \
             patch("gui_qt.dialogs.item_detail_dialog.QMessageBox.information") as info:
            self._click_and_wait(dlg)
        cmp_exec.assert_not_called()
        self.assertIn("同じ", info.call_args[0][2])
        dlg.close()

    def test_04_failure_shows_details_and_logs(self):
        dlg = self._open(self.notion_id)
        dlg._toggle_edit_mode()

        def boom(pid):
            raise ConnectionError("Notion に接続できません")

        with patch.object(notion_sync_dialog, "fetch_notion_page", boom):
            self._click_and_wait(dlg)
        self.assertEqual(len(self.popups), 1)
        self.assertIn("『影の館』", self.popups[0]["operation"])
        self.assertIn("Notion に接続できません", self.popups[0]["message"])
        self.assertIn("ConnectionError", self.popups[0]["entry"])
        with open(error_log.LOG_PATH, encoding="utf-8") as f:
            self.assertIn(self.popups[0]["entry"], f.read())
        self.assertTrue(dlg.notion_sync_btn.isEnabled(), "失敗後にボタンが押せないまま")
        dlg.close()

    def test_05_missing_settings(self):
        with self.assertRaises(notion_sync_dialog.NotionSetupError) as cm:
            notion_sync_dialog.open_notion_connection()
        self.assertIn("トークン", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
