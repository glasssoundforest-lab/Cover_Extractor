"""ウィンドウサイズ・位置・最大化状態の保存・復元（メイン画面＆詳細画面）の検証テストスイート
tests/test_window_geometry_persistence.py
"""

import os
import sys
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

import app_settings
from core.database import Database
from gui_qt.main_window import MainWindow
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog


class TestWindowGeometryPersistence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.app.setFont(QFont("Yu Gothic UI", 9))
        cls.tmp_dir = tempfile.mkdtemp()

        cls.db_path = os.path.join(cls.tmp_dir, "test_catalog.db")
        cls.ini_path = os.path.join(cls.tmp_dir, "test_settings.ini")

        cls.orig_get_settings = app_settings.get_settings
        app_settings.get_settings = lambda: app_settings.Settings(cls.ini_path)

        cls.db = Database(cls.db_path)
        cls.item_id = cls.db.save_item(
            file_path="C:/scenarios/geom_test.pdf",
            title="ジオメトリ検証シナリオ",
            system_name="クトゥルフ神話TRPG",
            players_text="3〜4人",
            duration_text="4時間",
            overview="ウィンドウサイズ永続化のテストシナリオ。",
            synopsis="画面サイズの記憶と復元を検証するあらすじ。",
            thumbnail_bytes=None,
        )

    @classmethod
    def tearDownClass(cls):
        app_settings.get_settings = cls.orig_get_settings
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_01_main_window_geometry_save_and_restore(self):
        """メインウィンドウのサイズ・位置が settings.ini へ保存・復元されること"""
        app_settings.save_window_geometry(width=1320, height=860, maximized=False, x=110, y=90)

        win = MainWindow(db_path=self.db_path)
        win.show()
        self.app.processEvents()

        self.assertEqual(win.width(), 1320)
        self.assertEqual(win.height(), 860)

        # リサイズして閉じる
        win.resize(1400, 920)
        self.app.processEvents()
        win.close()
        self.app.processEvents()

        saved = app_settings.get_window_geometry()
        self.assertEqual(saved["width"], 1400)
        self.assertEqual(saved["height"], 920)

    def test_02_detail_dialog_geometry_save_and_restore(self):
        """シナリオ詳細画面（ItemDetailDialog）のサイズ・位置が settings.ini へ保存・復元されること"""
        app_settings.save_detail_window_geometry(width=1080, height=840, maximized=False, x=150, y=100)

        dlg = ItemDetailDialog(self.item_id, self.db, parent=None)
        dlg.show()
        self.app.processEvents()

        # 初回開いた時に指定サイズになっていること
        self.assertEqual(dlg.width(), 1080)
        self.assertEqual(dlg.height(), 840)

        # ユーザーがダイアログを拡大操作（例: 1200x900）
        dlg.resize(1200, 900)
        self.app.processEvents()

        # ダイアログを閉じる（reject / Esc / ×ボタン）
        dlg.reject()
        self.app.processEvents()

        # settings.ini の detail_window セクションに最新サイズが書き込まれていること
        saved = app_settings.get_detail_window_geometry()
        self.assertEqual(saved["width"], 1200)
        self.assertEqual(saved["height"], 900)

        # 再度別のシナリオや同一シナリオで開いた際、前回のサイズ（1200x900）が復元されること
        dlg2 = ItemDetailDialog(self.item_id, self.db, parent=None)
        dlg2.show()
        self.app.processEvents()

        self.assertEqual(dlg2.width(), 1200)
        self.assertEqual(dlg2.height(), 900)
        dlg2.reject()
        self.app.processEvents()

    def test_03_maximized_state_persistence(self):
        """最大化状態の保存と復元が正しく動作すること"""
        # メインウィンドウを最大化で保存
        app_settings.save_window_geometry(width=1260, height=820, maximized=True, x=100, y=100)
        win = MainWindow(db_path=self.db_path)
        win.show()
        self.app.processEvents()

        self.assertTrue(win.isMaximized())
        win.close()
        self.app.processEvents()

        # 詳細画面も最大化で保存
        app_settings.save_detail_window_geometry(width=1020, height=890, maximized=True, x=150, y=150)
        dlg = ItemDetailDialog(self.item_id, self.db, parent=None)
        dlg.show()
        self.app.processEvents()

        self.assertTrue(dlg.isMaximized())
        dlg.reject()
        self.app.processEvents()

    def test_04_legacy_geometry_compatibility(self):
        """旧来の main_geometry / detail_geometry 形式も正しくパースして復元できること"""
        s = app_settings.Settings(self.ini_path)
        s.set("window", "main_geometry", "1180x760+120+80", save=False)
        s.set("window", "main_maximized", "0", save=False)
        s.set("window", "detail_geometry", "960x780+200+140", save=False)
        s.set("window", "detail_maximized", "0", save=False)
        # width, height を削除して互換キーのみにする
        for sec in ["window", "detail_window"]:
            for key in ["width", "height", "x", "y", "maximized"]:
                s.cp.remove_option(sec, key) if s.cp.has_section(sec) else None
        s.save()

        main_geom = app_settings.get_window_geometry()
        self.assertEqual(main_geom["width"], 1180)
        self.assertEqual(main_geom["height"], 760)
        self.assertEqual(main_geom["x"], 120)
        self.assertEqual(main_geom["y"], 80)

        detail_geom = app_settings.get_detail_window_geometry()
        self.assertEqual(detail_geom["width"], 960)
        self.assertEqual(detail_geom["height"], 780)
        self.assertEqual(detail_geom["x"], 200)
        self.assertEqual(detail_geom["y"], 140)

    def test_05_detail_dialog_centered_on_parent(self):
        """詳細ダイアログが親ウィンドウ（MainWindow）の中央に表示されること"""
        win = MainWindow(db_path=self.db_path)
        win.resize(1100, 750)
        win.move(50, 50)
        win.show()
        self.app.processEvents()

        app_settings.save_detail_window_geometry(width=750, height=550, maximized=False)

        dlg = ItemDetailDialog(self.item_id, self.db, parent=win)
        dlg.show()
        self.app.processEvents()

        expected_y = win.y() + (win.height() - dlg.height()) // 2
        self.assertAlmostEqual(dlg.y(), expected_y, delta=4)

        dlg.reject()
        self.app.processEvents()
        win.close()


if __name__ == "__main__":
    unittest.main()
