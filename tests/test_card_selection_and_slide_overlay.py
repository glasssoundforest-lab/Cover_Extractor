"""カード選択解除と書架枠下辺あらすじ・概要スライドイン機能のテストスイート (tests/test_card_selection_and_slide_overlay.py)

検証項目:
1. カード選択・同一カード再クリックによるトグル解除
2. 書架背景（余白）クリックによる選択解除
3. 書架一覧枠の下辺から競り上がるあらすじ・概要スライドインパネル（BookshelfSlidePanel）の構造とテキスト
4. ホバー時のスライドインおよび離脱時のスライドアウト動作
5. 一覧（リスト）モードでの書架下部スライドイン連動
6. スライドイン状態・選択中・選択解除時の画面キャプチャ保存
"""

import os
import sys
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt, QPoint, QEvent, QPointF
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from core.database import Database
from gui_qt.main_window import MainWindow
from gui_qt.components.bookshelf_grid import BookshelfSlidePanel


class TestCardSelectionAndSlideOverlay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_slide.db")
        cls.db = Database(cls.db_path)

        # テストデータの投入（あらすじあり、概要あり、両方なし）
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
        cls.db.set_favorite(cls.item_id_1, True)
        cls.db.set_bookmarked(cls.item_id_1, True)

        cls.item_id_2 = cls.db.save_item(
            file_path="C:/scenarios/emoklore.pdf",
            title="新約・コトダマの檻",
            system_name="エモクロアTRPG",
            players_text="2〜3人",
            duration_text="3時間",
            overview="言葉が変異する怪異に立ち向かう現代伝奇。",
            synopsis="",  # あらすじなし、概要のみ
            thumbnail_bytes=None,
        )

        cls.item_id_3 = cls.db.save_item(
            file_path="C:/scenarios/empty_info.pdf",
            title="空白の魔導書",
            system_name="その他",
            players_text="",
            duration_text="",
            overview="",
            synopsis="",  # 両方なし
            thumbnail_bytes=None,
        )

        cls.artifact_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
        os.makedirs(cls.artifact_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def setUp(self):
        self.win = MainWindow(db_path=self.db_path)
        self.win.resize(1100, 750)
        self.win.show()
        self.app.processEvents()

    def tearDown(self):
        self.win.close()
        self.app.processEvents()

    def test_01_card_selection_and_toggle_clear(self):
        """カードをクリックで選択し、同じカードを再クリックして解除できること"""
        bookshelf = self.win.bookshelf
        self.assertGreater(len(bookshelf.cards), 0)
        card1 = bookshelf.cards[0]
        item_id_1 = card1.item_id

        # 1. 最初のクリックで選択
        card1.clicked.emit(item_id_1)
        self.app.processEvents()
        self.assertEqual(bookshelf.selected_item_id, item_id_1)
        self.assertTrue(card1.is_selected)
        self.assertIsNotNone(self.win.selected_item)
        self.assertEqual(self.win.selected_item[0], item_id_1)
        self.assertIn(f"選択中: {card1.title_text}", self.win.status_bar.info_label.text())

        # 2. 同一カードの再クリックで選択解除
        card1.clicked.emit(item_id_1)
        self.app.processEvents()
        self.assertIsNone(bookshelf.selected_item_id)
        self.assertFalse(card1.is_selected)
        self.assertIsNone(self.win.selected_item)
        self.assertIn("選択なし", self.win.status_bar.info_label.text())

    def test_02_bookshelf_background_click_clears_selection(self):
        """書架の余白（背景）をクリックした時に選択が解除されること"""
        bookshelf = self.win.bookshelf
        card1 = bookshelf.cards[0]
        card1.clicked.emit(card1.item_id)
        self.app.processEvents()
        self.assertEqual(bookshelf.selected_item_id, card1.item_id)

        # 書架の空き余白領域を左クリック
        vp = bookshelf.scroll.viewport()
        press_ev = QMouseEvent(
            QEvent.MouseButtonPress,
            QPointF(vp.width() - 5, vp.height() - 5),
            QPointF(vp.width() - 5, vp.height() - 5),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        QApplication.sendEvent(vp, press_ev)
        self.app.processEvents()

        self.assertIsNone(bookshelf.selected_item_id)
        self.assertFalse(card1.is_selected)
        self.assertIsNone(self.win.selected_item)
        self.assertIn("選択なし", self.win.status_bar.info_label.text())

    def test_03_bookshelf_slide_panel_structure_and_texts(self):
        """書架枠下部スライドインパネルの構造とあらすじ・概要表示の検証"""
        bookshelf = self.win.bookshelf
        panel = bookshelf.slide_panel
        self.assertIsInstance(panel, BookshelfSlidePanel)
        self.assertTrue(panel.testAttribute(Qt.WA_TransparentForMouseEvents))

        cards_map = {c.title_text: c for c in bookshelf.cards}

        # 1. 狂気山脈（あらすじあり）
        c_kyoki = cards_map["狂気山脈 〜邪神の山嶺〜"]
        panel.set_item(c_kyoki.item)
        self.assertEqual(panel.badge_lbl.text(), "📜 あらすじ")
        self.assertIn("狂気山脈へと挑んだ探検隊", panel.body_lbl.text())
        self.assertEqual(panel.title_lbl.text(), "狂気山脈 〜邪神の山嶺〜")

        # 2. 新約・コトダマの檻（概要あり）
        c_koto = cards_map["新約・コトダマの檻"]
        panel.set_item(c_koto.item)
        self.assertEqual(panel.badge_lbl.text(), "📜 概要")
        self.assertIn("言葉が変異する怪異", panel.body_lbl.text())

        # 3. 空白の魔導書（あらすじ・概要未登録）
        c_empty = cards_map["空白の魔導書"]
        panel.set_item(c_empty.item)
        self.assertEqual(panel.badge_lbl.text(), "📜 あらすじ・概要")
        self.assertIn("あらすじ・概要は未登録です", panel.body_lbl.text())

    def test_04_slide_in_and_out_animation(self):
        """カードホバー時に書架下辺からスライドインし、離脱ディレイ後にスライドアウトすること"""
        bookshelf = self.win.bookshelf
        panel = bookshelf.slide_panel
        panel.update_geometry(bookshelf.width(), bookshelf.height())

        card1 = bookshelf.cards[0]

        # 初期状態: パネルは枠外下部に位置
        self.assertEqual(panel.y(), panel.hide_y)

        # ホバー（enterEvent）
        QApplication.sendEvent(card1, QEvent(QEvent.Enter))
        self.app.processEvents()

        # アニメーション完了
        panel.anim.setCurrentTime(panel.anim.duration())
        self.app.processEvents()

        self.assertEqual(panel.y(), panel.show_y)
        self.assertFalse(panel.isHidden())

        # 離脱（leaveEvent）
        QApplication.sendEvent(card1, QEvent(QEvent.Leave))
        self.app.processEvents()

        # タイマー完了を実行
        bookshelf._on_slide_timeout()
        panel.anim.setCurrentTime(panel.anim.duration())
        self.app.processEvents()

        self.assertEqual(panel.y(), panel.hide_y)

    def test_05_list_mode_slide_panel(self):
        """一覧（リスト）モードでも書架下部スライドパネルが動作すること"""
        self.win._on_view_mode_changed("list")
        self.app.processEvents()

        bookshelf = self.win.bookshelf
        panel = bookshelf.slide_panel
        panel.update_geometry(bookshelf.width(), bookshelf.height())

        list_card = bookshelf.cards[0]
        QApplication.sendEvent(list_card, QEvent(QEvent.Enter))
        panel.anim.setCurrentTime(panel.anim.duration())
        self.app.processEvents()

        self.assertEqual(panel.y(), panel.show_y)
        self.assertFalse(panel.isHidden())

    def test_06_capture_shelf_slide_screens(self):
        """書架下辺からのスライドイン画面キャプチャを撮影"""
        self.win._on_view_mode_changed("medium")
        self.app.processEvents()

        bookshelf = self.win.bookshelf
        panel = bookshelf.slide_panel
        panel.update_geometry(bookshelf.width(), bookshelf.height())

        card_kyoki = [c for c in bookshelf.cards if "狂気山脈" in c.title_text][0]
        QApplication.sendEvent(card_kyoki, QEvent(QEvent.Enter))
        panel.anim.setCurrentTime(panel.anim.duration())
        self.app.processEvents()

        pix_shelf_slide = self.win.grab()
        capture_path = os.path.join(self.artifact_dir, "test_bookshelf_bottom_slide_panel.png")
        pix_shelf_slide.save(capture_path)
        self.assertTrue(os.path.exists(capture_path))


if __name__ == "__main__":
    unittest.main()
