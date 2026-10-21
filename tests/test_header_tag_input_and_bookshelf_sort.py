import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication

from core.database import Database
from gui_qt.main_window import MainWindow

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

class TestHeaderTagInputAndBookshelfSort(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db_path = "tests/test_header_sort.db"
        if os.path.exists(cls.test_db_path):
            os.remove(cls.test_db_path)
        cls.db = Database(cls.test_db_path)
        cls.db.add_tag("CoC", is_global=1)
        cls.db.add_tag("マダミス", is_global=1)
        cls.window = MainWindow(db_path=cls.test_db_path)
        cls.window.resize(1200, 800)
        cls.window.show()
        QApplication.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        if os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass

    def test_01_bookshelf_sort_in_top_right(self):
        """1. 書架一覧の枠右上に並び順コンボボックスが配置されているかテスト"""
        bookshelf = self.window.bookshelf
        self.assertTrue(hasattr(bookshelf, "sort_combo"))
        self.assertTrue(bookshelf.sort_combo.isVisible())
        self.assertEqual(bookshelf.sort_combo.count(), 7)

        # ヘッダー側の sort_combo は非表示になっていること
        self.assertFalse(self.window.header_bar.sort_combo.isVisible())

        # ソート変更が MainWindow に反映されるかテスト
        idx = bookshelf.sort_combo.findData("title_asc")
        self.assertNotEqual(idx, -1)
        bookshelf.sort_combo.setCurrentIndex(idx)
        QApplication.processEvents()
        self.assertEqual(self.window.current_sort, "title_asc")

    def test_02_search_container_and_tag_embed(self):
        """2. 検索入力枠コンテナ内へのタグ選択内包と、右側への検索種別配置テスト"""
        header = self.window.header_bar
        self.assertTrue(hasattr(header, "search_container"))
        self.assertTrue(hasattr(header, "tag_select_btn"))
        self.assertTrue(hasattr(header, "search_edit"))
        self.assertTrue(hasattr(header, "search_type_combo"))

        # tag_select_btn と search_edit の親が search_container であること
        self.assertEqual(header.tag_select_btn.parent(), header.search_container)
        self.assertEqual(header.search_edit.parent(), header.search_container)

        # 検索の種類（search_type_combo）が検索バーコンテナ（search_container）の右側に配置されていること
        pos_container = header.search_container.mapToGlobal(QPoint(0, 0))
        pos_type = header.search_type_combo.mapToGlobal(QPoint(0, 0))
        self.assertGreater(pos_type.x(), pos_container.x())

    def test_03_tag_visibility_toggle_by_search_type(self):
        """3. タグを含まない検索（題名検索など）でタグ選択項目が消え、タグ検索等で現れるかのテスト"""
        header = self.window.header_bar

        # (a) 初期状態（すべて検索: all）ではタグ選択ボタンが表示
        all_idx = header.search_type_combo.findData("all")
        header.search_type_combo.setCurrentIndex(all_idx)
        QApplication.processEvents()
        self.assertTrue(header.tag_select_btn.isVisible())

        artifact_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
        self.window.grab().save(os.path.join(artifact_dir, "test_header_all_search_with_tag_btn.png"))

        # (b) 題名検索 (title): タグを含まないためタグ選択ボタンが非表示（消える）
        title_idx = header.search_type_combo.findData("title")
        header.search_type_combo.setCurrentIndex(title_idx)
        QApplication.processEvents()
        self.assertFalse(header.tag_select_btn.isVisible())
        self.assertEqual(header.search_edit.placeholderText(), "題名で検索...")

        self.window.grab().save(os.path.join(artifact_dir, "test_header_title_search_no_tag_btn.png"))

        # (c) システム検索 (system): タグを含まないためタグ選択ボタンが非表示（消える）
        sys_idx = header.search_type_combo.findData("system")
        header.search_type_combo.setCurrentIndex(sys_idx)
        QApplication.processEvents()
        self.assertFalse(header.tag_select_btn.isVisible())
        self.assertEqual(header.search_edit.placeholderText(), "システム名で検索...")

        # (d) タグ検索 (tag): タグ検索のためタグ選択ボタンが再表示される
        tag_idx = header.search_type_combo.findData("tag")
        header.search_type_combo.setCurrentIndex(tag_idx)
        QApplication.processEvents()
        self.assertTrue(header.tag_select_btn.isVisible())
        self.assertEqual(header.search_edit.placeholderText(), "タグ名で検索（未設定も可）...")

        self.window.grab().save(os.path.join(artifact_dir, "test_header_tag_search_mode.png"))

if __name__ == "__main__":
    unittest.main()
