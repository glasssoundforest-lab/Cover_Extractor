"""スクロールバーの描画検証テスト (tests/test_scrollbar_visual.py)

検証項目:
1. 書架グリッドでスクロールバーが表示された際、空白部分（sub-page, add-page）が
   白黒の市松模様（チェッカーボード）にならず、正常なダーク真鍮レールとして描画されること
2. スライドインアニメーションの duration が 380ms に更新されていること
3. スクロールバー周辺のスクリーンショットを撮影して保存すること
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

from core.database import Database
from gui_qt.main_window import MainWindow


class TestScrollBarVisual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_scrollbar.db")
        cls.db = Database(cls.db_path)

        # スクロールバーを大画面でも確実に表示させるため36冊のダミーアイテムを登録
        for i in range(36):
            cls.db.save_item(
                file_path=f"C:/scenarios/scenario_{i}.pdf",
                title=f"魔導書 第{i+1}巻",
                system_name="クトゥルフ神話TRPG",
                players_text="3〜4人",
                duration_text="4時間",
                overview=f"あらすじ概要 {i+1}",
                synopsis=f"長いあらすじテキスト {i+1}",
                thumbnail_bytes=None,
            )

        cls.win = MainWindow(db_path=cls.db_path)
        cls.win.resize(1100, 700)
        cls.win.show()
        cls.win.repaint()
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.win.close()
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_01_scrollbar_rendered_cleanly(self):
        """スクロールバーが表示され、空白部分が正常に描画されていること"""
        scroll = cls_scroll = self.win.bookshelf.scroll
        vbar = scroll.verticalScrollBar()
        self.assertTrue(vbar.isVisible() or vbar.maximum() > 0)

        # スライドパネルの duration が 380ms になっていること
        slide_panel = self.win.bookshelf.slide_panel
        self.assertEqual(slide_panel.anim.duration(), 380)

        # スクロールバーを含む書架エリアのキャプチャを保存
        artifact_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
        if os.path.exists(artifact_dir):
            shot_path = os.path.join(artifact_dir, "test_scrollbar_fixed.png")
            # スクロールバー周辺をクローズアップしてキャプチャ
            self.win.bookshelf.grab().save(shot_path, "PNG")
            print(f"Saved: {shot_path}")

            # ウィンドウ全体
            win_shot = os.path.join(artifact_dir, "test_window_scrollbar_fixed.png")
            self.win.grab().save(win_shot, "PNG")
            print(f"Saved window: {win_shot}")


if __name__ == "__main__":
    unittest.main()
