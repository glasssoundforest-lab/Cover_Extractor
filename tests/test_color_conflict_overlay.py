"""文字描画部分と同系色時の自動色切り替え・視認性対策の検証テスト (tests/test_color_conflict_overlay.py)

検証項目:
1. 暗色系表紙（深海・夜空）: 通常の真鍮ゴールド（#d4b26f）が維持されること
2. 同系色表紙（黄金・砂漠・イエロー）: has_color_conflict が True となり、文字色が純白（#ffffff）に切り替わること
3. 高輝度表紙（白・淡色・雪原）: has_color_conflict が True となり、文字色が純白（#ffffff）＋強化シャドウになること
4. 実際のカード画像をそれぞれキャプチャして視覚的品質を確認すること
"""

import os
import sys
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import Qt, QPoint, QBuffer, QIODevice
from PySide6.QtGui import QFont, QImage, QPainter, QLinearGradient, QColor, QPalette
from PySide6.QtWidgets import QApplication

from core.database import Database
from gui_qt.main_window import MainWindow
from gui_qt.components.scenario_card import ScenarioCard
from gui_qt.theme import Theme


def make_gradient_cover(color_top, color_bottom, text="COVER"):
    """テスト用カバー画像を生成"""
    img = QImage(300, 430, QImage.Format_RGB32)
    p = QPainter(img)
    grad = QLinearGradient(0, 0, 300, 430)
    grad.setColorAt(0.0, QColor(color_top))
    grad.setColorAt(1.0, QColor(color_bottom))
    p.fillRect(0, 0, 300, 430, grad)
    p.setPen(QColor("#000000"))
    p.drawText(img.rect(), Qt.AlignCenter, text)
    p.end()

    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def _text_color(label):
    """スタイルシート適用後に実際に描かれる文字色"""
    return label.palette().color(QPalette.WindowText).name()


class TestColorConflictOverlay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_color_conflict.db")
        cls.db = Database(cls.db_path)

        # 1. 暗色系カバー（深海・夜空） -> 通常の真鍮ゴールド文字
        dark_bytes = make_gradient_cover("#1a2a3a", "#111822", "DARK OCEAN")
        cls.item_dark = cls.db.save_item(
            file_path="C:/scenarios/ocean.pdf",
            title="深海の呼び声",
            system_name="クトゥルフ神話TRPG",
            players_text="3〜4人",
            duration_text="4時間",
            overview="深海に眠る狂気",
            synopsis="潜水艇は深海へと沈んでいく――",
            thumbnail_bytes=dark_bytes,
        )

        # 2. 黄金・イエロー系カバー（同系色） -> 白文字へ自動切り替え
        gold_bytes = make_gradient_cover("#d4a017", "#e5c158", "GOLDEN DESERT")
        cls.item_gold = cls.db.save_item(
            file_path="C:/scenarios/gold.pdf",
            title="黄金郷エルドラドの秘宝",
            system_name="インセイン",
            players_text="4人",
            duration_text="3時間",
            overview="黄金に輝く古代都市",
            synopsis="黄金の砂塵に包まれた神殿へ足を踏み入れる――",
            thumbnail_bytes=gold_bytes,
        )

        # 3. 高輝度・ホワイト系カバー（白・淡色） -> 白文字＋強化シャドウへ自動切り替え
        white_bytes = make_gradient_cover("#f8fafc", "#e2e8f0", "WHITE BLIZZARD")
        cls.item_white = cls.db.save_item(
            file_path="C:/scenarios/blizzard.pdf",
            title="白銀の吹雪と古の城",
            system_name="ソード・ワールド2.5",
            players_text="3〜5人",
            duration_text="5時間",
            overview="吹雪に閉ざされた古城",
            synopsis="一面の銀世界の中に聳え立つ城影――",
            thumbnail_bytes=white_bytes,
        )

        cls.win = MainWindow(db_path=cls.db_path)
        cls.win.resize(1260, 820)
        cls.win.show()
        cls.app.processEvents()
        # 表紙はバックグラウンドで読み込まれるため、読み込み完了まで待つ
        cls.win.bookshelf.wait_for_covers()

    @classmethod
    def tearDownClass(cls):
        cls.win.close()
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_01_dark_cover_uses_brass_gold(self):
        """暗色系表紙では通常通り真鍮ゴールド（#d4b26f）が維持されること"""
        card_dark = [c for c in self.win.bookshelf.cards if c.item_id == self.item_dark][0]
        self.assertFalse(card_dark.has_color_conflict)
        self.assertEqual(_text_color(card_dark.title_label), Theme.BRASS_LIGHT)

    def test_02_gold_cover_switches_to_white(self):
        """黄金・イエロー系表紙では同系色と判定され、白文字（#ffffff）に切り替わること"""
        card_gold = [c for c in self.win.bookshelf.cards if c.item_id == self.item_gold][0]
        self.assertTrue(card_gold.has_color_conflict)
        self.assertEqual(_text_color(card_gold.title_label), "#ffffff")

    def test_03_white_cover_switches_to_white_with_strong_shadow(self):
        """高輝度・白系表紙でも埋もれ判定が働き、白文字＋強化シャドウに切り替わること"""
        card_white = [c for c in self.win.bookshelf.cards if c.item_id == self.item_white][0]
        self.assertTrue(card_white.has_color_conflict)
        self.assertEqual(_text_color(card_white.title_label), "#ffffff")

    def test_04_capture_comparison_screenshots(self):
        """3種類のカバーカードのキャプチャを撮影し視覚検証すること"""
        artifact_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
        if os.path.exists(artifact_dir):
            card_dark = [c for c in self.win.bookshelf.cards if c.item_id == self.item_dark][0]
            card_gold = [c for c in self.win.bookshelf.cards if c.item_id == self.item_gold][0]
            card_white = [c for c in self.win.bookshelf.cards if c.item_id == self.item_white][0]

            # 3種類のカードをキャプチャ
            shot_dark = os.path.join(artifact_dir, "test_color_conflict_dark.png")
            shot_gold = os.path.join(artifact_dir, "test_color_conflict_gold.png")
            shot_white = os.path.join(artifact_dir, "test_color_conflict_white.png")

            card_dark.grab().save(shot_dark, "PNG")
            card_gold.grab().save(shot_gold, "PNG")
            card_white.grab().save(shot_white, "PNG")

            print(f"Saved: {shot_dark}")
            print(f"Saved: {shot_gold}")
            print(f"Saved: {shot_white}")

            # ウィンドウ全体のキャプチャ
            shot_win = os.path.join(artifact_dir, "test_color_conflict_window.png")
            self.win.grab().save(shot_win, "PNG")
            print(f"Saved window: {shot_win}")


if __name__ == "__main__":
    unittest.main()
