"""詳細画面編集中ローカルタグ設定時のテキスト保持テスト (tests/test_detail_edit_tags_no_reset.py)

検証項目:
1. 編集モード中に各入力項目（タイトル、フリガナ、作者、システム名、人数、時間、URL、概要、あらすじ）を入力中に、
   ローカルタグ編集（_on_edit_tags）を行っても、入力中のテキストがリセットされずに保持されること。
2. タグピルの表示のみが更新されること。
3. その後「保存」を実行した際に、入力したテキストと更新したタグの両方が正常にDBに保存されること。
4. 「取消」を実行した場合は、未保存のテキストが破棄されDBの保存済み値に正しく復元されること。
5. 表紙画像の変更時にも編集中テキストがリセットされないこと。
"""

import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QPixmap, QImage, QColor
from PySide6.QtWidgets import QApplication, QDialog

from core.database import Database
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog


class TestDetailEditTagsNoReset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_no_reset.db")
        cls.db = Database(cls.db_path)

        # テスト用初期アイテム
        cls.item_id = cls.db.save_item(
            file_path="M:/dummy/scenario.pdf",
            title="元タイトル",
            system_name="CoC6th",
            players_text="2人",
            duration_text="3時間",
            overview="元の概要文です。",
            synopsis="元のあらすじです。",
            thumbnail_bytes=None,
        )
        cls.db.set_title_kana(cls.item_id, "モトタイトル")
        cls.db.update_item_all(cls.item_id, author="元作者")
        cls.db.set_source_url(cls.item_id, "https://example.com/original")

        # グローバルタグとローカルタグの登録
        cls.tag_coc = cls.db.add_tag("CoC", is_global=True, color="#8b1c1c")
        cls.tag_unpassed = cls.db.add_tag("未通過", is_global=True, color="#1e3a5f")
        cls.tag_original_local = cls.db.add_tag("現代日本", is_global=False, color="#2d5a27")
        cls.tag_new_local = cls.db.add_tag("クローズド", is_global=False, color="#d4a373")

        # 初期タグ割り当て
        cls.db.set_item_tags(cls.item_id, [cls.tag_coc, cls.tag_unpassed, cls.tag_original_local])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_tags_edit_does_not_reset_inputs(self):
        """詳細編集中のローカルタグ設定で入力内容が消滅しないことを検証"""
        dlg = ItemDetailDialog(self.item_id, db=self.db, item_ids=[self.item_id])

        # 編集モードに入る
        dlg._toggle_edit_mode()
        self.assertTrue(dlg.is_edit_mode)

        # ユーザーが各項目に入力を行う
        dlg.edit_inputs["title"].setText("編集中タイトル★")
        dlg.edit_inputs["kana"].setText("ヘンシュウチュウタイトル")
        dlg.edit_inputs["author"].setText("編集中作者★")
        dlg.edit_inputs["system"].setText("編集中システム★")
        dlg.edit_inputs["players"].setText("4〜5人")
        dlg.edit_inputs["duration"].setText("8時間")
        dlg.url_edit.setText("https://booth.pm/ja/items/9999999")
        dlg.overview_edit.setPlainText("編集中に入力した新しい概要文。")
        dlg.synopsis_edit.setPlainText("編集中に入力した新しいあらすじ文。")

        # MultiTagEditDialog をモックして、新しいローカルタグ「クローズド」を追加選択した状態をシミュレート
        with patch("gui_qt.dialogs.item_detail_dialog.MultiTagEditDialog") as mock_tag_dlg_cls:
            mock_dlg_inst = MagicMock()
            mock_dlg_inst.exec.return_value = QDialog.Accepted
            # 新しいローカルタグ ID リスト
            mock_dlg_inst.get_selected_tag_ids.return_value = [self.tag_original_local, self.tag_new_local]
            mock_tag_dlg_cls.return_value = mock_dlg_inst

            # ローカルタグ編集を実行！
            dlg._on_edit_tags()

        # 検証1: 編集中に入力したテキストが全てリセットされずに保持されていること
        self.assertEqual(dlg.edit_inputs["title"].text(), "編集中タイトル★")
        self.assertEqual(dlg.edit_inputs["kana"].text(), "ヘンシュウチュウタイトル")
        self.assertEqual(dlg.edit_inputs["author"].text(), "編集中作者★")
        self.assertEqual(dlg.edit_inputs["system"].text(), "編集中システム★")
        self.assertEqual(dlg.edit_inputs["players"].text(), "4〜5人")
        self.assertEqual(dlg.edit_inputs["duration"].text(), "8時間")
        self.assertEqual(dlg.url_edit.text(), "https://booth.pm/ja/items/9999999")
        self.assertEqual(dlg.overview_edit.toPlainText(), "編集中に入力した新しい概要文。")
        self.assertEqual(dlg.synopsis_edit.toPlainText(), "編集中に入力した新しいあらすじ文。")

        # 検証2: タグの表示（tags_box）に新しいタグが反映されていること
        self.assertIn("クローズド", dlg.tags_box.text())
        self.assertIn("現代日本", dlg.tags_box.text())
        self.assertIn("CoC", dlg.tags_box.text())

        # 検証3: 表紙画像変更（_on_change_cover）でも入力テキストがリセットされないこと
        img = QImage(100, 100, QImage.Format_RGB32)
        img.fill(QColor("gold"))
        tmp_img_path = os.path.join(self.tmp_dir, "test_cover.png")
        img.save(tmp_img_path)

        with patch("gui_qt.dialogs.item_detail_dialog.QFileDialog.getOpenFileName", return_value=(tmp_img_path, "PNG")):
            dlg._on_change_cover()

        self.assertEqual(dlg.edit_inputs["title"].text(), "編集中タイトル★")
        self.assertEqual(dlg.overview_edit.toPlainText(), "編集中に入力した新しい概要文。")

        # 検証4: 「保存」を実行し、DBに編集内容とタグの両方が保存されること
        with patch("gui_qt.dialogs.item_detail_dialog.QMessageBox.information"):
            dlg._on_save()

        # 閲覧モードに戻っていること
        self.assertFalse(dlg.is_edit_mode)

        # DBから値を取得して確認
        saved_item = self.db.get_item(self.item_id)
        self.assertEqual(saved_item[2], "編集中タイトル★")
        self.assertEqual(saved_item[3], "編集中システム★")
        self.assertEqual(saved_item[4], "4〜5人")
        self.assertEqual(saved_item[5], "8時間")
        self.assertEqual(saved_item[6], "編集中に入力した新しい概要文。")
        self.assertEqual(saved_item[7], "編集中に入力した新しいあらすじ文。")
        self.assertEqual(self.db.get_title_kana(self.item_id), "ヘンシュウチュウタイトル")
        self.assertEqual(self.db.get_author(self.item_id), "編集中作者★")
        self.assertEqual(self.db.get_source_url(self.item_id), "https://booth.pm/ja/items/9999999")

        # タグがDBに反映されていること
        current_tags = [t[1] for t in self.db.get_item_tags(self.item_id)]
        self.assertIn("クローズド", current_tags)
        self.assertIn("現代日本", current_tags)
        self.assertIn("CoC", current_tags)
        self.assertIn("未通過", current_tags)

        # 検証5: 編集モードで再度テキストを変更し、「取消」を押すとDBの保存済み値に復元されること
        dlg._toggle_edit_mode()
        self.assertTrue(dlg.is_edit_mode)
        dlg.edit_inputs["title"].setText("破棄されるべき未保存タイトル")
        dlg._on_cancel()
        self.assertFalse(dlg.is_edit_mode)
        self.assertEqual(dlg.edit_inputs["title"].text(), "編集中タイトル★")
        self.assertEqual(dlg.view_labels["title"].text(), "編集中タイトル★")

        # 画面スクリーンショットの取得
        dlg.resize(1000, 680)
        dlg.show()
        dlg.repaint()
        pix = dlg.grab()
        artifact_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
        if os.path.exists(artifact_dir):
            pix.save(os.path.join(artifact_dir, "test_detail_edit_tags_no_reset.png"))

        dlg.close()


if __name__ == "__main__":
    unittest.main()
