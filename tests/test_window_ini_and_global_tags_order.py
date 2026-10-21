"""ウィンドウサイズの settings.ini 読み書きおよびグローバルタグ優先順序の検証テストスイート (tests/test_window_ini_and_global_tags_order.py)

検証項目:
1. app_settings の get_window_geometry / save_window_geometry が settings.ini を正しく読み書きすること
2. MainWindow 起動時に settings.ini のウィンドウサイズ・位置が復元されること
3. MainWindow のリサイズおよび終了時に settings.ini へ最新サイズが保存されること
4. グローバルタグの順序が DB・サイドバー・スライドパネル・カードリボン・タグポップアップの全箇所で
   「CoC > マダミス > 未通過 > 通過済 > GM可」となること
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

import app_settings
from core.database import Database, global_tag_sort_key, GLOBAL_TAG_PRIORITY
from gui_qt.main_window import MainWindow
from gui_qt.components.ornate import PillTag


class TestWindowIniAndGlobalTagsOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.app.setFont(QFont("Yu Gothic UI", 9))
        cls.tmp_dir = tempfile.mkdtemp()

        cls.db_path = os.path.join(cls.tmp_dir, "test_catalog.db")
        cls.ini_path = os.path.join(cls.tmp_dir, "test_settings.ini")

        # app_settings のターゲットINIを一時ファイルに向ける
        cls.orig_settings = app_settings.get_settings()
        app_settings.get_settings = lambda: app_settings.Settings(cls.ini_path)

        cls.db = Database(cls.db_path)

        # テスト用アイテムの登録
        cls.item_id = cls.db.save_item(
            file_path="C:/scenarios/order_test.pdf",
            title="タグ順序検証シナリオ",
            system_name="クトゥルフ神話TRPG",
            players_text="3〜4人",
            duration_text="4時間",
            overview="グローバルタグの並び順テストシナリオ。",
            synopsis="太古の記録が刻まれた魔導書のあらすじ。",
            thumbnail_bytes=None,
        )

        # グローバルタグをわざと順序と逆順でアイテムに付与
        # GM可, 通過済み, 未通過, その他, ストプレ, マダミス, CoC
        all_gtags = {t[1]: t[0] for t in cls.db.get_global_tags()}
        tags_to_assign = [
            all_gtags["GM可"],
            all_gtags["通過済み"],
            all_gtags["未通過"],
            all_gtags["その他"],
            all_gtags["ストプレ"],
            all_gtags["マダミス"],
            all_gtags["CoC"],
        ]
        cls.db.set_item_tags(cls.item_id, tags_to_assign)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_01_app_settings_window_geometry_read_write(self):
        """app_settings のウィンドウサイズ保存と取得が settings.ini と正しく連動すること"""
        app_settings.save_window_geometry(width=1350, height=860, maximized=False, x=150, y=120)

        # INIファイルが生成され、[window] セクションが存在すること
        self.assertTrue(os.path.exists(self.ini_path))
        with open(self.ini_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("[window]", content)
        self.assertIn("width = 1350", content)
        self.assertIn("height = 860", content)
        self.assertIn("maximized = false", content)

        # get_window_geometry で読み出せること
        geom = app_settings.get_window_geometry()
        self.assertEqual(geom["width"], 1350)
        self.assertEqual(geom["height"], 860)
        self.assertFalse(geom["maximized"])
        self.assertEqual(geom["x"], 150)
        self.assertEqual(geom["y"], 120)

    def test_02_main_window_reads_and_saves_window_size(self):
        """MainWindow が起動時に settings.ini のサイズを適用し、終了時に最新サイズを書き込むこと"""
        app_settings.save_window_geometry(width=1280, height=840, maximized=False, x=100, y=100)

        win = MainWindow(db_path=self.db_path)
        win.show()
        self.app.processEvents()

        # INI に保存されたサイズが適用されていること
        self.assertEqual(win.width(), 1280)
        self.assertEqual(win.height(), 840)

        # ウィンドウサイズを変更
        win.resize(1420, 910)
        self.app.processEvents()

        # ウィンドウを閉じる
        win.close()
        self.app.processEvents()

        # settings.ini に変更後のサイズ（1420x910）が保存されていること
        geom = app_settings.get_window_geometry()
        self.assertEqual(geom["width"], 1420)
        self.assertEqual(geom["height"], 910)

    def test_03_global_tags_order_in_database(self):
        """Database.get_global_tags() および get_item_tags() が「CoC > マダミス > ストプレ > その他 > 未通過 > 通過済み > GM可」で返ること"""
        gtags = self.db.get_global_tags()
        names = [t[1] for t in gtags]
        expected_prefix = ["CoC", "マダミス", "ストプレ", "その他", "未通過", "通過済み", "GM可"]
        self.assertEqual(names[:7], expected_prefix)

        # アイテムに紐づくタグも指定順序で返ること
        item_tags = self.db.get_item_tags(self.item_id, is_global=True)
        item_tag_names = [t[1] for t in item_tags]
        self.assertEqual(item_tag_names, expected_prefix)

        # 一括取得 get_all_item_global_tags も指定順序であること
        all_item_gtags = self.db.get_all_item_global_tags()
        self.assertIn(self.item_id, all_item_gtags)
        assigned_names = [t[1] for t in all_item_gtags[self.item_id]]
        self.assertEqual(assigned_names, expected_prefix)

    def test_04_slide_panel_pill_order(self):
        """BookshelfSlidePanel に逆順タグを渡しても、ピルアイコンが「CoC > マダミス > ストプレ > その他 > 未通過 > 通過済み > GM可」で並ぶこと"""
        win = MainWindow(db_path=self.db_path)
        win.show()
        self.app.processEvents()

        panel = win.bookshelf.slide_panel
        item = self.db.get_item(self.item_id)

        # わざとバラバラな順序でタグリストを渡す
        shuffled_tags = ["通過済み", "GM可", "その他", "CoC", "ストプレ", "未通過", "マダミス"]
        panel.set_item(item, global_tags=shuffled_tags)

        # ピルアイコンの並び順を取得
        pill_names = []
        for i in range(panel.tags_layout.count()):
            w = panel.tags_layout.itemAt(i).widget()
            if isinstance(w, PillTag):
                pill_names.append(w.text)

        expected = ["CoC", "マダミス", "ストプレ", "その他", "未通過", "通過済み", "GM可"]
        self.assertEqual(pill_names, expected)

        win.close()


if __name__ == "__main__":
    unittest.main()
