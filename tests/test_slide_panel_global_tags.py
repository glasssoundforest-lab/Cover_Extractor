"""スライドイン詳細パネルのタイトル右側グローバルタグ（ピルアイコン）表示のテストスイート (tests/test_slide_panel_global_tags.py)

検証項目:
1. BookshelfSlidePanel にグローバルタグを渡した際、タイトル右側の tags_layout に PillTag が動的に配置されること
2. 別のアイテム（タグなし）をセットした際、過去のピルタグが確実にクリアされること
3. BookshelfGrid のカードホバー連動で、DBに登録されたグローバルタグが自動取得されてピルアイコン表示されること
4. 西洋古書調のピルアイコン（カラーインジケータ、タグ名、丸みのある真鍮ボーダー）のスタイリングとスクリーンショット撮影
"""

import os
import sys
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from core.database import Database
from gui_qt.main_window import MainWindow
from gui_qt.components.bookshelf_grid import BookshelfSlidePanel
from gui_qt.components.ornate import PillTag


class TestSlidePanelGlobalTags(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.app.setFont(QFont("Yu Gothic UI", 9))
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_slide_tags.db")
        cls.db = Database(cls.db_path)

        # テストデータの投入
        cls.item_id_1 = cls.db.save_item(
            file_path="C:/scenarios/call_of_cthulhu.pdf",
            title="狂気山脈 〜邪神の山嶺〜",
            system_name="クトゥルフ神話TRPG",
            players_text="3〜4人",
            duration_text="4〜6時間",
            overview="南極最高峰に挑む登山家たちの過酷な挑戦と狂気。",
            synopsis="1930年代、南極大陸。前人未到の狂気山脈へと挑んだ探検隊が遭遇したものは、太古の異形と凍てつく絶望であった――。",
            thumbnail_bytes=None,
        )

        # グローバルタグの作成と付与
        # 1つ目: キャンペーン (真鍮レッド系 #8b261e)
        cls.tag_camp_id = cls.db.add_tag("キャンペーン", color="#8b261e", is_global=True)
        # 2つ目: 初心者向け (深緑系 #245c36)
        cls.tag_begin_id = cls.db.add_tag("初心者向け", color="#245c36", is_global=True)
        # 3つ目: 公式シナリオ (金茶系 #a67c2e)
        cls.tag_official_id = cls.db.add_tag("公式シナリオ", color="#a67c2e", is_global=True)

        cls.db.set_item_tags(cls.item_id_1, [cls.tag_camp_id, cls.tag_begin_id])

        cls.item_id_2 = cls.db.save_item(
            file_path="C:/scenarios/no_tags.pdf",
            title="名もなき古文書",
            system_name="エモクロアTRPG",
            players_text="1人",
            duration_text="1時間",
            overview="タグが存在しないシナリオのテストデータ。",
            synopsis="",
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

    def test_01_slide_panel_direct_set_item_with_global_tags(self):
        """BookshelfSlidePanel にグローバルタグを渡した際のピルタグ生成と消去の検証"""
        panel = self.win.bookshelf.slide_panel
        self.assertIsInstance(panel, BookshelfSlidePanel)

        # 1. 2つのタグを持つアイテムをセット
        item1 = self.db.get_item(self.item_id_1)
        gtags1 = [("キャンペーン", "#8b261e"), ("初心者向け", "#245c36")]
        panel.set_item(item1, global_tags=gtags1)

        self.assertEqual(panel.title_lbl.text(), "狂気山脈 〜邪神の山嶺〜")
        self.assertEqual(panel.tags_layout.count(), 2)

        pill0 = panel.tags_layout.itemAt(0).widget()
        self.assertIsInstance(pill0, PillTag)
        self.assertEqual(pill0.text, "キャンペーン")
        self.assertEqual(pill0.tag_color, "#8b261e")

        pill1 = panel.tags_layout.itemAt(1).widget()
        self.assertIsInstance(pill1, PillTag)
        self.assertEqual(pill1.text, "初心者向け")
        self.assertEqual(pill1.tag_color, "#245c36")

        # 2. タグなしアイテムをセットした場合、ピルが全削除されること
        item2 = self.db.get_item(self.item_id_2)
        panel.set_item(item2, global_tags=[])
        self.assertEqual(panel.title_lbl.text(), "名もなき古文書")
        self.assertEqual(panel.tags_layout.count(), 0)

    def test_02_bookshelf_hover_integration_with_global_tags(self):
        """カードホバー時にDBからグローバルタグが取得され、スライドパネルにピル表示されること"""
        bookshelf = self.win.bookshelf
        panel = bookshelf.slide_panel

        # 書架のカードから狂気山脈カードを探す
        target_card = None
        for card in bookshelf.cards:
            if card.item_id == self.item_id_1:
                target_card = card
                break
        self.assertIsNotNone(target_card, "狂気山脈カードが存在すること")

        # ホバーイベントをシミュレート
        bookshelf._on_card_hover_entered(target_card.item)
        self.app.processEvents()

        # パネルが狂気山脈の情報になり、タグが2個表示されていること
        self.assertEqual(panel.title_lbl.text(), "狂気山脈 〜邪神の山嶺〜")
        self.assertEqual(panel.tags_layout.count(), 2)

        tag_names = [panel.tags_layout.itemAt(i).widget().text for i in range(panel.tags_layout.count())]
        self.assertIn("キャンペーン", tag_names)
        self.assertIn("初心者向け", tag_names)

        # スライドパネルをアニメーション完了状態にして表示
        panel.move(14, panel.show_y)
        panel.show()
        self.app.processEvents()

        # スクリーンショットをアーティファクトディレクトリに保存
        artifact_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
        if os.path.exists(artifact_dir):
            screenshot_path = os.path.join(artifact_dir, "test_slide_panel_global_tag_pills.png")
            panel_pixmap = panel.grab()
            panel_pixmap.save(screenshot_path, "PNG")
            self.assertTrue(os.path.exists(screenshot_path))
            print(f"Captured slide panel screenshot: {screenshot_path}")

            # ウィンドウ全体のスクリーンショットも撮影
            win_screenshot_path = os.path.join(artifact_dir, "test_window_slide_panel_pills.png")
            win_pixmap = self.win.grab()
            win_pixmap.save(win_screenshot_path, "PNG")
            self.assertTrue(os.path.exists(win_screenshot_path))
            print(f"Captured window screenshot: {win_screenshot_path}")


if __name__ == "__main__":
    unittest.main()
