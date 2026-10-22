"""詳細画面のセッション履歴（セッション記録）とページめくりの配置の検証テスト (tests/test_detail_play_log_layout.py)

1. 閲覧画面にはセッション履歴の追加・編集・削除ボタンが無く、編集画面でだけ出ること
2. 編集画面で、Notion から取り込んだ記録も編集できること
3. セッション履歴の各項目（PC・GM・卓メンバー・キャラクターシート・メモ）が 1 行ずつ表示され、
   長い名前でもカードの幅を広げない（編集・削除ボタンが画面外へはみ出さない）こと
4. 前の書物・次の書物（冊数の表示）が、閲覧画面でも編集画面でも詳細画面の中央にあること
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

import app_settings
from core.database import Database
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog

LONG_PC = "御手洗 清十郎（私立探偵・HO1 探索者）／ 立花 美雪（HO2 新聞記者）／ 黒木 透（HO3 医師）"
LONG_MEMBERS = "、".join(f"{n}さん（PC{n}）" for n in "BCDEFGHIJK")


class TestDetailPlayLogLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (app_settings.SETTINGS_FILE, app_settings._settings_instance)
        app_settings.SETTINGS_FILE = os.path.join(self.tmp, "settings.ini")
        app_settings._settings_instance = None
        self.db = Database(os.path.join(self.tmp, "detail.db"))
        self.item_id = self.db.save_item("notion://page-1", "影の館", "クトゥルフ神話TRPG", "2人", "3時間", "", "", None)
        self.db.set_notion_link(self.item_id, "page-1")
        self.db.apply_notion_play_log(self.item_id, "page-1", {
            "session_date": "2024-05-03", "gm": "Aさん", "character_name": LONG_PC,
            "party_members": LONG_MEMBERS, "sheet_url": "https://iachara.com/view/" + "9" * 80,
        })
        self.db.add_play_log(self.item_id, session_date="2023-01-01", character_name="手元PC", memo="手元の記録")
        self.dlg = ItemDetailDialog(self.item_id, self.db)
        self.dlg.resize(980, 660)
        self.dlg.show()
        self._settle()

    def tearDown(self):
        self.dlg.close()
        self.db.conn.close()
        app_settings.SETTINGS_FILE, app_settings._settings_instance = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _settle(self):
        for _ in range(5):
            QApplication.processEvents()
        # 消したカードを実際に破棄する（イベントループの外では自動で行われないため）
        QApplication.sendPostedEvents(None, 52)  # QEvent.DeferredDelete
        QApplication.processEvents()

    def _log_buttons(self, text):
        return [b for b in self.dlg.playlog_container.findChildren(QPushButton) if text in b.text() and b.isVisible()]

    def test_01_add_edit_delete_only_in_edit_mode(self):
        self.assertFalse(self.dlg.add_playlog_btn.isVisible(), "閲覧画面に「記録を追加」がある")
        self.assertEqual(self._log_buttons("編集"), [])
        self.assertEqual(self._log_buttons("削除"), [])

        self.dlg._toggle_edit_mode()
        self._settle()
        self.assertTrue(self.dlg.add_playlog_btn.isVisible())
        self.assertEqual(len(self._log_buttons("編集")), 2)
        self.assertEqual(len(self._log_buttons("削除")), 2)

        self.dlg._on_cancel()
        self._settle()
        self.assertFalse(self.dlg.add_playlog_btn.isVisible())
        self.assertEqual(self._log_buttons("編集"), [])

    def test_02_edit_notion_record_in_edit_mode(self):
        self.dlg._toggle_edit_mode()
        self._settle()
        notion_log = next(l for l in self.db.get_play_logs(self.item_id) if l["notion_page_id"])
        # 日付の新しい順に並ぶため、先頭のカードが Notion から取り込んだ記録
        edit_btn = self._log_buttons("編集")[0]
        # 編集・削除ボタンが下部バーの右端より内側にある（はみ出して押せない状態になっていない）
        bar = self.dlg._bottom_bar
        right_edge = bar.mapTo(self.dlg, bar.rect().topRight()).x()
        self.assertLessEqual(edit_btn.mapTo(self.dlg, edit_btn.rect().topRight()).x(), right_edge + 2)

        def fill_and_save():
            w = QApplication.activeModalWidget()
            w.res_edit.setText("生還")
            w.gm_edit.setText("Zさん")
            w._on_save()

        QTimer.singleShot(200, fill_and_save)
        edit_btn.click()
        log = next(l for l in self.db.get_play_logs(self.item_id) if l["id"] == notion_log["id"])
        self.assertEqual((log["result"], log["gm"]), ("生還", "Zさん"))

    def test_03_each_field_on_its_own_line(self):
        texts = [lbl.text() for lbl in self.dlg.playlog_container.findChildren(QLabel) if lbl.isVisible()]
        for prefix in ("PC: 御手洗", "GM: Aさん", "卓メンバー: ", "キャラクターシート: "):
            matches = [t for t in texts if prefix in t]
            self.assertEqual(len(matches), 1, f"{prefix} が 1 行になっていない: {texts}")
        pc_line = next(t for t in texts if "PC: 御手洗" in t)
        self.assertNotIn("GM:", pc_line)
        self.assertNotIn("2024-05-03", pc_line, "日付と同じ行に並んでいる")
        self.assertIn("手元の記録", texts)
        # 長い名前でも横にはみ出さない
        scroll = self.dlg.playlog_container.parentWidget()
        while scroll is not None and not hasattr(scroll, "horizontalScrollBar"):
            scroll = scroll.parentWidget()
        self.assertIsNotNone(scroll)
        self.assertEqual(scroll.horizontalScrollBar().maximum(), 0, "セッション履歴が横にはみ出している")

    def test_04_page_navigation_is_centered(self):
        def offset():
            # 冊数の表示の中央と、詳細画面の中央のずれ
            ind = self.dlg.page_indicator
            return abs(ind.mapTo(self.dlg, ind.rect().center()).x() - self.dlg.width() // 2)

        for size in ((980, 660), (1100, 700), (1400, 820)):
            self.dlg.resize(*size)
            self._settle()
            for edit in (False, True):
                if edit != self.dlg.is_edit_mode:
                    self.dlg._toggle_edit_mode()
                self._settle()
                self.assertLessEqual(offset(), 1, f"{size} 編集={edit} で中央にない")
        # 「Notionと同期」は「保存」「取消」の上の段にあり、ページめくりは「保存」「取消」と同じ段に並ぶ
        self.dlg.resize(980, 660)
        self._settle()
        self.assertTrue(self.dlg.is_edit_mode)
        y = lambda w: w.mapTo(self.dlg, w.rect().topLeft()).y()
        self.assertEqual(y(self.dlg.prev_btn), y(self.dlg.save_btn))
        self.assertLess(y(self.dlg.notion_sync_btn), y(self.dlg.save_btn))


if __name__ == "__main__":
    unittest.main()
