"""書架のカードから詳細画面・右クリックメニューを開き、その中で編集して書架が描き直されても
エラーにならないことの検証テスト (tests/test_card_reopen_after_edit.py)

以前は、カードをダブルクリックして開いた詳細画面で編集すると、閉じたときに
「Internal C++ object (ScenarioCard) already deleted」の想定外のエラーが出ていた
（詳細画面を開いている間に書架が描き直され、開いたカード自身が作り直されていたため）。
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import app_settings


class TestCardReopenAfterEdit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        from gui_qt.main_window import MainWindow

        self.tmp = tempfile.mkdtemp()
        self._orig = (app_settings.SETTINGS_FILE, app_settings._settings_instance, sys.excepthook)
        app_settings.SETTINGS_FILE = os.path.join(self.tmp, "settings.ini")
        app_settings._settings_instance = None
        self.errors = []
        sys.excepthook = lambda *exc: self.errors.append(exc)

        self.win = MainWindow(db_path=os.path.join(self.tmp, "shelf.db"))
        for i in range(3):
            self.win.db.save_item(f"C:/books/{i}.pdf", f"書物{i}", "クトゥルフ神話TRPG", "2人", "3時間", "", "", None)
        self.win.resize(1200, 800)
        self.win.show()
        self.win.reload_data()
        self._settle()
        self.item_id = self.win.filtered_items[0][0]

    def tearDown(self):
        self.win.close()
        self.win.db.conn.close()
        app_settings.SETTINGS_FILE, app_settings._settings_instance, sys.excepthook = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _settle(self):
        for _ in range(20):
            QApplication.processEvents()
            QTest.qWait(5)

    def _card(self, item_id):
        from gui_qt.components.scenario_card import ScenarioCard, ScenarioListCard

        for cls in (ScenarioCard, ScenarioListCard):
            for card in self.win.bookshelf.findChildren(cls):
                if card.item_id == item_id and card.isVisible():
                    return card
        self.fail("カードが見つからない")

    def test_double_click_then_edit_in_detail(self):
        from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog

        opened = []

        def fake_exec(dlg):
            # 詳細画面で編集・保存したことにする（書架が描き直され、カードが作り直される）
            opened.append(dlg.item_id)
            self.win.db.update_item_meta(dlg.item_id, "改題した書物", "クトゥルフ神話TRPG", "2人", "3時間")
            dlg.item_updated.emit(dlg.item_id)
            self._settle()
            return 0

        card = self._card(self.item_id)
        with patch.object(ItemDetailDialog, "exec", fake_exec):
            QTest.mouseDClick(card, Qt.LeftButton, Qt.NoModifier, card.rect().center())
            self._settle()

        self.assertEqual(opened, [self.item_id], "詳細画面が開かない・二重に開いた")
        self.assertEqual(self.errors, [], f"想定外のエラー: {self.errors}")
        # 描き直された書架から、もう一度開ける
        card = self._card(self.item_id)
        with patch.object(ItemDetailDialog, "exec", fake_exec):
            QTest.mouseDClick(card, Qt.LeftButton, Qt.NoModifier, card.rect().center())
            self._settle()
        self.assertEqual(len(opened), 2)
        self.assertEqual(self.errors, [])

    def test_context_menu_then_reload(self):
        from gui_qt.components.tag_context_menu import ScenarioContextMenu

        shown = []

        def fake_exec(menu, *args, **kwargs):
            shown.append(True)
            menu.favorite_toggled.emit(self.item_id, True)  # メニューの操作で書架が描き直される
            self._settle()

        card = self._card(self.item_id)
        with patch.object(ScenarioContextMenu, "exec", fake_exec):
            card.contextMenuEvent(type("E", (), {"globalPos": lambda self: QPoint(10, 10)})())
            self._settle()
        self.assertEqual(shown, [True])
        self.assertEqual(self.errors, [], f"想定外のエラー: {self.errors}")


if __name__ == "__main__":
    unittest.main()
