"""ドメイン登録設定および詳細画面連携の総合テスト (tests/test_domain_settings.py)

検証項目:
1. app_settings のドメイン正規化 (clean_domain) と URLドメイン判定 (get_domain_label_for_url)
2. SettingsDialog の「ドメイン設定」タブの表示、ドメイン追加、編集、削除、初期化
3. SettingsDialog で保存したドメイン設定が settings.ini に永続化されること
4. ItemDetailDialog で新規登録ドメイン（例: TALTO）が省略名「🔗 TALTO」としてリンク表示されること
5. 設定画面と詳細画面のスクリーンショット保存
"""

import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

import app_settings
from core.database import Database
from gui_qt.dialogs.settings_dialog import SettingsDialog, DomainEditDialog
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog


class TestDomainSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.app.setFont(QFont("Yu Gothic UI", 9))
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_domain.db")
        cls.db = Database(cls.db_path)

        # テスト用設定ファイルパスを設定
        cls.original_settings_file = app_settings.SETTINGS_FILE
        cls.test_ini = os.path.join(cls.tmp_dir, "test_settings.ini")
        app_settings.SETTINGS_FILE = cls.test_ini
        app_settings._settings_instance = None  # シングルトンリセット

        # テスト用アイテムの作成（TALTOのURLを持つアイテム）
        cls.item_id_talto = cls.db.save_item(
            file_path="",
            title="新約・コトダマの檻",
            system_name="エモクロアTRPG",
            players_text="2〜3人",
            duration_text="3時間",
            overview="言葉が変異する怪異に立ち向かう現代伝奇。",
            synopsis="シナリオあらすじテキスト",
            thumbnail_bytes=None,
        )
        cls.db.set_source_url(cls.item_id_talto, "https://talto.cc/projects/kotodama_ori")

        cls.artifact_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
        os.makedirs(cls.artifact_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        app_settings.SETTINGS_FILE = cls.original_settings_file
        app_settings._settings_instance = None
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_01_domain_utilities_and_matching(self):
        """clean_domain および get_domain_label_for_url の動作確認"""
        # 1. clean_domain
        self.assertEqual(app_settings.clean_domain("booth.pm"), "booth.pm")
        self.assertEqual(app_settings.clean_domain("https://TALTO.CC/scenarios/123"), "talto.cc")
        self.assertEqual(app_settings.clean_domain("http://shop.booth.pm:8080/path"), "shop.booth.pm")
        self.assertEqual(app_settings.clean_domain("  pixiv.net/  "), "pixiv.net")

        # 2. 初期状態でのマッチング（Boothのみ登録）
        self.assertEqual(app_settings.get_domain_label_for_url("https://booth.pm/ja/items/123"), "Booth")
        self.assertEqual(app_settings.get_domain_label_for_url("https://user.booth.pm/"), "Booth")
        self.assertIsNone(app_settings.get_domain_label_for_url("https://talto.cc/projects/abc"))

    def test_02_settings_dialog_domain_tab_and_add(self):
        """SettingsDialog のドメイン設定タブで TALTO を追加して保存"""
        dlg = SettingsDialog(self.db)
        dlg.resize(700, 640)
        dlg.show()
        self.app.processEvents()

        # ドメイン設定タブ（インデックス2）に切り替え
        dlg.tabs.setCurrentIndex(2)
        self.app.processEvents()

        # 初期状態で booth.pm が含まれていること
        self.assertIn("booth.pm", dlg.domains_data)
        self.assertEqual(dlg.domains_data["booth.pm"], "Booth")
        self.assertGreaterEqual(dlg.domain_table.rowCount(), 1)

        # 新規ドメイン（talto.cc -> TALTO）を追加
        dlg.new_domain_input.setText("talto.cc")
        dlg.new_domain_label_input.setText("TALTO")
        dlg._on_add_domain()
        self.app.processEvents()

        self.assertIn("talto.cc", dlg.domains_data)
        self.assertEqual(dlg.domains_data["talto.cc"], "TALTO")

        # さらにPixivも追加（https付きで入力されても自動でpixiv.netに正規化されること）
        dlg.new_domain_input.setText("https://www.pixiv.net/novel/")
        dlg.new_domain_label_input.setText("Pixiv")
        dlg._on_add_domain()
        self.app.processEvents()

        self.assertIn("www.pixiv.net", dlg.domains_data)
        self.assertEqual(dlg.domains_data["www.pixiv.net"], "Pixiv")

        # スクリーンショット撮影
        cap_path = os.path.join(self.artifact_dir, "test_settings_domain_tab.png")
        dlg.grab().save(cap_path)

        # 保存実行 (QMessageBox.information がブロックしないよう patch)
        with patch("gui_qt.dialogs.settings_dialog.QMessageBox.information"):
            dlg._save_settings()
        self.app.processEvents()

        # settings.ini に永続化されていることを確認
        loaded_mappings = app_settings.get_domain_mappings()
        self.assertIn("talto.cc", loaded_mappings)
        self.assertEqual(loaded_mappings["talto.cc"], "TALTO")
        self.assertIn("booth.pm", loaded_mappings)
        self.assertEqual(loaded_mappings["booth.pm"], "Booth")

    def test_03_detail_dialog_shows_custom_domain(self):
        """詳細画面で登録したTALTOが省略表示「🔗 TALTO」として表示されること"""
        dlg = ItemDetailDialog(self.item_id_talto, self.db, None, item_ids=[self.item_id_talto])
        dlg.resize(980, 720)
        dlg.show()
        self.app.processEvents()

        # URLラベルの検証
        self.assertFalse(dlg.url_label.isHidden())
        self.assertEqual(dlg.url_label.text(), "🔗  TALTO")
        self.assertIn("https://talto.cc/projects/kotodama_ori", dlg.url_label.toolTip())

        # キャプチャ保存
        cap_path = os.path.join(self.artifact_dir, "test_detail_custom_domain_talto.png")
        dlg.grab().save(cap_path)

    def test_04_domain_edit_delete_reset(self):
        """ドメイン設定の編集・削除・初期値リセット動作の検証"""
        dlg = SettingsDialog(self.db)
        dlg.resize(700, 640)
        dlg.show()
        dlg.tabs.setCurrentIndex(2)
        self.app.processEvents()

        # 1. DomainEditDialog の単体テスト
        edit_dlg = DomainEditDialog(domain="https://kakuyomu.jp/", label="カクヨム")
        self.assertEqual(edit_dlg.domain_edit.text(), "https://kakuyomu.jp/")
        self.assertEqual(edit_dlg.label_edit.text(), "カクヨム")
        with patch("gui_qt.dialogs.settings_dialog.QMessageBox.warning"):
            edit_dlg._on_save()
        self.assertEqual(edit_dlg.result_domain, "kakuyomu.jp")
        self.assertEqual(edit_dlg.result_label, "カクヨム")

        # 2. テーブルからの削除テスト
        # booth.pm 行を選択
        for row in range(dlg.domain_table.rowCount()):
            if dlg.domain_table.item(row, 0).text() == "booth.pm":
                dlg.domain_table.selectRow(row)
                break
        with patch("gui_qt.dialogs.settings_dialog.QMessageBox.question", return_value=16384):  # QMessageBox.Yes = 0x4000 = 16384
            dlg._delete_selected_domain()
        self.app.processEvents()
        self.assertNotIn("booth.pm", dlg.domains_data)

        # 3. リセットテスト（初期状態に戻す）
        with patch("gui_qt.dialogs.settings_dialog.QMessageBox.question", return_value=16384):
            dlg._reset_domains_to_default()
        self.app.processEvents()
        self.assertIn("booth.pm", dlg.domains_data)
        self.assertEqual(dlg.domains_data["booth.pm"], "Booth")


if __name__ == "__main__":
    unittest.main()
