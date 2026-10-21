"""詳細画面の情報元リンク機能テスト (tests/test_detail_source_links.py)

検証項目:
1. ドメインが booth の場合、情報元に「Booth」としてリンク表示されること
2. ドメインが booth 以外の場合、そのURLが表示されること
3. ファイル登録している場合、登録したファイル名またはフォルダ名が表示されること
4. ファイルリンククリック時に、フォルダであればそのフォルダ、ファイルならそのファイルが存在するフォルダが開かれること
5. 詳細画面のUIスクリーンショット保存
"""

import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt, QPoint, QEvent
from PySide6.QtWidgets import QApplication

from core.database import Database
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog


class TestDetailSourceLinks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_detail_source.db")
        cls.db = Database(cls.db_path)

        # 実際のテスト用ファイルとフォルダを作成
        cls.test_file_path = os.path.join(cls.tmp_dir, "狂気山脈_邪神の山嶺.pdf")
        with open(cls.test_file_path, "wb") as f:
            f.write(b"%PDF-1.4 test")

        cls.test_folder_path = os.path.join(cls.tmp_dir, "エモクロア_シナリオ集パック")
        os.makedirs(cls.test_folder_path, exist_ok=True)

        # 1. Booth URL + ファイル登録
        cls.item_id_booth_file = cls.db.save_item(
            file_path=cls.test_file_path,
            title="狂気山脈 〜邪神の山嶺〜",
            system_name="クトゥルフ神話TRPG",
            players_text="3〜4人",
            duration_text="4〜6時間",
            overview="南極最高峰に挑む登山家たちの過酷な挑戦と狂気。",
            synopsis="1930年代、南極大陸。前人未到の狂気山脈へと挑んだ探検隊――。",
            thumbnail_bytes=None,
        )
        cls.db.set_source_url(cls.item_id_booth_file, "https://dappleox.booth.pm/items/1234567")

        # 2. 一般URL + フォルダ登録
        cls.item_id_other_folder = cls.db.save_item(
            file_path=cls.test_folder_path,
            title="新約・コトダマの檻",
            system_name="エモクロアTRPG",
            players_text="2〜3人",
            duration_text="3時間",
            overview="言葉が変異する怪異に立ち向かう現代伝奇。",
            synopsis="",
            thumbnail_bytes=None,
        )
        cls.db.set_source_url(cls.item_id_other_folder, "https://talto.cc/scenarios/98765")

        # 3. Notion取り込みアイテム（ファイル + Booth URL + Notion連携）
        cls.item_id_notion_coexist = cls.db.save_item(
            file_path=cls.test_file_path,
            title="狂気山脈（Notion同期版）",
            system_name="クトゥルフ神話TRPG",
            players_text="3〜4人",
            duration_text="5時間",
            overview="Notionから情報を取り込んだシナリオ。",
            synopsis="南極の神秘。",
            thumbnail_bytes=None,
        )
        cls.db.set_source_url(cls.item_id_notion_coexist, "https://dappleox.booth.pm/items/1234567")
        cls.db.set_notion_link(cls.item_id_notion_coexist, "12345678-1234-1234-1234-123456789abc")

        # 4. Notionのみから取り込んだアイテム（ファイルなし、URLなし）
        cls.item_id_notion_only = cls.db.save_or_update_from_notion(
            page_id="87654321-4321-4321-4321-cba987654321",
            values={
                "title": "コーヒー一杯分の恐怖",
                "system_name": "新クトゥルフ神話TRPG",
                "players_text": "2-4人",
                "duration_text": "1時間",
                "overview": "喫茶店での恐怖体験。",
                "synopsis": "寒さの厳しい2月の冬。",
            }
        )

        cls.artifact_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
        os.makedirs(cls.artifact_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_01_booth_link_and_file_name_display(self):
        """Boothドメインの場合は『Booth』リンクとなり、ファイル名が表示されること"""
        dlg = ItemDetailDialog(self.item_id_booth_file, self.db, None, item_ids=[self.item_id_booth_file])
        dlg.resize(980, 720)
        dlg.show()
        self.app.processEvents()

        # 1. ファイルリンク検証
        self.assertFalse(dlg.file_link_label.isHidden())
        self.assertIn("狂気山脈_邪神の山嶺.pdf", dlg.file_link_label.text())
        self.assertIn("📄", dlg.file_link_label.text())
        self.assertIn("クリックしてフォルダを開きます", dlg.file_link_label.toolTip())

        # 2. Boothリンク検証
        self.assertFalse(dlg.url_label.isHidden())
        self.assertIn("Booth", dlg.url_label.text())
        self.assertIn("🔗", dlg.url_label.text())
        self.assertIn("dappleox.booth.pm", dlg.url_label.toolTip())

        # キャプチャ保存
        pix = dlg.grab()
        cap_path = os.path.join(self.artifact_dir, "test_detail_booth_and_file_link.png")
        pix.save(cap_path)
        self.assertTrue(os.path.exists(cap_path))

        dlg.close()
        self.app.processEvents()

    def test_02_folder_name_and_other_url_display(self):
        """フォルダ登録の場合はフォルダ名が表示され、一般URLはURLが表示されること"""
        dlg = ItemDetailDialog(self.item_id_other_folder, self.db, None, item_ids=[self.item_id_other_folder])
        dlg.resize(980, 720)
        dlg.show()
        self.app.processEvents()

        # 1. フォルダリンク検証
        self.assertFalse(dlg.file_link_label.isHidden())
        self.assertIn("エモクロア_シナリオ集パック", dlg.file_link_label.text())
        self.assertIn("📁", dlg.file_link_label.text())

        # 2. 一般URL検証
        self.assertFalse(dlg.url_label.isHidden())
        self.assertIn("talto.cc", dlg.url_label.text())

        dlg.close()
        self.app.processEvents()

    def test_03_file_link_click_opens_parent_folder(self):
        """ファイルリンククリック時にファイルが存在するフォルダが開かれること"""
        dlg = ItemDetailDialog(self.item_id_booth_file, self.db, None, item_ids=[self.item_id_booth_file])
        dlg.show()
        self.app.processEvents()

        with patch("subprocess.run") as mock_sub:
            dlg._on_file_link_clicked()
            # Windowsの場合 explorer.exe /select,<path> が呼ばれること
            if sys.platform == "win32":
                mock_sub.assert_called_once()
                args = mock_sub.call_args[0][0]
                self.assertEqual(args[0], "explorer.exe")
                self.assertIn("/select,", args[1])
                self.assertIn("狂気山脈_邪神の山嶺.pdf", args[1])

        dlg.close()
        self.app.processEvents()

    def test_04_folder_link_click_opens_folder(self):
        """フォルダリンククリック時にそのフォルダ自体が開かれること"""
        dlg = ItemDetailDialog(self.item_id_other_folder, self.db, None, item_ids=[self.item_id_other_folder])
        dlg.show()
        self.app.processEvents()

        if sys.platform == "win32":
            with patch("os.startfile") as mock_startfile:
                dlg._on_file_link_clicked()
                mock_startfile.assert_called_once_with(os.path.normpath(self.test_folder_path))

        dlg.close()
        self.app.processEvents()

    def test_05_notion_source_link_and_coexistence(self):
        """Notionから情報を取り込んだアイテムで、ファイル・WebURL・Notionがすべて併記されること"""
        dlg = ItemDetailDialog(self.item_id_notion_coexist, self.db, None, item_ids=[self.item_id_notion_coexist])
        dlg.resize(980, 720)
        dlg.show()
        self.app.processEvents()

        # 1. ファイルリンクが表示されていること
        self.assertFalse(dlg.file_link_label.isHidden())
        self.assertIn("狂気山脈_邪神の山嶺.pdf", dlg.file_link_label.text())

        # 2. Booth Webリンクが表示されていること
        self.assertFalse(dlg.url_label.isHidden())
        self.assertIn("Booth", dlg.url_label.text())

        # 3. Notionリンクが表示され、併記されていること
        self.assertFalse(dlg.notion_link_label.isHidden())
        self.assertIn("Notion", dlg.notion_link_label.text())
        self.assertIn("📓", dlg.notion_link_label.text())
        self.assertIn("12345678123412341234123456789abc", dlg.notion_link_label.toolTip())

        # キャプチャ保存
        pix = dlg.grab()
        cap_path = os.path.join(self.artifact_dir, "test_detail_notion_coexistence.png")
        pix.save(cap_path)
        self.assertTrue(os.path.exists(cap_path))

        dlg.close()
        self.app.processEvents()

    def test_06_notion_only_source_link(self):
        """Notionのみから取り込んだアイテム（ローカルファイルなし）で、情報元にNotionが表示されること"""
        dlg = ItemDetailDialog(self.item_id_notion_only, self.db, None, item_ids=[self.item_id_notion_only])
        dlg.resize(980, 720)
        dlg.show()
        self.app.processEvents()

        # 1. ファイルリンクは非表示
        self.assertTrue(dlg.file_link_label.isHidden())

        # 2. Web URLリンクは非表示（「未設定」にはならず、Notionが表示される）
        self.assertTrue(dlg.url_label.isHidden())

        # 3. Notionリンクが表示されていること
        self.assertFalse(dlg.notion_link_label.isHidden())
        self.assertIn("Notion", dlg.notion_link_label.text())
        self.assertIn("87654321432143214321cba987654321", dlg.notion_link_label.toolTip())

        # キャプチャ保存
        pix = dlg.grab()
        cap_path = os.path.join(self.artifact_dir, "test_detail_notion_only.png")
        pix.save(cap_path)
        self.assertTrue(os.path.exists(cap_path))

        dlg.close()
        self.app.processEvents()

    def test_07_notion_link_click(self):
        """Notionリンククリック時にNotionページURLが開かれること"""
        dlg = ItemDetailDialog(self.item_id_notion_coexist, self.db, None, item_ids=[self.item_id_notion_coexist])
        dlg.show()
        self.app.processEvents()

        with patch("PySide6.QtGui.QDesktopServices.openUrl") as mock_open:
            dlg._on_notion_link_clicked()
            mock_open.assert_called_once()
            called_url = mock_open.call_args[0][0].toString()
            self.assertIn("https://www.notion.so/12345678123412341234123456789abc", called_url)

        dlg.close()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
