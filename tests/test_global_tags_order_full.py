"""グローバルタグ新順序（CoC > マダミス > ストプレ > その他 > 未通過 > 通過済 > GM可）のUI統合検証テスト (tests/test_global_tags_order_full.py)

検証項目:
1. Database の初期グローバルタグに「ストプレ」と「その他」がマダミスの後ろに含まれること
2. MainWindow 起動時にサイドバーのグローバルタグ一覧がユーザー指定の新順序で整列すること
3. スライドイン詳細パネルにタグを渡した際、ピルアイコンが新順序で並ぶこと
4. 画面キャプチャを撮影して視覚的に確認すること
"""

import os
import sys
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from core.database import Database, GLOBAL_TAG_PRIORITY
from gui_qt.main_window import MainWindow
from gui_qt.components.ornate import PillTag


class TestGlobalTagsOrderFull(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_gtags_order.db")
        cls.db = Database(cls.db_path)

        # テストデータの投入
        cls.item_id = cls.db.save_item(
            file_path="C:/scenarios/story_playing.pdf",
            title="終焉のオーケストラ",
            system_name="ストーリープレイング",
            players_text="2人",
            duration_text="3時間",
            overview="二人だけで紡ぐ、世界の終わりの物語。",
            synopsis="滅びゆく世界で奏でられる最後の旋律。二人の運命が交錯する――。",
            thumbnail_bytes=None,
        )

        cls.win = MainWindow(db_path=cls.db_path)
        cls.win.resize(1260, 800)
        cls.win.show()
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.win.close()
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_01_global_tags_in_database(self):
        """DBから取得されるグローバルタグが新順序（CoC > マダミス > ストプレ > その他 > 未通過 > 通過済み > GM可）であること"""
        gtags = self.db.get_global_tags()
        names = [t[1] for t in gtags]
        expected = ["CoC", "マダミス", "ストプレ", "その他", "未通過", "通過済み", "GM可"]
        self.assertEqual(names, expected)

    def test_02_sidebar_global_tags_order(self):
        """サイドバーに表示されるグローバルタグが新順序で並んでいること"""
        sidebar = self.win.sidebar
        tag_widgets = sidebar.tag_widgets
        # グローバルタグの名前を取得
        sidebar_gtag_names = [name for name in tag_widgets if name in GLOBAL_TAG_PRIORITY]
        expected = ["CoC", "マダミス", "ストプレ", "その他", "未通過", "通過済み", "GM可"]
        self.assertEqual(sidebar_gtag_names, expected)

    def test_03_slide_panel_pills_order(self):
        """スライドパネルのピルアイコンが新順序で並ぶこと"""
        panel = self.win.bookshelf.slide_panel
        item = self.db.get_item(self.item_id)
        # わざとバラバラにタグを渡す
        shuffled = ["その他", "GM可", "ストプレ", "通過済み", "CoC", "未通過", "マダミス"]
        panel.set_item(item, global_tags=shuffled)

        pill_names = []
        for i in range(panel.tags_layout.count()):
            w = panel.tags_layout.itemAt(i).widget()
            if isinstance(w, PillTag):
                pill_names.append(w.text)

        expected = ["CoC", "マダミス", "ストプレ", "その他", "未通過", "通過済み", "GM可"]
        self.assertEqual(pill_names, expected)

    def test_04_capture_screenshots(self):
        """ウィンドウ全体のスクリーンショットを撮影して保存すること"""
        self.app.processEvents()
        artifact_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
        if os.path.exists(artifact_dir):
            win_shot = os.path.join(artifact_dir, "test_global_tags_order_full.png")
            self.win.grab().save(win_shot, "PNG")
            print(f"Saved: {win_shot}")


if __name__ == "__main__":
    unittest.main()
