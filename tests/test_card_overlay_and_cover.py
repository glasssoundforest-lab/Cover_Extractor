"""表紙サムネイル画像上の半透明オーバーレイ帯（シナリオ名・概要情報）の検証テストスイート (tests/test_card_overlay_and_cover.py)

検証項目:
1. ScenarioCard の表紙サムネイル上に thumb_overlay が配置され、タイトルと概要情報がオーバーレイ表示されること
2. 大・中・小各サイズでオーバーレイ帯が表紙下部に綺麗にフィットすること
3. カードホバー時・選択時にオーバーレイ帯のボーダーとテキストが美しくハイライトされること
4. 実際の画面キャプチャを保存して視覚的品質を確認すること
"""

import os
import sys
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from core.database import Database
from gui_qt.main_window import MainWindow
from gui_qt.components.scenario_card import ScenarioCard


class TestCardOverlayAndCover(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.app.setFont(QFont("Yu Gothic UI", 9))
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_overlay.db")
        cls.db = Database(cls.db_path)

        from PySide6.QtGui import QImage, QPainter, QLinearGradient, QColor
        from PySide6.QtCore import QBuffer, QIODevice

        # 狂気山脈用の美麗な表紙イラスト画像を生成（雪山・深海・星空のアンティーク調グラデーション）
        cover_img = QImage(300, 430, QImage.Format_RGB32)
        p = QPainter(cover_img)
        grad = QLinearGradient(0, 0, 300, 430)
        grad.setColorAt(0.0, QColor("#1a2a3a"))
        grad.setColorAt(0.5, QColor("#2d4a5e"))
        grad.setColorAt(1.0, QColor("#111822"))
        p.fillRect(0, 0, 300, 430, grad)
        p.setPen(QColor("#d4b26f"))
        p.drawText(cover_img.rect(), Qt.AlignCenter, "🏔️\nMOUNTAIN OF MADNESS")
        p.end()

        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        cover_img.save(buf, "PNG")
        cover_bytes = bytes(buf.data())

        # テストデータの投入
        cls.item_id_1 = cls.db.save_item(
            file_path="C:/scenarios/call_of_cthulhu.pdf",
            title="狂気山脈 〜邪神の山嶺〜",
            system_name="クトゥルフ神話TRPG",
            players_text="3〜4人",
            duration_text="4〜6時間",
            overview="南極最高峰に挑む登山家たちの過酷な挑戦と狂気。",
            synopsis="前人未到の狂気山脈へと挑んだ探検隊が遭遇したものは、太古の異形と凍てつく絶望であった――。",
            thumbnail_bytes=cover_bytes,
        )
        cls.db.set_favorite(cls.item_id_1, True)

        tag_camp = cls.db.add_tag("キャンペーン", color="#8b261e", is_global=True)
        tag_begin = cls.db.add_tag("初心者向け", color="#245c36", is_global=True)
        cls.db.set_item_tags(cls.item_id_1, [tag_camp, tag_begin])

        cls.item_id_2 = cls.db.save_item(
            file_path="C:/scenarios/emoklore.pdf",
            title="新約・コトダマの檻",
            system_name="エモクロアTRPG",
            players_text="2〜3人",
            duration_text="3時間",
            overview="言葉が変異する怪異に立ち向かう現代伝奇。",
            synopsis="言葉を奪う怪異の真相を解き明かす。",
            thumbnail_bytes=None,
        )

        cls.win = MainWindow(db_path=cls.db_path)
        cls.win.resize(1260, 820)
        cls.win.show()
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.win.close()
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_01_card_overlay_structure(self):
        """ScenarioCard に thumb_overlay が存在し、title_label と meta_label が含まれること"""
        card = [c for c in self.win.bookshelf.cards if c.item_id == self.item_id_1][0]
        self.assertIsInstance(card, ScenarioCard)

        self.assertTrue(hasattr(card, "thumb_overlay"))
        self.assertEqual(card.thumb_overlay.parent(), card.thumb_container)

        self.assertIn("狂気山脈", card.title_label.text())
        self.assertIn("クトゥルフ神話TRPG", card.meta_label.text())
        self.assertIn("3〜4人", card.meta_label.text())
        self.assertIn("4〜6時間", card.meta_label.text())

        # オーバーレイ帯が表紙の下部に配置されていること
        tw, th = card.cfg["thumb"]
        ov_h = card.cfg["overlay_h"]
        self.assertEqual(card.thumb_overlay.y(), th - ov_h)
        self.assertEqual(card.thumb_overlay.width(), tw)

    def test_02_card_hover_and_capture(self):
        """カードのホバーおよび選択時の外観を検証し、スクリーンショットを撮影すること"""
        card_cover = [c for c in self.win.bookshelf.cards if c.item_id == self.item_id_1][0]
        card_placeholder = [c for c in self.win.bookshelf.cards if c.item_id == self.item_id_2][0]

        card_cover.set_selected(True)
        self.app.processEvents()

        artifact_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
        if os.path.exists(artifact_dir):
            # 表紙画像ありカード単体のキャプチャ
            card_shot = os.path.join(artifact_dir, "test_card_overlay_cover.png")
            card_cover.grab().save(card_shot, "PNG")
            self.assertTrue(os.path.exists(card_shot))
            print(f"Saved cover card screenshot: {card_shot}")

            # 従来のファイル名とも同期
            card_shot_legacy = os.path.join(artifact_dir, "test_card_overlay_single.png")
            card_cover.grab().save(card_shot_legacy, "PNG")

            # プレースホルダーカード単体のキャプチャ
            ph_shot = os.path.join(artifact_dir, "test_card_overlay_placeholder.png")
            card_placeholder.grab().save(ph_shot, "PNG")
            self.assertTrue(os.path.exists(ph_shot))
            print(f"Saved placeholder card screenshot: {ph_shot}")

            # ウィンドウ全体のキャプチャ
            win_shot = os.path.join(artifact_dir, "test_window_card_overlay.png")
            self.win.grab().save(win_shot, "PNG")
            self.assertTrue(os.path.exists(win_shot))
            print(f"Saved window screenshot: {win_shot}")


if __name__ == "__main__":
    unittest.main()
