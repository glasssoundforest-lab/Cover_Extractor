"""詳細情報の概要・あらすじ保存更新およびWeb情報比較採否選択ダイアログのテスト
(tests/test_detail_edit_and_web_diff_dialog.py)

検証項目:
1. 編集モードで概要およびあらすじを編集して保存した際、閲覧ラベル（overview_label, synopsis_label）が即座に最新値に更新されること。
2. Web情報取得時に、新旧比較・採否選択ダイアログ（WebInfoComparisonDialog）が立ち上がり、差分のある項目を視覚的に対比できること。
3. ユーザーが選択した項目のみが編集入力欄に反映され、非選択項目は元の値が保持されること。
4. 反映後に保存を実行すると、選択されたWeb情報がDBに正常にコミットされること。
5. WebInfoComparisonDialog のUIスクリーンショットを取得・保存すること。
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

from PySide6.QtCore import Qt, QByteArray, QBuffer
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication, QDialog

from core.database import Database
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog
from gui_qt.dialogs.web_info_diff_dialog import WebInfoComparisonDialog


class TestDetailEditAndWebDiffDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_diff.db")
        cls.db = Database(cls.db_path)

        # テスト用画像
        img = QImage(120, 80, QImage.Format_RGB32)
        img.fill(QColor("darkred"))
        from PySide6.QtCore import QBuffer
        buf = QBuffer()
        buf.open(QBuffer.WriteOnly)
        img.save(buf, "PNG")
        cls.dummy_thumb_bytes = buf.data().data()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def _create_test_item(self):
        item_id = self.db.save_item(
            file_path="M:/dummy/scenario_diff.pdf",
            title="元々の古いタイトル",
            system_name="クトゥルフ神話TRPG",
            players_text="3人",
            duration_text="4時間",
            overview="古い概要文です。",
            synopsis="古いあらすじ文です。",
            thumbnail_bytes=self.dummy_thumb_bytes,
        )
        self.db.update_item_all(item_id, author="旧作者")
        self.db.set_source_url(item_id, "https://ponzu12345.booth.pm/items/8205068")
        return item_id

    def test_overview_synopsis_labels_update_on_save(self):
        """詳細編集で概要・あらすじを変更して保存した際、閲覧ラベルが即座に最新値に更新されることを検証"""
        item_id = self._create_test_item()
        dlg = ItemDetailDialog(item_id, db=self.db, item_ids=[item_id])

        # 初期閲覧ラベルの確認
        self.assertEqual(dlg.overview_label.text(), "古い概要文です。")
        self.assertEqual(dlg.synopsis_label.text(), "古いあらすじ文です。")

        # 編集モードに入る
        dlg._toggle_edit_mode()
        self.assertTrue(dlg.is_edit_mode)

        # 概要とあらすじを新しい文章に変更
        new_ov = "新しく手動入力した最新の概要文。"
        new_syn = "新しく手動入力した最新のあらすじ文。\n第二段落の文章です。"
        dlg.overview_edit.setPlainText(new_ov)
        dlg.synopsis_edit.setPlainText(new_syn)

        # 保存を実行
        with patch("gui_qt.dialogs.item_detail_dialog.QMessageBox.information"):
            dlg._on_save()

        # 閲覧モードに戻っていること
        self.assertFalse(dlg.is_edit_mode)

        # 検証: 閲覧ラベル（overview_label, synopsis_label）が更新されていること！
        self.assertEqual(dlg.overview_label.text(), new_ov)
        self.assertEqual(dlg.synopsis_label.text(), new_syn)

        # DBにも保存されていること
        saved = self.db.get_item(item_id)
        self.assertEqual(saved[6], new_ov)
        self.assertEqual(saved[7], new_syn)

        dlg.close()

    def test_web_info_diff_dialog_selection(self):
        """Web情報比較ダイアログの選択・反映ロジックの検証"""
        current_data = {
            "title": "現在のタイトル",
            "author": "現在の作者",
            "system": "クトゥルフ神話TRPG",
            "players": "3人",
            "duration": "4時間",
            "overview": "現在の概要",
            "synopsis": "現在のあらすじ",
            "thumbnail_bytes": self.dummy_thumb_bytes,
        }

        # 新しい表紙画像
        new_img = QImage(120, 80, QImage.Format_RGB32)
        new_img.fill(QColor("gold"))
        buf2 = QBuffer()
        buf2.open(QBuffer.WriteOnly)
        new_img.save(buf2, "PNG")
        new_thumb_bytes = buf2.data().data()

        web_data = {
            "title": "【ストプレ】嘘吐き",
            "author": "冷蔵庫の中身",
            "system": "ストーリープレイング",
            "players": "2人",
            "duration": "30分〜1.5時間",
            "overview": "最初に、嘘を吐いた。 最後に、嘘を吐く。",
            "synopsis": "最初に、嘘を吐いた。\n最後に、嘘を吐く。\n\n「ずっと、そばにいるからね」",
            "image_bytes": new_thumb_bytes,
        }

        diff_dlg = WebInfoComparisonDialog(current_data, web_data)

        # 初期状態: 変更がある項目（すべて）にチェックが入っていること
        fields = diff_dlg.get_selected_fields()
        self.assertIn("title", fields)
        self.assertIn("overview", fields)
        self.assertIn("synopsis", fields)
        self.assertIn("system", fields)
        self.assertIn("cover", fields)

        # すべて解除のテスト
        diff_dlg._deselect_all()
        self.assertEqual(len(diff_dlg.get_selected_fields()), 0)

        # すべて選択のテスト
        diff_dlg._select_all()
        self.assertEqual(len(diff_dlg.get_selected_fields()), 8)

        # あらすじと概要だけを選択
        diff_dlg._deselect_all()
        diff_dlg.checkboxes["overview"][0].setChecked(True)
        diff_dlg.checkboxes["synopsis"][0].setChecked(True)
        chosen = diff_dlg.get_selected_fields()
        self.assertEqual(chosen, {"overview", "synopsis"})

        # スクリーンショットの撮影と保存
        diff_dlg.resize(780, 680)
        diff_dlg.show()
        diff_dlg.repaint()
        pix = diff_dlg.grab()
        artifact_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
        if os.path.exists(artifact_dir):
            pix.save(os.path.join(artifact_dir, "test_web_info_diff_dialog.png"))

        diff_dlg.close()

    def test_detail_web_fetch_integration_with_diff_dialog(self):
        """詳細ダイアログのWeb情報取得ボタンから比較ダイアログ経由で選択反映・保存する総合テスト"""
        item_id = self._create_test_item()
        dlg = ItemDetailDialog(item_id, db=self.db, item_ids=[item_id])
        dlg._toggle_edit_mode()

        web_extracted_data = {
            "title": "【ストプレ】嘘吐き",
            "author": "冷蔵庫の中身",
            "system": "ストーリープレイング",
            "players": "2人",
            "duration": "30分〜1.5時間",
            "overview": "新しくWebから取得した概要文",
            "synopsis": "新しくWebから取得したあらすじ文",
            "image_bytes": None,
        }

        # WebScenarioExtractor.extract_from_url をモック
        with patch("core.web_extractor.WebScenarioExtractor.extract_from_url", return_value=web_extracted_data):
            # WebInfoComparisonDialog をモックし、「overview」「synopsis」「system」のみ採用を選択した状態にする
            with patch("gui_qt.dialogs.item_detail_dialog.WebInfoComparisonDialog") as mock_diff_cls:
                mock_dlg_inst = MagicMock()
                mock_dlg_inst.exec.return_value = QDialog.Accepted
                mock_dlg_inst.get_selected_fields.return_value = {"overview", "synopsis", "system"}
                mock_diff_cls.return_value = mock_dlg_inst

                with patch("gui_qt.dialogs.item_detail_dialog.QMessageBox.information"):
                    dlg._on_fetch_web_info()
                    # Web 情報の取得は別スレッドで行われるため、完了（ボタンの再有効化）まで待つ。
                    # QTest.qWait は GIL を手放さず別スレッドが進まないため、sleep を挟んで待つ
                    deadline = time.time() + 10
                    while not dlg.fetch_web_btn.isEnabled() and time.time() < deadline:
                        QApplication.processEvents()
                        time.sleep(0.01)
                    QApplication.processEvents()

        # 入力欄の検証: 選択した概要・あらすじ・システムが反映され、非選択のタイトルは元のままであること
        self.assertEqual(dlg.overview_edit.toPlainText(), "新しくWebから取得した概要文")
        self.assertEqual(dlg.synopsis_edit.toPlainText(), "新しくWebから取得したあらすじ文")
        self.assertEqual(dlg.edit_inputs["system"].text(), "ストーリープレイング")
        self.assertEqual(dlg.edit_inputs["title"].text(), "元々の古いタイトル")  # 非選択なので維持！

        # 保存を実行
        with patch("gui_qt.dialogs.item_detail_dialog.QMessageBox.information"):
            dlg._on_save()

        # 閲覧ラベルに新しい概要・あらすじが即座に反映されていること！
        self.assertEqual(dlg.overview_label.text(), "新しくWebから取得した概要文")
        self.assertEqual(dlg.synopsis_label.text(), "新しくWebから取得したあらすじ文")

        # DBに保存されていること
        saved = self.db.get_item(item_id)
        self.assertEqual(saved[6], "新しくWebから取得した概要文")
        self.assertEqual(saved[7], "新しくWebから取得したあらすじ文")
        self.assertEqual(saved[3], "ストーリープレイング")
        self.assertEqual(saved[2], "元々の古いタイトル")

        dlg.close()


if __name__ == "__main__":
    unittest.main()
