"""メインウィンドウの自由なリサイズ・解像度最適化・レスポンシブ動作テスト (tests/test_window_resizing_and_responsiveness.py)

検証項目:
1. 最小サイズ（900x600）の適用と極小化防止
2. 自由なサイズ変更（小型 960x640、標準 1260x820、大型 1500x900）への適応
3. リサイズ境界（四辺・四隅）におけるエッジ判定とカーソル形状変更
4. 下部ステータスバー右端のリサイズグリップ（QSizeGrip）の存在
5. 最大化・通常表示のトグルと書架グリッドの列数追従
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QColor

from core.database import Database
from gui_qt.main_window import MainWindow

app = QApplication.instance() or QApplication(sys.argv)
TEST_DB = "tests/test_resize.db"


class TestWindowResizingAndResponsiveness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        cls.db = Database(TEST_DB)
        # テスト用アイテムをいくつか登録
        for i in range(8):
            cls.db.save_item(
                file_path=f"test_res_{i}.pdf",
                title=f"シナリオ巻 {i+1}",
                system_name="CoC",
                players_text="2-4人",
                duration_text="3時間",
                overview="概要テキスト",
                synopsis="あらすじテキスト",
                thumbnail_bytes=None,
            )

        cls.window = MainWindow(db_path=TEST_DB)
        cls.window.show()
        QApplication.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        try:
            cls.db.conn.close()
        except Exception:
            pass
        if os.path.exists(TEST_DB):
            try:
                os.remove(TEST_DB)
            except Exception:
                pass

    def test_01_minimum_size_and_limits(self):
        """1. 最小サイズ（900x600）が設定され、それ未満への過剰な縮小が制限されることの検証"""
        min_sz = self.window.minimumSize()
        self.assertGreaterEqual(min_sz.width(), 900)
        self.assertGreaterEqual(min_sz.height(), 600)

        # 800x400 への縮小を試みても 900x600 で止まること
        self.window.resize(800, 400)
        QApplication.processEvents()
        self.assertGreaterEqual(self.window.width(), 900)
        self.assertGreaterEqual(self.window.height(), 600)

    def test_02_free_resize_small_medium_large(self):
        """2. 小型・標準・大型への自由なサイズ変更と書架グリッドの追従テスト"""
        artifact_dir = os.environ.get("ANTIGRAVITY_ARTIFACT_DIR", r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449")

        # (a) 小型ウィンドウ (960 x 640) - 小画面・ノートPC想定
        self.window.resize(960, 640)
        QApplication.processEvents()
        self.assertEqual(self.window.width(), 960)
        self.assertEqual(self.window.height(), 640)
        small_cols = self.window.bookshelf.column_count()
        self.assertGreaterEqual(small_cols, 2)
        self.window.grab().save(os.path.join(artifact_dir, "test_window_resized_small_960x640.png"))

        # (b) 標準ウィンドウ (1260 x 820)
        self.window.resize(1260, 820)
        QApplication.processEvents()
        self.assertEqual(self.window.width(), 1260)
        self.assertEqual(self.window.height(), 820)
        med_cols = self.window.bookshelf.column_count()
        self.assertGreaterEqual(med_cols, small_cols)
        self.window.grab().save(os.path.join(artifact_dir, "test_window_resized_standard_1260x820.png"))

        # (c) 大型ウィンドウ (1500 x 900) - WQHD/4K/大画面想定
        self.window.resize(1500, 900)
        QApplication.processEvents()
        self.assertEqual(self.window.width(), 1500)
        self.assertEqual(self.window.height(), 900)
        large_cols = self.window.bookshelf.column_count()
        self.assertGreaterEqual(large_cols, med_cols)
        self.window.grab().save(os.path.join(artifact_dir, "test_window_resized_large_1500x900.png"))

    def test_03_resize_edges_and_cursor_detection(self):
        """3. 四辺および四隅の端座標で適切なリサイズエッジとカーソルが判定されるか検証"""
        w = self.window.width()
        h = self.window.height()

        # 左端
        edges, cur = self.window._get_resize_edge(QPoint(2, h // 2))
        self.assertEqual(edges, Qt.LeftEdge)
        self.assertEqual(cur, Qt.SizeHorCursor)

        # 右端
        edges, cur = self.window._get_resize_edge(QPoint(w - 2, h // 2))
        self.assertEqual(edges, Qt.RightEdge)
        self.assertEqual(cur, Qt.SizeHorCursor)

        # 上端
        edges, cur = self.window._get_resize_edge(QPoint(w // 2, 2))
        self.assertEqual(edges, Qt.TopEdge)
        self.assertEqual(cur, Qt.SizeVerCursor)

        # 下端
        edges, cur = self.window._get_resize_edge(QPoint(w // 2, h - 2))
        self.assertEqual(edges, Qt.BottomEdge)
        self.assertEqual(cur, Qt.SizeVerCursor)

        # 右下角
        edges, cur = self.window._get_resize_edge(QPoint(w - 2, h - 2))
        self.assertEqual(edges, Qt.BottomEdge | Qt.RightEdge)
        self.assertEqual(cur, Qt.SizeFDiagCursor)

        # 左上角
        edges, cur = self.window._get_resize_edge(QPoint(2, 2))
        self.assertEqual(edges, Qt.TopEdge | Qt.LeftEdge)
        self.assertEqual(cur, Qt.SizeFDiagCursor)

        # 中央（リサイズ対象外）
        edges, cur = self.window._get_resize_edge(QPoint(w // 2, h // 2))
        self.assertIsNone(edges)
        self.assertEqual(cur, Qt.ArrowCursor)

    def test_04_size_grip_in_status_bar(self):
        """4. ステータスバー右端に QSizeGrip が配置されていることの検証"""
        sbar = self.window.status_bar
        self.assertTrue(hasattr(sbar, "size_grip"))
        self.assertTrue(sbar.size_grip.isVisible())
        self.assertEqual(sbar.size_grip.cursor().shape(), Qt.SizeFDiagCursor)

    def test_05_maximize_and_restore(self):
        """5. 最大化ボタンおよび元に戻す動作の検証"""
        tbar = self.window.title_bar
        self.assertTrue(hasattr(tbar, "max_btn"))

        # 最大化
        tbar._toggle_maximize_window()
        QApplication.processEvents()
        self.assertTrue(self.window.isMaximized())

        # 元に戻す
        tbar._toggle_maximize_window()
        QApplication.processEvents()
        self.assertFalse(self.window.isMaximized())


if __name__ == "__main__":
    unittest.main()
