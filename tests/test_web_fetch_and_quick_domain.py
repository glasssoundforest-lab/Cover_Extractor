"""Web情報取得およびワンクリックドメイン登録の結合テスト (tests/test_web_fetch_and_quick_domain.py)
"""

import os
import sys
import unittest
import tempfile
import shutil
import time
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap, QImage, QColor
from PySide6.QtWidgets import QApplication

import app_settings
from core.database import Database
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog
from gui_qt.dialogs.settings_dialog import DomainEditDialog


def create_dummy_png_bytes():
    img = QImage(100, 100, QImage.Format_RGB32)
    img.fill(QColor("blue"))
    from PySide6.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


class TestWebFetchAndQuickDomain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.app.setFont(QFont("Yu Gothic UI", 9))
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_quick_domain.db")
        cls.db = Database(cls.db_path)

        cls.original_settings_file = app_settings.SETTINGS_FILE
        cls.test_ini = os.path.join(cls.tmp_dir, "test_settings.ini")
        app_settings.SETTINGS_FILE = cls.test_ini
        app_settings._settings_instance = None

        # テスト用アイテム（未登録ドメインのURLを持つ）
        cls.item_id = cls.db.save_item(
            file_path="",
            title="未設定の書物",
            system_name="",
            players_text="",
            duration_text="",
            overview="",
            synopsis="",
            thumbnail_bytes=None,
        )
        cls.db.set_source_url(cls.item_id, "https://kakuyomu.jp/works/123456789")

        cls.artifact_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
        os.makedirs(cls.artifact_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        app_settings.SETTINGS_FILE = cls.original_settings_file
        app_settings._settings_instance = None
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_01_unregistered_domain_shows_quick_add_btn(self):
        """未登録ドメインの場合、『＋ ドメイン登録』ボタンが表示されること"""
        dlg = ItemDetailDialog(self.item_id, self.db, None, item_ids=[self.item_id])
        dlg.resize(980, 720)
        dlg.show()
        self.app.processEvents()

        # 未登録なので「＋ ドメイン登録」ボタンが表示されていること
        self.assertFalse(dlg.view_add_domain_btn.isHidden())
        self.assertEqual(dlg.url_label.text(), "🔗  https://kakuyomu.jp/works/123456789")

        # キャプチャ保存
        cap_path = os.path.join(self.artifact_dir, "test_detail_quick_domain_btn.png")
        dlg.grab().save(cap_path)

        # ワンクリック登録を実行（DomainEditDialog で "カクヨム" と入力して保存をモック）
        with patch("gui_qt.dialogs.settings_dialog.DomainEditDialog") as mock_dlg_cls, \
             patch("gui_qt.dialogs.item_detail_dialog.QMessageBox.information"):
            mock_inst = MagicMock()
            mock_inst.exec.return_value = 1
            mock_inst.result_domain = "kakuyomu.jp"
            mock_inst.result_label = "カクヨム"
            mock_dlg_cls.return_value = mock_inst
            dlg._on_add_domain_clicked()

        self.app.processEvents()

        # 登録後は「🔗 カクヨム」となり、「＋ ドメイン登録」ボタンが非表示になること
        self.assertEqual(dlg.url_label.text(), "🔗  カクヨム")
        self.assertTrue(dlg.view_add_domain_btn.isHidden())

        # キャプチャ保存（登録後）
        cap_path = os.path.join(self.artifact_dir, "test_detail_registered_domain.png")
        dlg.grab().save(cap_path)

    def test_02_web_fetch_metadata_and_save(self):
        """Web情報取得ボタンでメタ情報と表紙が入力欄に反映され、保存できること"""
        dlg = ItemDetailDialog(self.item_id, self.db, None, item_ids=[self.item_id])
        dlg.resize(980, 720)
        dlg.show()
        self.app.processEvents()

        # 編集モードに入る
        dlg._toggle_edit_mode()
        self.assertTrue(dlg.is_edit_mode)
        self.assertFalse(dlg.fetch_web_btn.isHidden())

        dummy_img = create_dummy_png_bytes()
        mock_data = {
            "title": "深海に眠る星辰",
            "author": "深淵サークル",
            "system": "クトゥルフ神話TRPG",
            "players": "3〜4人",
            "duration": "4〜5時間",
            "overview": "太平洋沖に突如浮上した未知の石造建造物を調査する探索者たち。",
            "synopsis": "太平洋沖に突如浮上した未知の石造建造物を調査する探索者たち。\n狂気と深海の神秘が交錯する。",
            "image_bytes": dummy_img,
            "image_url": "https://example.com/cover.png",
        }

        # WebScenarioExtractor.extract_from_url をモック化し、比較ダイアログは自動承認
        from gui_qt.dialogs.web_info_diff_dialog import WebInfoComparisonDialog
        with patch("core.web_extractor.WebScenarioExtractor.extract_from_url", return_value=mock_data), \
             patch.object(WebInfoComparisonDialog, "exec", return_value=1), \
             patch("gui_qt.dialogs.item_detail_dialog.QMessageBox.information"):
            dlg.url_edit.setText("https://booth.pm/ja/items/999999")
            dlg._on_fetch_web_info()
            # Web 情報の取得は別スレッドで行われるため、完了（ボタンの再有効化）まで待つ
            deadline = time.time() + 10
            while not dlg.fetch_web_btn.isEnabled() and time.time() < deadline:
                self.app.processEvents()
                time.sleep(0.01)

        self.app.processEvents()

        # 各入力欄に反映されていることを検証
        self.assertEqual(dlg.edit_inputs["title"].text(), "深海に眠る星辰")
        self.assertEqual(dlg.edit_inputs["author"].text(), "深淵サークル")
        self.assertEqual(dlg.edit_inputs["system"].text(), "クトゥルフ神話TRPG")
        self.assertEqual(dlg.edit_inputs["players"].text(), "3〜4人")
        self.assertEqual(dlg.edit_inputs["duration"].text(), "4〜5時間")
        self.assertIn("太平洋沖に突如浮上した", dlg.overview_edit.toPlainText())
        self.assertIn("狂気と深海の神秘", dlg.synopsis_edit.toPlainText())
        self.assertIsNotNone(dlg._temp_thumb_bytes)

        # 編集画面キャプチャ保存
        cap_path = os.path.join(self.artifact_dir, "test_detail_web_fetch_edited.png")
        dlg.grab().save(cap_path)

        # 保存を実行
        with patch("gui_qt.dialogs.item_detail_dialog.QMessageBox.information"):
            dlg._on_save()
        self.app.processEvents()

        # DBに保存されていることを検証
        saved_item = self.db.get_item(self.item_id)
        self.assertEqual(saved_item[2], "深海に眠る星辰")
        self.assertEqual(saved_item[3], "クトゥルフ神話TRPG")
        self.assertEqual(saved_item[4], "3〜4人")
        self.assertEqual(saved_item[5], "4〜5時間")
        self.assertIsNotNone(saved_item[8])  # 表紙画像バイト列が保存されていること


if __name__ == "__main__":
    unittest.main()
